"""
content_pipeline/generate/writer.py
===================================
Deterministic article writer — the harness's editing step.

Editing used to be a deep-agent subagent that wrote the whole edition as one
giant ``write_file`` tool call. The vLLM/Qwen3.6 tool-call parser kept mangling
that huge JSON-string argument (truncation, unterminated strings). So we moved
editing here: small **plain chat → JSON** calls — one for the AI section, one
per fun story. Small outputs, no tool-call serialisation, robust lenient parse.
The agent now does only research (its reliable strength).

The LLM call is injected as ``generate(prompt) -> dict`` so this is unit-testable
offline and trivially parallelisable across fleet boxes later.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]


def loads_lenient(raw: str) -> dict:
    """Parse JSON that may be wrapped in markdown fences or thinking-model tags."""
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Tolerate an UNCLOSED <think> preamble (thinking truncated before </think>):
    # drop everything up to the first JSON brace if one exists.
    if "<think>" in text and "{" in text:
        text = text[text.index("{"):]
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
    raise ValueError(f"could not parse JSON from model output: {text[:120]!r}")


def _default_generate(prompt: str) -> dict:
    """Plain chat completion on the write model, parsed leniently to a dict.

    Thinking mode is disabled — Qwen3.6 otherwise emits a long ``<think>`` preamble
    that consumes the output budget before any JSON appears.
    """
    from content_pipeline.providers.litellm import get_litellm_llm

    llm = get_litellm_llm(
        content_cfg.write_model,
        max_tokens=6000,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    resp = llm.invoke(prompt)
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    return loads_lenient(text)


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (concise — keeps each output small and parseable)
# ─────────────────────────────────────────────────────────────────────────────
_AI_PROMPT = (
    "You are CraicGPT's AI editor. Write in Graham's house voice: Irish, witty, "
    "gently cynical, teaching-minded — never corporate-deck-speak.\n\n"
    "From the AI-landscape candidates below, write today's AI coverage and output "
    "ONLY compact JSON (no markdown), exactly this shape:\n"
    '{{"headliner": {{"title","standfirst","body","source_url"}}, '
    '"subarticles": [{n_sub} items of {{"title","body","source_url"}}], '
    '"shorts": [{n_short} items of {{"title","body","source_url"}}]}}\n'
    "Lengths: headliner body <=150 words, subarticles <=90, shorts <=40. Rank by "
    "genuine significance. Reuse each candidate's real source_url.\n\n"
    "Candidates JSON:\n{candidates}"
)

_FUN_PROMPT = (
    "Rewrite this good-news story as a punchy, fun tabloid piece IN THE "
    "UNMISTAKABLE VOICE of {persona} — {voice}\n"
    "Max 130 words, PG-13, warm and positive, use their signature phrases. Keep "
    "the real source_url. Output ONLY compact JSON (no markdown): "
    '{{"title","body","source_url"}}\n\n'
    "Story JSON:\n{story}"
)


def write_ai_section(
    ai_candidates: list,
    *,
    num_subarticles: int,
    num_shorts: int,
    generate: Optional[Generate] = None,
) -> dict:
    """Write the AI section (1 headliner + N subs + M shorts) in one JSON call."""
    gen = generate or _default_generate
    prompt = _AI_PROMPT.format(
        n_sub=num_subarticles,
        n_short=num_shorts,
        candidates=json.dumps(ai_candidates)[:6000],
    )
    data = gen(prompt)
    return {
        "headliner": data.get("headliner") or {},
        "subarticles": (data.get("subarticles") or [])[:num_subarticles],
        "shorts": (data.get("shorts") or [])[:num_shorts],
    }


def write_fun_story(
    candidate: dict,
    persona: str,
    voice_brief: str,
    *,
    generate: Optional[Generate] = None,
) -> dict:
    """Write one fun story in the assigned persona's voice (small JSON call)."""
    gen = generate or _default_generate
    prompt = _FUN_PROMPT.format(
        persona=persona,
        voice=voice_brief,
        story=json.dumps(candidate)[:1500],
    )
    data = gen(prompt)
    return {
        "title": data.get("title", ""),
        "body": data.get("body", ""),
        "source_url": data.get("source_url") or candidate.get("source_url", ""),
    }
