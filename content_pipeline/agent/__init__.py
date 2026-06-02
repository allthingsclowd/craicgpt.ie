"""The LangChain Deep-Agents content engine.

- ``tools``: the @tool wrappers the subagents call (web search, fetch, link
  validation, persona assignment, image generation).
- ``subagents``: the fun-news / AI-landscape / link-validator / editor specs.
- ``editor_in_chief``: the create_deep_agent assembly.
- ``hitl``: interrupt()-based human approval + checkpointer.
- ``trace``: capture the agent's plan / subagent / tool events for the UI.
"""
