"""
content_pipeline/agents/orchestrator.py
=========================================
LangGraph StateGraph orchestrating the full newspaper generation pipeline.

TUTORIAL: LangGraph StateGraph
---------------------------------
LangGraph builds on LangChain to create stateful, multi-step "graph" workflows.
Unlike a simple LCEL chain (A | B | C), a StateGraph lets you:
  - Define explicit state (a TypedDict passed between nodes)
  - Add conditional edges (branch based on state values)
  - Handle retries, human-in-the-loop, and persistence
  - Visualise the graph with graph.get_graph().draw_mermaid()

The pipeline graph has four nodes connected linearly:

    START → [research] → [generate] → [compile] → [publish] → END

Each node is a Python function that:
  1. Receives the full current state as a TypedDict
  2. Does its work (calls tools, chains, S3, etc.)
  3. Returns a dict of state fields to UPDATE (not replace the whole state)

TUTORIAL: Why not just call functions sequentially?
StateGraph gives you:
  - A clear, visualisable execution graph (great for tutorials!)
  - Easy checkpointing — if publish fails, you can resume from compile's output
  - Structured error handling per node
  - A mental model that maps directly to agentic reasoning patterns

This is the tutorial site's centrepiece — readers can trace exactly what happened
at each pipeline stage by reading the logs or the "Under the Hood" UI drawer.
"""

import json
import logging
from datetime import date
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from content_pipeline.config import cfg
from content_pipeline.agents.research_agent import run_research_agent
from content_pipeline.chains.newspaper_chain import run_parallel_generation
from content_pipeline.providers.claude import get_claude_llm
from content_pipeline.providers.gemini import get_gemini_llm
from content_pipeline.providers.lmstudio import get_lmstudio_llm
from content_pipeline.publisher.s3_publisher import publish_to_s3

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline State
# ─────────────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    """
    The state object passed between every node in the pipeline graph.

    TUTORIAL: TypedDict as State Contract
    ----------------------------------------
    Using TypedDict makes the state explicit and self-documenting. Every field
    that can appear in state is declared here. Nodes only READ fields they need
    and only RETURN fields they update — LangGraph merges the returned dict
    into the current state rather than replacing it entirely.

    `total=False` means all fields are optional at the TypedDict level —
    LangGraph handles missing fields gracefully by treating them as None.
    """
    # Set at pipeline start
    target_date: date
    date_iso: str               # "2026-03-03" — used for S3 key paths

    # Populated by the [research] node
    context: dict               # weather, headlines, ai_trends, date_str

    # Populated by the [generate] node
    raw_articles: dict          # article_id → {claude: {...}, gemini: {...}, local: {...}}

    # Populated by the [compile] node
    paper_content: dict         # Final JSON ready for S3 upload

    # Set by the [publish] node
    published: bool
    s3_key: str
    errors: list[str]           # Accumulated non-fatal errors


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Nodes
# ─────────────────────────────────────────────────────────────────────────────

def node_research(state: PipelineState) -> dict:
    """
    NODE 1: Research Agent
    -----------------------
    Runs the ReAct research agent to gather news and weather context.

    TUTORIAL: This node demonstrates the "tools + agents" layer of LangChain.
    The research agent autonomously decides which tools to call and in what order.
    Compare this to the [generate] node, which uses deterministic LCEL chains.
    Both approaches have their place in a production pipeline.
    """
    logger.info("[node:research] Starting research phase")
    target_date = state.get("target_date", date.today())

    context = run_research_agent(target_date)

    logger.info(
        f"[node:research] Complete — "
        f"{len(context.get('headlines', []))} headlines, "
        f"weather: {context.get('weather', {}).get('conditions', 'unknown')}"
    )
    return {"context": context}


def node_generate(state: PipelineState) -> dict:
    """
    NODE 2: Multi-Provider Parallel Content Generation
    ---------------------------------------------------
    Runs all 5 article templates against all 3 LLM providers simultaneously
    using RunnableParallel. This is the core of the comparator site.

    TUTORIAL: Provider Initialisation
    ------------------------------------
    Notice that each LLM is initialised fresh in this node rather than
    at module level. This ensures credentials are read from the current
    environment (important for CI where secrets are injected at runtime,
    not at import time).

    TUTORIAL: Graceful Local LLM Degradation
    ------------------------------------------
    If LM Studio isn't running (SKIP_LOCAL_LLM=true or connection refused),
    the local provider is skipped and a placeholder is written to state.
    The site still works — it just shows "Local LLM unavailable" in that column.
    """
    logger.info("[node:generate] Starting multi-provider generation")

    context = state["context"]
    errors = list(state.get("errors", []))

    # Build the input dict passed to every chain.
    # TUTORIAL: This is the "context injection" step — we format the raw tool
    # outputs into clean strings that fit naturally into our prompt templates.
    chain_inputs = {
        "date": context["date_str"],
        "weather": json.dumps(context["weather"], indent=2),
        "weather_location": context.get("weather_location", cfg.news.weather_location),
        "headlines": json.dumps(context["headlines"], indent=2),
        "ai_trends": context.get("ai_trends", ""),
    }

    # Initialise providers — failures become placeholder results, not crashes.
    claude_llm = _safe_init(get_claude_llm, "claude", errors)
    gemini_llm = _safe_init(get_gemini_llm, "gemini", errors)

    local_llm = None
    if not cfg.skip_local_llm:
        local_llm = _safe_init(get_lmstudio_llm, "local", errors)

    if claude_llm is None and gemini_llm is None:
        logger.error("[node:generate] No cloud providers available — aborting")
        return {"errors": errors, "raw_articles": {}}

    raw_articles = run_parallel_generation(
        inputs=chain_inputs,
        claude_llm=claude_llm,
        gemini_llm=gemini_llm,
        local_llm=local_llm,
    )

    logger.info(f"[node:generate] Generated {len(raw_articles)} articles")
    return {"raw_articles": raw_articles, "errors": errors}


def node_compile(state: PipelineState) -> dict:
    """
    NODE 3: Compile Output JSON
    ----------------------------
    Assembles the final paper_content.json structure from research context
    and raw article outputs.

    TUTORIAL: Schema Design for the Frontend
    ------------------------------------------
    The output JSON must be stable — the frontend JavaScript depends on it.
    We version the schema (`pipeline_version`) so the frontend can handle
    old and new content files gracefully when the schema evolves.
    """
    logger.info("[node:compile] Assembling paper_content.json")

    target_date = state.get("target_date", date.today())
    context = state.get("context", {})
    raw_articles = state.get("raw_articles", {})

    # TUTORIAL: We embed the resolved prompt text in the output so the frontend
    # "Under the Hood" drawer can show exactly what was sent to each model.
    # This is the prompt transparency feature that makes the site educational.
    articles_out = {}
    for article_id, provider_outputs in raw_articles.items():
        articles_out[article_id] = {
            "outputs": provider_outputs,
            # The langchain_node label helps readers trace back to the source code.
            "langchain_node": "generate/RunnableParallel",
        }

    paper_content = {
        "date": target_date.isoformat(),
        "generated_at": _utcnow_iso(),
        "pipeline_version": cfg.pipeline_version,
        "context": {
            "news_headlines": context.get("headlines", []),
            "weather": context.get("weather", {}),
            "ai_trends": context.get("ai_trends", ""),
            # Include the agent's reasoning trace for the "Under the Hood" UI.
            "research_trace": context.get("agent_trace", []),
        },
        "articles": articles_out,
    }

    logger.info("[node:compile] paper_content.json assembled")
    return {"paper_content": paper_content}


def node_publish(state: PipelineState) -> dict:
    """
    NODE 4: Publish to S3
    ----------------------
    Uploads paper_content.json to the S3 bucket at the date-based key path.

    In dry_run mode (DRY_RUN=true), the file is written to /tmp instead
    so you can inspect it without uploading to S3.

    TUTORIAL: Separation of Concerns
    -----------------------------------
    Publishing is its own node rather than part of compile because:
      - It's the only step with external side effects (network I/O, cost)
      - In dry_run mode we can skip just this node
      - If publishing fails, we know exactly which step failed from the logs
    """
    logger.info("[node:publish] Publishing content")

    paper_content = state.get("paper_content", {})
    date_iso = state.get("date_iso", date.today().isoformat())
    errors = list(state.get("errors", []))

    if cfg.dry_run:
        # Write to a local tmp file so you can inspect the output.
        tmp_path = f"/tmp/paper_content_{date_iso}.json"
        with open(tmp_path, "w") as f:
            json.dump(paper_content, f, indent=2)
        logger.info(f"[node:publish] DRY RUN — written to {tmp_path}")
        return {"published": False, "s3_key": tmp_path, "errors": errors}

    try:
        s3_key = publish_to_s3(paper_content, date_iso)
        logger.info(f"[node:publish] Published to s3://{cfg.aws.s3_bucket}/{s3_key}")
        return {"published": True, "s3_key": s3_key, "errors": errors}
    except Exception as exc:
        logger.error(f"[node:publish] S3 upload failed: {exc}")
        errors.append(f"publish:{exc}")
        return {"published": False, "s3_key": "", "errors": errors}


# ─────────────────────────────────────────────────────────────────────────────
# Graph Assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_pipeline() -> "CompiledStateGraph":
    """
    Assemble and compile the LangGraph StateGraph.

    TUTORIAL: Graph Structure
    --------------------------
    Nodes are added with .add_node(name, function).
    Edges define the execution order with .add_edge(from, to).
    compile() validates the graph and returns a runnable object.

    To visualise this graph as a Mermaid diagram (great for docs!):
        graph = build_pipeline()
        print(graph.get_graph().draw_mermaid())

    The output looks like:
        graph TD
            __start__ --> research
            research --> generate
            generate --> compile
            compile --> publish
            publish --> __end__
    """
    # TUTORIAL: StateGraph(StateType) tells LangGraph which TypedDict
    # defines the shape of the state flowing between nodes.
    builder = StateGraph(PipelineState)

    builder.add_node("research", node_research)
    builder.add_node("generate", node_generate)
    builder.add_node("compile",  node_compile)
    builder.add_node("publish",  node_publish)

    # Linear flow: research → generate → compile → publish
    builder.add_edge(START,      "research")
    builder.add_edge("research", "generate")
    builder.add_edge("generate", "compile")
    builder.add_edge("compile",  "publish")
    builder.add_edge("publish",  END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(target_date: date | None = None) -> PipelineState:
    """
    Run the full newspaper generation pipeline for the given date.

    Args:
        target_date: Date to generate content for (defaults to today).

    Returns:
        Final pipeline state dict. Check state["published"] for success.
    """
    today = target_date or date.today()

    initial_state: PipelineState = {
        "target_date": today,
        "date_iso": today.isoformat(),
        "errors": [],
    }

    logger.info(f"[orchestrator] Pipeline starting for {today.isoformat()}")
    graph = build_pipeline()

    final_state = graph.invoke(initial_state)

    if final_state.get("published"):
        logger.info(f"[orchestrator] SUCCESS — published to {final_state['s3_key']}")
    else:
        logger.warning(
            f"[orchestrator] INCOMPLETE — errors: {final_state.get('errors', [])}"
        )

    return final_state


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_init(factory, label: str, errors: list) -> object | None:
    """Try to initialise an LLM provider; return None and log on failure."""
    try:
        return factory()
    except Exception as exc:
        logger.warning(f"[orchestrator] Provider '{label}' unavailable: {exc}")
        errors.append(f"provider_init:{label}:{exc}")
        return None


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
