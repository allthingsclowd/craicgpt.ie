"""
content_pipeline/agent/article_review.py
=========================================
PER-ARTICLE fabrication grading — the half the edition-level rubric can't do.

The edition rubric (:mod:`rubric_review`) returns ONE verdict for the whole paper:
when an article hallucinates, the *entire* edition is held (2026-06-15: a fabricated
headliner held a paper whose shorts + fun were all fine). This module grades each
article INDEPENDENTLY for fabrication so the gate can drop the bad ones and publish
the valid rest.

Split, per ``deciding-deterministic-vs-llm``:
  * DEAD-LINK / structural hallucination → caught deterministically elsewhere
    (``cli._check_links`` + ``review.validate_paper``); no LLM needed.
  * CONTENT fabrication (real-looking live source, invented claims presented as
    fact) → needs the judge to READ each article. That is this module.

One BATCHED judge call (not N) returns the list of fabricated layout refs, so the
call count stays bounded (the gemma-490-call runaway lesson). Local-first via the
grazlab LiteLLM proxy with a frontier fallback; thinking is suppressed so the model
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
_FABRICATION_PROMPT = (
    "You are CraicGPT's fact-integrity sub-editor. Below are today's articles, each "
    "tagged with a [ref]. Some MAY contain FABRICATED claims about real, named "
    "entities — invented events, products, orders or quotes presented as factual "
    "news (a hallucination), even when the source link looks real. Identify ONLY the "
    "articles with a clear, on-its-face fabrication. Do NOT flag an article merely "
    "because you cannot verify it, because it is brief, or because it is light satire "
    "that is obviously comedic. When in doubt, DO NOT flag it.\n\n"
    "Reply with JSON ONLY, no prose, in exactly this shape:\n"
    '{\"fabricated\": [{\"ref\": \"<the ref>\", \"reason\": \"<one short clause>\"}]}\n'
    "If nothing is clearly fabricated, reply {\"fabricated\": []}.\n\n"
    "ARTICLES:\n"
)


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


def _labelled_view(paper: dict, *, budget: int = 8000) -> str:
    """One labelled block per article: ``[ref] TITLE — src=host\\nBODY`` so the judge
    can return refs. Fun items note their parody flag (comedic ≠ fabrication)."""
    from content_pipeline.compile import resolve_ref

    lines: list[str] = []
    for ref in article_refs(paper):
        it = resolve_ref(paper, ref) or {}
        tag = ""
        if ref.startswith("fun.") and it.get("satire_disclaimer"):
            tag = " [marked parody]"
        lines.append(
            f"[{ref}] {_clip(it.get('title'), 140)} — src={_host(it.get('source_url'))}{tag}\n"
            f"{_clip(it.get('body'), 320)}"
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


def _pick_promotion(paper: dict, bad: dict) -> Optional[tuple]:
    """Choose a surviving, non-bad article to promote to headliner when the real
    headliner is fabricated. A headliner needs title+body+source_url+IMAGE, so only
    subarticles/fun qualify (shorts carry no image). Prefer a subarticle (lead-grade),
    then a fun item. Returns ``(ref, obj)`` or None."""
    from content_pipeline.compile import resolve_ref
    from content_pipeline.agent.review import _is_http_url, _nonempty

    ai = paper.get("ai") or {}
    candidates = ([f"ai.subarticles.{i}" for i in range(len(ai.get("subarticles") or []))]
                  + [f"fun.{i}" for i in range(len(paper.get("fun") or []))])
    for ref in candidates:
        if ref in bad:
            continue
        it = resolve_ref(paper, ref) or {}
        if (_nonempty(it, "title") and _nonempty(it, "body")
                and _is_http_url(it.get("source_url")) and _is_http_url(it.get("image_url"))):
            return ref, it
    return None


def auto_remediate(paper: dict, *, link_ok=None, grade=None,
                   judge_model: Optional[str] = None,
                   fallback_model: Optional[str] = None) -> dict:
    """The per-article gate. Drop fabricated / dead-link articles and return a CLEAN
    edition to publish — or a HARD hold when it can't be made safe.

    Returns one of:
      * ``{"action":"publish", "paper": cleaned, "dropped":[refs], "promoted": ref|None,
            "reasons":[...]}`` — publish the cleaned edition.
      * ``{"action":"hold", "severity":"hard", "reasons":[...], "dropped":[...],
            "promoted":None}`` — cannot auto-fix; HARD hold (must never passive-publish,
            unlike a soft judgement hold). Routed through the existing hard-hold path.

    Bad = dead/unreachable source link (deterministic) ∪ fabricated content (the LLM
    per-article grade). A fabricated headliner is replaced by promoting the best valid
    story; if none qualifies, or the cleaned edition falls below the structural floors,
    it HARD-holds. ``link_ok``/``grade`` are injectable for offline tests."""
    import copy

    from content_pipeline.agent.review import validate_paper
    from content_pipeline.compile import recompile_layout, resolve_ref

    if link_ok is None:
        from content_pipeline.research.curation import validate_source_link as link_ok
    paper = copy.deepcopy(paper)

    # 1. Deterministic: dead/unreachable source links (the cheap hallucination net).
    bad: dict[str, str] = {}
    for ref in article_refs(paper):
        url = (resolve_ref(paper, ref) or {}).get("source_url")
        if url and not link_ok(url):
            bad[ref] = "dead/unreachable source link"

    # 2. LLM: per-article content fabrication.
    grade_fn = grade or (lambda p: grade_articles(
        p, judge_model=judge_model, fallback_model=fallback_model))
    g = grade_fn(paper)
    if not g.get("ok", True):
        return {"action": "hold", "severity": "hard", "dropped": [], "promoted": None,
                "reasons": ["per-article fabrication grade unavailable — failing safe"]}
    for ref in g.get("fabricated_refs", []):
        bad.setdefault(ref, g.get("by_ref", {}).get(ref, "fabricated claim"))

    if not bad:
        return {"action": "publish", "paper": paper, "dropped": [], "promoted": None,
                "reasons": []}

    # 3. Headliner: promote a valid story over a fabricated lead, or HARD hold.
    promoted: Optional[str] = None
    consumed: set[int] = set()
    ai = paper.get("ai") or {}
    if "ai.headliner" in bad:
        pick = _pick_promotion(paper, bad)
        if pick is None:
            return {"action": "hold", "severity": "hard", "dropped": [], "promoted": None,
                    "reasons": [f"fabricated headliner and no valid story to promote "
                                f"({bad['ai.headliner']})"]}
        promoted, obj = pick
        ai["headliner"] = obj
        consumed.add(id(obj))
        del bad["ai.headliner"]

    # 4. Remove bad + consumed items by identity, then rebuild the layout.
    remove = {id(resolve_ref(paper, r)) for r in bad if resolve_ref(paper, r) is not None}
    remove |= consumed
    ai["subarticles"] = [x for x in (ai.get("subarticles") or []) if id(x) not in remove]
    ai["shorts"] = [x for x in (ai.get("shorts") or []) if id(x) not in remove]
    paper["ai"] = ai
    paper["fun"] = [x for x in (paper.get("fun") or []) if id(x) not in remove]
    recompile_layout(paper)
    dropped = sorted(bad)

    # 5. The cleaned edition must still clear the structural floors, else HARD hold
    #    (never publish a too-thin paper).
    v = validate_paper(paper)
    if not v["valid"]:
        return {"action": "hold", "severity": "hard", "dropped": dropped, "promoted": promoted,
                "reasons": [f"after dropping {dropped or '[]'}"
                            + (f" + promoting {promoted}" if promoted else "")
                            + " the edition is structurally too thin: "
                            + "; ".join(v["reasons"])]}
    reasons = [f"dropped {r}: {bad[r]}" for r in dropped]
    if promoted:
        reasons.append(f"promoted {promoted} to headliner (original lead was fabricated)")
    return {"action": "publish", "paper": paper, "dropped": dropped,
            "promoted": promoted, "reasons": reasons}
