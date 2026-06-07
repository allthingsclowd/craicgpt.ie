"""The podcast banter gate — the deepagents rubric pass over the LLM-written banter.

We patch ``_grade_once`` (the deep-agent grading call) so these run offline: the test is
the verdict mapping + fallback behaviour, not the LLM itself (same as the edition rubric).
"""
from content_pipeline.agent import rubric_review as rr


def test_approves_when_rubric_satisfied(monkeypatch):
    monkeypatch.setattr(
        rr, "_grade_once",
        lambda model, view, **kw: {"result": "satisfied", "criteria": [], "explanation": "grand"},
    )
    v = rr.grade_podcast_script("GRAHAM: Morning.\nTOM: Howya!")
    assert v["verdict"] == "APPROVE"
    assert v["judge_model"] == rr.content_cfg.judge_model
    assert v["reasons"] == []


def test_holds_with_reasons_when_rubric_fails(monkeypatch):
    bad = {"result": "failed",
           "criteria": [{"passed": False, "gap": "Tom is cruel about a named person"}],
           "explanation": "not fit to air"}
    monkeypatch.setattr(rr, "_grade_once", lambda model, view, **kw: bad)
    v = rr.grade_podcast_script("GRAHAM: ...\nTOM: something mean")
    assert v["verdict"] == "HOLD"
    assert any("cruel" in r for r in v["reasons"])


def test_falls_back_then_holds_when_judge_unavailable(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("judge down")
    monkeypatch.setattr(rr, "_grade_once", _boom)
    v = rr.grade_podcast_script("GRAHAM: hi")
    assert v["verdict"] == "HOLD"
    assert v["judge_model"] == rr.content_cfg.fallback_text_model


def test_uses_the_podcast_rubric_not_the_edition_rubric(monkeypatch):
    seen = {}

    def _capture(model, view, **kw):
        seen["rubric"] = kw.get("rubric")
        return {"result": "satisfied", "criteria": [], "explanation": ""}

    monkeypatch.setattr(rr, "_grade_once", _capture)
    rr.grade_podcast_script("GRAHAM: Morning.")
    assert seen["rubric"] == rr.PODCAST_RUBRIC
