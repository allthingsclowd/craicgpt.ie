"""
content_pipeline/agent/rubric_review.py
=======================================
In-pipeline edition review with a **deepagents Rubric**.

This replaces the old two-VM (openclaw + hermes) approval consensus with a single
LLM judge that grades the finished edition against an explicit rubric, run via
``content_cfg.judge_model``.

THE JUDGE IS ``m3/mlx/gemma-4-12b-it-nothink`` — an INDEPENDENT, different-family
(Google Gemma 4) local model, not the writer's own qwen3.6-35b (no more marking its
own homework). Set ``content_cfg.judge_model`` / the ``JUDGE_MODEL`` env var to swap
it; any LiteLLM route that returns a real ``tool_calls`` field works.

How the grade runs — ONE structured tool call, not a deep-agent loop
--------------------------------------------------------------------
deepagents' :class:`RubricMiddleware` grades via a reviewer **deep-agent loop** + a
grader sub-agent. A frontier model or the 35B writer drove that to a clean stop, but
a ~12B open model could not: the reviewer deep-agent ships write_todos / task /
filesystem / execute tools and a ``recursion_limit=9999``, and gemma engaged that
machinery and looped hundreds of times instead of replying once; even past it, the
grader re-called its discriminated-union structured tool (``CriterionPass |
CriterionFail``) forever because a 12B can't satisfy that schema. One real
``grade_edition`` made 490+ LLM calls with no verdict and would hang the autonomous
05:00 run past its task cap.

So we DON'T run the deepagents loop. :func:`_grade_once` makes **one forced
``submit_grade`` tool call** against a FLAT schema (:data:`_GRADE_TOOL`: a ``result``
enum + a one-sentence ``explanation``) that gemma — and any tool-caller — produces
reliably in a single ~1s call. ``satisfied`` → APPROVE; ``needs_revision`` → HOLD
with the explanation as the reason. If the local judge returns no usable tool call
(or is unreachable), :func:`grade_edition` falls back ONCE to the frontier, then
HOLDs — we never auto-publish an edition no judge could read.

Validate a candidate route before switching ``JUDGE_MODEL``: run ``grade_edition`` on
a real edition and confirm it returns ``judge_model == <route>`` (not the frontier
fallback) in a single-digit number of calls and a few seconds, and that it HOLDs a
deliberately-bad edition (empty AI desk / unattributed impersonation).

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


# A FLAT grading tool — the publish-gate verdict in one structured tool call.
# deepagents' RubricMiddleware grades via a deep-agent loop whose grader emits a
# discriminated-union schema (CriterionPass | CriterionFail). A frontier model or
# the 35B writer drives that to a clean stop, but a ~12B open model can't: the
# reviewer deep-agent (write_todos/task/fs/execute + recursion_limit=9999) loops
# instead of replying once, and even past it the grader re-calls its structured
# tool forever because it can't satisfy the union. So we DON'T run the deepagents
# loop — we grade with one forced tool call against this flat schema, which gemma
# (and any tool-caller) produces reliably in a single ~1s call.
_GRADE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_grade",
        "description": "Submit the publish-gate grade for today's edition.",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "enum": ["satisfied", "needs_revision"],
                    "description": "satisfied = every rubric criterion passes; "
                                   "needs_revision = at least one fails.",
                },
                # Two flat fields only — a small (~12B) model reliably fills strings
                # + an enum, but mangles array-of-string fields in tool args (returns
                # a truncated string like '[__Q1__'). The explanation must NAME each
                # failing criterion, so it carries the gap detail without an array.
                "explanation": {
                    "type": "string",
                    "description": "One sentence. If needs_revision, name EACH failing "
                                   "criterion and what makes it unsafe/unfair to "
                                   "publish (e.g. 'empty AI desk; unattributed "
                                   "impersonation of a real person').",
                },
            },
            "required": ["result", "explanation"],
        },
    },
}

_GRADER_SYSTEM = (
    "You are CraicGPT's publish-gate grader. Decide whether today's edition is SAFE "
    "and FAIR to publish by checking it against EVERY criterion in the rubric. This "
    "is a publish gate, not a style review: pass plain or dry prose — only fail an "
    "item for something that makes it unsafe or unfair (harm, defamation, "
    "unattributed impersonation, an empty AI desk). Call submit_grade exactly once."
)


def _grade_once(model_name: str, view: str) -> Optional[dict]:
    """ONE structured grading call → a RubricEvaluation-shaped dict (or None).

    A single forced ``submit_grade`` tool call against :data:`_GRADE_TOOL`, NOT a
    deepagents reviewer/grader loop (which a ~12B can't terminate — see the note on
    :data:`_GRADE_TOOL`). Returns the same ``{result, criteria, explanation}`` shape
    :func:`_verdict_from_evaluation` reads, so the verdict mapping + frontier
    fallback are unchanged. Works for the 35B and the frontier fallback too."""
    llm = get_litellm_llm(model_name, temperature=0)
    user = (f"<rubric>\n{EDITION_RUBRIC}</rubric>\n\n"
            f"<edition>\n{view}\n</edition>\n\n"
            "Grade this edition against the rubric, then call submit_grade.")
    resp = llm.bind_tools([_GRADE_TOOL], tool_choice="required").invoke(
        [{"role": "system", "content": _GRADER_SYSTEM},
         {"role": "user", "content": user}]
    )
    calls = getattr(resp, "tool_calls", None) or []
    grade = next((c for c in calls if c.get("name") == "submit_grade"), None)
    if not grade:
        return None  # no usable tool call → grade_edition falls back to the frontier
    args = grade.get("args") or {}
    # No per-criterion `criteria` list — the explanation carries the gap detail, and
    # `_verdict_from_evaluation` falls back to the explanation for the HOLD reason.
    return {
        "result": args.get("result") or "needs_revision",
        "criteria": [],
        "explanation": (args.get("explanation") or "").strip(),
    }


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
