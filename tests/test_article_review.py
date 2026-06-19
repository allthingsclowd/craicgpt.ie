"""Per-article fabrication grader. The LLM call is monkeypatched — pure/offline,
per deciding-deterministic-vs-llm (the judge judges; the mapping/fail-safe is tested
here)."""

from __future__ import annotations

from content_pipeline.agent import article_review as ar


def _paper():
    return {
        "ai": {
            "headliner": {"title": "Anthropic Pulls the Plug", "body": "Fabricated.",
                          "source_url": "https://nytimes.com/x", "image_url": "https://x/i"},
            "subarticles": [{"title": "DiffusionGemma", "body": "b", "source_url": "https://blog.google/x"}],
            "shorts": [{"title": "WASM Wheels", "body": "b", "source_url": "https://simonwillison.net/x"}],
        },
        "fun": [{"title": "Parody bit", "body": "b", "source_url": "https://youtube.com/x",
                 "source": "Creator", "satire_disclaimer": True}],
    }


def test_article_refs_enumerates_in_order():
    refs = ar.article_refs(_paper())
    assert refs == ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0"]


def test_labelled_view_tags_each_ref():
    view = ar._labelled_view(_paper())
    for ref in ("[ai.headliner]", "[ai.subarticles.0]", "[ai.shorts.0]", "[fun.0]"):
        assert ref in view
    assert "[marked parody]" in view  # fun item carries its disclaimer flag


def test_extract_json_tolerates_preamble_and_fences():
    txt = "Here's my analysis...\n```json\n{\"fabricated\": [{\"ref\": \"ai.headliner\", \"reason\": \"invented\"}]}\n```\n"
    obj = ar._extract_json_obj(txt)
    assert obj and obj["fabricated"][0]["ref"] == "ai.headliner"


def test_grade_articles_maps_flagged_refs(monkeypatch):
    monkeypatch.setattr(ar, "_grade_articles_once",
                        lambda m, v: {"fabricated": [{"ref": "ai.headliner", "reason": "invented order"}]})
    out = ar.grade_articles(_paper(), judge_model="j", fallback_model="f")
    assert out["ok"] is True
    assert out["fabricated_refs"] == ["ai.headliner"]
    assert out["by_ref"]["ai.headliner"] == "invented order"


def test_grade_articles_ignores_unknown_refs(monkeypatch):
    monkeypatch.setattr(ar, "_grade_articles_once",
                        lambda m, v: {"fabricated": [{"ref": "ai.shorts.99", "reason": "x"},
                                                     {"ref": "fun.0", "reason": "y"}]})
    out = ar.grade_articles(_paper())
    assert out["fabricated_refs"] == ["fun.0"]  # the bogus ai.shorts.99 is dropped


def test_grade_articles_clean_edition(monkeypatch):
    monkeypatch.setattr(ar, "_grade_articles_once", lambda m, v: {"fabricated": []})
    out = ar.grade_articles(_paper())
    assert out["ok"] is True and out["fabricated_refs"] == []


def test_grade_articles_fail_safe_when_no_verdict(monkeypatch):
    def _boom(m, v):
        raise RuntimeError("judge unreachable")
    monkeypatch.setattr(ar, "_grade_articles_once", _boom)
    out = ar.grade_articles(_paper(), judge_model="j", fallback_model="f")
    assert out["ok"] is False  # caller must hard-hold an ungraded edition
    assert out["fabricated_refs"] == []


# ── auto_remediate (the per-article gate) ──────────────────────────────────
from content_pipeline import compile as cc  # noqa: E402


def _full(n_sub=3, n_short=9, n_fun=5):
    ai = {
        "headliner": {"title": "Head", "body": "b", "source_url": "https://x/h",
                      "image_url": "https://x/i"},
        "subarticles": [{"title": f"Sub{i}", "body": "b", "source_url": f"https://x/s{i}",
                         "image_url": "https://x/i"} for i in range(n_sub)],
        "shorts": [{"title": f"Short{i}", "body": "b", "source_url": f"https://x/h{i}"}
                   for i in range(n_short)],
    }
    fun = [{"title": f"Fun{i}", "body": "b", "source_url": f"https://x/f{i}",
            "image_url": "https://x/i", "source": "Creator"} for i in range(n_fun)]
    return cc.build_paper("2026-06-15", "t", ai=ai, fun=fun)


def _grade(refs):
    return lambda p: {"ok": True, "fabricated_refs": list(refs),
                      "by_ref": {r: "invented" for r in refs}, "judge_model": "j"}


def _resolves(paper):
    return all(cc.resolve_ref(paper, r) is not None for r in paper["layout"])


# The gate is ADVISORY (2026-06-19): it NEVER drops an article and NEVER hard-holds —
# it stamps flagged stories with a `_qc` marker and always publishes. The UI renders
# the stamp as a quality-control warning banner.

def test_clean_edition_publishes_unchanged():
    out = ar.auto_remediate(_full(), link_ok=lambda u: True, grade=_grade([]))
    assert out["action"] == "publish" and out["flagged"] == [] and out["graded"] is True
    assert ar.qc_flags(out["paper"]) == {}


def test_flags_fabricated_fun_but_keeps_it():
    out = ar.auto_remediate(_full(), link_ok=lambda u: True, grade=_grade(["fun.1"]))
    assert out["action"] == "publish"
    assert out["flagged"] == ["fun.1"]
    assert len(out["paper"]["fun"]) == 5                       # NOT dropped
    assert out["paper"]["fun"][1]["_qc"]["flag"] == "fabrication"
    assert _resolves(out["paper"])


def test_flags_dead_link_short_deterministically():
    bad_url = "https://x/h2"
    out = ar.auto_remediate(_full(), link_ok=lambda u: u != bad_url, grade=_grade([]))
    assert out["action"] == "publish"
    assert out["flagged"] == ["ai.shorts.2"]
    assert len(out["paper"]["ai"]["shorts"]) == 9             # NOT dropped
    assert out["paper"]["ai"]["shorts"][2]["_qc"]["flag"] == "dead_link"


def test_fabricated_headliner_kept_with_stamp_not_promoted():
    # The 2026-06-17/06-19 blackout shape: a fabricated headliner is STAMPED in place,
    # not promoted-away, so the subarticle floor is never breached.
    out = ar.auto_remediate(_full(n_sub=3), link_ok=lambda u: True,
                            grade=_grade(["ai.headliner"]))
    assert out["action"] == "publish"
    assert out["paper"]["ai"]["headliner"]["title"] == "Head"          # unchanged
    assert out["paper"]["ai"]["headliner"]["_qc"]["flag"] == "fabrication"
    assert len(out["paper"]["ai"]["subarticles"]) == 3                 # untouched
    assert _resolves(out["paper"])


def test_06_19_fabricated_headliner_two_subs_still_publishes():
    # REGRESSION: fabricated headliner + exactly MIN_SUBARTICLES subs must NOT hold.
    p = _full(n_sub=2, n_fun=2)
    out = ar.auto_remediate(p, link_ok=lambda u: True, grade=_grade(["ai.headliner"]))
    assert out["action"] == "publish"
    assert len(out["paper"]["ai"]["subarticles"]) == 2
    assert out["paper"]["ai"]["headliner"]["_qc"]["reason"] == "invented"


def test_many_flags_below_old_floor_still_publishes():
    # Previously a HARD hold (7 < MIN_SHORTS); now publishes all 9, two stamped.
    out = ar.auto_remediate(_full(n_short=9), link_ok=lambda u: True,
                            grade=_grade(["ai.shorts.0", "ai.shorts.1"]))
    assert out["action"] == "publish"
    assert len(out["paper"]["ai"]["shorts"]) == 9
    assert sorted(ar.qc_flags(out["paper"])) == ["ai.shorts.0", "ai.shorts.1"]


def test_ungraded_edition_publishes_unflagged_and_signals():
    out = ar.auto_remediate(_full(), link_ok=lambda u: True,
                            grade=lambda p: {"ok": False, "fabricated_refs": [], "by_ref": {}})
    assert out["action"] == "publish"          # infra blip never sinks the edition
    assert out["graded"] is False              # caller alerts on this
    assert ar.qc_flags(out["paper"]) == {}     # nothing stamped (couldn't grade)


def test_fabrication_outranks_dead_link_on_same_ref():
    out = ar.auto_remediate(_full(), link_ok=lambda u: u != "https://x/s0",
                            grade=_grade(["ai.subarticles.0"]))
    assert out["paper"]["ai"]["subarticles"][0]["_qc"]["flag"] == "fabrication"
