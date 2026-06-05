# 01 — System Overview

## What is The Craic Gazette?

The Craic Gazette is an AI-powered Irish daily newspaper — fun, witty, and refreshingly
free of doom. Every morning it generates a fresh edition with two desks:

- **AI landscape** — what *changed* in the AI world in the last 24 hours: 1 headliner,
  2 subarticles, 10 shorts, written in Graham's house voice.
- **Fun** — an **Irish-creator digest** that credits real creators (Foil Arms and Hog,
  The 2 Johnnies, Graham Norton…), rewritten as 5 short pieces that point readers their way.

**The twist:** the whole paper is researched by a single **LangChain deep agent** and the
work is done **open-source-first** — local models on a homelab fleet (an M3 Ultra and a
DGX Spark), reached through one **LiteLLM proxy**, with a frontier model used only as a
fallback. The website's "Under the Hood" drawer replays the agent's *actual* run, so the
site is both a working newspaper and a live deep-agents tutorial.

> **Heads up — this used to be something else.** v1 was an AWS Lambda pipeline; v2 was a
> 3-way *model comparator* (Claude/Gemini/local on the same prompt). Both are dead. This
> documentation describes the live **v3 deep-agent daily paper**. If you read about
> `RunnableParallel` across three providers, or Lambda/Bedrock, that's the old design.

---

## Architecture at a Glance

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Conductor (Orkes OSS) on .75 — cron craicgpt_daily_0500 @ 05:00 UTC        │
│  worker shells out:  python -m content_pipeline.agent.cli run --publish-draft│
│                                                                              │
│  run_edition  (content_pipeline/agent/editor_in_chief.py)                    │
│   1. RESEARCH   Editor-in-Chief deep agent (deepagents.create_deep_agent)    │
│                 plans → delegates to subagents → writes candidate JSON       │
│                   • fun-news-researcher       → research/fun_candidates.json │
│                   • ai-landscape-researcher   → research/ai_candidates.json  │
│                 tools: web_search (Brave) · fetch_page · validate_link       │
│   2. CURATE     deterministic: merge curated feeds, drop grim/recent/dupe/   │
│                 unreachable, HOLD if a desk is below its integrity floor     │
│   3. WRITE      deterministic: generate/writer.py → prose (LiteLLM Qwen3.6)  │
│   4. IMAGES     deterministic: generate/images.py (LiteLLM image route)      │
│   5. COMPILE    compile.py → schema-v3 paper_content.json                    │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼  6. JUDGE (in-pipeline) — rubric_review.grade_edition: a deepagents
           RubricMiddleware grades the finished edition (harmless/on-brand/
           attributed) on gemma-4-12b-it, a model independent of the writer
        │
        ▼  draft + images + verdict-rubric.json → S3 preview/ + status.json
        ▼
  Publish gate (Conductor cron @ 06–08 UTC → cli gate): the single rubric APPROVE
  + host structural validation + browser-UA link-check → promote to content/ (live),
  version it, invalidate CloudFront, sync the frontend
        │
        ▼
  S3 / CloudFront → craicgpt.ie  (static HTML/JS fetches paper_content.json,
  renders the woven edition + a version picker + the "Under the Hood" trace)
```

Generation now **judges itself in-pipeline** (the rubric is the last build step), so the
only remaining hop is the **publish gate**, **decoupled through S3 state** — nothing is
physically chained, so it is independently retriable and idempotent (safe to poll every
10 min).

---

## Why two phases (research, then a deterministic harness)?

The deep agent is excellent at **research** — searching, reading, and writing candidate
JSON to its virtual filesystem. It is *not* reliable at the final, single, giant
"write the whole edition" call (the local vLLM tool-call parser mangled it, and the model
invented stock-image URLs and skipped fields). So we split the work:

- **Agent → research only.** It plans (`write_todos`), delegates to subagents, and leaves
  `research/ai_candidates.json` + `research/fun_candidates.json`.
- **Harness → everything mechanical.** Curation, recency filtering, link validation,
  article writing (small structured calls), persona/credit assignment, image generation,
  and compiling the schema are all done in plain Python (`run_edition`). The rule of thumb
  (`deciding-deterministic-vs-llm`): *if a script could do it deterministically, don't pay
  the model to do it.*

This is also why fabrication is structurally hard: the writer only ever sees **real,
link-validated** sources, and if a desk can't clear its integrity floor the whole edition
**HOLDs** rather than print thin or invented content.

---

## Directory Structure

```
craicgpt.ie/
├── content_pipeline/
│   ├── agent/                     ← the deep-agent engine (v3)
│   │   ├── editor_in_chief.py     ← build_editor_in_chief + run_edition (THE harness)
│   │   ├── subagents.py           ← deepagents SubAgent specs + Editor-in-Chief prompt
│   │   ├── tools.py               ← @tool: web_search / fetch_page / validate_link / image
│   │   ├── hitl.py                ← OSS human-in-the-loop: interrupt() + checkpointer
│   │   ├── trace.py               ← TraceRecorder → "Under the Hood" payload
│   │   ├── cli.py                 ← run / gate / validate / verdict / consensus / …
│   │   ├── review.py              ← validate_paper, verdict exchange, gate consensus
│   │   ├── rubric_review.py       ← in-pipeline RubricMiddleware judge (gemma) → verdict-rubric.json
│   │   └── publish.py             ← S3 publish + versioning + CloudFront invalidation
│   ├── generate/                  ← deterministic writers + images
│   │   ├── writer.py              ← AI section, fun story, editor's brief, About page
│   │   ├── images.py / image_styles.py
│   │   └── personas.py
│   ├── research/                  ← candidates & curation
│   │   ├── curation.py            ← curate_candidates + validate_source_link
│   │   ├── feeds.py / ai_sources.py / fun_sources.py   ← deterministic RSS/Atom harvest
│   │   └── recency.py
│   ├── providers/litellm.py       ← get_litellm_llm + run_with_fallback (local-first→frontier)
│   ├── compile.py                 ← build_paper (schema v3) + build_layout
│   ├── content_config.py          ← all config from env (singleton content_cfg)
│   └── notifications.py           ← Telegram lifecycle alerts
│
├── frontend/                      ← static HTML/CSS/JS (S3 hosted)
├── terraform/frontend/            ← S3 + CloudFront + ACM + Route53
└── docs/                          ← these tutorial files
```

> The sibling dirs `content_pipeline/{agents,chains,prompts,publisher,tools}/` and
> `providers/{claude,gemini,lmstudio}.py` are **v2 leftovers** — not part of the v3 pipeline.

---

## Quick Start (local development)

### Prerequisites

- Python 3.11+
- Access to a **LiteLLM proxy** that fronts at least one chat model and one image model
  (the grazlab default is `https://llm.grazlab.thescriptingpaddy.com/v1`; point
  `LITELLM_BASE_URL` at your own if you have one). A frontier API key for the fallback.
- A **Brave Search API key** (`BRAVE_SEARCH_API_KEY`) for `web_search`.
- AWS credentials with S3 put + CloudFront-invalidation permission (only for publishing).

### Setup

```bash
git clone https://github.com/allthingsclowd/craicgpt.ie
cd craicgpt.ie
pip install -r content_pipeline/requirements.txt

cp .env.example .env        # never commit this
# edit .env: LITELLM_BASE_URL, BRAVE_SEARCH_API_KEY, model routes, S3_BUCKET, …

# run the tests (mostly offline — fetch + LLM are injected stubs)
python -m pytest -q

# generate an edition as a DRAFT (S3 preview/) — needs LiteLLM + Brave + AWS
python -m content_pipeline.agent.cli run --publish-draft --date 2026-06-05

# validate it exactly as the publish gate will (structural + live link-check)
python -m content_pipeline.agent.cli validate --date 2026-06-05 --check-links
```

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LITELLM_BASE_URL` | The one proxy that fronts the fleet | grazlab proxy |
| `BRAIN_MODEL` | Research-agent route (needs tool-calling) | `dgx/vllm/qwen3.6-35b-a3b-fp8` |
| `WRITE_MODEL` | Prose-writing route | `m3/mlx/qwen3.6-35b-a3b-unsloth-8bit` |
| `IMAGE_MODEL` | Image route | `m3/mlx/hidream-o1-image-dev` |
| `FALLBACK_TEXT_MODEL` | Frontier fallback (only on local failure) | `claude-sonnet-4-6` |
| `BRAVE_SEARCH_API_KEY` | Brave Search API key for `web_search` | — |
| `S3_BUCKET` / `CLOUDFRONT_DISTRIBUTION_ID` | Publishing target | `craicgpt-ie-production` / — |

Full list (integrity floors, feed window, Telegram, etc.) lives in
`content_pipeline/content_config.py`.

---

## The Tutorial Learning Path

1. **This file** — architecture overview
2. **[02-lcel-and-chains.md](02-lcel-and-chains.md)** — LCEL, structured output, and the local-first fallback wrapper
3. **[03-langgraph-workflow.md](03-langgraph-workflow.md)** — `create_deep_agent`, the research→write harness, HITL & the trace
4. **[04-multi-provider-setup.md](04-multi-provider-setup.md)** — one LiteLLM proxy, the grazlab fleet, `run_with_fallback`
5. **[05-tools-and-agents.md](05-tools-and-agents.md)** — the `@tool` decorator, deepagents `SubAgent` delegation, deterministic-vs-LLM
