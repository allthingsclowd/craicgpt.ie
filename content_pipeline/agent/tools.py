"""
content_pipeline/agent/tools.py
===============================
The ``@tool`` wrappers the deep agent and its subagents call.

TUTORIAL: @tool is the LangChain 1.0 way
----------------------------------------
A plain Python function + the ``@tool`` decorator = a tool the model can call.
The function name becomes the tool name; the docstring becomes the description
the model reads to decide *when* and *how* to call it. Keep docstrings short and
action-oriented.

Division of labour (``deciding-deterministic-vs-llm``):
- **Live judgment tools** live here — searching, fetching, validating a link,
  generating an image: things that need the network or the model's discretion.
- **Deterministic mechanics** (dedupe, filter, diversity selection) are NOT
  tools — the harness runs them over the candidates the researcher collects, so
  we don't pay the model to do arithmetic. See ``research.curation.curate_candidates``.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from content_pipeline.generate.images import generate_image as _generate_image
from content_pipeline.generate.personas import (
    SATIRE_DISCLAIMER,
    assign_personas,
    persona_byline,
    voice_brief,
)
from content_pipeline.research.curation import validate_source_link

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Live research tools
# ─────────────────────────────────────────────────────────────────────────────
@tool
def web_search(query: str) -> str:
    """Search the web for recent stories or pages about a topic.

    Use this to discover candidate news stories or AI-landscape developments.
    Returns a block of text results (titles, snippets, and URLs).
    """
    # Lazy import keeps the heavy community package out of unit-test import paths.
    from langchain_community.tools import DuckDuckGoSearchRun

    try:
        return DuckDuckGoSearchRun().run(query)
    except Exception as exc:  # noqa: BLE001 — tool failures must not crash the agent
        logger.warning("[tool:web_search] failed: %s", exc)
        return f"web_search error: {exc}"


@tool
def fetch_page(url: str) -> str:
    """Fetch a web page and return its readable text (truncated to ~6000 chars).

    Use this to read a candidate source before writing about it or citing it.
    """
    import re

    import httpx

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "CraicGPT/1.0"})
        resp.raise_for_status()
        # Crude tag strip — enough for the model to read the gist.
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tool:fetch_page] failed for %s: %s", url, exc)
        return f"fetch_page error: {exc}"


@tool
def validate_link(url: str) -> bool:
    """Return True if a source URL resolves (HTTP 2xx).

    Always validate a source link before citing it — every published story must
    link to a real, reachable original.
    """
    return validate_source_link(url)


# ─────────────────────────────────────────────────────────────────────────────
# Editor support tools
# ─────────────────────────────────────────────────────────────────────────────
@tool
def assign_marvel_voices(count: int, seed: str) -> str:
    """Assign `count` distinct Marvel personas (one per fun story) for a day.

    `seed` should be the edition date (YYYY-MM-DD) so the lineup is stable per
    day and rotates across days. Returns JSON: a list of
    {character, voice_brief, byline, disclaimer}. Write each fun story in its
    assigned character's voice and show the disclaimer.
    """
    characters = assign_personas(count, seed=seed)
    payload = [
        {
            "character": c,
            "voice_brief": voice_brief(c),
            "byline": persona_byline(c),
            "disclaimer": SATIRE_DISCLAIMER,
        }
        for c in characters
    ]
    return json.dumps(payload)


@tool
def generate_cover_image(prompt: str) -> str:
    """Generate an illustration for a story from a vivid visual prompt.

    Describe the scene concretely (subject, setting, mood, tabloid-cover style).
    Returns JSON: {model, size, b64_png_len} — the bytes are handled by the
    harness, which saves and links the image. Generate one image per fun story,
    directly related to that story.
    """
    img = _generate_image(prompt)
    return json.dumps({"model": img.model, "size": "1024x1024",
                       "b64_png_len": len(img.b64_png)})
