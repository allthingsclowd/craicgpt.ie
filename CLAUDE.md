# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code
in this repository.

---

## Project Overview

**The Craic Gazette** is an AI-powered Irish newspaper that:
1. Sends identical prompts to **Claude, Gemini, and a local LLM** simultaneously
2. Stores all three responses in a structured JSON file on S3
3. Presents a **model comparator** website where readers switch between editions
4. Serves as a **LangChain + LangGraph tutorial** — every file is heavily commented

---

## Common Development Commands

```bash
# Install pipeline dependencies
pip install -r content_pipeline/requirements.txt

# Run the full pipeline (requires API keys in .env)
python content_pipeline/main.py

# Dry run (generates content, writes to /tmp, skips S3 upload)
python content_pipeline/main.py --dry-run

# Generate for a specific date
python content_pipeline/main.py 2026-03-03

# Skip local LLM (if LM Studio isn't running)
python content_pipeline/main.py --skip-local

# Show LangGraph pipeline as Mermaid diagram
python content_pipeline/main.py --show-graph

# Verbose (DEBUG) logging
python content_pipeline/main.py --verbose

# Open the frontend locally (no server needed for basic testing)
open frontend/index.html
```

> **No build/test tooling in this repo.** There is no `Makefile`,
> `pyproject.toml`, or configured test framework — the global `make lint` /
> `make test` / `make ci` targets do **not** exist here. The pipeline runs
> directly via `python content_pipeline/main.py`. The `test_*.py` files at the
> repo root are stale Lambda-era scripts (not pytest), kept only for reference.

---

## Architecture

> **Note:** the `.github/workflows/` directory is currently **empty** — the
> `generate-content.yml` (daily cron) and `deploy-frontend.yml` (S3 sync)
> workflows described below are the *intended* automation but are not yet
> committed. Today the pipeline is run manually via `python content_pipeline/main.py`
> and the frontend is deployed with the `aws s3 sync` command in the Deployment
> section. The cron box in the diagram is aspirational.

```
GitHub Actions (cron 06:00 UTC, runs-on: self-hosted)   ← planned, not yet committed
   │
   ▼  content_pipeline/main.py
LangGraph StateGraph:
   [research] → [generate] → [compile] → [publish]
   │                │
   │         RunnableParallel × 3 providers:
   │           Claude (Anthropic API)
   │           Gemini (Google AI)
   │           Local LLM (LM Studio, localhost:1234)
   │
   ▼
S3: content/YYYY/MM/DD/paper_content.json
   │
   ▼
CloudFront → craicgpt.ie
   │
   ▼
Browser JS: fetches JSON, model comparator UI
```

---

## Key Files

| File | Purpose |
|------|---------|
| `content_pipeline/agents/orchestrator.py` | LangGraph StateGraph — the main pipeline |
| `content_pipeline/agents/research_agent.py` | ReAct agent: news + weather tools |
| `content_pipeline/chains/newspaper_chain.py` | LCEL + RunnableParallel across providers |
| `content_pipeline/providers/claude.py` | ChatAnthropic factory |
| `content_pipeline/providers/gemini.py` | ChatGoogleGenerativeAI factory |
| `content_pipeline/providers/lmstudio.py` | ChatOpenAI (base_url=localhost) factory |
| `content_pipeline/prompts/templates.py` | All ChatPromptTemplates (single source of truth) |
| `content_pipeline/tools/news_tool.py` | @tool: DuckDuckGo news search |
| `content_pipeline/tools/weather_tool.py` | @tool: wttr.in weather |
| `content_pipeline/publisher/s3_publisher.py` | boto3 S3 upload + CloudFront invalidation |
| `content_pipeline/config.py` | All configuration from environment variables |
| `content_pipeline/main.py` | CLI entry point |
| `frontend/index.html` | Beano/tabloid newspaper layout |
| `frontend/static_assets/style.css` | Tabloid newspaper styles |
| `frontend/static_assets/main.js` | Model comparator + "Under the Hood" drawer |
| `.github/workflows/generate-content.yml` | Daily cron, self-hosted runner — **planned, not yet committed** |
| `.github/workflows/deploy-frontend.yml` | S3 sync on push to main — **planned, not yet committed** |
| `terraform/frontend/` | IaC for S3, CloudFront, ACM, Route53 |

---

## Output JSON Schema (paper_content.json)

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO8601",
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
        "claude": { "title": "", "content": "", "_model_id": "", "_latency_ms": 0 },
        "gemini": { ... },
        "local":  { ... }
      }
    },
    "comparison_article": { ... },
    "llm_muse":           { ... },
    "daily_joke":         { ... },
    "editors_note":       { ... }
  }
}
```

---

## Code Style Conventions

- **Python 3.11+** throughout
- **Heavy comments** — this is a tutorial codebase. Every non-obvious decision is explained.
- **Tutorial markers** — comments starting with `# TUTORIAL:` explain LangChain concepts
- **Factory functions** for LLM providers (not module-level singletons)
- **Env-var driven config** — all secrets from environment, never hardcoded
- **Graceful degradation** — providers fail silently, pipeline continues with placeholders
- **Type hints** throughout, Pydantic for structured outputs

---

## What NOT to do

- Do NOT hardcode API keys or bucket names in source files
- Do NOT remove the `# TUTORIAL:` comments — they are the educational value
- Do NOT use `lambda_code/` (deleted) — the pipeline is now in `content_pipeline/`
- Do NOT use `terraform/backend/` (deleted) — no Lambda infrastructure anymore
- Do NOT treat the root `test_date_range.py`, `test_enhanced_prompts.py`, or
  `test_idempotent_processing.py` as live tests — they are stale Lambda-era
  scripts and do not exercise `content_pipeline/`
- Do NOT commit `.env` files

---

## Environment Variables

See `.env.example` for the full list. Key ones:

| Variable | Required | Default |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | — |
| `GOOGLE_API_KEY` | Yes | — |
| `LM_STUDIO_BASE_URL` | No | `http://localhost:1234/v1` |
| `S3_BUCKET` | Yes (non-dry-run) | `craicgpt-ie-production` |
| `DRY_RUN` | No | `false` |
| `SKIP_LOCAL_LLM` | No | `false` |
| `WEATHER_LOCATION` | No | `Dublin` |

---

## Deployment

### GitHub Actions Self-Hosted Runner Setup

1. GitHub repo → Settings → Actions → Runners → "New self-hosted runner"
2. Follow the macOS instructions to download and configure the runner
3. Start: `./run.sh` (or install as a service: `./svc.sh install && ./svc.sh start`)
4. Add GitHub Secrets: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY`, `CLOUDFRONT_DISTRIBUTION_ID`
5. Add GitHub Variables: `S3_BUCKET`, `WEATHER_LOCATION`

### Frontend Deployment

**Current (manual):** `aws s3 sync frontend/ s3://craicgpt-ie-production/ --delete`
**Planned:** automatic on push to `main` (when `frontend/**` changes) once
`deploy-frontend.yml` is committed.

### Infrastructure

```bash
cd terraform/frontend
terraform init
terraform plan
terraform apply
```

---

## Tutorial Documentation

See `docs/` for the full LangChain tutorial:

1. `docs/01-overview.md` — Architecture and quick start
2. `docs/02-lcel-and-chains.md` — LCEL pipes and RunnableParallel
3. `docs/03-langgraph-workflow.md` — StateGraph and nodes
4. `docs/04-multi-provider-setup.md` — Claude, Gemini, LM Studio configuration
5. `docs/05-tools-and-agents.md` — @tool decorator and ReAct agents
