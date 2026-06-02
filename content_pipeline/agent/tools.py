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
    # The legacy DuckDuckGoSearchRun hits html.duckduckgo.com, which is
    # frequently rate-limited/blocked. Use ddgs and try reliable backends in
    # order (the bare "duckduckgo" backend is deliberately last); return the
    # first that yields results.
    from ddgs import DDGS

    last_err = None
    for backend in ("brave", "bing", "auto"):
        try:
            results = list(DDGS().text(query, max_results=6, backend=backend))
        except Exception as exc:  # noqa: BLE001 — try the next backend
            last_err = exc
            continue
        if results:
            blocks = [
                f"{r.get('title', '')}\n{r.get('body', '')}\n{r.get('href', '')}"
                for r in results
            ]
            # Cap the blob — long dumps accumulate and blow the context window.
            return "\n\n".join(blocks)[:1800]
    logger.warning("[tool:web_search] no backend returned results (last err: %s)", last_err)
    return "no results found"


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
        return text[:2500]  # enough for the gist; keeps the context window in check
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
    The PNG is saved locally and the path returned as JSON
    {image_url, model} — set the story's image_url to this value. The harness
    uploads the file and rewrites the URL to the public CDN path at publish time
    (base64 never enters your context). Generate one image per fun story,
    directly related to that story.
    """
    import hashlib
    import os

    from content_pipeline.content_config import content_cfg

    img = _generate_image(prompt)
    os.makedirs(content_cfg.image_dir, exist_ok=True)
    fname = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] + ".png"
    path = os.path.join(content_cfg.image_dir, fname)
    with open(path, "wb") as fh:
        fh.write(img.to_bytes())
    logger.info("[tool:generate_cover_image] saved %s (%s)", path, img.model)
    return json.dumps({"image_url": path, "model": img.model})
