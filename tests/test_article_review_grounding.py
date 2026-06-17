"""The per-article fabrication gate must (A) ground on the OKF research bundle so a
TRUE-but-recent story isn't false-flagged, and (B) publish the valid remainder —
promoting a valid subarticle whose image is still a LOCAL path at gate time (images
upload to https only at publish), instead of hard-holding.

Regression for 2026-06-17: a true "SpaceX/Cursor" headliner was held because the
gate graded prose against training data, and promotion required an http image that
doesn't exist until publish.
"""

from __future__ import annotations

from content_pipeline import compile as cc
from content_pipeline.agent import article_review as ar
from content_pipeline.agent import review
from content_pipeline.okf import build_craicgpt_bundle, bundle_to_json


# --- Fix A: OKF grounding of the per-article gate ---------------------------


def _okf_for(headliner_url: str) -> dict:
    """An OKF bundle whose AI concept matches the headliner's source_url."""
    bundle = build_craicgpt_bundle(
        [
            {
                "title": "SpaceX acquires Cursor in $60B deal",
                "summary": "A real, recent acquisition.",
                "source_url": headliner_url,
                "why_it_matters": "Reshapes the AI-coding market.",
                "key_points": ["$60B all-stock", "closed this week"],
                "conclusion": "Big consolidation.",
            }
        ],
        [],
        date="2026-06-17",
    )
    return bundle_to_json(bundle)


def _paper_with_okf() -> dict:
    url = "https://reuters.com/spacex-cursor"
    ai = {
        "headliner": {"title": "SpaceX acquires Cursor in $60B deal", "body": "Per Reuters.",
                      "source_url": url, "image_url": "/scratch/h.png"},
        "subarticles": [{"title": f"Sub{i}", "body": "b", "source_url": f"https://x/s{i}",
                         "image_url": "/scratch/s.png"} for i in range(3)],
        "shorts": [{"title": f"Short{i}", "body": "b", "source_url": f"https://x/h{i}"}
                   for i in range(9)],
    }
    fun = [{"title": f"Fun{i}", "body": "b", "source_url": f"https://x/f{i}",
            "image_url": "/scratch/f.png", "source": "Creator"} for i in range(5)]
    paper = cc.build_paper("2026-06-17", "t", ai=ai, fun=fun)
    paper.setdefault("edition", {})["okf"] = _okf_for(url)
    return paper


def test_labelled_view_prepends_ground_truth_from_okf() -> None:
    view = ar._labelled_view(_paper_with_okf())
    assert "GROUND TRUTH:" in view
    # the headliner's research + its source URL are present so the judge can verify it
    assert "reshapes the ai-coding market" in view.lower() or "Reshapes the AI-coding" in view
    assert "reuters.com/spacex-cursor" in view


def test_labelled_view_ungrounded_without_okf() -> None:
    # back-compat: a paper with no edition.okf grades as before (no GROUND TRUTH block)
    p = _paper_with_okf()
    p["edition"].pop("okf")
    assert "GROUND TRUTH:" not in ar._labelled_view(p)


def test_fabrication_prompt_treats_research_as_authoritative() -> None:
    assert "GROUND TRUTH" in ar._FABRICATION_PROMPT
    assert "CONTRADICTS" in ar._FABRICATION_PROMPT or "contradicts" in ar._FABRICATION_PROMPT


# --- Fix B: publish the valid remainder (local images at gate time) ---------


def test_pick_promotion_accepts_local_image_paths() -> None:
    # PRODUCTION shape: subarticle images are LOCAL paths at gate time. A fabricated
    # headliner must promote a valid subarticle (not hard-hold over the http check).
    p = _paper_with_okf()
    p["edition"].pop("okf")  # isolate Fix B from grounding
    grade = lambda pp: {"ok": True, "fabricated_refs": ["ai.headliner"],  # noqa: E731
                        "by_ref": {"ai.headliner": "invented"}, "judge_model": "j"}
    out = ar.auto_remediate(p, link_ok=lambda u: True, grade=grade)
    assert out["action"] == "publish"
    assert out["promoted"] == "ai.subarticles.0"
    assert out["paper"]["ai"]["headliner"]["title"] == "Sub0"


def test_validate_paper_accepts_local_images_at_gate_time() -> None:
    p = _paper_with_okf()
    # http-strict (publish time) rejects the local image; gate-time accepts presence
    assert review.validate_paper(p, require_http_images=True)["valid"] is False
    assert review.validate_paper(p, require_http_images=False)["valid"] is True
