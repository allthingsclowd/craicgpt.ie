"""
content_pipeline/agent/hitl.py
==============================
LangGraph-native human-in-the-loop approval gate (open source).

TUTORIAL: interrupt() + a checkpointer = pause-for-human
--------------------------------------------------------
A node calls ``interrupt(payload)``. LangGraph stops the run, persists state via
the checkpointer, and surfaces the payload to the caller. A human resumes with
``Command(resume=<decision>)`` and the graph continues from exactly where it
paused — only an "approve" reaches the publish node. No LangSmith, no hosted
platform: this is the OSS primitive.

In v1 the resume is delivered by a CLI command / tiny endpoint. In phase 2 the
openclaw/hermes Telegram bot calls the same resume so Graham approves from his
phone. The graph below doesn't care who resumes it — that's the point.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class ApprovalState(TypedDict, total=False):
    """State threaded through the approval graph."""

    paper: dict[str, Any]
    decision: str
    published: bool


def build_approval_graph(
    publish_fn: Callable[[dict[str, Any]], Any],
    *,
    checkpointer: Any | None = None,
):
    """Build a compiled graph: request approval → (on approve) publish.

    Args:
        publish_fn: Called with the paper dict ONLY when the human approves.
            In production this is the publish-live step (S3 + CloudFront).
        checkpointer: A LangGraph checkpointer. Defaults to ``InMemorySaver``;
            production uses a durable SqliteSaver so a paused edition survives a
            restart until Graham approves it.

    Returns:
        A compiled ``StateGraph``. Invoke it with ``{"paper": …}`` and a
        ``thread_id`` config; it pauses at the approval interrupt. Resume with
        ``Command(resume="approve")`` or ``Command(resume="reject")``.
    """

    def request_approval(state: ApprovalState) -> ApprovalState:
        # Pauses here. The payload is what an approver (CLI/Telegram) sees.
        paper = state["paper"]
        decision = interrupt(
            {
                "action": "approve_edition",
                "date": paper.get("date"),
                "summary": _summarise(paper),
            }
        )
        return {"decision": str(decision)}

    def publish(state: ApprovalState) -> ApprovalState:
        if state.get("decision") == "approve":
            publish_fn(state["paper"])
            return {"published": True}
        return {"published": False}

    graph = StateGraph(ApprovalState)
    graph.add_node("request_approval", request_approval)
    graph.add_node("publish", publish)
    graph.add_edge(START, "request_approval")
    graph.add_edge("request_approval", "publish")
    graph.add_edge("publish", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _summarise(paper: dict[str, Any]) -> dict[str, Any]:
    """A compact preview of the edition for the approval prompt."""
    ai = paper.get("ai", {})
    headliner = (ai.get("headliner") or {}).get("title")
    return {
        "headliner": headliner,
        "ai_shorts": len(ai.get("shorts", [])),
        "fun_stories": len(paper.get("fun", [])),
    }
