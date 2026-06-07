"""
content_pipeline/compile.py
===========================
Assemble the published ``paper_content.json`` (schema v3).

This is the contract between the generation step and the frontend. It takes the
two story sets — AI landscape (1 headliner + 2 subarticles + 10 shorts) and fun
news (5 persona-written pieces) — and produces the JSON the site renders,
including the ``layout`` that interleaves the fun pieces among the AI shorts so
the paper reads as one woven edition rather than two stacked lists.

Pure function: no network, no clock. The caller passes ``generated_at`` (and,
on approval, the approval timestamp) so runs are reproducible and resumable.
"""

from __future__ import annotations

from typing import Any, Optional

PIPELINE_VERSION = "3.0"


# ─────────────────────────────────────────────────────────────────────────────
# Layout interleaving
# ─────────────────────────────────────────────────────────────────────────────
def _interleave(num_shorts: int, num_fun: int) -> list[str]:
    """Weave ``fun.*`` references evenly among ``ai.shorts.*`` references.

    Distributes the fun pieces at roughly even intervals across the shorts so
    they're spread through the edition, never clustered at the end.
    """
    refs: list[str] = []
    if num_fun == 0:
        return [f"ai.shorts.{i}" for i in range(num_shorts)]

    # Insert a fun piece after every `step` shorts.
    step = max(1, num_shorts // num_fun)
    fun_idx = 0
    for i in range(num_shorts):
        refs.append(f"ai.shorts.{i}")
        if fun_idx < num_fun and (i + 1) % step == 0:
            refs.append(f"fun.{fun_idx}")
            fun_idx += 1
    # Any leftover fun pieces (if step rounding left some) — distribute, not dump:
    while fun_idx < num_fun:
        # Insert near the front-third to keep them from all landing at the tail.
        insert_at = min(len(refs), 1 + fun_idx * 3)
        refs.insert(insert_at, f"fun.{fun_idx}")
        fun_idx += 1
    return refs


def build_layout(num_subarticles: int, num_shorts: int, num_fun: int) -> list[str]:
    """The ordered list of item references for the edition.

    Leads with the headliner, then the subarticles, then the interleaved
    shorts + fun pieces.
    """
    layout = ["ai.headliner"]
    layout += [f"ai.subarticles.{i}" for i in range(num_subarticles)]
    layout += _interleave(num_shorts, num_fun)
    return layout


# ─────────────────────────────────────────────────────────────────────────────
# Build / resolve / approve
# ─────────────────────────────────────────────────────────────────────────────
def build_paper(
    date_iso: str,
    generated_at: str,
    *,
    ai: dict[str, Any],
    fun: list[dict[str, Any]],
    editors_brief: Optional[dict[str, Any]] = None,
    about: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
    podcast: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the schema-v3 paper.

    Args:
        date_iso: Edition date ``YYYY-MM-DD``.
        generated_at: ISO8601 timestamp (passed in — no clock here).
        ai: ``{"headliner": {...}, "subarticles": [...], "shorts": [...]}``.
        fun: list of persona-written fun stories.
        editors_brief: optional ``{"title", "body"}`` — Graham's whole-edition brief,
            rendered full-width at the top of the front page.
        about: optional ``{"title", "body"}`` — the daily Father-Ted "About the
            Editor" page, fetched by ``about.html``.
        context: optional research trace / fallback log for the "Under the Hood"
            drawer.

    Returns:
        The paper dict, ready to serialise. ``edition.approved_by`` is None
        (it's a draft until :func:`mark_approved`). ``editors_brief`` and ``about``
        default to ``{}`` so the frontend can degrade gracefully when a synthesis
        step was skipped or failed.
    """
    subarticles = ai.get("subarticles", [])
    shorts = ai.get("shorts", [])
    return {
        "date": date_iso,
        "generated_at": generated_at,
        "pipeline_version": PIPELINE_VERSION,
        "edition": {"approved_by": None, "approved_at": None},
        "editors_brief": editors_brief or {},
        "ai": {
            "headliner": ai.get("headliner"),
            "subarticles": subarticles,
            "shorts": shorts,
        },
        "fun": fun,
        "about": about or {},
        # The daily podcast (audio_url + transcript) — filled by the narration step that
        # runs after validation; None until then so the schema key is always present.
        "podcast": podcast,
        "layout": build_layout(len(subarticles), len(shorts), len(fun)),
        "context": context or {},
    }


def resolve_ref(paper: dict[str, Any], ref: str) -> Optional[Any]:
    """Resolve a ``layout`` reference (e.g. ``ai.shorts.3``, ``fun.0``) to its item.

    Returns None if the reference doesn't point at a real item — used in tests
    and by the frontend's renderer to stay schema-driven.
    """
    parts = ref.split(".")
    try:
        if ref == "ai.headliner":
            return paper["ai"]["headliner"]
        if parts[:2] == ["ai", "subarticles"]:
            return paper["ai"]["subarticles"][int(parts[2])]
        if parts[:2] == ["ai", "shorts"]:
            return paper["ai"]["shorts"][int(parts[2])]
        if parts[0] == "fun":
            return paper["fun"][int(parts[1])]
    except (KeyError, IndexError, ValueError):
        return None
    return None


def mark_approved(paper: dict[str, Any], *, approver: str, at: str) -> dict[str, Any]:
    """Stamp the edition as human-approved (called by the publish-live step)."""
    paper = {**paper, "edition": {**paper.get("edition", {})}}
    paper["edition"]["approved_by"] = approver
    paper["edition"]["approved_at"] = at
    return paper
