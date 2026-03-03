"""
content_pipeline/agents/research_agent.py
==========================================
ReAct research agent: fetches news and weather before content generation.

TUTORIAL: What is a ReAct Agent?
-----------------------------------
ReAct (Reason + Act) is the most widely used agent pattern in LangChain.
The agent loops through:
  1. Thought  — "I need to get the weather first"
  2. Action   — Calls the `get_weather` tool
  3. Observation — Receives the tool result
  4. Thought  — "Now I should get news headlines"
  5. Action   — Calls `get_news_headlines`
  ... (repeats until it has all it needs)
  6. Final Answer — Returns collected context as a structured dict

You can watch this reasoning in the logs (it's educational to read!).

TUTORIAL: create_react_agent vs AgentExecutor
----------------------------------------------
LangGraph provides `create_react_agent` which builds a proper stateful
LangGraph graph under the hood. It's more powerful than the older
AgentExecutor class because:
  - It handles interrupts and checkpointing
  - State is an explicit TypedDict, not a magic internal dict
  - You can inspect every step of the reasoning loop

For this use case (simple tool use, no user interaction), the difference is
minimal — but we use create_react_agent to teach modern LangGraph patterns.
"""

import json
import logging
from datetime import date

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from content_pipeline.config import cfg
from content_pipeline.tools.news_tool import get_news_headlines, get_ai_tech_trends
from content_pipeline.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)

# ─── Tools the research agent has access to ───────────────────────────────────
# TUTORIAL: This list defines the agent's "toolbox". The LLM reads each tool's
# docstring to decide which to use and in what order. Order doesn't enforce
# execution sequence — the model reasons about that itself.
RESEARCH_TOOLS = [
    get_weather,
    get_news_headlines,
    get_ai_tech_trends,
]


def run_research_agent(target_date: date | None = None) -> dict:
    """
    Run the research agent to gather context for today's newspaper.

    The agent will:
      1. Fetch weather for Dublin (or configured location)
      2. Fetch top Irish/tech news headlines
      3. Fetch current AI/tech trends
      4. Return everything as a structured context dict

    Args:
        target_date: The date to generate content for (defaults to today).

    Returns:
        A dict with keys: weather, headlines, ai_trends, date_str, agent_trace
    """
    today = target_date or date.today()
    date_str = today.strftime("%A, %-d %B %Y")  # e.g. "Monday, 3 March 2026"

    logger.info(f"[research] Starting research agent for {date_str}")

    # TUTORIAL: We use Claude as the research agent's "brain" even when the
    # user has selected a different provider for content generation. Why?
    # Because the research agent needs reliable tool use — Claude is
    # consistently excellent at structured tool calling. The content generation
    # chains (which show the comparison) use all three providers.
    if not cfg.providers.anthropic_api_key:
        logger.warning("[research] No Claude API key — using fallback context")
        return _fallback_context(date_str)

    research_llm = ChatAnthropic(
        model=cfg.providers.claude_model,
        api_key=cfg.providers.anthropic_api_key,
        temperature=0.0,   # Zero temperature for research: we want facts, not creativity.
        max_tokens=512,
        max_retries=3,
    )

    # TUTORIAL: create_react_agent returns a compiled LangGraph app.
    # It automatically manages the Thought → Action → Observation loop.
    agent = create_react_agent(
        model=research_llm,
        tools=RESEARCH_TOOLS,
    )

    # The task prompt tells the agent what to collect and why.
    task = f"""
You are the research assistant for The Craic Gazette, an Irish AI newspaper.
Today's date is {date_str}.

Please collect the following context for today's newspaper edition:
1. Current weather in {cfg.news.weather_location} using the get_weather tool
2. Top news headlines using get_news_headlines (topic: "Ireland AI tech news")
3. Latest AI trends using get_ai_tech_trends (focus: "LangChain LLM agentic AI 2025")

Once you have all three pieces of information, summarise them in plain text.
Do not make up information — only use what the tools return.
""".strip()

    # Capture each step of the agent's reasoning for the frontend trace viewer.
    agent_trace = []
    final_messages = []

    try:
        # TUTORIAL: agent.stream() yields each step as it happens.
        # We collect the full trace for display in the "Under the Hood" drawer.
        for chunk in agent.stream(
            {"messages": [("human", task)]},
            # stream_mode="values" yields the full state after each node.
            stream_mode="values",
        ):
            messages = chunk.get("messages", [])
            for msg in messages:
                role = getattr(msg, "type", type(msg).__name__)
                content = getattr(msg, "content", str(msg))
                # Avoid logging binary/base64 content
                content_preview = str(content)[:300] if content else ""
                agent_trace.append({"role": role, "content": content_preview})
            final_messages = messages

        # Extract structured data from tool call results stored in messages.
        context = _extract_context_from_messages(final_messages, date_str)
        context["agent_trace"] = agent_trace
        logger.info(f"[research] Research complete. Headlines: {len(context['headlines'])}")
        return context

    except Exception as exc:
        logger.error(f"[research] Agent failed: {exc}")
        return _fallback_context(date_str)


def _extract_context_from_messages(messages: list, date_str: str) -> dict:
    """
    Walk through agent messages and extract tool outputs into a clean dict.

    TUTORIAL: Agent Message Structure
    ------------------------------------
    After agent.stream() or agent.invoke(), messages is a list of:
      - HumanMessage  — the original task
      - AIMessage     — the model's reasoning steps + tool calls
      - ToolMessage   — each tool's response

    We find ToolMessages by name and parse their JSON content.
    """
    weather = {}
    headlines = []
    ai_trends = ""

    for msg in messages:
        # ToolMessage has a `name` attribute identifying which tool returned it.
        if hasattr(msg, "name") and msg.name and hasattr(msg, "content"):
            try:
                data = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": str(msg.content)}

            if msg.name == "get_weather":
                weather = data
            elif msg.name == "get_news_headlines":
                headlines = data.get("headlines", [])
            elif msg.name == "get_ai_tech_trends":
                ai_trends = data.get("trends_summary", "")

    return {
        "date_str": date_str,
        "weather": weather,
        "headlines": headlines,
        "ai_trends": ai_trends,
        "weather_location": cfg.news.weather_location,
    }


def _fallback_context(date_str: str) -> dict:
    """Return sensible fallback context when the research agent cannot run."""
    return {
        "date_str": date_str,
        "weather_location": cfg.news.weather_location,
        "weather": {
            "location": cfg.news.weather_location,
            "temp_c": 9,
            "conditions": "Overcast with a chance of existential drizzle",
            "humidity_pct": 80,
            "wind_kmh": 22,
        },
        "headlines": [
            "AI continues to reshape the Irish tech landscape",
            "Local developers embrace open-source LLM tooling",
            "Government announces new digital strategy",
        ],
        "ai_trends": (
            "LangChain and LangGraph continue to gain traction. "
            "Local LLMs via LM Studio are becoming mainstream for developers."
        ),
        "agent_trace": [{"role": "system", "content": "Fallback context — research agent skipped"}],
    }
