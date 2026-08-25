# 05 — Tools and (Deep) Agents

## What is a tool?

A **tool** is a function an agent can call to act on the world. LangChain's `@tool`
decorator turns a plain Python function into one: the function name becomes the tool name,
and the **docstring** is the description the model reads to decide *when* and *how* to call
it. Keep docstrings short and action-oriented.

```python
from langchain_core.tools import tool

@tool
def validate_link(url: str) -> bool:
    """Return True if a source URL resolves (HTTP 2xx).

    Always validate a source link before citing it — every published story must
    link to a real, reachable original.
    """
    return validate_source_link(url)
```

---

## The deterministic-vs-LLM split (the most important rule here)

Not everything should be a tool. The dividing line (`deciding-deterministic-vs-llm`):

- **Live judgment → a tool.** Searching, fetching a page, validating a link, generating an
  image — things that need the network or the model's discretion. These live in
  `content_pipeline/agent/tools.py`.
- **Mechanical work → the harness, not a tool.** Dedupe, grim/political filtering,
  continent diversity, recency exclusion, snapping URLs, counting to 13 — pure functions.
  These live in `content_pipeline/research/curation.py` and run over the candidates the
  agent collects. We don't pay a model to do arithmetic.

> **TUTORIAL takeaway:** the smallest reliable agent is one that only calls tools for
> things code genuinely can't do, and hands everything else to deterministic code.

### A worked example of drawing the line: the cartoon step

Each article carries a cartoon of a **visual gag** — a one-line joke about the story, not an
illustration of its headline (`generate/image_gag.py`). Inventing a joke is judgement, so it
is an LLM call. But look at how narrow that call is. The model is **not** asked to:

| Decision | Where it lives | Why |
|---|---|---|
| which art style | `image_styles.py`, a day-stable constant | the paper has ONE house style; a model would drift |
| what size / how many steps | the tier table (`HERO`/`STANDARD`/`THUMBNAIL`) | it is a cost decision measured in seconds, not taste |
| whether the story is about a motorcycle | the `_vertical` flag, derived from the source registry | a model asked to infer it draws a **car** — this shipped live on 2026-08-24 |
| what to keep out of frame | `NEGATIVE_PROMPT`, one constant | it is the same for every image |

So the model contributes exactly one thing: the idea. Everything around it stays reproducible,
and the failure mode is bounded — a failed gag falls back to the literal prompt and the edition
still gets its picture.

**The cost of getting this wrong is not theoretical.** When the gag step was first wired in, the
offline test suite began firing eighteen live LLM calls at the DGX per `run_edition` test,
because the default generator is a real one and nothing stubbed it. If you add an LLM call to a
deterministic path, stub it in the offline fixtures in the same commit.

---

## The Craic Gazette's tools

```python
# content_pipeline/agent/tools.py

@tool
def web_search(query: str) -> str:
    """Search the web for recent stories about a topic.

    Returns titles/snippets/URLs. On backend failure returns a line starting
    'SEARCH_FAILED:' — when you see that, do NOT invent stories or URLs; report it and stop.
    Uses the Serper.dev (Google SERP) API (keyed, built for automation) — not scraping.
    """

@tool
def fetch_page(url: str) -> str:
    """Fetch a page and return its readable text (~4500 chars) — read the article body,
    not just the headline, before citing it."""

@tool
def validate_link(url: str) -> bool:
    """True if a source URL resolves (HTTP 2xx). Validate before citing."""

@tool
def generate_cover_image(prompt: str) -> str:
    """Render an illustration; saves a PNG locally and returns {image_url, model} JSON.
    The harness uploads it and rewrites the URL to the CDN path at publish time (base64
    never enters the agent's context)."""
```

Two design decisions worth calling out:

- **`web_search` fails loudly, never silently.** v2's scraper got `429`-rate-limited from
  the datacenter IP and the agent *hallucinated* stories to fill the gap. Now `web_search`
  uses the keyed Serper.dev API and returns an explicit `SEARCH_FAILED:` sentinel; the prompts
  say "report it and stop", and the harness HOLDs the edition. (It also sends a real
  browser `User-Agent` so legitimate hosts don't 403 it.)
- **Images return a *path*, not base64.** Keeping image bytes out of the agent's context
  window is what lets a long run stay under the model's token budget. The harness actually
  generates the images deterministically anyway (the agent invented stock URLs), but the
  tool exists for the deepagents pattern and tests.

---

## Deep-agent delegation vs a flat ReAct loop

v2 used a single `create_react_agent` (one Thought→Action→Observation loop over news/weather
tools). v3 uses a **deep agent** that **delegates to subagents** via the `task` tool. Each
subagent is a `SubAgent` spec — a name, a description the main agent reads to decide *when*
to delegate, a focused system prompt, and a narrow tool set — and crucially each runs in
**its own context window**, so the Editor-in-Chief's context stays clean.

```python
# content_pipeline/agent/subagents.py
from deepagents import SubAgent

AI_LANDSCAPE_RESEARCHER: SubAgent = {
    "name": "ai-landscape-researcher",
    "description": "Review what changed in AI in the last 24h across US labs, China, "
                   "Europe + top AI YouTubers/bloggers. Use for the AI coverage.",
    "system_prompt": (
        "You are CraicGPT's AI-desk analyst… focus on the last 24 hours… every item needs "
        "a real, reachable source link (call validate_link)… If web_search returns "
        "'SEARCH_FAILED:', say so and STOP — NEVER invent stories or URLs… for each story "
        "call fetch_page and READ THE ACTUAL ARTICLE. Write ~15 candidates with "
        "{title, summary, source_url, why_it_matters, key_points, conclusion} to "
        "research/ai_candidates.json."
    ),
    "tools": [web_search, fetch_page, validate_link],
}

SUBAGENTS = [FUN_NEWS_RESEARCHER, AI_LANDSCAPE_RESEARCHER, LINK_VALIDATOR]
```

The Editor-in-Chief's own prompt tells it to **plan with `write_todos`, delegate, and then
STOP** — it does research only; the harness writes the articles (see
[03-langgraph-workflow.md](03-langgraph-workflow.md)). There is deliberately **no editor
subagent**: the one giant write got mangled by the local tool-call parser, so the harness
does it deterministically.

> The two researcher prompts are the canonical source for the `curating-positive-news` and
> `reviewing-ai-landscape` skills in the scripting-paddy-skills repo (kept in sync).

---

## The edition judge: an in-pipeline rubric

There's a second, separate use of an agent in the system — the **edition judge**. It is no
longer a fleet of reviewer VMs polling S3; it's a LangChain `deepagents`
**`RubricMiddleware`** grader that runs **in-pipeline**, as the last step of `run_edition`
(`content_pipeline/agent/rubric_review.py`, `grade_edition`):

- A tiny reviewer deep agent is handed the compiled edition; its grader sub-agent scores the
  transcript against an explicit `EDITION_RUBRIC` (harmless / no-defamation / every fun item
  attributed / the AI desk is substantive). The grader runs on an **independent** local model
  — `qwen3-coder-next` (Qwen3-Coder-Next 80B-A3B on the M3, a different family from the
  writer's Qwen3.8, so a genuine second opinion), with a cross-box fallback if the local judge errors. It writes `verdict-rubric.json`
  (decision + per-criterion reasons + the version id in the body).
- The deterministic **gate** (`cli gate`, `content_pipeline/agent/review.py`) publishes
  live only on the **rubric `APPROVE`** + host structural validation + a live link-check.
  `compute_consensus` requires an *explicit* APPROVE from every required agent (now the
  single `rubric`) — a missing/garbled verdict is a WAIT, never a silent pass.

This keeps the LLM's job to **judgment** ("is this harmless/on-brand?") and the gate's job
to **fact** ("is it structurally valid and are all links reachable?") — the same
deterministic-vs-LLM split, applied to publishing. (It replaces the earlier two-VM
openclaw + hermes consensus: one local in-pipeline judge instead of two networked agents.)

---

## Tool failure handling

Tools degrade gracefully but **honestly**. `web_search` returns `SEARCH_FAILED:` (not a
fake result); `fetch_page` returns an error string; `generate_cover_image` returns
`{image_url: null, error: …}` so one bad image can't crash the edition. The prompts and
harness are built so a degraded tool leads to a **HOLD**, never to fabricated filler.

---

## Inspecting an agent run

Stream the agent and watch its messages, or read the embedded trace after the fact:

```python
for chunk in agent.stream({"messages": [("human", brief)]}, stream_mode="values"):
    for m in chunk.get("messages", []):
        print(f"{type(m).__name__}: {str(m.content)[:100]}")
```

`extract_trace(result["messages"])` turns those real tool calls into the
`context.agent_trace` payload the website's "Under the Hood" drawer renders (doc 03).

---

## Where to Find This in the Craic Gazette

| Concept | File |
|---------|------|
| `@tool` definitions | `content_pipeline/agent/tools.py` |
| Subagent specs + Editor-in-Chief prompt | `content_pipeline/agent/subagents.py` |
| Deterministic curation (NOT tools) | `content_pipeline/research/curation.py` |
| In-pipeline rubric judge + consensus gate | `content_pipeline/agent/rubric_review.py` + `review.py` + `cli.py` (`gate`) |
| The publish rubric (criteria) | `content_pipeline/agent/rubric_review.py` (`EDITION_RUBRIC`) |
| Trace capture / display | `content_pipeline/agent/trace.py` · `frontend/static_assets/main.js` |

> **Next:** [06-narration-and-audio.md](06-narration-and-audio.md) extends this
> deterministic-vs-LLM split to **audio** — articles are read deterministically, while the
> dad↔son podcast banter is LLM-written and gated by the same `deepagents` rubric before it's voiced.
