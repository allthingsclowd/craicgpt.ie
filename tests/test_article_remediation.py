"""Per-article remediation: ref-based drop + layout rebuild.

The layout is index-based (`ai.shorts.3`, `fun.1`), so dropping any list item must
rebuild it or the frontend dangles/misrenders. These guard that.
"""

from __future__ import annotations

from content_pipeline import compile as cc
from content_pipeline.agent import review


def _paper(n_sub=2, n_short=9, n_fun=5):
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
    return cc.build_paper("2026-06-15", "2026-06-15T00:00:00Z", ai=ai, fun=fun)


def _layout_resolves(paper):
    """Every layout ref must resolve to a real item (no dangling indices)."""
    return all(cc.resolve_ref(paper, r) is not None for r in paper["layout"])


def test_fresh_paper_layout_resolves():
    assert _layout_resolves(_paper())


def test_drop_refs_reindexes_layout_no_dangling():
    paper = _paper(n_short=9, n_fun=5)
    # drop a middle short and a middle fun
    cleaned, dropped = review.drop_refs(paper, ["ai.shorts.3", "fun.1"])
    assert {d["title"] for d in dropped} == {"Short3", "Fun1"}
    assert len(cleaned["ai"]["shorts"]) == 8
    assert len(cleaned["fun"]) == 4
    # the killer assertion: no layout ref dangles after the drop
    assert _layout_resolves(cleaned), cleaned["layout"]
    # and the dropped titles are gone from the resolved layout
    titles = {(cc.resolve_ref(cleaned, r) or {}).get("title") for r in cleaned["layout"]}
    assert "Short3" not in titles and "Fun1" not in titles


def test_drop_refs_never_drops_headliner():
    paper = _paper()
    cleaned, dropped = review.drop_refs(paper, ["ai.headliner", "fun.0"])
    assert cleaned["ai"]["headliner"]["title"] == "Head"  # untouched
    assert {d["title"] for d in dropped} == {"Fun0"}


def test_remove_items_rebuilds_layout():
    paper = _paper(n_fun=5)
    cleaned, dropped = review.remove_items(paper, ["Fun2"])
    assert len(cleaned["fun"]) == 4
    assert _layout_resolves(cleaned), cleaned["layout"]


def test_recompile_layout_matches_counts():
    paper = _paper(n_sub=2, n_short=8, n_fun=3)
    paper["ai"]["shorts"] = paper["ai"]["shorts"][:5]  # mutate behind layout's back
    cc.recompile_layout(paper)
    assert sum(1 for r in paper["layout"] if r.startswith("ai.shorts.")) == 5
    assert _layout_resolves(paper)
