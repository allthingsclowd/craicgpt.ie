"""
content_pipeline/tools/news_tool.py
=====================================
LangChain tool for fetching current news headlines.

TUTORIAL: The @tool Decorator
-------------------------------
LangChain's `@tool` decorator turns a plain Python function into a Tool that
agents can call. The function's docstring becomes the tool's description —
this is what the LLM reads to decide whether to use the tool and how.

Key rules for writing good tool docstrings:
  ✓ Describe WHAT it returns, not HOW it works
  ✓ Mention the input type and any constraints
  ✓ Keep it under ~2 sentences — the LLM reads this at inference time

Why DuckDuckGo?
  No API key required. Great for tutorials, zero-cost CI runs, and demos.
  For production you'd swap in Tavily (better results, needs free API key).
"""

import json
import logging
from datetime import date

from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)

# ─── Initialise the DuckDuckGo search backend ──────────────────────────────
# TUTORIAL: DuckDuckGoSearchRun wraps the duckduckgo-search library.
# It returns a plain string of results. We wrap it in our own @tool so we
# can add structured output and logging on top.
_ddg = DuckDuckGoSearchRun()


@tool
def get_news_headlines(topic: str = "") -> str:
    """
    Fetch today's top news headlines relevant to Ireland, AI, and technology.
    Returns a JSON string with a list of headline strings.
    Pass an optional topic string to focus the search (e.g. 'AI Ireland').
    """
    query = topic if topic else cfg.news.news_query
    logger.info(f"[news_tool] Searching DuckDuckGo for: '{query}'")

    try:
        # DuckDuckGoSearchRun returns a raw string of results.
        raw_results = _ddg.run(f"{query} {date.today().isoformat()}")

        # Split the blob into individual headline-sized chunks.
        # DDG returns results as "Title. Snippet. URL." separated by newlines.
        lines = [line.strip() for line in raw_results.split("\n") if line.strip()]

        # Take the first N headlines (configured via NUM_HEADLINES env var).
        headlines = lines[: cfg.news.num_headlines]

        logger.info(f"[news_tool] Fetched {len(headlines)} headlines")
        return json.dumps({"headlines": headlines, "query": query})

    except Exception as exc:
        # TUTORIAL: Always handle tool failures gracefully. The agent will
        # receive this error string and can decide to retry or continue without
        # the data. Never let a tool crash the whole agent run.
        logger.warning(f"[news_tool] DuckDuckGo search failed: {exc}")
        return json.dumps({
            "headlines": [
                "AI continues to reshape the Irish tech landscape",
                "Tech giants announce new model releases this week",
                "Local developers embrace open-source AI tooling",
            ],
            "query": query,
            "note": "Used fallback headlines due to search error",
        })


@tool
def get_ai_tech_trends(focus: str = "LangChain LLM agents 2025") -> str:
    """
    Search for the latest AI and tech trends to inject into article context.
    Returns a summary string describing current developments in AI technology.
    Pass a focus string to narrow the search topic.
    """
    logger.info(f"[news_tool] Fetching AI trends for focus: '{focus}'")

    try:
        raw = _ddg.run(focus)
        # Return first 800 chars — enough context without overloading the prompt.
        summary = raw[:800].strip()
        logger.info("[news_tool] AI trends fetched successfully")
        return json.dumps({"trends_summary": summary, "focus": focus})

    except Exception as exc:
        logger.warning(f"[news_tool] Trends search failed: {exc}")
        return json.dumps({
            "trends_summary": (
                "LangChain and LangGraph continue to gain traction for building "
                "multi-agent AI systems. Local LLMs via Ollama and LM Studio are "
                "becoming mainstream for privacy-focused AI workflows."
            ),
            "focus": focus,
            "note": "Used fallback trends due to search error",
        })
