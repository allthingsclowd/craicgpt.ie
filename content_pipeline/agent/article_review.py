"""
content_pipeline/agent/article_review.py
=========================================
PER-ARTICLE fabrication grading — the half the edition-level rubric can't do.

The edition rubric (:mod:`rubric_review`) returns ONE verdict for the whole paper:
when an article hallucinates, the *entire* edition is held (2026-06-15: a fabricated
headliner held a paper whose shorts + fun were all fine). This module grades each
article INDEPENDENTLY for fabrication so the gate can FLAG the bad ones with a visible
quality-control stamp and still publish — advisory since 2026-06-19 (geek parity):
nothing is dropped and the edition is never hard-held over a flagged article.

Split, per ``deciding-deterministic-vs-llm``:
  * DEAD-LINK / structural hallucination → caught deterministically elsewhere
    (``cli._check_links`` + ``review.validate_paper``); no LLM needed.
  * CONTENT fabrication (real-looking live source, invented claims presented as
    fact) → needs the judge to READ each article. That is this module.

One BATCHED judge call (not N) returns the list of fabricated layout refs, so the
call count stays bounded (the gemma-490-call runaway lesson). Local-first via the
grazlab LiteLLM proxy with a cross-box local fallback; thinking is suppressed so the model
returns clean JSON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from content_pipeline.agent.rubric_review import _clip, _host
from content_pipeline.content_config import content_cfg
from content_pipeline.providers.litellm import get_litellm_llm, run_with_fallback

logger = logging.getLogger(__name__)

# Conservative by design — mirrors the edition rubric's "when in doubt, PASS". We
# only ever DROP an article on a clear, on-its-face fabrication; a false drop loses
# a good story, a false keep ships a hallucination, so we bias toward keeping unless
# the judge is confident.
#
# GROUNDED (2026-06-17): each article is preceded by its GROUND TRUTH — the
# code-verified, link-validated research it was written from (the OKF bundle). The
# judge checks the prose against THAT, not its training data, so a true-but-recent
# story (e.g. a fresh acquisition newer than the model's cutoff) is no longer
# false-flagged. Phrased to match geek's research/article_gate.py.
_FABRICATION_PROMPT = (
    "You are CraicGPT's fact-integrity sub-editor. Below are today's articles, each "
    "tagged with a [ref] and, where available, preceded by its GROUND TRUTH — the "
    "code-verified, link-validated research the article was written from. The ground "
    "truth is AUTHORITATIVE: its events are REAL and its source resolves, even if they "
    "are newer than anything you have seen — never question whether a story 'really "
    "happened' when its ground truth backs it.\n\n"
    "Flag an article ONLY if its prose CONTRADICTS or INVENTS BEYOND its ground truth: "
    "a named event, product, order, quote or figure that the ground truth does not "
    "support, presented as factual news. Do NOT flag an article merely because you "
    "cannot personally verify it, because it is brief, or because it is light satire "
    "that is obviously comedic (a [marked parody] item is never a fabrication). When "
    "in doubt, DO NOT flag it.\n\n"
    "Reply with JSON ONLY, no prose, in exactly this shape:\n"
    '{\"fabricated\": [{\"ref\": \"<the ref>\", \"reason\": \"<one short clause>\"}]}\n'
    "If nothing is clearly fabricated, reply {\"fabricated\": []}.\n\n"
    "ARTICLES:\n"
)


def _okf_ground_truth_index(paper: dict) -> dict[str, str]:
    """Map each article's ``source_url`` → a compact GROUND TRUTH string built from the
    OKF bundle riding on ``paper["edition"]["okf"]`` (concept ``resource`` == the
    article's ``source_url``). Empty when no bundle is present (ungrounded fallback).
    Mirrors geek's ``research/article_gate.py:_ground_truth``."""
    data = (paper.get("edition") or {}).get("okf")
    if not data:
        return {}
    from content_pipeline.okf import bundle_from_json

    try:
        concepts = bundle_from_json(data).concepts
    except Exception:  # noqa: BLE001 — grounding is best-effort, never sink the gate
        return {}
    index: dict[str, str] = {}
    for c in concepts:
        if not c.resource:
            continue
        parts = [p for p in [c.title, f"source: {c.resource}", (c.body or "").strip()] if p]
        index[c.resource] = " | ".join(parts[:2]) + ("\n" + parts[2] if len(parts) > 2 else "")
    return index


def article_refs(paper: dict) -> list[str]:
    """Every gradeable article's canonical layout ref, in reading order."""
    ai = paper.get("ai") or {}
    refs: list[str] = []
    if ai.get("headliner"):
        refs.append("ai.headliner")
    refs += [f"ai.subarticles.{i}" for i in range(len(ai.get("subarticles") or []))]
    refs += [f"ai.shorts.{i}" for i in range(len(ai.get("shorts") or []))]
    refs += [f"fun.{i}" for i in range(len(paper.get("fun") or []))]
    return refs


def _labelled_view(paper: dict, *, budget: int = 12000) -> str:
    """One labelled block per article, each preceded by its OKF GROUND TRUTH (when the
    research bundle is on the paper) so the judge checks the prose against the
    code-verified research rather than its training data:
    ``[ref] TITLE — src=host\\nGROUND TRUTH: …\\nARTICLE: BODY``. Fun items note their
    parody flag (comedic ≠ fabrication)."""
    from content_pipeline.compile import resolve_ref

    ground = _okf_ground_truth_index(paper)
    lines: list[str] = []
    for ref in article_refs(paper):
        it = resolve_ref(paper, ref) or {}
        tag = ""
        if ref.startswith("fun.") and it.get("satire_disclaimer"):
            tag = " [marked parody]"
        gt = ground.get(it.get("source_url", ""))
        truth = f"GROUND TRUTH: {gt}\n" if gt else ""
        lines.append(
            f"[{ref}] {_clip(it.get('title'), 140)} — src={_host(it.get('source_url'))}{tag}\n"
            f"{truth}ARTICLE: {_clip(it.get('body'), 320)}"
        )
    view = "\n\n".join(lines)
    return view if len(view) <= budget else view[: budget - 1] + "…"


def _extract_json_obj(text: str) -> Optional[dict]:
    """Pull the JSON object out of a model reply (tolerates a reasoning preamble /
    ```json fences). Returns None if no parseable object with a 'fabricated' key."""
    if not text:
        return None
    # Prefer a fenced block, else the last balanced {...} containing "fabricated".
    candidates = re.findall(r"\{.*\}", text, re.DOTALL)
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except Exception:  # noqa: BLE001 — try the next candidate
            continue
        if isinstance(obj, dict) and "fabricated" in obj:
            return obj
    return None


def _grade_articles_once(model_name: str, view: str) -> Optional[dict]:
    """ONE batched grading pass on ``model_name`` → parsed JSON dict (or None).

    Monkeypatched in tests. Thinking is suppressed so the reply is clean JSON."""
    llm = get_litellm_llm(
        model_name,
        temperature=0,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    resp = llm.invoke(_FABRICATION_PROMPT + view)
    text = getattr(resp, "content", None) or str(resp)
    return _extract_json_obj(text)


def grade_articles(paper: dict, *, judge_model: Optional[str] = None,
                   fallback_model: Optional[str] = None) -> dict:
    """Grade each article for fabrication. Returns
    ``{"fabricated_refs": [ref], "by_ref": {ref: reason}, "judge_model": route,
    "ok": bool}``.

    ``ok`` is False if NO judge produced a usable verdict — the caller must then
    fail safe (treat as a hard hold; don't publish an ungraded edition). Only refs
    that exist in the paper are returned (a hallucinated ref from the judge is
    ignored)."""
    judge = judge_model or content_cfg.judge_model
    fallback = fallback_model or content_cfg.fallback_text_model
    view = _labelled_view(paper)
    valid_refs = set(article_refs(paper))

    try:
        result = run_with_fallback(
            lambda m: _grade_articles_once(m, view),
            local_model=judge,
            fallback_model=fallback,
            validate=lambda o: isinstance(o, dict) and "fabricated" in o,
        )
    except Exception as exc:  # noqa: BLE001 — both judges failed → fail safe
        logger.error("[article-review] no usable per-article verdict: %s", exc)
        return {"fabricated_refs": [], "by_ref": {}, "judge_model": judge, "ok": False}

    by_ref: dict[str, str] = {}
    for entry in (result.output or {}).get("fabricated") or []:
        ref = (entry or {}).get("ref")
        if ref in valid_refs:
            by_ref[ref] = (entry or {}).get("reason") or "fabricated claim"
    logger.info("[article-review] judge=%s flagged %d/%d articles: %s",
                result.model_used, len(by_ref), len(valid_refs), sorted(by_ref))
    return {
        "fabricated_refs": sorted(by_ref),
        "by_ref": by_ref,
        "judge_model": result.model_used,
        "ok": True,
    }


def qc_flags(paper: dict) -> dict[str, dict]:
    """Map each article ref carrying a ``_qc`` quality-control marker → that marker.
    Used by the harness to alert + trace what the advisory gate stamped."""
    from content_pipeline.compile import resolve_ref

    out: dict[str, dict] = {}
    for ref in article_refs(paper):
        it = resolve_ref(paper, ref) or {}
        qc = it.get("_qc")
        if isinstance(qc, dict):
            out[ref] = qc
    return out


def auto_remediate(paper: dict, *, link_ok=None, grade=None,
                   judge_model: Optional[str] = None,
                   fallback_model: Optional[str] = None) -> dict:
    """The per-article gate — ADVISORY since 2026-06-19 (geek parity).

    It NO LONGER drops articles, promotes a replacement headliner, or hard-holds the
    edition. The old hard-hold path could sink the WHOLE multilingual edition over a
    single fabricated headliner: the pipeline emits exactly ``num_ai_subarticles``
    subarticles, which equals ``review.MIN_SUBARTICLES``, so promoting one to replace a
    fabricated lead dropped the desk below its floor and hard-held — mathematically
    guaranteed (the 2026-06-19 blackout). Graham ruled: publish the edition with a
    visible QUALITY-CONTROL stamp on each flagged article rather than suppressing it —
    transparency over a frozen front page.

    For every flagged article it attaches an additive ``_qc`` marker
    (``{"flag": "fabrication"|"dead_link", "reason": str, "by": "per-article gate"}``)
    that the frontend renders as a warning banner, then ALWAYS returns::

        {"action": "publish", "paper": annotated, "flagged": [refs],
         "by_ref": {ref: reason}, "reasons": [...], "graded": bool}

    ``graded`` is False only when no judge produced a verdict (an infra failure): the
    edition still publishes — UNflagged for fabrication — and the caller alerts, rather
    than the whole paper sinking over an infra blip. Nothing here is dropped, so the
    structural floors can never be breached by the gate. ``link_ok``/``grade`` are
    injectable for offline tests."""
    import copy

    from content_pipeline.compile import resolve_ref

    if link_ok is None:
        from content_pipeline.research.curation import validate_source_link as link_ok
    paper = copy.deepcopy(paper)

    flags: dict[str, dict] = {}

    # 1. Deterministic: dead/unreachable source links (the cheap hallucination net).
    for ref in article_refs(paper):
        url = (resolve_ref(paper, ref) or {}).get("source_url")
        if url and not link_ok(url):
            flags[ref] = {"flag": "dead_link", "reason": "source link unreachable"}

    # 2. LLM: per-article content fabrication (a fabrication outranks a dead-link flag).
    grade_fn = grade or (lambda p: grade_articles(
        p, judge_model=judge_model, fallback_model=fallback_model))
    g = grade_fn(paper)
    graded = bool(g.get("ok", True))
    if graded:
        for ref in g.get("fabricated_refs", []):
            flags[ref] = {"flag": "fabrication",
                          "reason": g.get("by_ref", {}).get(ref, "fabricated claim")}

    # 3. Stamp each flagged article with an additive _qc marker — never drop it, never
    #    re-order. The structure is untouched, so the structural floors cannot be
    #    breached by the gate; the UI renders a quality-control warning on the stamp.
    for ref, info in flags.items():
        it = resolve_ref(paper, ref)
        if it is not None:
            it["_qc"] = {"flag": info["flag"], "reason": info["reason"],
                         "by": "per-article gate"}

    reasons = [f"flagged {ref} ({flags[ref]['flag']}): {flags[ref]['reason']}"
               for ref in sorted(flags)]
    if not graded:
        reasons.append("per-article fabrication grade unavailable — published unflagged")
    return {
        "action": "publish",
        "paper": paper,
        "flagged": sorted(flags),
        "by_ref": {r: info["reason"] for r, info in flags.items()},
        "reasons": reasons,
        "graded": graded,
    }
