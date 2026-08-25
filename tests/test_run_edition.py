"""Tests for run_edition — the harness around the deep agent.

The deep agent does the creative work and writes the edition to its virtual
filesystem (result["files"]["/draft/edition.json"]). run_edition extracts that,
enforces the counts deterministically (5 fun, 13 AI) as a safety net, and runs
compile.build_paper to guarantee schema v3 — regardless of how the model
formatted things. The agent is injected here so this runs offline.
"""

import json

import pytest

from content_pipeline.agent.editor_in_chief import run_edition


@pytest.fixture(autouse=True)
def _no_network_images(monkeypatch):
    """Stub the harness's default image AND gag calls so these tests stay offline.

    Tests that inject their own image_generate bypass the image half entirely.

    The GAG stub matters as much as the image one: `_generate_images` asks the writer
    for a one-line visual gag per article, so without this an "offline" run_edition
    test fires eighteen live LLM calls at the DGX.
    """
    monkeypatch.setattr(
        "content_pipeline.generate.images.save_image",
        lambda prompt, **kw: ("/tmp/fake-image.png", "test-image-model"),
    )
    monkeypatch.setattr(
        "content_pipeline.generate.image_gag.build_gag",
        lambda item, **kw: "a fake visual gag",
    )


class _FakeAgent:
    """Stands in for the compiled deep agent: returns a fixed files dict."""

    def __init__(self, edition: dict):
        self._files = {"/draft/edition.json": {"content": json.dumps(edition)}}

    def invoke(self, _inputs, config=None):
        return {"messages": [], "files": self._files}


class _ResearchAgent:
    """Stands in for the research-only agent: returns candidate JSON files."""

    def __init__(self, fun_candidates: list, ai_candidates: list):
        self._files = {
            "/research/fun_candidates.json": {"content": json.dumps(fun_candidates)},
            "/research/ai_candidates.json": {"content": json.dumps(ai_candidates)},
        }

    def invoke(self, _inputs, config=None):
        return {"messages": [], "files": self._files}


def _edition(n_fun=6, n_shorts=12):
    return {
        "ai": {
            "headliner": {"title": "H", "standfirst": "s", "body": "b", "source_url": "https://h"},
            "subarticles": [{"title": "S1", "body": "b", "source_url": "https://s1"},
                            {"title": "S2", "body": "b", "source_url": "https://s2"}],
            "shorts": [{"title": f"sh{i}", "body": "b", "source_url": f"https://x/{i}"}
                       for i in range(n_shorts)],
        },
        "fun": [{"title": f"f{i}", "body": "b", "source_url": f"https://f/{i}",
                 "persona": "Spider-Man", "satire_disclaimer": "Parody.",
                 "image_url": f"https://img/{i}.png", "kind": "article"} for i in range(n_fun)],
    }


def test_run_edition_builds_schema_v3_from_agent_draft():
    paper = run_edition("2026-06-02", generated_at="2026-06-02T06:00:00Z",
                        agent=_FakeAgent(_edition()))
    assert paper["pipeline_version"] == "3.0"
    assert paper["date"] == "2026-06-02"
    assert paper["ai"]["headliner"]["title"] == "H"
    assert "layout" in paper and paper["layout"][0] == "ai.headliner"


def test_run_edition_enforces_counts_as_safety_net():
    # Agent over-produced (6 fun, 12 shorts); harness trims to 5 fun + 10 shorts.
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition(6, 12)))
    assert len(paper["fun"]) == 5
    assert len(paper["ai"]["shorts"]) == 10


def test_run_edition_embeds_agent_trace():
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()))
    assert "agent_trace" in paper["context"]


def test_run_edition_finalizes_personas_and_disclaimer():
    from content_pipeline.generate.personas import SATIRE_DISCLAIMER

    ed = _edition()
    ed["fun"][0].pop("persona", None)        # editor left the field blank
    ed["fun"][0]["satire_disclaimer"] = ""   # and the disclaimer blank
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed))
    for f in paper["fun"]:
        assert f["satire_disclaimer"] == SATIRE_DISCLAIMER  # always present (legal)
        assert f.get("persona")                              # assigned where blank
        assert f["byline"].startswith("As told to")


def test_run_edition_credited_fun_keeps_source_and_gains_voice():
    # The behavioural flip (Goal 2b): a CREDITED fun item (carries `source`, the
    # creator's name) is no longer stripped of its persona/disclaimer. It's now a
    # celebrity-VOICE impression riffing on that creator's clip, so it KEEPS the
    # credit AND gains a roster persona + byline + the satire disclaimer — both
    # coexist (and review.validate_paper accepts the combination).
    from content_pipeline.generate.personas import ROSTER, SATIRE_DISCLAIMER

    ed = _edition()
    for i, f in enumerate(ed["fun"]):
        f["source"] = f"Creator {i}"   # a credited Irish-creator digest item
        f.pop("persona", None)         # editor didn't set the voice
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed))
    for f in paper["fun"]:
        assert f["source"].startswith("Creator")            # creator credit KEPT (not stripped)
        assert f["persona"] in ROSTER                        # a real voice assigned
        assert f["byline"].startswith("As told to")          # persona byline
        assert f["satire_disclaimer"] == SATIRE_DISCLAIMER   # parody guard for the voice


def test_run_edition_illustrates_every_article():
    # The harness — not the agent — assigns images. Inject a fake generator so this
    # runs offline; it must image EVERY article and overwrite any URL the editor invented.
    #
    # This test used to assert that shorts carry NO image. That inverted in 2026-08 when
    # the paper went to a cartoon per article (issue #103) — the assertion below is the
    # same guarantee turned the right way up.
    ed = _edition()
    ed["fun"][0]["image_url"] = "https://images.unsplash.com/hallucinated"  # editor's bad guess
    calls = []

    def fake_gen(prompt):
        calls.append(prompt)
        return (f"/tmp/img/{len(calls)}.png", "m3/comfy/flux-2-dev")

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed),
                        image_generate=fake_gen)
    ai = paper["ai"]
    assert ai["headliner"]["image_url"].startswith("/tmp/img/")
    assert ai["headliner"]["_image_model"] == "m3/comfy/flux-2-dev"
    for s in ai["subarticles"]:
        assert s["image_url"].startswith("/tmp/img/")
    # Shorts are illustrated too, at the cheaper THUMBNAIL tier.
    for s in ai["shorts"]:
        assert s["image_url"].startswith("/tmp/img/")
        assert s["_image_tier"] == "thumbnail"
    # Every fun story imaged too, overwriting the Unsplash guess.
    for f in paper["fun"]:
        assert f["image_url"].startswith("/tmp/img/")
        assert f["_image_model"] == "m3/comfy/flux-2-dev"
    # One call per article — no slot silently skipped, none rendered twice.
    assert len(calls) == 3 + len(ai["shorts"]) + len(paper["fun"])


def test_run_edition_tiers_the_render_cost():
    """The page-leading images are worth full steps; the rest are bought down.

    This is what makes 18 images fit a 190-minute task cap at all (issue #101) — at
    FLUX.2 [dev]'s baked 28 steps an all-hero edition is 3h38m of GPU.
    """
    from content_pipeline.agent.editor_in_chief import image_targets

    ed = _edition()
    tiers = dict()
    for item, tier in image_targets(ed["ai"], ed["fun"]):
        tiers[tier] = tiers.get(tier, 0) + 1
    assert tiers["hero"] == 3, "headliner + both subarticles only"
    assert tiers["thumbnail"] == len(ed["ai"]["shorts"])
    assert tiers["standard"] == len(ed["fun"])


def test_run_edition_replaces_off_brand_persona():
    from content_pipeline.generate.personas import ROSTER

    ed = _edition()
    ed["fun"][0]["persona"] = "Aquaman"  # not in our parody-journalist roster
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed))
    assert paper["fun"][0]["persona"] in ROSTER  # replaced with a roster character


def test_run_edition_stamps_model_attribution():
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                        text_model="dgx/vllm/qwen3.6-35b-a3b-fp8",
                        image_generate=lambda p: ("/tmp/x.png", "m3/ollama/flux2-klein"))
    assert paper["ai"]["headliner"]["_text_model"] == "dgx/vllm/qwen3.6-35b-a3b-fp8"
    assert paper["fun"][0]["_text_model"] == "dgx/vllm/qwen3.6-35b-a3b-fp8"
    # image model is whatever actually generated the image.
    assert paper["fun"][0]["_image_model"] == "m3/ollama/flux2-klein"


def test_run_edition_holds_if_no_candidates():
    # No draft AND no research candidates → HOLD (EditionHeld, a RuntimeError
    # subclass), never a thin/empty paper.
    from content_pipeline.agent.editor_in_chief import EditionHeld

    class _Empty:
        def invoke(self, _i, config=None):
            return {"messages": [], "files": {}}

    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=_Empty(),
                    ai_feed_fetch=lambda url: None)  # disable harvest → truly no candidates
    assert "candidates" in str(exc.value).lower()


def test_run_edition_writes_from_research_candidates():
    # The real path: agent returns only research candidates; the harness writes
    # the AI section + fun stories via the injected write generator.
    ai_c = [{"title": f"AI cand {i}", "summary": "s", "source_url": f"https://ai/{i}"}
            for i in range(15)]
    fun_c = [{"title": f"Otters rescued {i}", "summary": "lovely", "source_url": f"https://f/{i}",
              "continent": ["Europe", "Asia", "Africa", "Americas", "Oceania"][i % 5]}
             for i in range(12)]

    def fake_write(prompt):
        if "AI editor" in prompt:  # one per-item AI call (headliner / sub / short)
            return {"title": "Big AI Thing", "standfirst": "sf", "body": "b"}
        return {"title": "Rewritten in voice", "body": "...", "source_url": ""}  # a fun story

    paper = run_edition("2026-06-02", generated_at="t",
                        agent=_ResearchAgent(fun_c, ai_c),
                        write_generate=fake_write,
                        link_fetch=lambda url: 200,  # all candidate links resolve (offline)
                        recent_keys=set(),           # disable the live recency lookup
                        ai_feed_fetch=lambda url: None,  # disable the live feed harvest
                        image_generate=lambda p: ("/tmp/i.png", "flux"))
    assert paper["ai"]["headliner"]["title"] == "Big AI Thing"
    assert len(paper["ai"]["shorts"]) == 10
    assert len(paper["fun"]) == 5
    # Fun stories got a real roster persona + byline + disclaimer + source link.
    from content_pipeline.generate.personas import ROSTER
    for f in paper["fun"]:
        assert f["persona"] in ROSTER
        assert f["byline"].startswith("As told to")
        assert f["satire_disclaimer"]
        assert f["source_url"].startswith("https://f/")


def test_run_edition_grades_with_rubric_when_grade_provided():
    # Goal 3: when a `grade` judge is supplied, run_edition grades the FINISHED
    # edition, attaches the verdict at paper["edition"]["rubric"], and records a
    # `rubric` trace event for the "Under the Hood" drawer. A stub judge keeps it
    # offline (the real judge is an LLM call; tests omit `grade` to skip it).
    seen = {}

    def fake_grade(paper):
        seen["got_fun"] = len(paper.get("fun", []))   # graded the COMPILED paper
        return {"verdict": "APPROVE", "reasons": [], "result": "satisfied",
                "judge_model": "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit"}

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                        grade=fake_grade)
    assert seen["got_fun"] == 5                         # judged after the harness trimmed to 5
    assert paper["edition"]["rubric"]["verdict"] == "APPROVE"
    assert paper["edition"]["rubric"]["judge_model"].endswith("qwen3.6-35b-a3b-unsloth-8bit")
    kinds = [e["kind"] for e in paper["context"]["agent_trace"]]
    assert "rubric" in kinds                            # the drawer will show the judge step


def test_run_edition_records_hold_if_grader_raises():
    # A judge crash must not sink generation — it yields a HOLD verdict the gate surfaces.
    def boom(paper):
        raise RuntimeError("judge unreachable")

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()), grade=boom)
    assert paper["edition"]["rubric"]["verdict"] == "HOLD"
    assert any("judge unreachable" in r for r in paper["edition"]["rubric"]["reasons"])


def test_run_edition_per_article_gate_flags_and_traces():
    # The ADVISORY per-article gate (2026-06-19) applies the returned paper and records a
    # `remediation` trace event listing the flagged refs. Stub keeps it offline.
    def fake_remediate(paper):
        return {"action": "publish", "paper": paper, "flagged": ["ai.headliner"],
                "by_ref": {"ai.headliner": "invented order"}, "graded": True,
                "reasons": ["flagged ai.headliner (fabrication): invented order"]}

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                        remediate=fake_remediate)
    assert [e["kind"] for e in paper["context"]["agent_trace"]].count("remediation") == 1
    ev = next(e for e in paper["context"]["agent_trace"] if e["kind"] == "remediation")
    assert ev["detail"]["flagged"] == ["ai.headliner"]


def test_run_edition_per_article_gate_never_hard_holds():
    # The advisory gate publishes even a flagged edition — it must NEVER raise EditionHeld
    # (the 2026-06-19 blackout fix: a fabricated headliner ships stamped, not held).
    from content_pipeline.agent.editor_in_chief import EditionHeld

    def fake_remediate(paper):
        return {"action": "publish", "paper": paper, "flagged": ["ai.headliner"],
                "by_ref": {"ai.headliner": "fabricated lead"}, "graded": True,
                "reasons": ["flagged ai.headliner (fabrication): fabricated lead"]}

    try:
        paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                            remediate=fake_remediate)
    except EditionHeld:  # pragma: no cover — must not happen
        pytest.fail("advisory gate must not hard-hold a flagged edition")
    assert paper["ai"]["headliner"]  # edition still built


# ── 2026-06-11: never hold the paper over the fun desk ───────────────────────
def _ai_cands(n=15):
    return [{"title": f"AI cand {i}", "summary": "s", "source_url": f"https://ai/{i}"}
            for i in range(n)]


def _ai_write(prompt):
    if "AI editor" in prompt:  # one per-item AI call (headliner / sub / short)
        return {"title": "Big AI Thing", "standfirst": "sf", "body": "b"}
    return {"title": "Rewritten in voice", "body": "...", "source_url": ""}


def test_run_edition_publishes_a_thin_fun_desk_instead_of_holding():
    """Graham (2026-06-11): worst case, publish with what you have — a thin fun
    desk must never hold the whole paper. (The no-repeat rule is untouched.)"""
    fun_c = [{"title": "Only sketch", "summary": "s", "source_url": "https://f/0"},
             {"title": "Only ride-out", "summary": "s", "source_url": "https://f/1"}]
    paper = run_edition("2026-06-02", generated_at="t",
                        agent=_ResearchAgent(fun_c, _ai_cands()),
                        write_generate=_ai_write,
                        link_fetch=lambda url: 200,
                        recent_keys=set(),
                        ai_feed_fetch=lambda url: None,
                        image_generate=lambda p: ("/tmp/i.png", "flux"))
    assert len(paper["fun"]) == 2                      # what we have, published
    infos = [e for e in paper["context"]["agent_trace"] if e["kind"] == "tool"]
    assert any("thin" in str(e).lower() for e in infos)  # the shortfall is traced


def test_run_edition_publishes_with_zero_fun_when_the_pool_is_empty():
    paper = run_edition("2026-06-02", generated_at="t",
                        agent=_ResearchAgent([], _ai_cands()),
                        write_generate=_ai_write,
                        link_fetch=lambda url: 200,
                        recent_keys=set(),
                        ai_feed_fetch=lambda url: None,
                        image_generate=lambda p: ("/tmp/i.png", "flux"))
    assert paper["fun"] == []
    assert paper["ai"]["headliner"]["title"] == "Big AI Thing"  # the paper still ships
    assert all(not r.startswith("fun.") for r in paper["layout"])


def test_run_edition_retries_a_flaky_fun_harvest(monkeypatch):
    """The 2026-06-11 outage: one transient harvest failure at 05:00 killed the
    day's paper. The harvest is now retried before any fallback."""
    from content_pipeline.agent import editor_in_chief as eic

    calls = {"n": 0}

    def flaky_harvest(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient DNS wobble")
        return [{"title": f"Recovered upload {i}", "summary": "s",
                 "source_url": f"https://yt/{i}", "source": f"Creator {i}",
                 "_creator": f"Creator {i}"} for i in range(6)]

    monkeypatch.setattr(eic.feeds, "harvest_fun_candidates", flaky_harvest)
    monkeypatch.setattr(eic, "_HARVEST_RETRY_DELAY_S", 0)
    paper = run_edition("2026-06-02", generated_at="t",
                        agent=_ResearchAgent([], _ai_cands()),
                        write_generate=_ai_write,
                        link_fetch=lambda url: 200,
                        recent_keys=set(),
                        ai_feed_fetch=lambda url: "ignored-by-stub",
                        image_generate=lambda p: ("/tmp/i.png", "flux"))
    assert calls["n"] == 3                              # two failures, then success
    assert len(paper["fun"]) == 5                       # written from the recovered pool
