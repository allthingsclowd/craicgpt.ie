"""
content_pipeline/chains/newspaper_chain.py
============================================
LCEL chains and the multi-provider parallel runner.

TUTORIAL: LangChain Expression Language (LCEL)
------------------------------------------------
LCEL is LangChain's composition system. You build pipelines using the pipe `|`
operator, similar to Unix pipes or Elixir/Haskell function composition.

A basic chain looks like this:

    chain = prompt | llm | output_parser

When you call `chain.invoke({"key": "value"})`, LangChain:
  1. Passes the dict to `prompt.invoke()` → produces a list of ChatMessages
  2. Passes those messages to `llm.invoke()` → produces an AIMessage
  3. Passes the AIMessage to `output_parser.invoke()` → produces your final value

TUTORIAL: RunnableParallel
---------------------------
RunnableParallel runs multiple chains with the SAME input simultaneously.
Under the hood it uses Python's ThreadPoolExecutor. This means all three
LLM API calls happen concurrently — cutting total generation time roughly in thirds.

    parallel = RunnableParallel(
        claude=claude_chain,
        gemini=gemini_chain,
        local=local_chain,
    )
    results = parallel.invoke(input_dict)
    # results == {"claude": {...}, "gemini": {...}, "local": {...}}

The keys you give RunnableParallel become the keys in the output dict.
That output maps directly onto the JSON schema stored in S3.

TUTORIAL: Output Parsing
-------------------------
LLMs return plain text. We need structured data. Two options:
  1. StrOutputParser → raw string → parse JSON manually  (used here for robustness)
  2. with_structured_output(PydanticModel) → automatic parsing (cleaner but less
     tolerant of malformed responses from smaller local models)

We use option 1 with a fallback parser to handle cases where the local LLM
wraps its JSON in markdown fences or adds a polite preamble.
"""

import json
import logging
import re
import time
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnableLambda
from langchain_core.language_models import BaseChatModel

from content_pipeline.config import cfg
from content_pipeline.prompts.templates import ARTICLE_TEMPLATES

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Output Parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_llm_json(raw: str) -> dict:
    """
    Parse JSON from an LLM response, handling common formatting issues.

    TUTORIAL: Defensive JSON Parsing for Multi-Model Systems
    ----------------------------------------------------------
    Different models format their responses differently, and thinking models
    add an extra layer of complexity. This parser handles all known cases:

    1. Normal models — JSON straight away, or wrapped in markdown fences:
           ```json
           {"title": "...", "content": "..."}
           ```

    2. Thinking models with XML tags (DeepSeek-R1, Qwen3):
           <think>
           Let me reason about this...
           </think>
           {"title": "...", "content": "..."}

    3. Thinking models with prose reasoning (some LM Studio models):
           Thinking Process:
           1. Analyze the request...
           ...
           {"title": "...", "content": "..."}

    Strategy: strip known thinking wrappers, then scan left-to-right for the
    first { that begins a valid JSON object (using the last } as the fixed
    endpoint). For thinking models, early { chars appear in reasoning text
    and fail json.loads(); the actual JSON { succeeds. For normal models the
    first { is always correct, so there's no performance penalty.
    """
    text = raw.strip()

    # Step 1: Strip <think>...</think> blocks (DeepSeek-R1, Qwen3 thinking mode).
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Step 2: Strip markdown code fences (```json ... ``` or ``` ... ```).
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Step 3: Scan left-to-right for the first { that yields valid JSON.
    # The fixed right boundary is the last } in the text.
    end = text.rfind("}") + 1
    if end > 0:
        for match in re.finditer(r"\{", text):
            start = match.start()
            if start >= end:
                break
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue  # This { was inside thinking text — try the next one.

    logger.warning(f"[chain] JSON parse failed — no valid JSON found. Raw: {raw[:200]}")
    return {
        "content": raw[:500],
        "parse_error": "no valid JSON found",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-Provider Chain Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_provider_chain(
    template_name: str,
    llm: BaseChatModel,
    provider_label: str,
) -> Any:
    """
    Build an LCEL chain for a single article template and LLM provider.

    The chain adds metadata (model name, latency) to the parsed JSON output
    so the frontend can display "Generated by claude-3-5-sonnet in 1.2s".

    TUTORIAL: RunnableLambda
    -------------------------
    RunnableLambda wraps any Python function as a Runnable so it can be used
    in an LCEL pipe chain. Here we use it to:
      - Time the LLM call
      - Add metadata to the output dict
      - Handle per-provider errors gracefully

    Chain structure:
        prompt | llm | StrOutputParser() | RunnableLambda(_parse_and_annotate)
    """
    prompt = ARTICLE_TEMPLATES[template_name]
    str_parser = StrOutputParser()

    def _parse_and_annotate(raw_text: str) -> dict:
        """Parse LLM output and add provider metadata."""
        parsed = _parse_llm_json(raw_text)
        # Inject metadata — the frontend uses this for the model comparison UI.
        parsed["_provider"] = provider_label
        parsed["_model_id"] = getattr(llm, "model", getattr(llm, "model_name", "unknown"))
        return parsed

    # TUTORIAL: The | operator composes Runnables left-to-right.
    # Each stage receives the output of the previous stage as its input.
    return prompt | llm | str_parser | RunnableLambda(_parse_and_annotate)


# ─────────────────────────────────────────────────────────────────────────────
# Timed Provider Wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _timed_invoke(chain: Any, inputs: dict, provider: str) -> dict:
    """
    Invoke a chain and capture wall-clock latency.

    TUTORIAL: Why track latency?
    The comparator site shows which model was fastest — this is genuinely
    interesting data for users choosing between providers. Local LLMs are
    often slower than cloud APIs for the same output quality, but they're free.
    """
    t0 = time.monotonic()
    try:
        result = chain.invoke(inputs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        result["_latency_ms"] = latency_ms
        logger.info(f"[chain:{provider}] Done in {latency_ms}ms")
        return result
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[chain:{provider}] Failed after {latency_ms}ms: {exc}")
        return {
            "content": "",
            "error": str(exc),
            "_provider": provider,
            "_latency_ms": latency_ms,
            "_model_id": "error",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def run_parallel_generation(
    inputs: dict,
    claude_llm: BaseChatModel,
    gemini_llm: BaseChatModel,
    local_llm: BaseChatModel | None,
) -> dict[str, dict[str, dict]]:
    """
    Run all article templates against all three providers in parallel.

    TUTORIAL: How RunnableParallel scales
    ----------------------------------------
    With 5 article types × 3 providers = 15 LLM calls.
    Running sequentially: ~15 × 2s avg = ~30 seconds.
    Running in parallel (one RunnableParallel per article): ~3 × 2s = ~6 seconds.

    Each article's three providers run concurrently via RunnableParallel.
    The five articles themselves run sequentially here (simple, readable, debuggable).
    For a production system with stricter time budgets you could also parallelise
    across articles using ThreadPoolExecutor or LangGraph's parallel node branching.

    Args:
        inputs:    Dict of context variables (date, weather, headlines, etc.)
        claude_llm:  Initialised ChatAnthropic instance
        gemini_llm:  Initialised ChatGoogleGenerativeAI instance
        local_llm:   Initialised local ChatOpenAI instance, or None if unavailable

    Returns:
        Dict keyed by article_id → {"claude": {...}, "gemini": {...}, "local": {...}}
    """
    results: dict[str, dict[str, dict]] = {}

    for article_id, template in ARTICLE_TEMPLATES.items():
        logger.info(f"[chain] Generating article: {article_id}")

        # Build per-provider chains for this article template.
        claude_chain = _build_provider_chain(article_id, claude_llm, "claude")
        gemini_chain = _build_provider_chain(article_id, gemini_llm, "gemini")

        # TUTORIAL: RunnableParallel — the heart of the comparator.
        # All providers receive identical `inputs` and run simultaneously.
        parallel_runners: dict[str, Any] = {
            "claude": RunnableLambda(lambda inp, c=claude_chain: _timed_invoke(c, inp, "claude")),
            "gemini": RunnableLambda(lambda inp, g=gemini_chain: _timed_invoke(g, inp, "gemini")),
        }

        if local_llm is not None and not cfg.skip_local_llm:
            local_chain = _build_provider_chain(article_id, local_llm, "local")
            parallel_runners["local"] = RunnableLambda(
                lambda inp, lc=local_chain: _timed_invoke(lc, inp, "local")
            )

        # TUTORIAL: RunnableParallel.invoke() runs all values concurrently
        # using threads, then returns when ALL of them have finished.
        parallel = RunnableParallel(**parallel_runners)
        article_outputs = parallel.invoke(inputs)

        # If local LLM was skipped, add a placeholder so the frontend
        # always has a consistent schema to render.
        if "local" not in article_outputs:
            article_outputs["local"] = {
                "content": "Local LLM unavailable — start LM Studio and re-run.",
                "_provider": "local",
                "_model_id": "unavailable",
                "_latency_ms": 0,
            }

        results[article_id] = article_outputs
        logger.info(f"[chain] Completed: {article_id}")

    return results
