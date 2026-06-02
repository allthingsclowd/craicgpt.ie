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

    def tool_call(self, name: str, detail: str = "") -> None:
        """A tool invocation (web_search, validate_link, generate_cover_image…)."""
        self._add("tool", name, {"info": detail})

    def fallback(self, scope: str, *, local: str, to: str, reason: str) -> None:
        """A local→frontier fallback (honest model attribution for the UI note)."""
        self._add("fallback", scope, {"local": local, "to": to, "reason": reason})

    def note(self, name: str, detail: str = "") -> None:
        """A free-form milestone (e.g. 'curated 5 of 37 candidates')."""
        self._add("note", name, {"info": detail})

    def as_list(self) -> list[dict[str, Any]]:
        """Return the events for embedding in paper_content.context.agent_trace."""
        return list(self.events)
