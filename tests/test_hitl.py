"""Tests for the LangGraph-native human-in-the-loop approval gate.

This is the OSS approval mechanism (no LangSmith / no Platform): the graph runs
to a node that calls interrupt(), which pauses the run and persists state via a
checkpointer. A human resumes with approve/reject, and only an approval reaches
the publish node. In v1 the resume is a CLI/endpoint; phase 2 wraps the same
resume in the openclaw/hermes Telegram bot.
"""

from langgraph.types import Command

from content_pipeline.agent.hitl import build_approval_graph


def _run_to_interrupt(graph, paper):
    config = {"configurable": {"thread_id": paper["date"]}}
    result = graph.invoke({"paper": paper, "published": False}, config=config)
    return result, config


def test_run_pauses_at_interrupt_before_publishing():
    published = []
    graph = build_approval_graph(lambda paper: published.append(paper["date"]))
    result, _ = _run_to_interrupt(graph, {"date": "2026-06-02"})
    # The run is interrupted (awaiting approval) and has NOT published.
    assert "__interrupt__" in result
    assert published == []


def test_approve_resumes_and_publishes():
    published = []
    graph = build_approval_graph(lambda paper: published.append(paper["date"]))
    _, config = _run_to_interrupt(graph, {"date": "2026-06-02"})
    final = graph.invoke(Command(resume="approve"), config=config)
    assert published == ["2026-06-02"]
    assert final["published"] is True


def test_reject_resumes_without_publishing():
    published = []
    graph = build_approval_graph(lambda paper: published.append(paper["date"]))
    _, config = _run_to_interrupt(graph, {"date": "2026-06-02"})
    final = graph.invoke(Command(resume="reject"), config=config)
    assert published == []
    assert final["published"] is False
