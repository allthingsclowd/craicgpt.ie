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
    Returns a block of text results (titles, snippets, URLs). If the search backend
    is unavailable it returns a line starting "SEARCH_FAILED:" — when you see that,
    do NOT invent stories or URLs: report that search failed and stop. The newsroom
    holds the edition rather than publish fabricated content.

    Uses the official Brave Search API (keyed, built for automation) — NOT scraping,
    which got 429-rate-limited from the datacenter IP and triggered hallucination.
    """
    import time

    import httpx

    from content_pipeline.content_config import WEB_USER_AGENT, content_cfg

    key = content_cfg.brave_search_api_key
    if not key:
        logger.error("[tool:web_search] no BRAVE_SEARCH_API_KEY configured")
        return "SEARCH_FAILED: no Brave API key configured (set BRAVE_SEARCH_API_KEY)"
    time.sleep(1.1)  # Brave free tier = 1 query/sec; pace the agent's sequential searches
    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 8},
            headers={"X-Subscription-Token": key, "Accept": "application/json",
                     "User-Agent": WEB_USER_AGENT},
            timeout=20,
        )
    except Exception as exc:  # noqa: BLE001 — a network failure is a real signal, not "nothing found"
        logger.error("[tool:web_search] Brave request failed: %s", exc)
        return f"SEARCH_FAILED: network error ({type(exc).__name__})"
    if resp.status_code != 200:
        reason = {429: "429 rate-limited (slow down / over quota)",
                  401: "401 unauthorized (bad BRAVE_SEARCH_API_KEY)",
                  403: "403 forbidden (key/plan)"}.get(
            resp.status_code, f"HTTP {resp.status_code}")
        logger.error("[tool:web_search] Brave %s", reason)
        return f"SEARCH_FAILED: {reason}"
    results = ((resp.json() or {}).get("web") or {}).get("results") or []
    if not results:
        return "no results found"
    blocks = [f"{r.get('title', '')}\n{r.get('description', '')}\n{r.get('url', '')}"
              for r in results]
    return "\n\n".join(blocks)[:2200]


@tool
def fetch_page(url: str) -> str:
    """Fetch a web page and return its readable text (truncated to ~4500 chars).

    Use this to read a candidate source before writing about it or citing it —
    far enough into the body to capture the article's conclusion, not just its lede.
    """
    import re

    import httpx

    from content_pipeline.content_config import WEB_USER_AGENT

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": WEB_USER_AGENT})
        resp.raise_for_status()
        # Crude tag strip — enough for the model to read the gist.
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4500]  # far enough in to reach the conclusion; still context-safe
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
def assign_journalist_voices(count: int, seed: str) -> str:
    """Assign `count` distinct parody-journalist personas (one per fun story).

    Each is a well-known public figure's voice bylined under a punny misspelling
    (e.g. Donald Trump's style → "Ronald Dump"). `seed` should be the edition
    date (YYYY-MM-DD) so the lineup is stable per day and rotates across days.
    Returns JSON: a list of {character, voice_brief, byline, disclaimer}. Write
    each fun story in its assigned figure's voice and keep the disclaimer.
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

    # Resilient: a failed image must not crash the whole edition — return an
    # error string and let the editor continue without that illustration.
    try:
        img = _generate_image(prompt)
        os.makedirs(content_cfg.image_dir, exist_ok=True)
        fname = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] + ".png"
        path = os.path.join(content_cfg.image_dir, fname)
        with open(path, "wb") as fh:
            fh.write(img.to_bytes())
        logger.info("[tool:generate_cover_image] saved %s (%s)", path, img.model)
        return json.dumps({"image_url": path, "model": img.model})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tool:generate_cover_image] failed: %s", exc)
        return json.dumps({"image_url": None, "error": str(exc)[:200]})
