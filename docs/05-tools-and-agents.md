# 05 — Tools and Agents

## What is a Tool?

A **tool** is a function that an AI agent can call to interact with the world.
LangChain's `@tool` decorator turns any Python function into a tool the agent can use.

The function's **docstring** is the tool's description — it's what the LLM reads
when deciding whether and how to call the tool. Write it as if explaining to a
colleague what the function does and what it returns.

```python
from langchain_core.tools import tool

@tool
def get_weather(location: str = "Dublin") -> str:
    """
    Fetch current weather for the specified location.
    Returns a JSON string with temperature, conditions, and humidity.
    Use this to add weather context to article prompts.
    """
    # ... implementation ...
```

Key rules for tool docstrings:
- Describe WHAT it returns, not HOW it works internally
- Mention the input type and any defaults
- Keep it under 2 sentences — the LLM reads this at inference time
- Include what the output looks like (JSON? string? list?)

---

## The Craic Gazette's Research Tools

### `get_news_headlines(topic: str)`

```python
# content_pipeline/tools/news_tool.py

@tool
def get_news_headlines(topic: str = "") -> str:
    """
    Fetch today's top news headlines relevant to Ireland, AI, and technology.
    Returns a JSON string with a list of headline strings.
    Pass an optional topic string to focus the search (e.g. 'AI Ireland').
    """
```

Uses `DuckDuckGoSearchRun` from `langchain-community`.
No API key required — good for tutorials and demos.

### `get_ai_tech_trends(focus: str)`

```python
@tool
def get_ai_tech_trends(focus: str = "LangChain LLM agents 2025") -> str:
    """
    Search for the latest AI and tech trends to inject into article context.
    Returns a summary string describing current developments in AI technology.
    """
```

### `get_weather(location: str)`

```python
# content_pipeline/tools/weather_tool.py

@tool
def get_weather(location: str = "") -> str:
    """
    Fetch the current weather conditions for the specified location (default: Dublin).
    Returns a JSON string with temperature, conditions, humidity, and wind speed.
    Use this to set the mood and atmosphere in article opening paragraphs.
    """
```

Uses the free `wttr.in` API — no key needed.

---

## What is a ReAct Agent?

**ReAct** (Reason + Act) is the most widely used agent pattern in LangChain.

The agent loops through:

```
Thought:  "I need to know the weather before I can set the article's mood."
Action:   Call get_weather("Dublin")
Observation: {"temp_c": 9, "conditions": "Drizzly", ...}

Thought:  "Good. Now I need today's news headlines."
Action:   Call get_news_headlines("Ireland AI tech news")
Observation: {"headlines": ["AI reshapes Irish tech...", ...]}

Thought:  "I have all the context I need."
Final Answer: {weather: ..., headlines: [...], ai_trends: "..."}
```

The agent keeps looping until it has everything it needs, then returns.

---

## `create_react_agent` (LangGraph)

LangGraph provides `create_react_agent` which builds a proper stateful graph
under the hood, handling the Thought → Action → Observation loop automatically.

```python
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

# The "brain" LLM that decides which tools to call
research_llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0.0,   # Zero temp for research — we want facts, not creativity
    max_tokens=512,
)

# Pass the LLM + list of tools
agent = create_react_agent(
    model=research_llm,
    tools=[get_weather, get_news_headlines, get_ai_tech_trends],
)

# Run the agent with a natural-language task description
result = agent.invoke({
    "messages": [("human", "Get today's weather in Dublin and top Irish tech news.")]
})
```

---

## Why Claude as the Research Brain?

The Craic Gazette uses Claude as the research agent's "brain" even when the
user has selected Gemini or a local model for content generation. Why?

1. **Tool calling reliability:** Claude consistently calls tools in the right
   format on the first attempt. Smaller local models sometimes hallucinate tool calls
   or return malformed JSON.

2. **Separation of concerns:** The research phase is about **facts** (weather,
   headlines). The content generation phase is about **creativity** (writing style,
   personality). Different task types → different temperature and model needs.

3. **Cost:** The research agent uses `max_tokens=512` and `temperature=0.0`.
   It's cheap even with a premium model.

---

## Tool Failure Handling

Tools in the Craic Gazette always return a result — they never raise exceptions.
If the underlying API fails, they return a fallback:

```python
@tool
def get_weather(location: str = "") -> str:
    """..."""
    try:
        # ... real API call ...
        return json.dumps(weather_data)
    except Exception:
        # Return a plausible fallback — the agent can still continue
        return json.dumps({
            "location": location,
            "temp_c": 9,
            "conditions": "Overcast with a chance of existential drizzle",
            "note": "Fallback data — API unreachable",
        })
```

**Why this approach?**
If a tool raises an exception, the agent gets confused and may loop.
Returning graceful fallbacks lets the agent continue and produce *something*
rather than crashing the whole pipeline because the weather API is flaky.

---

## Inspecting Agent Tool Calls

To see the agent's reasoning, stream the execution and inspect messages:

```python
for chunk in agent.stream(
    {"messages": [("human", task)]},
    stream_mode="values",
):
    for msg in chunk.get("messages", []):
        print(f"{type(msg).__name__}: {str(msg.content)[:100]}")
```

Output looks like:
```
HumanMessage: Get today's weather in Dublin...
AIMessage: [ToolUse(name='get_weather', input={'location': 'Dublin'})]
ToolMessage: {"temp_c": 9, "conditions": "Overcast", ...}
AIMessage: [ToolUse(name='get_news_headlines', input={'topic': 'Ireland AI'})]
ToolMessage: {"headlines": ["AI reshapes Irish tech...", ...]}
AIMessage: I now have all the context needed. Weather: 9°C overcast in Dublin...
```

The Craic Gazette captures this trace in `context["research_trace"]` and displays
it in the "Under the Hood" drawer on the website.

---

## Where to Find This in the Craic Gazette

| Concept                    | File                                               |
|----------------------------|----------------------------------------------------|
| `@tool` news tool          | `content_pipeline/tools/news_tool.py`              |
| `@tool` weather tool       | `content_pipeline/tools/weather_tool.py`           |
| ReAct agent setup          | `content_pipeline/agents/research_agent.py`        |
| Agent trace capture        | `content_pipeline/agents/research_agent.py:run_research_agent()` |
| Frontend trace display     | `frontend/static_assets/main.js:renderHoodContext()` |
