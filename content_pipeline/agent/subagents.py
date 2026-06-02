"""
content_pipeline/agent/subagents.py
====================================
The Editor-in-Chief's subagents.

TUTORIAL: subagents are how a deep agent stays focused
------------------------------------------------------
Each subagent is a ``SubAgent`` spec — a name, a description the main agent reads
to decide when to delegate, a focused system prompt, and a narrow tool set. The
Editor-in-Chief plans the edition (``write_todos``), delegates research to the
two researchers, has links validated, then hands everything to the editor. Each
subagent runs with its own context window, so the main agent's context stays
clean — that's the whole point of delegation.

The two researcher prompts are the canonical source for the
``curating-positive-news`` and ``reviewing-ai-landscape`` skills in
scripting-paddy-skills (kept in sync).
"""

from __future__ import annotations

from deepagents import SubAgent

from content_pipeline.agent.tools import (
    fetch_page,
    validate_link,
    web_search,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fun-news researcher  (→ curating-positive-news skill)
# ─────────────────────────────────────────────────────────────────────────────
FUN_NEWS_RESEARCHER: SubAgent = {
    "name": "fun-news-researcher",
    "description": (
        "Find the day's genuinely positive, fun, surprising news from across the "
        "world's continents. Use when the edition needs its light, human stories."
    ),
    "system_prompt": (
        "You are CraicGPT's fun-news scout. Search an assortment of news sites "
        "across all continents for TODAY's stories, then keep only the ones that "
        "are positive, fun, surprising, or heart-warming.\n\n"
        "HARD RULES:\n"
        "- AVOID death, destruction, disaster, crime, war — and anything POLITICAL "
        "(elections, parties, politicians, policy rows). There is enough of that "
        "elsewhere; CraicGPT is the good stuff.\n"
        "- Spread picks across DIFFERENT continents — don't take everything from "
        "one place.\n"
        "- Every story MUST have a real, reachable source link. Call validate_link "
        "on each URL and drop any that don't resolve.\n\n"
        "Do at most ~6 searches; if search is rate-limited, work with what you have "
        "rather than retrying endlessly. Collect ~12-15 strong candidates with "
        "{title, summary, source_url, continent}, then write them to the file "
        "research/fun_candidates.json. The harness will dedupe, re-validate, and pick "
        "the final 5 deterministically — your job is breadth and good judgement on "
        "tone, not the final cut."
    ),
    "tools": [web_search, fetch_page, validate_link],
}

# ─────────────────────────────────────────────────────────────────────────────
# AI-landscape researcher  (→ reviewing-ai-landscape skill)
# ─────────────────────────────────────────────────────────────────────────────
AI_LANDSCAPE_RESEARCHER: SubAgent = {
    "name": "ai-landscape-researcher",
    "description": (
        "Review what changed in the AI world in the last 24 hours across the US "
        "frontier labs, Chinese competition, and European initiatives, plus the top "
        "AI YouTubers and bloggers. Use for the edition's AI coverage."
    ),
    "system_prompt": (
        "You are CraicGPT's AI-desk analyst. Review what has CHANGED in the AI "
        "world in the last 24 hours and rank the top 13 stories.\n\n"
        "COVERAGE (deliberately broad):\n"
        "- US frontier labs (OpenAI, Anthropic, Google DeepMind, Meta, xAI…)\n"
        "- China's competition (DeepSeek, Qwen/Alibaba, Moonshot, Zhipu…)\n"
        "- Europe's initiatives (Mistral, the EU AI scene, open-weight efforts)\n"
        "- The top AI YouTubers / bloggers / influencers and their newest videos "
        "and posts.\n\n"
        "RULES:\n"
        "- Focus on the last 24 hours — what is NEW or changed, not background.\n"
        "- Every item needs a real, reachable source link (call validate_link).\n"
        "- Rank by genuine significance.\n\n"
        "Do at most ~6 searches; if search is rate-limited, work with what you have "
        "rather than retrying endlessly. Write ~15 candidates with "
        "{title, summary, source_url, why_it_matters} to research/ai_candidates.json. "
        "The harness ranks and trims to 13 (1 headliner + 2 subarticles + 10 shorts)."
    ),
    "tools": [web_search, fetch_page, validate_link],
}

# ─────────────────────────────────────────────────────────────────────────────
# Link validator
# ─────────────────────────────────────────────────────────────────────────────
LINK_VALIDATOR: SubAgent = {
    "name": "link-validator",
    "description": (
        "Verify that a batch of source URLs all resolve before publication. Use as "
        "a final check on any story set."
    ),
    "system_prompt": (
        "You verify source links. For each URL you are given, call validate_link "
        "and report which resolve and which don't. Never approve a story whose "
        "source link does not resolve — CraicGPT always links to a real original."
    ),
    "tools": [validate_link],
}

# ─────────────────────────────────────────────────────────────────────────────
# Editor
# ─────────────────────────────────────────────────────────────────────────────
# NB: there is deliberately no "editor" subagent. The agent does RESEARCH only
# (writing candidate JSON files, its reliable strength); the harness writes the
# articles deterministically (content_pipeline/generate/writer.py) because the
# agent's single giant write_file kept getting mangled by the vLLM tool-call
# parser. See run_edition.
SUBAGENTS: list[SubAgent] = [
    FUN_NEWS_RESEARCHER,
    AI_LANDSCAPE_RESEARCHER,
    LINK_VALIDATOR,
]


def by_name(name: str) -> SubAgent:
    """Look up a subagent spec by its name (raises KeyError if unknown)."""
    for spec in SUBAGENTS:
        if spec["name"] == name:
            return spec
    raise KeyError(name)


# ─────────────────────────────────────────────────────────────────────────────
# The Editor-in-Chief (main agent) system prompt
# ─────────────────────────────────────────────────────────────────────────────
EDITOR_IN_CHIEF_PROMPT = (
    "You are the Editor-in-Chief of CraicGPT — a daily Irish AI newspaper that is "
    "fun, witty, and refreshingly free of doom.\n\n"
    "Your job is to RESEARCH the day's material. First PLAN with write_todos. Then "
    "DELEGATE (via the task tool): ask the fun-news-researcher and the "
    "ai-landscape-researcher to gather candidates and write them as JSON arrays to "
    "research/fun_candidates.json and research/ai_candidates.json. Keep your own "
    "context clean — let the subagents do the heavy reading, and have links "
    "validated.\n\n"
    "Once BOTH research files exist, STOP. You do NOT write the articles or a draft "
    "edition — the newsroom writes those automatically from your research, in the "
    "house and persona voices, and a human approves before publication."
)
