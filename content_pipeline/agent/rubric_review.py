"""
content_pipeline/agent/rubric_review.py
=======================================
In-pipeline edition review with a **deepagents Rubric**.

This replaces the old two-VM (openclaw + hermes) approval consensus with a single
LLM judge that grades the finished edition against an explicit rubric, run via
``content_cfg.judge_model``.

THE JUDGE IS AN INDEPENDENT MODEL (June 2026): **Gemma 4 12B** on the M3 Ultra — a
*different* family from the writer (``qwen3.6-35b``), so the edition is graded by a
genuine second opinion at temperature 0, not the author marking its own homework.

We use the **reasoning-disabled** route ``m3/mlx/gemma-4-12b-it-nothink``. Gemma 4
tool-calls cleanly, but the reasoning-ENABLED route (``m3/mlx/gemma-4-12b-it``) emits
large reasoning-token streams (~5 tok/s) that made this one-shot grader loop take
~20 min; the ``-nothink`` sibling returns content directly, so the grade is quick.

    History: the judge briefly ran on the writer's own ``qwen3.6`` — back then the only
    M3 route that tool-called cleanly (the others returned tool calls as unparsed
    ``<tool_call>`` text; the FC route was down) — before Gemma 4 shipped.

Switching the judge
-------------------
NO code change is needed — set the ``JUDGE_MODEL`` env var (on the host, in
``/etc/craicgpt.env``) to another LiteLLM route::

    JUDGE_MODEL=claude-sonnet-4-6             # frontier second opinion
    JUDGE_MODEL=m3/mlx/<other-route>         # any other local route that tool-calls

First confirm the candidate returns a REAL ``tool_calls`` field (not ``<tool_call>``
text) — the deepagents grader silently retries/fails otherwise::

    curl -s "$LITELLM_BASE_URL/chat/completions" -H 'Authorization: Bearer sk-no-key-required' \
      -H 'Content-Type: application/json' -d '{"model":"<route>","tool_choice":"auto",
      "messages":[{"role":"user","content":"call the verdict tool with PASS"}],
      "tools":[{"type":"function","function":{"name":"verdict","parameters":{"type":"object",
      "properties":{"result":{"type":"string"}}}}}]}' \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["choices"][0]["message"].get("tool_calls"))'

Non-null ``tool_calls`` → safe to use. ``None`` / ``<tool_call>`` text → it will fail
the grade and the frontier fallback will carry it.

TUTORIAL: Rubrics for deep agents
---------------------------------
deepagents' :class:`RubricMiddleware` lets you declare *what "good" looks like* as
a checklist and have a separate **grader sub-agent** score an agent's work against
it (https://docs.langchain.com/oss/python/deepagents/rubric). Normally it loops the
*authoring* agent until the grader is satisfied. Here the edition is already written
deterministically by the harness, so we use it as a **one-shot judge**
(``max_iterations=1``): a tiny reviewer agent is handed the compiled edition, the
grader evaluates the transcript against :data:`EDITION_RUBRIC`, and we read the
structured :class:`RubricEvaluation` back via the ``on_evaluation`` callback —
``satisfied`` → APPROVE, anything else → HOLD with the failing criteria as reasons.

The deterministic structural check + browser-UA link-check still run host-side in
the publish gate (see :mod:`content_pipeline.agent.review` / ``cli`` ): the rubric
owns "harmless / on-brand / attributed", code owns "technically valid + links
resolve". Probabilistic judgement never replaces the deterministic guard.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.providers.litellm import get_litellm_llm

logger = logging.getLogger(__name__)


# The rubric: one criterion per line (the format RubricMiddleware expects). This is
# a PUBLISH GATE, not a style review — it must HOLD an edition for things that make it
# unsafe or unfair to publish (harm, defamation, unattributed impersonation, empty AI
# desk), NOT for stylistic imperfections like dry prose. Voice/wit is a generation
# nicety the writer owns; gating on it would block the paper from ever auto-publishing.
EDITION_RUBRIC = (
    "- Harmless: nothing hateful, grim, gory, sexual or genuinely cruel. A fun paper. "
    "Political topics appear only as light, even-handed satire, never partisan "
    "campaigning. (Dry or plain prose is FINE — do not fail an item for tone alone.)\n"
    "- No defamation: parody impressions of public figures are clearly comedic and do "
    "not assert false factual claims about a real, named person as if true.\n"
    "- Every fun item is attributed: it credits a real creator (a `credit=` line) "
    "and/or is marked as parody (`disclaimer=yes`). None is an unattributed, unmarked "
    "impersonation of a real person.\n"
    "- The AI desk is substantive, not empty: the headliner and subarticles each say "
    "what actually happened and cite a real source (rather than being blank or pure "
    "vague hype).\n"
)

# The reviewer agent's own instructions. It only needs to *receive* the edition so
# it lands in the transcript the grader reads; the grader (its own sub-agent) does
# the actual scoring against the rubric.
_REVIEWER_PROMPT = (
    "You are CraicGPT's duty sub-editor. You are handed today's compiled edition. "
    "Read it carefully and reply in ONE short sentence on whether it looks fit to "
    "print. Do not call any tools."
)

_REVIEW_TASK = (
    "Here is today's CraicGPT edition for review. Judge whether it is fit to "
    "publish.\n\n"
)


def _host(url: str) -> str:
    u = url or ""
    for p in ("https://", "http://"):
        if u.startswith(p):
            u = u[len(p):]
    return u.split("/", 1)[0]


def _clip(text: str, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def grading_view(paper: dict, *, budget: int = 3500) -> str:
    """Render a COMPACT, judgement-focused view of the edition for the grader.

    The grader truncates each transcript message to a few thousand chars, so we
    can't hand it the whole paper JSON (images, trace, full bodies). Instead we
    surface exactly what the rubric judges: each item's title, a short body
    snippet, and — for fun items — the parody/attribution flags. Fun pieces get
    the most detail (they carry the parody/legal risk); AI shorts get just titles.
    """
    ai = paper.get("ai") or {}
    fun = paper.get("fun") or []
    lines: list[str] = []

    brief = (paper.get("editors_brief") or {}).get("title")
    if brief:
        lines.append(f"EDITOR'S BRIEF: {_clip(brief, 120)}")

    h = ai.get("headliner") or {}
    if h:
        lines.append(f"AI HEADLINER: {_clip(h.get('title'), 110)} "
                     f"[src={_host(h.get('source_url'))}] {_clip(h.get('body'), 220)}")
    for i, s in enumerate(ai.get("subarticles") or []):
        lines.append(f"AI SUB {i}: {_clip(s.get('title'), 100)} "
                     f"[src={_host(s.get('source_url'))}] {_clip(s.get('body'), 130)}")
    shorts = ai.get("shorts") or []
    if shorts:
        lines.append("AI SHORTS: " + " / ".join(_clip(s.get("title"), 70) for s in shorts))

    for i, f in enumerate(fun):
        credit = f.get("source") or "—"
        disc = "yes" if f.get("satire_disclaimer") else "no"
        voice = f.get("persona") or "—"
        lines.append(f"FUN {i}: {_clip(f.get('title'), 100)} "
                     f"[voice={voice} | credit={credit} | disclaimer={disc}] "
                     f"{_clip(f.get('body'), 170)}")

    view = "\n".join(lines)
    if len(view) > budget:
        view = view[: budget - 1] + "…"
    return view


def _verdict_from_evaluation(ev: Optional[dict]) -> dict:
    """Map a deepagents :class:`RubricEvaluation` to a verdict dict.

    ``satisfied`` → APPROVE; every other terminal result (``needs_revision`` capped
    at one iteration, ``failed``, ``max_iterations_reached``, ``grader_error``) →
    HOLD, carrying the failing criteria's gaps as the human-readable reasons.
    """
    if not ev:
        return {"verdict": "HOLD", "result": "grader_error",
                "reasons": ["rubric grader returned no evaluation"], "explanation": ""}
    result = ev.get("result")
    gaps = [c.get("gap", "") for c in (ev.get("criteria") or []) if not c.get("passed")]
    gaps = [g for g in gaps if g]
    explanation = ev.get("explanation", "") or ""
    if result == "satisfied":
        return {"verdict": "APPROVE", "result": result, "reasons": [], "explanation": explanation}
    reasons = gaps or [explanation or f"rubric not satisfied ({result})"]
    return {"verdict": "HOLD", "result": result, "reasons": reasons, "explanation": explanation}


def _grade_once(model_name: str, view: str) -> Optional[dict]:
    """Run ONE rubric grading pass on ``model_name``; return the RubricEvaluation
    dict (or None on failure). Builds a minimal reviewer deep agent whose only job
    is to receive the edition so the grader can score the transcript."""
    from deepagents import RubricMiddleware, create_deep_agent

    captured: list[dict] = []
    llm = get_litellm_llm(model_name, temperature=0)
    middleware = RubricMiddleware(
        model=llm,
        max_iterations=1,  # one-shot judge: the harness already wrote the edition
        on_evaluation=lambda e: captured.append(dict(e)),
    )
    reviewer = create_deep_agent(
        model=llm, system_prompt=_REVIEWER_PROMPT, middleware=[middleware],
    )
    reviewer.invoke({
        "messages": [{"role": "user", "content": _REVIEW_TASK + view}],
        "rubric": EDITION_RUBRIC,
    })
    return captured[-1] if captured else None


def grade_edition(paper: dict, *, judge_model: Optional[str] = None,
                  fallback_model: Optional[str] = None) -> dict:
    """Grade the compiled edition against :data:`EDITION_RUBRIC` and return a verdict.

    Returns ``{"verdict": "APPROVE"|"HOLD", "reasons": [...], "result": <str>,
    "explanation": <str>, "judge_model": <route that decided>}``.

    Runs on ``content_cfg.judge_model`` (an M3 model that is NOT the writer). If that
    grader errors or is unreachable, it falls back ONCE to the frontier model — and
    if that also fails, HOLDs (we never auto-publish an edition no judge could read).
    """
    judge = judge_model or content_cfg.judge_model
    fallback = fallback_model or content_cfg.fallback_text_model
    view = grading_view(paper)

    used = judge
    try:
        ev = _grade_once(judge, view)
    except Exception as exc:  # noqa: BLE001 — any grader failure → try the fallback
        logger.warning("[rubric] judge %s raised: %s", judge, exc)
        ev = None

    if ev is None or ev.get("result") == "grader_error":
        logger.warning("[rubric] judge %s did not produce a usable verdict; "
                       "retrying on frontier %s", judge, fallback)
        used = fallback
        try:
            ev = _grade_once(fallback, view)
        except Exception as exc:  # noqa: BLE001 — fallback failed too → HOLD
            logger.error("[rubric] frontier judge %s also raised: %s", fallback, exc)
            ev = None

    verdict = _verdict_from_evaluation(ev)
    verdict["judge_model"] = used
    logger.info("[rubric] verdict=%s (result=%s, judge=%s) reasons=%s",
                verdict["verdict"], verdict["result"], used, verdict["reasons"])
    return verdict
