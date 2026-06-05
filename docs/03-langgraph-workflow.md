# 03 — The Deep Agent, the Harness, and Human-in-the-Loop

## From a hand-wired StateGraph to a deep agent

v2 wired an explicit LangGraph `StateGraph` (`research → generate → compile → publish`).
v3 replaces the *research* half with a **deep agent** — `deepagents.create_deep_agent` —
which is itself a LangGraph graph, but a far more capable one: it ships a planning tool
(`write_todos`), a virtual filesystem, and **subagent delegation** (`task`) out of the box.
The deterministic *write → images → compile → publish* half is a plain Python harness
(`run_edition`) wrapped around it.

```
            ┌──────────────────────────────────────────────┐
  brief ───▶│  Editor-in-Chief  (create_deep_agent)         │
            │   write_todos → task(fun-news-researcher)      │
            │              → task(ai-landscape-researcher)   │
            │   tools: web_search · fetch_page · validate_link│
            │   virtual FS: research/{ai,fun}_candidates.json │
            └──────────────────────────────────────────────┘
                         │  result.files
                         ▼
            run_edition harness (plain Python, deterministic):
              curate → HOLD-or-write → snap URLs → images → compile → publish-draft
```

---

## Assembling the deep agent (three lines)

```python
# content_pipeline/agent/editor_in_chief.py
from deepagents import create_deep_agent
from content_pipeline.agent.subagents import EDITOR_IN_CHIEF_PROMPT, SUBAGENTS

def build_editor_in_chief(*, model=None, checkpointer=None):
    return create_deep_agent(
        model=model or build_brain(),        # a tool-calling LiteLLM route (Qwen3.6)
        system_prompt=EDITOR_IN_CHIEF_PROMPT, # "research only; never fabricate"
        subagents=SUBAGENTS,                  # fun-news / ai-landscape / link-validator
        checkpointer=checkpointer,            # pass a durable saver in production
    )
```

`create_deep_agent` returns a compiled LangGraph you invoke with messages + a `thread_id`:

```python
agent = build_editor_in_chief(checkpointer=InMemorySaver())
result = agent.invoke(
    {"messages": [{"role": "user", "content": brief}]},
    config={"configurable": {"thread_id": date_iso}, "recursion_limit": 200},
)
files = result.get("files", {})   # the agent's virtual FS — research candidates live here
```

The agent **plans, delegates, and writes candidate JSON** to its virtual filesystem, then
stops. It deliberately does **not** write the articles (see below).

---

## Why the harness writes the articles (not the agent)

The single hard-won lesson of v3: the deep agent reliably does **research**, but it does
**not** reliably (a) complete one giant final write, or (b) wire tool outputs into the
right fields — the local vLLM tool-call parser mangled the big `write_file`, and the model
invented stock-image URLs. So `run_edition` enforces the rest deterministically:

```python
# content_pipeline/agent/editor_in_chief.py  (run_edition, simplified)
result = agent.invoke({"messages": [{"role": "user", "content": brief}]}, config=config)
files  = result.get("files", {})

ai_candidates  = _read_candidates(files, "/research/ai_candidates.json")
fun_candidates = _read_candidates(files, "/research/fun_candidates.json")

# merge curated feeds, drop grim/recent/dupe/UNREACHABLE — and HOLD if a desk is too thin
ai_valid,  _ = _validate_ai_candidates(ai_candidates + harvested_ai, fetch=fetch, exclude_keys=recent)
fun_picks    = _curate_fun(fun_candidates or harvested_fun, fetch=fetch, exclude_keys=recent)
if len(ai_valid) < cfg.min_ai_sources or len(fun_picks) < cfg.min_fun_sources:
    raise EditionHeld([...])                      # never print thin/fabricated content

ai  = write_ai_section(ai_valid, ...)             # small structured LCEL calls (doc 02)
ai  = _snap_ai_sources(ai, ai_valid)              # force every URL onto a validated candidate
fun = _write_fun(fun_picks, date_iso, credits)    # Graham's voice, crediting the creator
_generate_images(ai, fun, date_iso)               # in the harness, not by the agent
paper = build_paper(date_iso, generated_at, ai=ai, fun=fun, context={"agent_trace": trace, ...})
```

> **TUTORIAL takeaway:** let the agent do judgment (what's newsworthy, is this on-brand);
> do the mechanical, must-be-exact work (counts, dedupe, link fidelity, images, schema) in
> code. It's cheaper, testable, and fabrication-resistant.

---

## Human-in-the-loop, the OSS way (`interrupt()` + a checkpointer)

No edition publishes itself. LangGraph's native HITL is a node that calls `interrupt()`:
the graph **pauses**, the checkpointer persists state, and a human resumes with
`Command(resume=…)`. No LangSmith, no hosted platform.

```python
# content_pipeline/agent/hitl.py  (simplified)
def request_approval(state):
    decision = interrupt({"action": "approve_edition", "date": state["paper"]["date"],
                          "summary": _summarise(state["paper"])})   # pauses HERE
    return {"decision": str(decision)}

def publish(state):
    if state.get("decision") == "approve":
        publish_fn(state["paper"]); return {"published": True}
    return {"published": False}

graph = StateGraph(ApprovalState)
graph.add_node("request_approval", request_approval)
graph.add_node("publish", publish)
graph.add_edge(START, "request_approval"); graph.add_edge("request_approval", "publish")
graph.add_edge("publish", END)
app = graph.compile(checkpointer=checkpointer or InMemorySaver())   # SqliteSaver in prod
```

A durable `SqliteSaver` means a paused, awaiting-approval edition survives a restart until
someone approves it. The graph doesn't care *who* resumes it.

### In production: an in-pipeline rubric judge + a decoupled publish gate

The live system doesn't keep a process paused for hours, and it no longer needs a separate
fleet of reviewer agents. Instead the **judgement runs in-pipeline**: as the last build
step, a LangChain `deepagents` **`RubricMiddleware`** grades the finished edition against an
explicit publish rubric (harmless / on-brand / attributed) on a local model
(`qwen3.6-35b` — interim, currently the writer's model; an independent judge is in progress),
writing the result to `verdict-rubric.json`. A
separate, idempotent **gate** (`cli gate`) then publishes live only on the **rubric
`APPROVE` + host structural validation + a live link-check**. Same human-in-the-loop
principle (a real approval is required before going live, and Graham can still override),
but a single local model replaces the old two-VM (openclaw + hermes) consensus — fewer
moving parts, still retriable and observable. See
[05-tools-and-agents.md](05-tools-and-agents.md) and
`content_pipeline/agent/rubric_review.py`.

---

## Observability without LangSmith: the trace

Every run records a flat, JSON-serialisable event list — the plan, each subagent
delegation, every tool call (with a snippet of what it returned), each model route, and
any local→frontier fallback. It's stored at `paper_content.context.agent_trace`, and the
website's **"Under the Hood"** drawer renders it so readers learn deepagents by watching
the Editor-in-Chief actually build the paper.

```python
# content_pipeline/agent/trace.py
rec = TraceRecorder()
rec.plan(["research fun news", "research AI landscape"])
rec.delegate("ai-landscape-researcher", "rank the day's top 13 AI stories")
rec.tool_call("web_search", "q=OpenAI", result="OpenAI ships … https://…")
rec.model_route("write", "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit")
# ...plus extract_trace(messages) turns a real run's tool calls into the same shape.
agent_trace = extract_trace(result["messages"]) + rec.as_list()
```

This is the project's whole observability story — deliberately plain, fully open source.

---

## Where to Find This in the Craic Gazette

| Concept | File |
|---------|------|
| Assemble the deep agent | `content_pipeline/agent/editor_in_chief.py` (`build_editor_in_chief`) |
| The research→write harness | `content_pipeline/agent/editor_in_chief.py` (`run_edition`) |
| HOLD on thin/degraded sources | `content_pipeline/agent/editor_in_chief.py` (`EditionHeld`, `_validate_ai_candidates`) |
| OSS human-in-the-loop graph | `content_pipeline/agent/hitl.py` |
| In-pipeline rubric judge + publish gate | `content_pipeline/agent/rubric_review.py` + `review.py` + `cli.py` (`gate`) |
| Trace for "Under the Hood" | `content_pipeline/agent/trace.py` |

---

## Why a deep agent over a hand-wired graph?

| Aspect | Hand-wired StateGraph (v2) | Deep agent + harness (v3) |
|--------|----------------------------|---------------------------|
| Research | Fixed nodes, fixed order | Agent plans + delegates; adapts per day |
| Context hygiene | One growing context | Subagents each get their own context window |
| Reliability of output | Trusted the model end-to-end | Agent researches; **harness** writes deterministically |
| Fabrication risk | Possible (model filled gaps) | HOLD below the integrity floor; URLs snapped to real sources |
| Observability | Mermaid of the static graph | A live per-run trace of the *actual* plan/tools/models |
