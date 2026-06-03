"""
content_pipeline/agent/trace.py
===============================
Capture the deep agent's work as a flat, JSON-serialisable event list.

This is the teaching payload. Each run records its plan (todos), every subagent
delegation, every tool call, and any local→frontier fallback. The list is stored
at ``paper_content.context.agent_trace`` and the frontend's "Under the Hood"
drawer renders it so readers learn deepagents by watching the Editor-in-Chief
build the paper.

Deliberately plain — no LangSmith. This *is* our OSS observability story.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceRecorder:
    """Accumulates ordered, serialisable trace events for one edition run."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def _add(self, kind: str, name: str, detail: Any) -> None:
        self.events.append({"kind": kind, "name": name, "detail": detail})

    # ── Event types (one method each, so call sites read clearly) ─────────────
    def plan(self, todos: list[str]) -> None:
        """The Editor-in-Chief's plan (write_todos)."""
        self._add("plan", "write_todos", {"todos": list(todos)})

    def delegate(self, subagent: str, task: str) -> None:
        """A delegation to a subagent (the deepagents `task` tool)."""
        self._add("subagent", subagent, {"task": task})

    def tool_call(self, name: str, detail: str = "", result: str = "") -> None:
        """A tool invocation (web_search, validate_link, generate_image…), with an
        optional short snippet of what the tool returned."""
        payload: dict[str, Any] = {"info": detail}
        if result:
            payload["result"] = result
        self._add("tool", name, payload)

    def fallback(self, scope: str, *, local: str, to: str, reason: str) -> None:
        """A local→frontier fallback (honest model attribution for the UI note)."""
        self._add("fallback", scope, {"local": local, "to": to, "reason": reason})

    def model_route(self, scope: str, model: str) -> None:
        """Which fleet model served a scope. LiteLLM routes by name — the teaching point."""
        self._add("model", scope, {"model": model})

    def structured_output(self, name: str, detail: str = "") -> None:
        """A plain-chat→JSON call the harness made (the writer's structured outputs)."""
        self._add("structured", name, {"info": detail})

    def vfs(self, op: str, path: str) -> None:
        """A deep-agent virtual-filesystem read/write (research candidates live here)."""
        self._add("vfs", op, {"path": path})

    def note(self, name: str, detail: str = "") -> None:
        """A free-form milestone (e.g. 'curated 5 of 37 candidates')."""
        self._add("note", name, {"info": detail})

    def as_list(self) -> list[dict[str, Any]]:
        """Return the events for embedding in paper_content.context.agent_trace."""
        return list(self.events)


def _tool_calls_of(message: Any) -> list[dict[str, Any]]:
    """Pull the tool_calls list off a LangChain message or a plain dict."""
    if isinstance(message, dict):
        return message.get("tool_calls") or []
    return getattr(message, "tool_calls", None) or []


def _tool_results(messages: list[Any]) -> dict[str, str]:
    """Map each ``tool_call_id`` → a short snippet of its ToolMessage result content.

    Lets the visualiser show not just *that* a tool was called but a glimpse of what
    it returned (the first search hits, the fetched gist) — the "real-time detail".
    """
    out: dict[str, str] = {}
    for message in messages:
        if isinstance(message, dict):
            tcid = message.get("tool_call_id")
            content = message.get("content")
        else:
            tcid = getattr(message, "tool_call_id", None)
            content = getattr(message, "content", None)
        if tcid:
            out[str(tcid)] = " ".join(str(content).split())[:200]
    return out


def extract_trace(messages: list[Any]) -> list[dict[str, Any]]:
    """Build a trace event list from a deep-agent run's messages.

    Walks the message history and turns the agent's actual tool calls into the
    visualiser payload: ``write_todos`` → a plan event, ``task`` → a subagent
    delegation, everything else → a tool event (with a snippet of the tool's
    result, matched by tool_call_id). This is what populates
    ``paper_content.context.agent_trace`` so "Under the Hood" shows the real run.
    """
    rec = TraceRecorder()
    results = _tool_results(messages)
    for message in messages:
        for call in _tool_calls_of(message):
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            if name == "write_todos":
                todos = args.get("todos") or []
                rec.plan([t.get("content", t) if isinstance(t, dict) else t for t in todos])
            elif name == "task":
                sub = args.get("subagent_type") or args.get("name") or "subagent"
                rec.delegate(sub, str(args.get("description", ""))[:200])
            else:
                # Keep the detail short — a glimpse of the args, not the payload.
                detail = "; ".join(f"{k}={v}" for k, v in args.items())[:200]
                rec.tool_call(name, detail, result=results.get(str(call.get("id")), ""))
    return rec.as_list()
