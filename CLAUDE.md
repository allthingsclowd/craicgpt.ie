# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code
in this repository.

---

## Project Overview

**The Craic Gazette** is an AI-powered Irish daily newspaper — fun, witty, and
refreshingly free of doom. Each morning it generates a fresh edition with two desks:

1. An **AI-landscape desk** — what changed in the AI world in the last 24 hours
   (1 headliner + 2 subarticles + 10 shorts), in Graham's house voice.
2. A **fun desk** — an Irish-creator digest that credits real creators (Foil Arms
   and Hog, The 2 Johnnies, Graham Norton…) rewritten as 5 short pieces.

It is built **open-source-first**: the work is done by local models on the grazlab
homelab fleet (reached through one **LiteLLM proxy**), with a frontier model as a
fallback only. It doubles as a **LangChain deep-agent tutorial** — every file is
heavily commented, and the website's "Under the Hood" drawer replays the agent's
actual run from a trace embedded in each edition.

> **History:** this was once a 3-way *model comparator* (Claude/Gemini/local on the
> same prompt). That v2 is **dead.** The live system is the v3 deep-agent daily
> paper described here. Ignore `content_pipeline/{agents,chains,prompts,publisher,tools}/`
> and `providers/{claude,gemini,lmstudio}.py` — they are v2 leftovers, not the pipeline.

---

## Common Development Commands

```bash
# Install
pip install -r content_pipeline/requirements.txt

# Tests (real pytest — ~190+ tests, mostly offline with injected fetch/LLM stubs)
python -m pytest -q

# Generate an edition locally (writes a DRAFT to S3 preview/ + images + verdict-rubric)
python -m content_pipeline.agent.cli run --publish-draft --date 2026-06-05

# Force a fresh same-day version when the news pool is thin (skip recency de-dup)
python -m content_pipeline.agent.cli run --no-recency --publish-draft --date 2026-06-05

# Host-side validate a draft the way the publish gate does (structural + live link-check)
python -m content_pipeline.agent.cli validate --date 2026-06-05 --check-links

# The publish gate: publish live on the rubric APPROVE verdict + host validation + link-check
python -m content_pipeline.agent.cli gate --publish --date 2026-06-05

# Narrate a validated edition: per-article audio + the rubric-gated dad↔son podcast,
# uploaded to S3 (preview/ unless --live). Runs on .75 or the M3 (calls the M3 TTS), NOT the laptop.
python -m content_pipeline.agent.cli narrate --date 2026-06-05 --prefix content --publish

# Other CLI verbs: verdict / consensus / announce / override / remediate / directive / syndicate / message
python -m content_pipeline.agent.cli --help
```

> **Tooling note.** There is no `Makefile`/`pyproject.toml` here; `make lint`/`make test`
> from the global AGENTS.md do **not** exist in this repo. Use `python -m pytest`.
> The root `test_*.py` files are stale **Lambda-era** scripts (not pytest) — ignore them.

---

## Architecture

The edition is built in two phases on purpose. The **deep agent does research only**
(reliably writing candidate JSON to its virtual filesystem); the **harness writes the
articles deterministically** from those candidates — because the agent's single giant
`write_file` kept getting mangled by the local vLLM tool-call parser. Mechanical work
(curation, persona assignment, images, snapping URLs) is done in code, not by the LLM.

```
Conductor (Orkes OSS) on .75 — cron craicgpt_daily_0500 @05:00 UTC
   │  worker shells out:  python -m content_pipeline.agent.cli run --publish-draft
   ▼
run_edition (content_pipeline/agent/editor_in_chief.py)
   │
   ├─ 1. RESEARCH — Editor-in-Chief deep agent (deepagents.create_deep_agent)
   │      plans (write_todos) → delegates via `task` to subagents:
   │        • fun-news-researcher      → research/fun_candidates.json
   │        • ai-landscape-researcher  → research/ai_candidates.json
   │        • link-validator
   │      tools: web_search (Serper API), fetch_page, validate_link
   │
   ├─ 2. HARVEST + CURATE (deterministic) — merge curated RSS/Atom feeds
   │      (research/ai_sources.py, research/fun_sources.py), then drop grim/
   │      political, recently-published, duplicate and UNREACHABLE-source stories.
   │      HOLD the whole edition (EditionHeld) if a desk is below its integrity floor.
   │
   ├─ 3. WRITE (deterministic) — generate/writer.py turns candidates into prose
   │      (AI section in one JSON call; each fun story in Graham's voice, crediting
   │      the creator). LiteLLM brain/writer = DGX/M3 Qwen3.6, frontier fallback.
   │      _snap_ai_sources forces every written source_url onto a validated candidate.
   │
   ├─ 4. IMAGES (deterministic) — generate/images.py (LiteLLM image route, HiDream-O1)
   │      one per AI lead + fun story, day-stable art-style rotation.
   │
   ├─ 5. COMPILE (compile.py, schema v3)
   │
   └─ 6. JUDGE (in-pipeline, rubric_review.grade_edition) — a deepagents
          RubricMiddleware grades the FINISHED edition (harmless/on-brand/attributed)
          on an INDEPENDENT local model (qwen3-coder-next, M3 :8087 — distinct from the writer; frontier fallback).
          Verdict → paper["edition"]["rubric"]; cli publishes the draft + images +
          verdict-rubric.json to S3 preview/.  (This in-pipeline rubric REPLACED the
          old decoupled two-VM openclaw+hermes review.)
   ▼
Narrate (AFTER validation) — cli narrate (Conductor task craicgpt_narrate, LIVE in the v2
   daily workflow): per-article readings with Graham & Tom ALTERNATING + the dad↔son podcast
   (verbatim readings + transitional "discussion" banter GATED by the deepagents rubric) + a
   deterministic <180s TL;DR headline bulletin — all topped & tailed by our own 80s call-sign
   jingle (Apple sampled instruments, bounced offline; generate/jingle.py). Parody items read
   in their OWN voice clone when deployed (else a spoken character intro). Adds audio_url per item + paper["podcast"] +
   paper["podcast_tldr"]. Runs on .75 or the M3 (M3 mlx-audio TTS clone), never the laptop.
   ▼
Publish gate — Conductor cron craicgpt_publish_gate_poll @06–08 UTC → cli gate:
   the single rubric APPROVE verdict + host structural validation + MANDATORY browser-UA
   link-check → promote to content/ live + CloudFront invalidation + frontend sync. A
   JUDGEMENT hold (rubric HOLD, structurally valid) escalates to Graham on Telegram and, if
   no human directive lands within CRAICGPT_HITL_PASSIVE_MINUTES (default 60), is PASSIVELY
   approved (published) — fenced so a structurally-broken edition is never auto-published.
   Editions are VERSIONED: content/<date>/paper_content.json (latest) +
   versions/<vid>.json + versions.json (multi-apply — several editions per day).
   ▼
S3 + CloudFront → craicgpt.ie  (static HTML/JS fetches paper_content.json)
```

Generation now **judges itself in-pipeline** (the rubric is the last build step), so
the only decoupled hop left is the **publish gate**, which coordinates via S3 state
(status.json / verdict-rubric.json / directive.json) — nothing is physically chained,
so each stage is independently retriable and the gate is idempotent.

---

## Key Files

| File | Purpose |
|------|---------|
| `content_pipeline/agent/editor_in_chief.py` | `build_editor_in_chief` (deep agent) + `run_edition` (the harness: research→curate→write→images→compile) |
| `content_pipeline/agent/subagents.py` | deepagents `SubAgent` specs (fun-news / ai-landscape researchers, link-validator) + the Editor-in-Chief prompt |
| `content_pipeline/agent/tools.py` | `@tool`s: `web_search` (Serper.dev), `fetch_page`, `validate_link`, `generate_cover_image`, `assign_journalist_voices` |
| `content_pipeline/agent/hitl.py` | OSS human-in-the-loop approval graph — LangGraph `interrupt()` + checkpointer |
| `content_pipeline/agent/trace.py` | `TraceRecorder` + `extract_trace` → `context.agent_trace` for the "Under the Hood" drawer |
| `content_pipeline/agent/cli.py` | CLI entry: `run` / `gate` / `validate` / `verdict` / `consensus` / `override` / … + the gate's link-check |
| `content_pipeline/agent/review.py` | `validate_paper` (structural), verdict exchange, `gate`/`compute_consensus` (default required set = the single `rubric` judge); the HITL **passive-approval** (escalate → auto-publish after `CRAICGPT_HITL_PASSIVE_MINUTES`, fenced by structural validity) + the `force-publish`/`remove-and-publish`/`hold` directives |
| `content_pipeline/agent/rubric_review.py` | `grade_edition`: in-pipeline deepagents **RubricMiddleware** judge on an **independent** local model (`qwen3-coder-next`, M3 :8087 — Qwen3-Coder-Next 80B-A3B, distinct from the writer; frontier fallback) → `verdict-rubric.json`; replaced the two-VM consensus. Also `grade_podcast_script` — the SAME RubricMiddleware over `PODCAST_RUBRIC`, gating the podcast banter |
| `content_pipeline/agent/publish.py` | S3 publish (preview↔content), versioning, CloudFront invalidation |
| `content_pipeline/generate/writer.py` | Deterministic article writers (AI section, fun story, editor's brief, About page) |
| `content_pipeline/generate/images.py` + `image_styles.py` | Image generation (LiteLLM image route) + day-stable art-style rotation |
| `content_pipeline/generate/audio.py` | Deterministic narration: M3 mlx-audio voice clones (Graham/Tom + parody-persona registry via `has_clone`/`resolve_voice`), chunk→synth→stitch, `_phonetic` (craic→"crack", craicgpt.ie→spoken URL), **mastering chain** (`_rms_normalize` per-chunk leveling → `_crossfade_concat` equal-power seams → `master_wav`: de-box EQ + two-pass EBU-R128 loudness + true-peak limiter; reserved `mode='apple'` Match-EQ seam), multi-voice podcast + 80s call-sign bookend (`render_podcast`) |
| `content_pipeline/generate/jingle.py` | The show's **80s call-sign** sting — our own Am–F–C–G hook voiced through Apple's sampled GM instruments, bounced offline to `assets/jingle_80s_{intro,outro}.wav` (renderer in `jingle_src/`); owned, zero-copyright. The stdlib *Whiskey in the Jar* Karplus-Strong synth remains as a graceful fallback |
| `content_pipeline/generate/podcast_script.py` | Dad↔son podcast script: "Craic of Dawn" signature + ALTERNATING verbatim readings (Graham/Tom) + transitional discussion banter (`build_podcast_script`); plus the deterministic **<180s** `build_tldr_script` headline bulletin |
| `content_pipeline/generate/narration.py` | `narrate_paper` — the narration step: per-article audio (best-effort, alternating voices) + the rubric-gated podcast + the deterministic TL;DR bulletin + trace events |
| `content_pipeline/generate/personas.py` | Parody-journalist roster (assigned day-stable to each fun item) + satire disclaimer + `persona_voice_key` (persona → voice-clone key the narrator resolves) |
| `content_pipeline/research/curation.py` | `curate_candidates`, `validate_source_link` (browser-UA link check), dedupe, diversity |
| `content_pipeline/research/feeds.py` + `ai_sources.py` + `fun_sources.py` | Deterministic RSS/Atom harvest (AI feeds; Irish-creator YouTube feeds) |
| `content_pipeline/research/recency.py` | Exclude stories from the last few live editions |
| `content_pipeline/compile.py` | `build_paper` (schema v3) + `build_layout` (interleaves fun among AI shorts) |
| `content_pipeline/providers/litellm.py` | `get_litellm_llm` (ChatOpenAI → LiteLLM proxy) + `run_with_fallback` (local-first→frontier) |
| `content_pipeline/content_config.py` | All config from env vars; singleton `content_cfg` |
| `content_pipeline/notifications.py` | Telegram lifecycle alerts (generated / published / HELD) to both agents' channels |
| `frontend/index.html` + `static_assets/{style.css,main.js}` | Tabloid layout, version picker, "Under the Hood" drawer |
| `terraform/frontend/` | IaC for S3, CloudFront, ACM, Route53 |

---

## Output JSON Schema (paper_content.json — `pipeline_version: "3.0"`)

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO8601",
  "pipeline_version": "3.0",
  "edition": { "approved_by": null, "approved_at": null },
  "editors_brief": { "title": "", "body": "" },
  "ai": {
    "headliner":    { "title": "", "standfirst": "", "body": "", "source_url": "", "image_url": "", "audio_url": "", "_text_model": "", "_image_model": "", "_audio_model": "" },
    "subarticles":  [ { "title": "", "body": "", "source_url": "", "image_url": "", "audio_url": "", "_text_model": "" } ],
    "shorts":       [ { "title": "", "body": "", "source_url": "", "audio_url": "", "_text_model": "" } ]
  },
  "fun": [ { "title": "", "body": "", "source_url": "", "source": "<creator credit>", "image_url": "", "audio_url": "", "_text_model": "", "_image_model": "" } ],
  "about": { "title": "", "body": "" },
  "podcast": { "audio_url": "", "transcript": "", "_voices": ["graham","tom"], "_text_model": "", "_tts_model": "", "rubric": {} },
  "podcast_tldr": { "audio_url": "", "transcript": "", "_voices": ["graham","tom"], "_kind": "tldr", "_tts_model": "" },
  "layout": ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0", "..."],
  "context": { "agent_trace": [ { "kind": "", "name": "", "detail": {} } ], "files": ["..."] }
}
```

`audio_url` (per item), `podcast` and `podcast_tldr` are **additive and optional** — the narration
step adds them after validation; an edition without audio still validates and renders. The full
show and the TL;DR both top & tail with our own **80s call-sign jingle** (Apple sampled
instruments, bounced offline); `podcast_tldr` is a deterministic, word-budgeted **<180s** two-voice headline bulletin.

Counts (resolved): **1 headliner + 2 subarticles + 10 shorts** (AI) + **5 fun**. Each
fun item is **either credited** (`source` = creator name, no disclaimer) **or parody**
(`satire_disclaimer`) — never neither (enforced by `review.validate_paper`).
Live editions are stored at `s3://<bucket>/content/<YYYY>/<MM>/<DD>/paper_content.json`
(latest) plus immutable `versions/<vid>.json` + a `versions.json` manifest.

---

## Code Style Conventions

- **Python 3.11+**, type hints throughout, Pydantic where structured output helps.
- **Heavy comments** — this is a tutorial codebase. Comments starting with `# TUTORIAL:`
  explain a LangChain / deepagents concept. **Do NOT remove them.**
- **Deterministic vs LLM** — if a shell-script/pure-function can do it (dedupe, filter,
  diversity, snapping URLs), do it in the harness, not the agent. Tools are for live
  judgment (search, fetch, validate, image).
- **Factory functions** for models (`get_litellm_llm`), never module-level singletons.
- **Env-var driven config** (`content_config.py`); never hardcode keys or bucket names.
- **Integrity over output** — when sources are too thin / search degraded, **HOLD**
  (`EditionHeld`) and alert; never fabricate stories or URLs to fill the gap.
- **Honest attribution** — `run_with_fallback` records which model actually ran; the
  published "_text_model"/"_image_model" reflect reality.

---

## What NOT to do

- Do NOT resurrect the v2 comparator: `content_pipeline/{agents,chains,prompts,publisher,tools}/`
  and `providers/{claude,gemini,lmstudio}.py` are dead leftovers — the live pipeline is
  `content_pipeline/agent/` + `generate/` + `research/` + `providers/litellm.py`.
- Do NOT remove `# TUTORIAL:` comments — they are the educational value.
- Do NOT hardcode API keys, bucket names, or engine URLs — route models by NAME through
  LiteLLM; read everything else from env.
- Do NOT weaken the publish gate's link-check to an allowlist. It validates with a real
  browser User-Agent (so it agrees with generation and isn't fooled by bot-blocking
  hosts like CNBC/OpenAI); an invented URL still 404s. Keep generation and the gate on
  the **same** `validate_source_link`.
- Do NOT treat the root `test_*.py` as live tests (stale Lambda-era). Real tests live in `tests/`.
- Do NOT commit `.env` files.

---

## Environment Variables

All config is in `content_pipeline/content_config.py` (defaults match the grazlab
catalog). On the host they live in `/etc/craicgpt.env`. Key ones:

| Variable | Required | Default |
|----------|----------|---------|
| `LITELLM_BASE_URL` | No | `https://llm.grazlab.thescriptingpaddy.com/v1` |
| `LITELLM_API_KEY` | No | `sk-no-key-required` |
| `BRAIN_MODEL` (research) | No | `dgx/vllm/qwen3.6-35b-a3b-fp8` |
| `WRITE_MODEL` (prose) | No | `dgx/vllm/qwen3.6-35b-a3b-fp8` |
| `JUDGE_MODEL` (rubric judge) | No | `m3/mlx/qwen3-coder-next-4bit` (independent of the writer) |
| `IMAGE_MODEL` | No | `m3/mlx/hidream-o1-image-dev` |
| `AUDIO_TTS_BASE_URL` (narration; M3 mlx-audio direct) | No | `http://192.168.50.206:8081/v1` |
| `AUDIO_TTS_MODEL` (voice clone) | No | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` |
| `GRAHAM_REF_AUDIO` / `TOM_REF_AUDIO` (M3-side ref WAVs) | No | `/Users/graz/ai-models/voice-ref/{graham,tom}/ref.wav` |
| `ENABLE_NARRATION` | No | `true` |
| `FALLBACK_TEXT_MODEL` (local cross-box) | No | `m3/mlx/qwen3.6-35b-a3b-unsloth-8bit` |
| `SERPER_API_KEY` | Yes (web_search) | — |
| `MIN_AI_SOURCES` / `MIN_FUN_SOURCES` | No | `11` / `4` |
| `AI_FEED_HOURS` | No | `48` |
| `S3_BUCKET` | Yes (publish) | `craicgpt-ie-production` |
| `CLOUDFRONT_DISTRIBUTION_ID` | Yes (live publish) | — |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Yes (publish) | — |
| `TELEGRAM_OPENCLAW_BOT_TOKEN` / `TELEGRAM_HERMES_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | No | — |

---

## Deployment

The engine runs on the **Conductor host `.75`** (`conductor.grazlab`). It is a plain
`/opt/craicgpt.ie` git checkout on branch **`grazzer`** with its own `.venv`, pulling
over **public HTTPS** — so the deploy is just:

```bash
# on .75
git -C /opt/craicgpt.ie pull          # <-- this IS the deploy; the worker shells out per task
```

No service restart is needed for engine code (the Conductor worker spawns a fresh
`python -m content_pipeline.agent.cli …` per task). The autonomous schedule
(`craicgpt_daily_0500` @05:00 generate-and-judge, `craicgpt_publish_gate_poll` @06–08,
UTC) does the rest — the rubric judge now runs **in-pipeline** at generation time, so
the old agent-VM `craicgpt-review.timer` is retired. See the grazlab-llm-fleet repo for
the Conductor workflows/triggers and the worker (`conductor/workers/craicgpt/worker.py`).

**Frontend:** `aws s3 sync frontend/ s3://craicgpt-ie-production/ --delete` (the publish
gate also syncs `frontend/` after each live publish so the shell never lags the content).

**Infrastructure:** `cd terraform/frontend && terraform init && terraform plan && terraform apply`.

---

## Tutorial Documentation

See `docs/` for the deep-agent tutorial (rewritten for v3):

1. `docs/01-overview.md` — Architecture and quick start
2. `docs/02-lcel-and-chains.md` — LCEL, structured output, and local-first fallback
3. `docs/03-langgraph-workflow.md` — `create_deep_agent`, the research/write harness, HITL & trace
4. `docs/04-multi-provider-setup.md` — One LiteLLM proxy, the grazlab fleet, `run_with_fallback`
5. `docs/05-tools-and-agents.md` — `@tool`, deepagents `SubAgent` delegation, deterministic-vs-LLM
