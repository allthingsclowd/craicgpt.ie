"""Regression: the rubric judge must ground on the OKF research bundle, not its
training data. Reproduces the false-HOLD — a FRESH story the judge hasn't seen —
and proves the bundle now carries the curated research so the judge can confirm the
desk is substantive instead of calling it "made up".

We monkeypatch ``_grade_once`` to capture the transcript the grader is handed; the
transcript carrying the ground truth IS the fix.
"""

from __future__ import annotations

from content_pipeline.agent import rubric_review as rr
from content_pipeline.okf import build_craicgpt_bundle, bundle_to_json


def _fresh_paper() -> dict:
    """A paper whose AI headliner is a fresh-2026 story the judge can't know."""
    return {
        "ai": {
            "headliner": {
                "title": "Fable 5 lands with native agentic tool use",
                "standfirst": "A new 2026 frontier model.",
                "body": "Fable 5, released this week, ships native MCP tool calling.",
                "source_url": "https://example.com/fable5",
            },
            "subarticles": [],
            "shorts": [],
        },
        "fun": [],
        "editors_brief": {"title": "Today's wrap"},
    }


def _okf() -> dict:
    bundle = build_craicgpt_bundle(
        [
            {
                "title": "Fable 5 lands with native agentic tool use",
                "summary": "A new 2026 frontier model.",
                "source_url": "https://example.com/fable5",
                "why_it_matters": "It changes how agents call tools.",
                "key_points": ["native MCP", "1M context"],
                "conclusion": "Worth a look.",
            }
        ],
        [],
        date="2026-06-17",
    )
    return bundle_to_json(bundle)


def test_grading_view_prepends_okf_when_present() -> None:
    paper = _fresh_paper()
    paper["edition"] = {"okf": _okf()}
    view = rr.grading_view(paper)
    assert "OKF RESEARCH BUNDLE" in view
    assert "authoritative" in view.lower()
    # the fresh story's research is present so the judge can confirm it's real
    assert "Fable 5" in view
    assert "example.com/fable5" in view
    # the edition content is still there for the safety checks
    assert "AI HEADLINER:" in view


def test_grade_edition_accepts_explicit_okf(monkeypatch) -> None:
    captured = {}

    def fake_once(model, view):
        captured["view"] = view
        return {"result": "satisfied", "criteria": [], "explanation": "ok"}

    monkeypatch.setattr(rr, "_grade_once", fake_once)
    v = rr.grade_edition(_fresh_paper(), okf=_okf(), judge_model="m3/judge",
                         fallback_model="frontier/x")
    assert v["verdict"] == "APPROVE"
    assert "OKF RESEARCH BUNDLE" in captured["view"]
    assert "Fable 5" in captured["view"]


def test_rubric_anchors_on_the_bundle() -> None:
    assert "OKF RESEARCH BUNDLE" in rr.EDITION_RUBRIC
    assert "AUTHORITATIVE" in rr.EDITION_RUBRIC

    # and a paper WITHOUT a bundle still grades (backward compatible)
    assert "OKF RESEARCH BUNDLE" not in rr.grading_view(_fresh_paper())
