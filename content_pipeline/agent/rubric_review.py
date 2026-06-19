"""
content_pipeline/agent/rubric_review.py
=======================================
In-pipeline edition review with a **deepagents Rubric**.

This replaces the old two-VM (openclaw + hermes) approval consensus with a single
LLM judge that grades the finished edition against an explicit rubric, run via
``content_cfg.judge_model``.

THE JUDGE IS INDEPENDENT: ``content_cfg.judge_model`` defaults to
``m3/mlx/qwen3-coder-next-4bit`` — a *different* model family from the writer
(qwen3.6 on the DGX), so it is a genuine second opinion, not the author marking its
own homework. It runs locally, drives the ``RubricMiddleware`` reviewer-agent loop to
a clean stop, and falls back ONCE to the frontier route on a grader error.

OKF GROUNDING (June 2026)
-------------------------
The judge once HELD legitimate editions because it graded the prose against its own
TRAINING DATA — a fresh story it hadn't seen read as "made up" or "unverifiable", and
the failures got worse whenever the judge model was swapped. The edition's curated,
link-validated research is now serialized as an Open Knowledge Format (OKF v0.1)
bundle (``content_pipeline/okf/``) and threaded into the grader's transcript as
ground truth, so it confirms the desk is substantive and real instead of guessing.
The bundle rides on ``paper["edition"]["okf"]``; :func:`grading_view` prepends the
flattened bundle. See ``docs/adr/0003-okf-research-grounding.md``.

(History: a 12B judge such as gemma-4-12b-it-nothink does NOT terminate the
RubricMiddleware reviewer loop — one ``grade_edition`` invoke once made 490+ LLM calls
with no verdict — which is why the judge is a ~30B+ non-writer route, not a 12B.)

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

Non-null ``tool_calls`` is necessary but NOT sufficient. Also confirm the candidate
**terminates the grader loop in a handful of calls** — run ``grade_edition`` on a real
edition and check it returns ``judge_model == <route>`` after a few LLM calls, not
hundreds (the gemma-12b failure above). ``None`` / ``<tool_call>`` text, OR a runaway
loop, → the grade stalls and the frontier fallback carries it.

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
from content_pipeline.okf import bundle_from_json, flatten_for_judge
from content_pipeline.providers.litellm import get_litellm_llm

logger = logging.getLogger(__name__)


# The rubric: one criterion per line (the format RubricMiddleware expects). This is
# a PUBLISH GATE, not a style review — it must HOLD an edition for things that make it
# unsafe or unfair to publish (harm, defamation, unattributed impersonation, empty AI
# desk), NOT for stylistic imperfections like dry prose. Voice/wit is a generation
# nicety the writer owns; gating on it would block the paper from ever auto-publishing.
EDITION_RUBRIC = (
    "HOW TO JUDGE (read first). This is a PUBLISH-SAFETY gate, not a fact-check and not "
    "a style review. When an OKF RESEARCH BUNDLE is provided above the edition, it is "
    "your verification source: it is the code-verified, link-validated research the "
    "stories were written from, so treat it as AUTHORITATIVE — the stories ARE "
    "substantive and real, even if they cover events newer than you've seen. NEVER fail "
    "an item because you 'cannot verify' a claim, a source, or comedic intent; the "
    "bundle and code already verified those. Fail a criterion ONLY for a clear, "
    "on-its-face violation visible in the edition; when in doubt, PASS. (The reachability "
    "of links is checked separately by code — not by you.)\n"
    "WHAT YOU MUST NOT FAIL ON (these caused repeated false holds):\n"
    "  • TRUNCATION / LENGTH. The bodies shown are deliberately shortened EXCERPTS, not "
    "the full articles. NEVER fail or remark that an item is 'truncated', 'cut off', "
    "'incomplete', 'too short' or 'ends mid-sentence' — completeness and length are not "
    "yours to judge.\n"
    "  • VERIFIABILITY / RECENCY. A shown `src=<host>` is a real, code-checked link. "
    "NEVER write that a source or claim is 'unverifiable', 'cannot be confirmed', 'lacks "
    "a verifiable source' or 'doesn't exist' — source truth is not your job.\n"
    "  • ATTRIBUTION ALREADY SHOWN. A fun item tagged `ATTRIBUTED (...)` IS attributed — "
    "never call it unattributed. Only `UNATTRIBUTED (no credit, no disclaimer)` may fail.\n"
    "- Harmless: nothing hateful, grim, gory, sexual or genuinely cruel. A fun paper. "
    "Political topics appear only as light, even-handed satire, never partisan "
    "campaigning. (Dry or plain prose is FINE — do not fail an item for tone alone.)\n"
    "- No defamation: parody of public figures — including comic look-alike names like "
    "'Ronald Dump' — is allowed and counts as clearly comedic. Fail ONLY if the text "
    "asserts a specific false factual claim about a real, named person as if it were "
    "true.\n"
    "- Every fun item is attributed: each fun item is tagged either `ATTRIBUTED (...)` "
    "or `UNATTRIBUTED (no credit, no disclaimer)`. PASS every `ATTRIBUTED` item. Fail "
    "ONLY an `UNATTRIBUTED` one — an unattributed, unmarked impersonation. Do not try to "
    "verify the credit; the tag is sufficient.\n"
    "- The AI desk is substantive, not empty: PASS if the headliner and subarticles each "
    "have a title and some body text. Fail ONLY if they are blank/placeholder or carry "
    "no source at all — NOT because you cannot confirm a story is true.\n"
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
    "Here is today's CraicGPT edition for review. The article bodies are deliberately "
    "shortened EXCERPTS (not the full text), so do not judge their length or "
    "completeness. Judge whether it is fit to publish.\n\n"
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


def _excerpt(text: str, n: int) -> str:
    """A short, CLEAN excerpt for the grader view — clipped on a word boundary with NO
    trailing '…'. The visible ellipsis was read by the judge as a TRUNCATED / "cut off"
    article and failed otherwise-complete editions (the 2026-06-19 false-positive: a
    short title clipped to "MolmoMotion…" → "headline cut off"). The rubric tells the
    judge these are deliberate excerpts, so a clean cut carries no truncation signal."""
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0] or t[:n]


def _okf_grounding(paper: dict, *, budget: int) -> str:
    """The edition's OKF research bundle (if it rode along on
    ``paper["edition"]["okf"]``), flattened into one budgeted ground-truth block."""
    data = (paper.get("edition") or {}).get("okf")
    if not data:
        return ""
    try:
        return flatten_for_judge(bundle_from_json(data), budget=budget)
    except Exception:  # noqa: BLE001 — grounding is best-effort; never sink the grade
        return ""


def grading_view(paper: dict, *, budget: int = 3500) -> str:
    """Render the grader's transcript: the OKF research bundle (code-verified ground
    truth, when present) followed by a COMPACT, judgement-focused view of the edition.

    The grader truncates each transcript message to a few thousand chars, so we
    can't hand it the whole paper JSON (images, trace, full bodies). Instead we
    surface exactly what the rubric judges: each item's title, a short body
    snippet, and — for fun items — the parody/attribution flags. Fun pieces get
    the most detail (they carry the parody/legal risk); AI shorts get just titles.
    The OKF bundle lets the judge confirm the desk is substantive and real rather
    than guessing from training data.
    """
    content = _edition_view(paper, budget=budget)
    okf_block = _okf_grounding(paper, budget=1800)
    if not okf_block:
        return content
    return (
        "OKF RESEARCH BUNDLE — code-verified, link-validated research the stories "
        "were written from (authoritative; the desk IS substantive and real):\n"
        f"{okf_block}\n\nEDITION TO CHECK:\n{content}"
    )


def _edition_view(paper: dict, *, budget: int = 3500) -> str:
    """A compact, judgement-focused view. Bodies are CLEAN excerpts (no truncation
    ellipsis), and each fun item states its attribution in plain words so the judge
    can't misread the terse flags (the 2026-06-19 false "FUN 3 unattributed" when the
    credit was right there). Titles are shown WHOLE — they are short and a clipped
    title reads as a "cut off" headline."""
    ai = paper.get("ai") or {}
    fun = paper.get("fun") or []
    lines: list[str] = []

    brief = (paper.get("editors_brief") or {}).get("title")
    if brief:
        lines.append(f"EDITOR'S BRIEF: {_excerpt(brief, 160)}")

    h = ai.get("headliner") or {}
    if h:
        lines.append(f"AI HEADLINER: {h.get('title') or ''} "
                     f"[src={_host(h.get('source_url'))}] {_excerpt(h.get('body'), 320)}")
    for i, s in enumerate(ai.get("subarticles") or []):
        lines.append(f"AI SUB {i}: {s.get('title') or ''} "
                     f"[src={_host(s.get('source_url'))}] {_excerpt(s.get('body'), 220)}")
    shorts = ai.get("shorts") or []
    if shorts:
        lines.append("AI SHORTS: " + " / ".join((s.get("title") or "") for s in shorts))

    for i, f in enumerate(fun):
        credit = f.get("source")
        disc = bool(f.get("satire_disclaimer"))
        voice = f.get("persona") or "—"
        # Plain-words attribution the judge cannot misread (credit OR disclaimer ⇒ attributed).
        if credit and disc:
            attribution = f"ATTRIBUTED (credit: {credit}; marked parody)"
        elif credit:
            attribution = f"ATTRIBUTED (credit: {credit})"
        elif disc:
            attribution = "ATTRIBUTED (marked parody/disclaimer)"
        else:
            attribution = "UNATTRIBUTED (no credit, no disclaimer)"
        lines.append(f"FUN {i}: {f.get('title') or ''} "
                     f"[voice={voice}] {attribution} {_excerpt(f.get('body'), 240)}")

    view = "\n".join(lines)
    # If we still overflow, drop whole trailing lines (never cut mid-item, which would
    # strip an attribution flag and re-create the false "unattributed" read).
    while len(view) > budget and len(lines) > 1:
        lines.pop()
        view = "\n".join(lines)
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


def _grade_once(model_name: str, view: str, *, rubric: str = EDITION_RUBRIC,
                task: str = _REVIEW_TASK, reviewer_prompt: str = _REVIEWER_PROMPT
                ) -> Optional[dict]:
    """Run ONE rubric grading pass on ``model_name``; return the RubricEvaluation
    dict (or None on failure). Builds a minimal reviewer deep agent whose only job is
    to receive the content so the grader can score the transcript against ``rubric``.

    The rubric/task/prompt are parameters so the same one-shot deepagents machinery
    can grade any content against any checklist (today: the edition vs
    :data:`EDITION_RUBRIC`)."""
    from deepagents import RubricMiddleware, create_deep_agent

    captured: list[dict] = []
    llm = get_litellm_llm(model_name, temperature=0)
    middleware = RubricMiddleware(
        model=llm,
        max_iterations=1,  # one-shot judge: the harness already wrote the content
        on_evaluation=lambda e: captured.append(dict(e)),
    )
    reviewer = create_deep_agent(
        model=llm, system_prompt=reviewer_prompt, middleware=[middleware],
    )
    reviewer.invoke({
        "messages": [{"role": "user", "content": task + view}],
        "rubric": rubric,
    })
    return captured[-1] if captured else None


def grade_edition(paper: dict, *, okf: Optional[dict] = None,
                  judge_model: Optional[str] = None,
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
    # An explicitly-passed bundle overrides whatever rode on the paper (used by
    # tests); otherwise grading_view reads paper["edition"]["okf"] directly.
    if okf is not None:
        paper = {**paper, "edition": {**(paper.get("edition") or {}), "okf": okf}}
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
