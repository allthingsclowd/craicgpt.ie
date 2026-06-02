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
from content_pipeline.agent.trace import TraceRecorder
from content_pipeline.compile import build_paper
from content_pipeline.content_config import content_cfg
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


def run_edition(
    date_iso: str,
    *,
    generated_at: str,
    agent: Any | None = None,
    brief: Optional[str] = None,
    thread_id: Optional[str] = None,
    recursion_limit: int = 200,
    trace: Optional[TraceRecorder] = None,
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
    agent = agent or build_editor_in_chief()
    brief = brief or (
        f"Produce CraicGPT's edition for {date_iso}. Today's date is {date_iso}. "
        "Plan it, delegate research and editing to your subagents, and write the "
        "finished edition to draft/edition.json. Then stop for human approval."
    )

    config = {
        "configurable": {"thread_id": thread_id or date_iso},
        "recursion_limit": recursion_limit,
    }
    result = agent.invoke({"messages": [{"role": "user", "content": brief}]}, config=config)

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

    return build_paper(
        date_iso,
        generated_at,
        ai=ai,
        fun=fun,
        context={"agent_trace": trace.as_list(), "files": list(files)},
    )
