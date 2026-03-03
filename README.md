<p align="center">
  <img src="frontend/static_assets/images/CraicGPT_240h.png" alt="CraicGPT Logo" width="350"/>
  <img src="frontend/static_assets/images/GeekwiththePeak.png" alt="Geek with the Peak Logo" width="150"/>
</p>

# The Craic Gazette — AI Newspaper Comparator

> **A hands-on LangChain + LangGraph tutorial site.**
> The same prompts are sent simultaneously to Claude, Gemini, and a local LLM.
> The differences in their responses *are* the content.

Live site: **[craicgpt.ie](https://craicgpt.ie)**

---

## What is this?

The Craic Gazette is an Irish-flavoured satirical AI newspaper that runs entirely from a home machine — no cloud functions, no per-invocation costs. Every morning a LangGraph pipeline:

1. Runs a **ReAct research agent** to fetch live news and weather
2. Sends identical prompts to **Claude**, **Gemini**, and a **local LM Studio model** in parallel
3. Uploads a single JSON file to S3
4. A static frontend reads that JSON and lets you switch between — or compare — all three responses side-by-side

The codebase is written as an educational tutorial. Every file is heavily commented and explains *why* things are done the way they are, not just *what* they do.

---

## Why the move from Lambda?

The original site used AWS Lambda + Bedrock to generate content. That worked, but:

- Lambda cold starts + Bedrock API latency added up fast
- Each generation run cost real money in invocation and model fees
- Adding a local LLM to the comparison was impossible from a cloud function

The new architecture runs on a home Mac. The only AWS cost is S3 storage + CloudFront — a few cents per month. Local LLM inference is free. Cloud API costs (Claude, Gemini) are pay-per-use but modest for one newspaper per day.

---

## Architecture

```
Your Mac (runs daily at 08:00 via launchd)
│
└── run_daily.sh
      └── content_pipeline/main.py
            │
            ├── [Node 1: research]
            │     create_react_agent (Claude) + @tool functions
            │     ├── get_weather()      → wttr.in (no API key)
            │     ├── get_news_headlines() → DuckDuckGo (no API key)
            │     └── get_ai_tech_trends() → DuckDuckGo
            │
            ├── [Node 2: generate]   ← RunnableParallel (runs all 3 at once)
            │     ├── prompt | claude_llm  | parser   (Anthropic API)
            │     ├── prompt | gemini_llm  | parser   (Google AI API)
            │     └── prompt | lmstudio_llm | parser  (localhost:1234)
            │
            ├── [Node 3: compile]
            │     Assemble paper_content.json with all outputs + metadata
            │
            └── [Node 4: publish]
                  boto3 → s3://craicgpt-ie-production/content/YYYY/MM/DD/paper_content.json
                  CloudFront invalidation → site live within 30s
```

The frontend is static HTML/CSS/JS served from S3 via CloudFront. It fetches the JSON on load and renders whichever provider tab is active.

---

## LangChain Concepts Used

This project is intentionally structured as a tutorial. Here is what each LangChain building block does and where to find it:

### 1. `@tool` — defining agent tools (`content_pipeline/tools/`)

```python
from langchain_core.tools import tool

@tool
def get_weather(location: str = "") -> str:
    """Fetch current weather. The docstring is what the LLM reads to decide when to use this tool."""
    ...
```

The `@tool` decorator wraps a plain Python function into a LangChain `StructuredTool`. The LLM reads the docstring to understand what the tool does and the type hints to know what arguments to pass. No other configuration is needed.

### 2. `create_react_agent` — ReAct agent loop (`content_pipeline/agents/research_agent.py`)

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(model=claude_llm, tools=[get_weather, get_news_headlines])
for chunk in agent.stream({"messages": [("human", task)]}):
    ...
```

ReAct (Reason + Act) is the standard agentic pattern:
1. **Reason** — the LLM thinks about what it needs
2. **Act** — it calls a tool
3. **Observe** — it reads the tool result
4. Loop until it has everything it needs

`create_react_agent` builds a full LangGraph `StateGraph` under the hood. You get streaming, checkpointing, and step-by-step inspection for free.

### 3. LCEL `|` pipe operator — building chains (`content_pipeline/chains/newspaper_chain.py`)

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

chain = prompt | llm | StrOutputParser() | RunnableLambda(parse_json)
result = chain.invoke({"date": "...", "weather": "..."})
```

LangChain Expression Language (LCEL) uses the `|` operator like Unix pipes. Each component receives the output of the previous one. All components share the same `.invoke()` / `.stream()` / `.batch()` interface regardless of whether they're prompts, LLMs, or plain functions.

### 4. `RunnableParallel` — running all three LLMs at once (same file)

```python
from langchain_core.runnables import RunnableParallel

parallel = RunnableParallel(
    claude=claude_chain,
    gemini=gemini_chain,
    local=lmstudio_chain,
)
results = parallel.invoke(inputs)
# results == {"claude": {...}, "gemini": {...}, "local": {...}}
```

`RunnableParallel` runs all three chains with identical inputs using Python's `ThreadPoolExecutor`. Total time is roughly the slowest provider, not the sum of all three. The output dict maps directly to the JSON schema stored in S3.

### 5. `StateGraph` — orchestrating the full pipeline (`content_pipeline/agents/orchestrator.py`)

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(PipelineState)
builder.add_node("research", node_research)
builder.add_node("generate", node_generate)
builder.add_node("compile",  node_compile)
builder.add_node("publish",  node_publish)
builder.add_edge(START, "research")
# ... etc
graph = builder.compile()
graph.invoke(initial_state)
```

`StateGraph` gives the pipeline an explicit, visualisable structure. Each node receives the full state dict, does its work, and returns only the fields it updates. Run `./run_daily.sh --show-graph` to print a Mermaid diagram of the pipeline.

### 6. Multi-provider setup — same interface, different backends

All three providers use the same `BaseChatModel` interface:

| Provider | Class | Auth |
|---|---|---|
| Claude | `ChatAnthropic` | `ANTHROPIC_API_KEY` |
| Gemini | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY` |
| LM Studio | `ChatOpenAI(base_url=...)` | none (placeholder key) |

LM Studio uses LangChain's `ChatOpenAI` with `base_url` overridden to point at the local server. The same chain code works for all three — that's the point of LangChain's abstraction layer.

> **Note on thinking models:** `gemini-2.5-pro` and some local models (DeepSeek-R1, Qwen3) output internal reasoning before the actual response. The JSON parser in `newspaper_chain.py` handles this by scanning past thinking prose and `<think>` blocks to find valid JSON.

---

## Project Structure

```
craicgpt.ie/
│
├── run_daily.sh              ← Generate today's content and upload to S3
├── deploy_frontend.sh        ← Sync frontend HTML/CSS/JS to S3
├── .env                      ← Your credentials (gitignored)
├── .env.example              ← Template — copy to .env
│
├── content_pipeline/         ← The LangChain/LangGraph pipeline
│   ├── main.py               ← CLI entry point
│   ├── config.py             ← All config from env vars (singleton cfg)
│   ├── requirements.txt      ← Python dependencies
│   ├── agents/
│   │   ├── orchestrator.py   ← LangGraph StateGraph (4 nodes)
│   │   └── research_agent.py ← ReAct agent with news/weather tools
│   ├── chains/
│   │   └── newspaper_chain.py ← LCEL chains + RunnableParallel
│   ├── prompts/
│   │   └── templates.py      ← All ChatPromptTemplates (single source of truth)
│   ├── providers/
│   │   ├── claude.py         ← ChatAnthropic factory
│   │   ├── gemini.py         ← ChatGoogleGenerativeAI factory
│   │   └── lmstudio.py       ← ChatOpenAI(base_url=localhost) factory
│   ├── publisher/
│   │   └── s3_publisher.py   ← boto3 upload + CloudFront invalidation
│   └── tools/
│       ├── news_tool.py      ← @tool: DuckDuckGo news search
│       └── weather_tool.py   ← @tool: wttr.in weather fetch
│
├── frontend/                 ← Static site (S3 + CloudFront)
│   ├── index.html            ← Tabloid newspaper layout
│   └── static_assets/
│       ├── style.css         ← Beano/tabloid design (CSS variables, Grid)
│       └── main.js           ← Model comparator, JSON reader, trace drawer
│
├── docs/                     ← Tutorial markdown files
│   ├── 01-overview.md
│   ├── 02-lcel-and-chains.md
│   ├── 03-langgraph-workflow.md
│   ├── 04-multi-provider-setup.md
│   └── 05-tools-and-agents.md
│
└── terraform/
    └── frontend/             ← S3 bucket, CloudFront, ACM cert, Route53
```

---

## Setup

### Prerequisites

- Python 3.11+
- AWS CLI configured (`aws configure`)
- [LM Studio](https://lmstudio.ai) with a model loaded and the local server running (optional)
- API keys for Anthropic and Google

### 1. Clone and configure

```bash
git clone git@github.com:allthingsclowd/craicgpt.ie.git
cd craicgpt.ie
cp .env.example .env
```

Edit `.env` and fill in your real values:

```bash
# ── Anthropic / Claude ────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-sonnet-4-5        # or claude-opus-4-6

# ── Google / Gemini ───────────────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.5-pro           # thinking model — needs LLM_MAX_TOKENS=8192

# ── Local LM Studio ───────────────────────────────────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1   # or your machine's LAN IP
LM_STUDIO_MODEL=local-model           # name shown in LM Studio UI

# ── AWS ───────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=craicgpt-ie-production
CLOUDFRONT_DISTRIBUTION_ID=E...

# ── Behaviour ─────────────────────────────────────────────────────────
DRY_RUN=false
SKIP_LOCAL_LLM=false
LLM_MAX_TOKENS=8192                   # must be high for thinking models
```

### 2. Test the pipeline (dry run — no S3 upload)

```bash
# Test all three providers
./run_daily.sh --dry-run --verbose

# Skip local LLM if LM Studio isn't running
./run_daily.sh --dry-run --skip-local --verbose

# Inspect the output
cat /tmp/paper_content_$(date +%Y-%m-%d).json | python3 -m json.tool | head -80
```

### 3. Visualise the pipeline graph

```bash
./run_daily.sh --show-graph
# Paste the output at https://mermaid.live
```

---

## Daily Operations

### Generate content and publish to S3

```bash
./run_daily.sh
```

This will:
1. Create `.venv` on first run and install dependencies
2. Load credentials from `.env`
3. Run the LangGraph pipeline (research → generate → compile → publish)
4. Upload `content/YYYY/MM/DD/paper_content.json` to S3
5. Invalidate the CloudFront cache — site is live within ~30 seconds

### Deploy frontend changes

Run this after editing `frontend/index.html`, `style.css`, or `main.js`:

```bash
./deploy_frontend.sh
```

This syncs `frontend/` to S3 and invalidates CloudFront. The `content/` prefix in S3 is excluded from `--delete` so generated JSON is never overwritten.

---

## Automating Daily Generation on macOS (launchd)

macOS uses `launchd` rather than cron for scheduled tasks. A `.plist` file describes the job; `launchctl` loads it.

### 1. Create the plist

Save this file as `~/Library/LaunchAgents/ie.craicgpt.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ie.craicgpt.daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/graz/repos/craicgpt.ie/run_daily.sh</string>
    </array>

    <!-- Run at 08:00 every morning -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Write stdout and stderr to log files -->
    <key>StandardOutPath</key>
    <string>/tmp/craicgpt.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/craicgpt.err</string>

    <!-- Only run if the machine is awake; don't catch up missed runs -->
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 2. Load the job

```bash
launchctl load ~/Library/LaunchAgents/ie.craicgpt.daily.plist
```

### 3. Verify it is scheduled

```bash
launchctl list | grep craicgpt
# Should show: -   0   ie.craicgpt.daily
```

### 4. Test it immediately (without waiting for 08:00)

```bash
launchctl start ie.craicgpt.daily
tail -f /tmp/craicgpt.log
```

### 5. View logs from the last run

```bash
cat /tmp/craicgpt.log
cat /tmp/craicgpt.err   # errors/warnings
```

### 6. Unload (disable) the job

```bash
launchctl unload ~/Library/LaunchAgents/ie.craicgpt.daily.plist
```

> **Note:** The Mac must be awake at 08:00 for the job to fire. If the machine is asleep, the run is skipped (not deferred). Set your Mac's sleep schedule in System Settings → Battery → Schedule to wake before 08:00 if needed.

---

## S3 Content Schema

Every run produces one JSON file at:

```
s3://craicgpt-ie-production/content/YYYY/MM/DD/paper_content.json
```

Structure:

```json
{
  "date": "2026-03-03",
  "generated_at": "2026-03-03T08:01:42+00:00",
  "pipeline_version": "2.0",
  "context": {
    "news_headlines": ["...", "..."],
    "weather": { "location": "Dublin", "temp_c": 9, "conditions": "Drizzly" },
    "ai_trends": "...",
    "research_trace": [{ "role": "tool", "content": "..." }]
  },
  "articles": {
    "main_article": {
      "langchain_node": "generate/RunnableParallel",
      "outputs": {
        "claude":  { "title": "...", "content": "...", "_model_id": "claude-sonnet-4-5", "_latency_ms": 3200 },
        "gemini":  { "title": "...", "content": "...", "_model_id": "gemini-2.5-pro",   "_latency_ms": 8100 },
        "local":   { "title": "...", "content": "...", "_model_id": "qwen2.5-7b",        "_latency_ms": 51000 }
      }
    },
    "comparison_article": { ... },
    "daily_joke":          { ... },
    "editors_note":        { ... },
    "llm_muse":            { ... }
  }
}
```

---

## Infrastructure

The AWS infrastructure is minimal — just enough to host a static site:

```
terraform/frontend/
├── main.tf       ← S3 bucket, CloudFront distribution, Route53 alias records
├── variables.tf  ← All input variables with sensible defaults
├── outputs.tf    ← Bucket name, CloudFront distribution ID
└── modules/
    ├── acm/        ← ACM SSL certificate (must be in us-east-1)
    ├── s3/         ← Bucket with OAC policy (CloudFront only)
    └── cloudfront/ ← Distribution with HTTPS redirect, caching
```

To apply (one-time setup or after infra changes):

```bash
cd terraform/frontend
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your domain
terraform init && terraform plan && terraform apply
```

No Lambda, no EventBridge, no Secrets Manager. Infrastructure cost: **~$0.50/month** (S3 + CloudFront free tier).

---

## Troubleshooting

### Gemini returns empty content

`gemini-2.5-pro` is a thinking model. It consumes its token budget on internal reasoning before producing output. Ensure `LLM_MAX_TOKENS=8192` in `.env`. With only 1024 tokens it exhausts the budget thinking and returns nothing.

### Local LLM shows "Thinking Process:" text instead of article

Some local models (DeepSeek-R1, Qwen3 in thinking mode) output reasoning before JSON. The parser handles this automatically by scanning past thinking text to find the first valid JSON block. If it still fails, try loading a non-thinking model variant in LM Studio.

### `ModuleNotFoundError: No module named 'content_pipeline'`

The script must set `PYTHONPATH` to the repo root. `run_daily.sh` does this automatically. If running `python` directly:

```bash
PYTHONPATH=/path/to/craicgpt.ie python content_pipeline/main.py
```

### Pipeline completes but site still shows old content

CloudFront caches aggressively. The pipeline invalidates `/*` automatically after upload. If the site is still stale after 60 seconds, invalidate manually:

```bash
source .env
aws cloudfront create-invalidation \
  --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
  --paths "/*"
```

### `content/` folder was wiped from S3

This happens if `aws s3 sync --delete` is run without `--exclude "content/*"`. Both `deploy_frontend.sh` and the old GitHub Actions workflow include this exclusion. If content was wiped, re-run the pipeline:

```bash
./run_daily.sh --date 2026-03-03
```

---

## Tutorial Documentation

The `docs/` folder contains step-by-step explanations of each LangChain concept used:

| File | Topic |
|---|---|
| `docs/01-overview.md` | Architecture and design decisions |
| `docs/02-lcel-and-chains.md` | The `\|` pipe operator and chain composition |
| `docs/03-langgraph-workflow.md` | StateGraph, nodes, edges, and state |
| `docs/04-multi-provider-setup.md` | Running Claude, Gemini, and LM Studio side by side |
| `docs/05-tools-and-agents.md` | `@tool` decorator and ReAct agents |

---

## License

MIT — see [LICENSE](LICENSE).
