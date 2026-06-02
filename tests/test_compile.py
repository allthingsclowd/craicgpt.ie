"""Tests for schema-v3 assembly (paper_content.json).

compile.build_paper is the contract between generation and the frontend: it
takes the AI and fun story sets and produces the published JSON, including the
``layout`` that interleaves the 5 fun pieces among the 10 AI shorts (headliner
and subarticles lead). Pure function — no I/O.
"""

from content_pipeline.compile import build_paper, resolve_ref


def _ai_set():
    return {
        "headliner": {"title": "H", "standfirst": "sf", "body": "b",
                      "source_url": "https://h", "_text_model": "qwen3.6"},
        "subarticles": [
            {"title": "S1", "body": "b", "source_url": "https://s1", "_text_model": "qwen3.6"},
            {"title": "S2", "body": "b", "source_url": "https://s2", "_text_model": "qwen3.6"},
        ],
        "shorts": [
            {"title": f"short{i}", "body": "b", "source_url": f"https://x/{i}",
             "_text_model": "qwen3.6"} for i in range(10)
        ],
    }


def _fun_set():
    return [
        {"title": f"fun{i}", "body": "b", "source_url": f"https://f/{i}",
         "persona": "Spider-Man", "satire_disclaimer": "Parody.",
         "image_url": f"https://img/{i}.png", "image_alt": "alt",
         "kind": "article", "_text_model": "qwen3.6", "_image_model": "flux2-klein"}
        for i in range(5)
    ]


def test_build_paper_has_v3_envelope():
    paper = build_paper("2026-06-02", "2026-06-02T06:00:00Z", ai=_ai_set(), fun=_fun_set())
    assert paper["date"] == "2026-06-02"
    assert paper["generated_at"] == "2026-06-02T06:00:00Z"
    assert paper["pipeline_version"] == "3.0"
    # Draft by default — not yet human-approved.
    assert paper["edition"]["approved_by"] is None


def test_build_paper_preserves_sections_and_attribution():
    paper = build_paper("2026-06-02", "t", ai=_ai_set(), fun=_fun_set())
    assert paper["ai"]["headliner"]["title"] == "H"
    assert len(paper["ai"]["shorts"]) == 10
    assert len(paper["fun"]) == 5
    assert paper["fun"][0]["_image_model"] == "flux2-klein"
    assert paper["ai"]["headliner"]["_text_model"] == "qwen3.6"


def test_layout_references_all_items_and_resolve():
    paper = build_paper("2026-06-02", "t", ai=_ai_set(), fun=_fun_set())
    layout = paper["layout"]
    # 1 headliner + 2 subs + 10 shorts + 5 fun = 18 slots, all unique.
    assert len(layout) == 18
    assert len(set(layout)) == 18
    # Every reference resolves to a real item.
    for ref in layout:
        assert resolve_ref(paper, ref) is not None


def test_layout_leads_with_headliner_then_subarticles():
    paper = build_paper("2026-06-02", "t", ai=_ai_set(), fun=_fun_set())
    assert paper["layout"][0] == "ai.headliner"
    assert paper["layout"][1:3] == ["ai.subarticles.0", "ai.subarticles.1"]


def test_layout_interleaves_fun_among_shorts():
    paper = build_paper("2026-06-02", "t", ai=_ai_set(), fun=_fun_set())
    tail = paper["layout"][3:]  # the shorts+fun weave
    fun_positions = [i for i, ref in enumerate(tail) if ref.startswith("fun.")]
    # Fun pieces must be spread out, not clustered at the very end.
    assert max(fun_positions) - min(fun_positions) >= 8
    assert fun_positions != list(range(len(tail) - 5, len(tail)))


def test_mark_approved_sets_edition_fields():
    paper = build_paper("2026-06-02", "t", ai=_ai_set(), fun=_fun_set())
    from content_pipeline.compile import mark_approved
    approved = mark_approved(paper, approver="graham", at="2026-06-02T07:30:00Z")
    assert approved["edition"]["approved_by"] == "graham"
    assert approved["edition"]["approved_at"] == "2026-06-02T07:30:00Z"
