"""
content_pipeline/agent/editor_in_chief.py
==========================================
The Editor-in-Chief — a LangChain **deep agent** that plans the edition, delegates
to its researchers and editor, and leaves a draft for human approval.

TUTORIAL: create_deep_agent in three lines
-------------------------------------------
A deep agent is the planning tool (``write_todos``), a virtual filesystem, and
subagent delegation (``task``) wrapped around a tool-calling model. We pass our
four subagents and the house system prompt; deepagents wires the rest. The model
is any LangChain chat model — here, a local open-source Qwen3.6 reached through
the grazlab LiteLLM proxy, with a frontier fallback supplied by the caller.

Open source only: no LangSmith, no hosted platform. The agent's plan, subagent
hand-offs, and tool calls are captured by ``trace.TraceRecorder`` for the
"Under the Hood" visualiser — that is our observability story.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from content_pipeline.agent.subagents import EDITOR_IN_CHIEF_PROMPT, SUBAGENTS
from content_pipeline.agent.trace import TraceRecorder, extract_trace
from content_pipeline.compile import build_paper
from content_pipeline.content_config import content_cfg
from content_pipeline.generate.personas import (
    ROSTER,
    SATIRE_DISCLAIMER,
    assign_personas,
    persona_byline,
)
from content_pipeline.providers.litellm import get_litellm_llm

logger = logging.getLogger(__name__)

EDITION_FILE = "/draft/edition.json"


def build_brain(model_name: Optional[str] = None) -> BaseChatModel:
    """Return the tool-calling model that drives the agent loop.

    Defaults to the configured brain route (DGX vLLM Qwen3.6 — confirmed
    tool-calling-capable). Construction does no network I/O.
    """
    return get_litellm_llm(model_name or content_cfg.brain_model)


def build_editor_in_chief(
    *,
    model: Optional[BaseChatModel] = None,
    checkpointer: Any | None = None,
):
    """Assemble the Editor-in-Chief deep agent.

    Args:
        model: The tool-calling chat model. Defaults to :func:`build_brain`.
        checkpointer: Optional LangGraph checkpointer. Pass a durable
            ``SqliteSaver`` in production so a paused (awaiting-approval) run
            survives a restart; omit for a one-shot run.

    Returns:
        A compiled LangGraph deep agent. Invoke with
        ``{"messages": [{"role": "user", "content": <brief>}]}`` and a
        ``thread_id`` config.
    """
    # Lazy import so the rest of the package (and most tests) don't need the
    # deepagents stack imported.
    from deepagents import create_deep_agent

    brain = model or build_brain()
    logger.info("[editor-in-chief] assembling deep agent on %s",
                getattr(brain, "model_name", brain))

    # NB: deepagents already includes a SummarizationMiddleware in its default
    # stack, so we don't add our own (it would trip the duplicate-middleware
    # check). We keep context bounded instead via small tool outputs (see
    # agent/tools.py) and a modest per-call max_tokens (content_config), with the
    # built-in summarizer as the backstop on long research loops.
    return create_deep_agent(
        model=brain,
        system_prompt=EDITOR_IN_CHIEF_PROMPT,
        subagents=SUBAGENTS,
        checkpointer=checkpointer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Running an edition
# ─────────────────────────────────────────────────────────────────────────────
def _loads_lenient(raw: str) -> dict:
    """Parse JSON that may be wrapped in markdown fences or thinking text."""
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        end = text.rfind("}") + 1
        for m in re.finditer(r"\{", text):
            if m.start() >= end:
                break
            try:
                return json.loads(text[m.start():end])
            except json.JSONDecodeError:
                continue
    raise RuntimeError("draft/edition.json was not valid JSON")


def _extract_file(files: dict, path: str) -> Optional[str]:
    """Read a virtual-FS file's content (paths are stored absolute, e.g. /draft/…)."""
    entry = files.get(path) or files.get(path.lstrip("/"))
    return entry.get("content") if entry else None


def _finalize_fun(fun: list, date_iso: str) -> None:
    """Stamp persona / byline / satire disclaimer on each fun story.

    The editor writes the prose in a Marvel voice but doesn't reliably populate
    the structured fields. We assign a day-stable persona where the editor left
    one blank, always set the byline, and ALWAYS set the satire disclaimer (a
    legal requirement — every persona piece must carry it).
    """
    assigned = assign_personas(len(fun), seed=date_iso) if fun else []
    for i, item in enumerate(fun):
        if not isinstance(item, dict):
            continue
        # Keep the editor's choice only if it's a real Marvel roster character;
        # otherwise (blank, or an off-brand pick like "Aquaman") assign one.
        if item.get("persona") not in ROSTER and i < len(assigned):
            item["persona"] = assigned[i]
        if item.get("persona"):
            item["byline"] = persona_byline(item["persona"])
        item["satire_disclaimer"] = SATIRE_DISCLAIMER


def _generate_fun_images(fun: list, *, generate=None, image_model: Optional[str] = None) -> Optional[str]:
    """Generate one image per fun story in the harness; set image_url to the path.

    Overwrites whatever the editor put in image_url (it tends to invent stock
    URLs). ``generate`` is injectable for tests: ``prompt -> (local_path, model)``;
    the default calls FLUX via :func:`generate.images.save_image`. A failed image
    leaves image_url empty rather than crashing the edition. Returns the image
    model actually used (for attribution), if any.
    """
    if not fun:
        return image_model

    def _default(prompt: str):
        from content_pipeline.generate.images import save_image

        return save_image(prompt)

    gen = generate or _default
    used_model = image_model
    for item in fun:
        if not isinstance(item, dict):
            continue
        prompt = (
            "Tabloid newspaper cover illustration, vivid comic-book style, no text: "
            f"{item.get('title', '')}. {(item.get('body', '') or '')[:160]}"
        )
        try:
            path, model = gen(prompt)
            item["image_url"] = path
            used_model = model or used_model
        except Exception as exc:  # noqa: BLE001 — a bad image must not sink the edition
            logger.warning("[run_edition] image generation failed: %s", exc)
            item["image_url"] = None
    return used_model


def _stamp_attribution(
    ai: dict,
    fun: list,
    *,
    text_model: Optional[str],
    image_model: Optional[str],
) -> None:
    """Stamp `_text_model` (and `_image_model` for illustrated fun items).

    Uses ``setdefault`` so any model-supplied attribution is preserved; otherwise
    records the configured routes that actually ran (honest "generated by" note).
    """
    text_model = text_model or content_cfg.brain_model
    image_model = image_model or content_cfg.image_model

    items = [ai.get("headliner")] + list(ai.get("subarticles", [])) + list(ai.get("shorts", []))
    for item in items:
        if isinstance(item, dict):
            item.setdefault("_text_model", text_model)
    for item in fun:
        if isinstance(item, dict):
            item.setdefault("_text_model", text_model)
            if item.get("image_url"):
                item.setdefault("_image_model", image_model)


def run_edition(
    date_iso: str,
    *,
    generated_at: str,
    agent: Any | None = None,
    brief: Optional[str] = None,
    thread_id: Optional[str] = None,
    recursion_limit: int = 200,
    trace: Optional[TraceRecorder] = None,
    text_model: Optional[str] = None,
    image_model: Optional[str] = None,
    image_generate=None,
) -> dict:
    """Run the deep agent for one edition and return a schema-v3 paper dict.

    The agent writes the edition to its virtual filesystem; we extract it,
    enforce the configured counts deterministically (a safety net over the
    model's selection), and run :func:`compile.build_paper` so the published
    JSON always matches schema v3 regardless of how the model formatted things.

    Args:
        date_iso: Edition date (YYYY-MM-DD).
        generated_at: ISO8601 timestamp (passed in — no clock here).
        agent: A compiled deep agent (injected in tests); defaults to a freshly
            built Editor-in-Chief.
        brief: Override the user brief sent to the agent.
        thread_id: Checkpointer thread id (defaults to the date).
        recursion_limit: LangGraph step budget for the agentic run.
        trace: Optional recorder; its events are embedded for the UI visualiser.

    Returns:
        The schema-v3 paper dict (a draft — not yet approved/published).

    Raises:
        RuntimeError: if the agent didn't write a parseable draft edition.
    """
    trace = trace or TraceRecorder()
    if agent is None:
        # A checkpointer lets the optional second pass resume the SAME thread with
        # the research files still in the virtual filesystem.
        from langgraph.checkpoint.memory import InMemorySaver

        agent = build_editor_in_chief(checkpointer=InMemorySaver())
    brief = brief or (
        f"Produce CraicGPT's edition for {date_iso}. Today's date is {date_iso}. "
        "Plan it, delegate research and editing to your subagents.\n\n"
        "THE SINGLE DELIVERABLE is one JSON file at draft/edition.json with EXACTLY "
        'this shape: {"ai": {"headliner": {"title","standfirst","body","source_url"}, '
        '"subarticles": [{"title","body","source_url"}], '
        '"shorts": [{"title","body","source_url"}]}, '
        '"fun": [{"title","body","source_url","persona","satire_disclaimer",'
        '"image_url","kind"}]}.\n'
        "Write 1 AI headliner + 2 subarticles + 10 shorts, and 5 fun stories. "
        "Write VALID JSON only — NOT markdown, NOT prose files. The task is NOT "
        "complete until draft/edition.json exists and parses as JSON. Then stop for "
        "human approval."
    )

    config = {
        "configurable": {"thread_id": thread_id or date_iso},
        "recursion_limit": recursion_limit,
    }
    result = agent.invoke({"messages": [{"role": "user", "content": brief}]}, config=config)
    files = result.get("files", {})

    # The autonomous agent reliably gathers research but sometimes stops before
    # writing the final edition. If the draft is missing, nudge it (on the SAME
    # checkpointed thread, so the candidate files persist) to assemble it now.
    if not _extract_file(files, EDITION_FILE):
        logger.warning("[run_edition] no draft after research pass; nudging editor to assemble")
        nudge = (
            "Read research/fun_candidates.json and research/ai_candidates.json, then "
            "WRITE the complete edition as VALID JSON to draft/edition.json now: "
            "1 AI headliner + 2 subarticles + 10 shorts in Graham's witty house voice, "
            "and 5 fun stories — each in a distinct Marvel voice (call assign_marvel_voices "
            "and set persona, byline, satire_disclaimer). Illustrations are added "
            "automatically afterwards. Shape: "
            '{"ai": {"headliner": {...}, "subarticles": [...], "shorts": [...]}, "fun": [...]}. '
            "Use write_file with path draft/edition.json, then stop."
        )
        result = agent.invoke({"messages": [{"role": "user", "content": nudge}]}, config=config)
        files = result.get("files", {})

    raw = _extract_file(files, EDITION_FILE)
    if not raw:
        raise RuntimeError(
            f"editor did not write {EDITION_FILE} (files present: {list(files)})"
        )

    edition = _loads_lenient(raw)
    ai = dict(edition.get("ai", {}))
    fun = list(edition.get("fun", []))

    # Deterministic safety net: enforce the resolved counts (13 AI / 5 fun).
    ai["subarticles"] = ai.get("subarticles", [])[: content_cfg.num_ai_subarticles]
    ai["shorts"] = ai.get("shorts", [])[: content_cfg.num_ai_shorts]
    fun = fun[: content_cfg.num_fun_stories]

    # Deterministically finalise persona/byline/disclaimer (the editor applies the
    # voice but doesn't reliably fill these fields), generate each fun story's
    # image in the harness (the editor invents stock URLs rather than using the
    # FLUX tool output), then stamp model attribution.
    _finalize_fun(fun, date_iso)
    image_model = _generate_fun_images(fun, generate=image_generate, image_model=image_model)
    _stamp_attribution(ai, fun, text_model=text_model, image_model=image_model)

    # Build the trace from the agent's actual run, prepended with any
    # harness-recorded events (e.g. fallbacks).
    agent_trace = trace.as_list() + extract_trace(result.get("messages", []))

    return build_paper(
        date_iso,
        generated_at,
        ai=ai,
        fun=fun,
        context={"agent_trace": agent_trace, "files": list(files)},
    )
