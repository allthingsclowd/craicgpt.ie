"""Tests for the in-pipeline rubric judge (rubric_review.grade_edition).

The grader's LLM call (deepagents RubricMiddleware on the judge model) is the one
network piece — we monkeypatch ``_grade_once`` to return canned RubricEvaluations,
so the mapping, the compact grading view, and the frontier fallback are all tested
offline. Per deciding-deterministic-vs-llm: the LLM judges; everything around it
(view-building, verdict mapping, fallback) is deterministic and unit-tested here.
"""

from content_pipeline.agent import rubric_review as rr


def _paper():
    return {
        "editors_brief": {"title": "The state of play today"},
        "ai": {
            "headliner": {"title": "Big AI thing happened", "body": "It happened. " * 10,
                          "source_url": "https://example.com/story"},
            "subarticles": [{"title": "A sub", "body": "b " * 10, "source_url": "https://x/1"}],
            "shorts": [{"title": f"Short {i}", "body": "b"} for i in range(10)],
        },
        "fun": [
            {"title": "Foil sketch", "body": "funny " * 12, "source": "Foil Arms and Hog",
             "persona": "Jack Blarney", "satire_disclaimer": "Parody."},
            {"title": "Johnnies bit", "body": "ha " * 12, "source": "The 2 Johnnies",
             "persona": "Roy Mean", "satire_disclaimer": "Parody."},
        ],
    }


# --- grading_view -----------------------------------------------------------
def test_grading_view_is_compact_and_judgment_focused():
    view = rr.grading_view(_paper(), budget=3500)
    assert len(view) <= 3500
    # the rubric judges harmless/on-brand/attribution, so the view surfaces titles
    # and — for fun items — the parody/credit flags it scores against.
    assert "AI HEADLINER:" in view
    assert "FUN 0:" in view and "FUN 1:" in view
    assert "ATTRIBUTED (credit: Foil Arms and Hog; marked parody)" in view
    assert "voice=Jack Blarney" in view


def test_grading_view_exposes_unattributed_fun_to_the_judge():
    p = _paper()
    p["fun"][0].pop("source")
    p["fun"][0].pop("satire_disclaimer")
    view = rr.grading_view(p)
    assert "UNATTRIBUTED (no credit, no disclaimer)" in view  # the judge can see it's bare


def test_grading_view_has_no_truncation_ellipsis_on_a_complete_edition():
    # 2026-06-19 false-positive: the visible '…' read as a truncated/"cut off" article.
    # A complete edition's view must carry no truncation ellipsis and show titles whole.
    p = _paper()
    view = rr._edition_view(p)
    assert "…" not in view
    assert "Big AI thing happened" in view          # headliner title shown WHOLE
    assert "Short 9" in view                          # every short title intact


def test_grading_view_never_cuts_mid_item_and_strips_attribution():
    # Even when over budget, drop WHOLE trailing items — never truncate an item so its
    # ATTRIBUTED tag vanishes (which re-creates the false "unattributed" read).
    p = _paper()
    view = rr._edition_view(p, budget=600)
    assert len(view) <= 600
    for line in view.splitlines():
        if line.startswith("FUN "):
            assert "ATTRIBUTED" in line               # any fun item shown keeps its tag


def test_rubric_forbids_the_known_false_positive_axes():
    rub = rr.EDITION_RUBRIC
    assert "TRUNCATION" in rub and "EXCERPTS" in rub
    assert "VERIFIABILITY" in rub and "unverifiable" in rub
    assert "ATTRIBUTION ALREADY SHOWN" in rub


def test_grading_view_respects_the_char_budget():
    p = _paper()
    p["fun"][0]["body"] = "x " * 5000  # a pathologically long body
    assert len(rr.grading_view(p, budget=1200)) <= 1200


# --- verdict mapping --------------------------------------------------------
def test_satisfied_maps_to_approve():
    ev = {"result": "satisfied", "criteria": [{"name": "harmless", "passed": True}], "explanation": "grand"}
    v = rr._verdict_from_evaluation(ev)
    assert v["verdict"] == "APPROVE" and v["reasons"] == []


def test_needs_revision_maps_to_hold_with_criterion_gaps():
    ev = {"result": "needs_revision", "explanation": "issues",
          "criteria": [{"name": "harmless", "passed": True},
                       {"name": "no defamation", "passed": False,
                        "gap": "fun 1 states a false fact about a real, named person"}]}
    v = rr._verdict_from_evaluation(ev)
    assert v["verdict"] == "HOLD"
    assert any("false fact" in r for r in v["reasons"])


def test_missing_evaluation_holds():
    v = rr._verdict_from_evaluation(None)
    assert v["verdict"] == "HOLD" and v["result"] == "grader_error"


# --- grade_edition (judge + frontier fallback) ------------------------------
def test_grade_edition_approves_on_satisfied(monkeypatch):
    monkeypatch.setattr(rr, "_grade_once",
                        lambda model, view: {"result": "satisfied", "criteria": [], "explanation": "ok"})
    v = rr.grade_edition(_paper(), judge_model="m3/judge", fallback_model="frontier/x")
    assert v["verdict"] == "APPROVE"
    assert v["judge_model"] == "m3/judge"   # the local judge decided; no fallback


def test_grade_edition_falls_back_to_frontier_on_grader_error(monkeypatch):
    calls = []

    def fake_once(model, view):
        calls.append(model)
        if model == "m3/judge":
            return {"result": "grader_error", "criteria": [], "explanation": "judge crashed"}
        return {"result": "satisfied", "criteria": [], "explanation": "ok"}

    monkeypatch.setattr(rr, "_grade_once", fake_once)
    v = rr.grade_edition(_paper(), judge_model="m3/judge", fallback_model="frontier/x")
    assert v["verdict"] == "APPROVE"
    assert v["judge_model"] == "frontier/x"     # fell back to the frontier judge
    assert calls == ["m3/judge", "frontier/x"]


def test_grade_edition_holds_when_both_judges_fail(monkeypatch):
    # Never auto-publish an edition no judge could read.
    monkeypatch.setattr(rr, "_grade_once", lambda model, view: None)
    v = rr.grade_edition(_paper(), judge_model="m3/judge", fallback_model="frontier/x")
    assert v["verdict"] == "HOLD"
