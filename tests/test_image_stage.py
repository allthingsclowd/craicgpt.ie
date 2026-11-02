"""The image stage after the Qwen-Image 2.1 move (craicgpt #154; fleet #221/#222/#219).

Four behaviours, all offline (the image client, the shim's /health and the ops lane are
injected or stubbed):

* **Routes per tier.** Heroes and fun items render on Qwen-Image 2.1 with 2.1-Turbo as the
  per-image fallback; the AI shorts (THUMBNAIL) render on Turbo first with 2.1 as the
  fallback (Graham, 2026-11-02). Each falls back to the other.
* **Steps per model.** 2.1 takes the tier's steps; Turbo's 8 are fixed by its sigma
  schedule, so the request carries no ``steps`` at all for it.
* **A per-image deadline** well below the 1800 s client ceiling, so one stuck render costs
  minutes, then the fallback model gets that one image.
* **A memory pre-flight** before the stage: read the shim's /health, wait briefly while it
  is unhealthy, then page ``decision_needed`` once and proceed regardless.
"""

from __future__ import annotations

import base64

import pytest

from content_pipeline.content_config import ContentConfig, content_cfg
from content_pipeline.generate import image_preflight as pf
from content_pipeline.generate import images as I
from content_pipeline.generate.image_gag import Gag
from content_pipeline.generate.image_styles import (
    HERO,
    STANDARD,
    THUMBNAIL,
    profile_for,
)

QWEN21 = "m3/comfy/qwen-image-2.1"
TURBO = "m3/comfy/qwen-image-2.1-turbo"
_B64 = base64.b64encode(b"PNG").decode()


class _Resp:
    def __init__(self):
        class _D:
            b64_json = _B64
            url = None
        self.data = [_D()]


class _Client:
    """Records every images.generate call; fails the routes named in ``down``."""

    def __init__(self, down=()):
        self.calls: list[dict] = []
        self.down = set(down)
        outer = self

        class _Images:
            def generate(_s, **kw):
                outer.calls.append(kw)
                if kw["model"] in outer.down:
                    raise TimeoutError(f"{kw['model']} timed out")
                return _Resp()

        self.images = _Images()


# ── Defaults ──────────────────────────────────────────────────────────────────
def test_the_default_routes_are_qwen21_with_turbo_behind_it(monkeypatch):
    for k in ("IMAGE_MODEL", "IMAGE_FALLBACK_MODEL", "IMAGE_THUMBNAIL_MODEL",
              "IMAGE_THUMBNAIL_FALLBACK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    c = ContentConfig()
    assert (c.image_model, c.image_fallback_model) == (QWEN21, TURBO)
    # Graham, 2026-11-02: the shorts' thumbnails render on Turbo first.
    assert (c.image_thumbnail_model, c.image_thumbnail_fallback_model) == (TURBO, QWEN21)


def test_the_thumbnail_routes_are_env_tunable(monkeypatch):
    monkeypatch.setenv("IMAGE_THUMBNAIL_MODEL", "m3/comfy/x")
    monkeypatch.setenv("IMAGE_THUMBNAIL_FALLBACK_MODEL", "m3/comfy/y")
    c = ContentConfig()
    assert (c.image_thumbnail_model, c.image_thumbnail_fallback_model) == ("m3/comfy/x",
                                                                          "m3/comfy/y")


@pytest.mark.parametrize("spec,primary,fallback", [
    (HERO, QWEN21, TURBO), (STANDARD, QWEN21, TURBO), (THUMBNAIL, TURBO, QWEN21)])
def test_each_tier_names_its_primary_and_fallback(monkeypatch, spec, primary, fallback):
    monkeypatch.setattr(content_cfg, "image_model", QWEN21)
    monkeypatch.setattr(content_cfg, "image_fallback_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_thumbnail_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_thumbnail_fallback_model", QWEN21)
    assert (spec.model, spec.fallback_model) == (primary, fallback)


# ── Steps per model ───────────────────────────────────────────────────────────
def test_qwen21_renders_every_tier_at_40_steps():
    """The bake-off (fleet #221) measured caption fidelity at 40 steps only."""
    for spec in (HERO, STANDARD, THUMBNAIL):
        assert spec.steps_for(QWEN21) == 40


def test_turbo_ignores_the_tier_steps():
    """Turbo's 8 steps are its sigma schedule; a `steps` on the wire would fight it."""
    for spec in (HERO, STANDARD, THUMBNAIL):
        assert spec.steps_for(TURBO) == 8
        assert spec.wire_steps(TURBO) is None
        assert spec.wire_steps(QWEN21) == 40


def test_a_flux_rollback_keeps_its_own_step_table():
    """IMAGE_MODEL=m3/comfy/flux-2-dev must still be a sane rollback, not 40 FLUX steps."""
    flux = "m3/comfy/flux-2-dev"
    assert (HERO.steps_for(flux), STANDARD.steps_for(flux), THUMBNAIL.steps_for(flux)) == (28, 20, 20)


def test_an_unknown_route_takes_the_tier_steps():
    assert profile_for("m3/comfy/something-new").fixed_steps is None
    assert HERO.steps_for("m3/comfy/something-new") == HERO.steps


# ── est_seconds, re-derived from the 2026-11-02 measurements ──────────────────
def test_estimates_match_the_bake_off_measurements():
    """2.1: 148-175 s at 1024²/40. Turbo: 34-41 s at 1024²/8. The fit budgets the top end."""
    assert 148 <= HERO.est_seconds_for(QWEN21) <= 180
    assert 34 <= HERO.est_seconds_for(TURBO) <= 45
    # 768² costs less than 1024² on the same route.
    assert THUMBNAIL.est_seconds_for(TURBO) < HERO.est_seconds_for(TURBO)
    assert THUMBNAIL.est_seconds_for(QWEN21) < HERO.est_seconds_for(QWEN21)


def test_the_default_edition_is_well_under_forty_minutes_of_render(monkeypatch):
    monkeypatch.setattr(content_cfg, "image_model", QWEN21)
    monkeypatch.setattr(content_cfg, "image_thumbnail_model", TURBO)
    images = 3 * HERO.est_seconds + 5 * STANDARD.est_seconds + 10 * THUMBNAIL.est_seconds
    assert images < 40 * 60, f"{images / 60:.0f} min"


# ── The per-image deadline ────────────────────────────────────────────────────
@pytest.mark.parametrize("spec", [HERO, STANDARD, THUMBNAIL])
@pytest.mark.parametrize("route", [QWEN21, TURBO])
def test_every_deadline_sits_well_below_the_1800s_ceiling(spec, route):
    d = I.image_deadline(spec, route)
    assert d >= spec.est_seconds_for(route) * 2, "no headroom over a normal render"
    assert d <= 900, f"{d:.0f}s — a stuck render should cost minutes, not half an hour"
    assert d < content_cfg.image_request_timeout


def test_the_deadline_rides_on_each_request_and_retries_stay_off():
    client = _Client()
    I.generate_image("p", spec=HERO, model=QWEN21, fallback_model=TURBO, client=client)
    assert client.calls[0]["timeout"] == pytest.approx(I.image_deadline(HERO, QWEN21))
    assert I._default_client().max_retries == 0


# ── Per-image fallback ────────────────────────────────────────────────────────
def test_a_timed_out_hero_is_rerendered_on_turbo_for_that_image_only():
    client = _Client(down={QWEN21})
    img = I.generate_image("p", spec=HERO, model=QWEN21, fallback_model=TURBO, client=client)
    assert [c["model"] for c in client.calls] == [QWEN21, TURBO]
    assert img.model == TURBO                       # honest: the route that rendered it
    assert img.fallback_from == QWEN21
    # 2.1 got its 40 steps; Turbo got none on the wire (its schedule is fixed).
    assert client.calls[0]["extra_body"]["steps"] == 40
    assert "steps" not in client.calls[1].get("extra_body", {})
    # ...and each attempt got its OWN route's deadline.
    assert client.calls[1]["timeout"] == pytest.approx(I.image_deadline(HERO, TURBO))


def test_a_failed_turbo_thumbnail_falls_back_to_qwen21():
    client = _Client(down={TURBO})
    img = I.generate_image("p", spec=THUMBNAIL, model=TURBO, fallback_model=QWEN21,
                           client=client)
    assert [c["model"] for c in client.calls] == [TURBO, QWEN21]
    assert img.model == QWEN21
    assert client.calls[1]["extra_body"]["steps"] == 40


def test_a_healthy_render_records_no_fallback():
    img = I.generate_image("p", spec=HERO, model=QWEN21, fallback_model=TURBO, client=_Client())
    assert img.model == QWEN21 and img.fallback_from is None


def test_the_spec_supplies_the_routes_when_none_are_passed(monkeypatch):
    monkeypatch.setattr(content_cfg, "image_thumbnail_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_thumbnail_fallback_model", QWEN21)
    client = _Client(down={TURBO})
    I.generate_image("p", spec=THUMBNAIL, client=client)
    assert [c["model"] for c in client.calls] == [TURBO, QWEN21]
    assert client.calls[0]["size"] == THUMBNAIL.size


# ── The harness: shorts on Turbo, leads and fun on 2.1, honest _image_model ───
def test_the_harness_routes_each_tier_and_records_the_model_that_rendered(monkeypatch):
    from content_pipeline.agent import editor_in_chief as eic

    monkeypatch.setattr(content_cfg, "image_model", QWEN21)
    monkeypatch.setattr(content_cfg, "image_fallback_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_thumbnail_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_thumbnail_fallback_model", QWEN21)
    monkeypatch.setattr(content_cfg, "image_dir", "/tmp/craicgpt-test-images")
    monkeypatch.setattr("content_pipeline.generate.image_gag.build_gag",
                        lambda item, **kw: Gag(gag="g", caption="C"))
    client = _Client()
    monkeypatch.setattr(I, "_default_client", lambda: client)

    ai = {"headliner": {"title": "H", "body": "b"},
          "subarticles": [{"title": "S1", "body": "b"}, {"title": "S2", "body": "b"}],
          "shorts": [{"title": f"sh{i}", "body": "b"} for i in range(10)]}
    fun = [{"title": "F", "body": "b"}]
    eic._generate_images(ai, fun, "2026-11-03")

    by_model = {}
    for c in client.calls:
        by_model.setdefault(c["model"], []).append(c["size"])
    assert len(by_model[TURBO]) == 10 and set(by_model[TURBO]) == {THUMBNAIL.size}
    assert len(by_model[QWEN21]) == 4                      # 3 leads + 1 fun
    assert all(s["_image_model"] == TURBO for s in ai["shorts"])
    assert ai["headliner"]["_image_model"] == QWEN21
    assert fun[0]["_image_model"] == QWEN21


def test_the_harness_stamps_a_per_image_fallback(monkeypatch):
    from content_pipeline.agent import editor_in_chief as eic

    monkeypatch.setattr(content_cfg, "image_model", QWEN21)
    monkeypatch.setattr(content_cfg, "image_fallback_model", TURBO)
    monkeypatch.setattr(content_cfg, "image_dir", "/tmp/craicgpt-test-images")
    monkeypatch.setattr("content_pipeline.generate.image_gag.build_gag",
                        lambda item, **kw: Gag(gag="g", caption="C"))
    client = _Client(down={QWEN21})
    monkeypatch.setattr(I, "_default_client", lambda: client)

    ai = {"headliner": {"title": "H", "body": "b"}, "subarticles": [], "shorts": []}
    eic._generate_images(ai, [], "2026-11-03")
    assert ai["headliner"]["_image_model"] == TURBO
    assert ai["headliner"]["_image_fallback_from"] == QWEN21


# ── Memory pre-flight ─────────────────────────────────────────────────────────
_HEALTHY = {"ok": True, "busy": False, "memory_pressure": "normal",
            "memory_available_gb": 140.0}


def test_a_healthy_slot_passes():
    r = pf.assess(_HEALTHY)
    assert r.ok and r.reasons == []


@pytest.mark.parametrize("health,needle", [
    ({**_HEALTHY, "memory_pressure": "critical"}, "pressure"),
    ({**_HEALTHY, "memory_pressure": 4}, "pressure"),
    ({**_HEALTHY, "memory_available_gb": 30.0}, "30"),
    ({**_HEALTHY, "busy": True, "job_age_s": 3600}, "3600"),
    ({**_HEALTHY, "ok": False}, "not ok"),
    (None, "unreachable"),
])
def test_each_unhealthy_signal_is_named(health, needle):
    r = pf.assess(health)
    assert not r.ok
    assert any(needle in reason for reason in r.reasons), r.reasons


def test_a_young_job_is_not_a_problem():
    """Hermes or an academy render mid-flight is normal; the slot queues callers."""
    assert pf.assess({**_HEALTHY, "busy": True, "job_age_s": 60}).ok


def test_the_old_health_shape_is_tolerated():
    """Today's shim has no memory or job-age fields (fleet #230 adds them)."""
    r = pf.assess({"ok": True, "busy": False, "queue_running": 0, "queue_pending": 0})
    assert r.ok
    assert r.snapshot["memory_pressure"] is None


def test_nested_memory_fields_are_read_too():
    r = pf.assess({"ok": True, "busy": False,
                   "memory": {"pressure_level": 2, "available_gb": 120}})
    assert not r.ok and any("pressure" in x for x in r.reasons)


def test_preflight_waits_then_proceeds_quietly_when_the_slot_clears():
    readings = iter([{**_HEALTHY, "memory_pressure": "warn"}, _HEALTHY])
    sent = []
    r = pf.preflight("2026-11-03", fetch=lambda: next(readings), sleep=lambda s: None,
                     notify=lambda *a, **k: sent.append(a))
    assert r.ok and sent == []


def test_preflight_pages_once_and_proceeds_when_the_slot_stays_sick():
    polls = []
    sent = []

    def fetch():
        polls.append(1)
        return {**_HEALTHY, "memory_pressure": "critical"}

    r = pf.preflight("2026-11-03", fetch=fetch, sleep=lambda s: None,
                     notify=lambda date, reasons, snapshot: sent.append((date, reasons)),
                     attempts=4)
    assert not r.ok
    assert len(polls) == 4                      # waited briefly...
    assert len(sent) == 1 and sent[0][0] == "2026-11-03"   # ...then paged once


def test_preflight_never_raises():
    def boom(*a, **k):
        raise RuntimeError("lane down")

    r = pf.preflight("2026-11-03", fetch=lambda: None, sleep=lambda s: None, notify=boom,
                     attempts=1)
    assert not r.ok


def test_the_preflight_event_is_a_safe_decision_that_proceeds(monkeypatch):
    from content_pipeline import notifications as N

    seen = {}

    def fake_emit(event, date_iso, ev, **kw):
        seen.update(event=event, ev=ev, kw=kw)
        return {}

    monkeypatch.setattr(N, "emit_once", fake_emit)
    N.notify_image_preflight("2026-11-03", ["memory pressure critical"],
                             snapshot={"memory_pressure": "critical"})
    ev = seen["ev"]
    assert ev["severity"] == "page" and ev["kind"] == "decision_needed"
    assert ev["component"] == "image_stage"
    assert ev["dedup_key"] == "craicgpt:decision_needed:image_preflight:2026-11-03"
    assert ev["decision"]["tier"] == "SAFE"
    assert ev["decision"]["passive_action"] == "proceed"
    assert "memory pressure critical" in ev["detail"]
    assert seen["kw"].get("page_fallback_text")


def test_run_edition_runs_the_preflight_before_real_images(monkeypatch):
    """Only on the real image path: a test that injects image_generate never reaches the M3."""
    from content_pipeline.agent import editor_in_chief as eic

    calls = []
    monkeypatch.setattr(pf, "preflight", lambda date_iso, **kw: calls.append(date_iso) or
                        pf.SlotReading(ok=True, reasons=[], snapshot={}))
    eic._image_preflight("2026-11-03", eic.TraceRecorder())
    assert calls == ["2026-11-03"]
