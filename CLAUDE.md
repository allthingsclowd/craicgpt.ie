# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code
in this repository.

---

## Project Overview

**The Craic Gazette** is an AI-powered Irish daily newspaper — fun, witty, and
refreshingly free of doom. Each morning it generates a fresh edition with two desks:

1. An **AI-landscape desk** — what changed in the AI world in the last 24 hours
   (1 headliner + 2 subarticles + 10 shorts), in Graham's house voice.
2. A **Craic & Throttle desk** — a creator digest that credits real creators:
   Irish AND British comedians (deliberate bias for female comedians — Sarah
   Millican, Katherine Ryan, Rosie Jones…) plus ALL things Honda motorcycles
   (official Honda moto channels + UK bike press filtered to Honda), rewritten as
   up to 5 short pieces. Freshness-first (24h → 48h → 96h ladder, ranked by view
   count); a thin desk publishes short — it NEVER holds the paper.

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

# Narrate a validated edition: per-article audio + the dad↔son podcast (banter ungated),
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
   │      (research/ai_sources.py, research/fun_sources.py — harvests RETRIED ×3),
   │      then drop grim/political, recently-published, duplicate and
   │      UNREACHABLE-source stories. HOLD the whole edition (EditionHeld) only if
   │      the AI desk is below its integrity floor — the fun desk is a TARGET, not
   │      a floor (thin/empty publishes with what we have, traced honestly).
   │
   ├─ 3. WRITE (deterministic) — generate/writer.py turns candidates into prose
   │      (AI section in one JSON call; each fun story in Graham's voice, crediting
   │      the creator). MOTO items carry a hard "this is a BIKE, never a car"
   │      constraint + a car-noun check with ONE re-write (writer.car_words_in). LiteLLM brain/writer = DGX/M3 Qwen3.6, frontier fallback.
   │      _snap_ai_sources forces every written source_url onto a validated candidate.
   │
   ├─ 4. IMAGES (deterministic) — generate/images.py (LiteLLM image route, FLUX.2 [dev])
   │      a cartoon for EVERY article (18: headliner + 2 subs + 10 shorts + 5 fun).
   │      ONE house cartoon style per edition, rotating DAILY across four looks
   │      (Beano / Simpsons / Saturday-morning / plasticine) — a true day-ordinal
   │      cycle, so consecutive editions never repeat. Text is allowed ONLY on the
   │      28-step heroes (8-step lettering comes out mangled); translations share
   │      those images, so a hero bubble stays English on every language.
   │      Each depicts a one-line VISUAL GAG invented per story (generate/image_gag.py)
   │      rather than a literal headline. Cost is TIERED — hero 1024²@28 steps,
   │      fun 1024²@8, shorts 512²@8 — which is what makes 18 images fit the
   │      190-min task cap (28 steps everywhere would be 3h38m).
   │
   ├─ 5. COMPILE (compile.py, schema v3)
   │
   ├─ 6. JUDGE (in-pipeline, rubric_review.grade_edition) — a deepagents
   │      RubricMiddleware grades the FINISHED edition (harmless/on-brand/attributed)
   │      on an INDEPENDENT local model (qwen3-coder-next, M3 :8087 — distinct from the writer; frontier fallback).
   │      Verdict → paper["edition"]["rubric"]; cli publishes the EN draft + images +
   │      verdict-rubric.json to S3 preview/.  (This in-pipeline rubric REPLACED the
   │      old decoupled two-VM openclaw+hermes review.)  ← English is judged ONCE.
   │
   └─ 7. TRANSLATE-MANY (deterministic) — for each other lang in CRAICGPT_LANGUAGES
          (default en,de,es,it,ja,fr): generate/translate.py translate_paper() turns the
          COMPILED English edition into <lang> (prose only — URLs/images/credits/persona
          kept verbatim; stamps edition.translated_by), structural-validate, publish a
          <lang>/ preview draft. NOT re-researched, NOT re-judged — the translations
          inherit the single English verdict. Images are SHARED (translations carry the
          absolute English image URLs → publish skips re-upload).
   ▼
Narrate EVERY language (AFTER validation) — cli narrate --language <l> (Conductor task
   craicgpt_narrate): per-article readings with Graham & Tom ALTERNATING + the dad↔son podcast
   (verbatim readings + transitional "discussion" banter — UNGATED since 2026-06-10, the
   per-banter rubric gate was too strict; a rambling link is length-guard dropped) + a
   deterministic <180s TL;DR headline bulletin — all topped & tailed by our own 80s call-sign
   jingle (Apple sampled instruments, bounced offline; generate/jingle.py). Voice clones are
   REUSED cross-lingually; a translated edition's podcast/TL;DR open with a spoken
   "machine-translated by <model>" note. Parody items read in their OWN voice clone when
   deployed (else a spoken character intro). Adds audio_url per item + paper["podcast"] +
   paper["podcast_tldr"]. Runs on .75 or the M3 (M3 mlx-audio TTS clone), never the laptop.
   ▼
Publish gate — Conductor cron craicgpt_publish_gate_poll @06–08 UTC → cli gate:
   the single rubric APPROVE verdict + host structural validation + MANDATORY browser-UA
   link-check → promote EN to content/ live, then promote ALL OTHER LANGUAGES on the SAME
   English verdict (_publish_translations_live — additive + isolated; one language failing
   never sinks English) + CloudFront invalidation + frontend sync. The verdict/status
   control-plane is language-neutral. A JUDGEMENT hold (rubric HOLD, structurally valid)
   escalates to Graham on Telegram and, if no human directive lands within
   CRAICGPT_HITL_PASSIVE_MINUTES (default 60), is PASSIVELY approved (published) — fenced so
   a structurally-broken edition is never auto-published. Editions are VERSIONED per language:
   <lang>/content/<date>/paper_content.json (latest) + versions/<vid>.json + versions.json.
   ▼
S3 + CloudFront (edge language router) → craicgpt.ie
   English lives at the S3 ROOT (content/…, /index.html); /en/ is a CloudFront ALIAS to it.
   Translations live under a real <lang>/content/… prefix. The CloudFront Function
   (infra/cloudfront/router.js) auto-detects language on a prefix-less request
   (cg_lang cookie → Accept-Language → en) and 302s to /<lang>/, aliases /en/* → /*, and
   rewrites /<lang>/ → /<lang>/index.html. Browser fetches /<lang>/…/paper_content.json.
```

Generation now **judges itself in-pipeline** (the rubric is the last build step), so
the only decoupled hop left is the **publish gate**, which coordinates via S3 state
(status.json / verdict-rubric.json / directive.json) — nothing is physically chained,
so each stage is independently retriable and the gate is idempotent.

---

## Multi-lingual editions (write-once, translate-many)

The paper ships daily in **`CRAICGPT_LANGUAGES`** (default `en,de,es,it,ja,fr` — the
Qwen3-TTS-supported set, so all carry audio). **English is the single editorial source of
truth**: it is researched, written, judged and link-checked **once**. Every other language
is a **translation of the compiled English edition** (`generate/translate.py`), not a fresh
generation — one extra LLM pass over the prose, preserving URLs/images/credits.

- **Storage:** English stays at the existing root (`content/…`, `/index.html`); `/en/` is a
  **CloudFront alias** to it (`infra/cloudfront/router.js`). Translations live under a real
  `<lang>/content/…` prefix with their **own `versions.json`** (`publish._prefix_for` +
  `_write_edition_version(language=…)` — a versioning prefix-collision fix made per-language
  manifests work). **Images are shared** (translations carry the absolute English image URLs
  → `publish._is_local_path` skips re-upload), audio is per-language. New `edition` fields:
  `language`, `available_languages`, `translated_by`.
- **Flow:** `run` writes the English preview, then translates + publishes a preview per
  language; `narrate --language <l>` adds per-language audio (the voice clones are reused
  cross-lingually; the podcast/TL;DR open with a spoken "machine-translated by `<model>`"
  note); the gate promotes English live, then **all other languages on the single English
  verdict** (`_publish_translations_live` — additive + isolated; a language failing never
  sinks English). Translations are faithful, not re-judged. The verdict/status control-plane
  stays **language-neutral**.
- **Honesty:** translated pages carry a light footer note + a link to the English original,
  and the audio its spoken apology — both naming `edition.translated_by` (the real model).
- **URLs / SEO:** `/en/`, `/de/`, … path prefixes, edge auto-detect (cg_lang cookie →
  Accept-Language → 302), `hreflang` + `x-default`. The CloudFront **Function**
  (`infra/cloudfront/router.js`, viewer-request) does it: 302 a prefix-less request to
  `/<lang>/`, alias `/en/*`→`/*`, rewrite `/<lang>/`→`…/index.html` (OAC→S3 REST origin
  needs this), pass assets/content/media through. Cost ≈ €0 ($0.10/1M, 2M/mo free).
  - **GOTCHA (cost real time):** a raw `set-cookie` HEADER on a function-GENERATED response
    fails CloudFront validation → the redirect **503**s. The fix in `router.js` is the
    response **`cookies`** structure (`{cookies:{cg_lang:{value,attributes}}}`), not a header.
  - **Deployed via AWS CLI, NOT `terraform apply`** (`infra/cloudfront/deploy-router.sh`):
    `terraform/frontend` has no backend → local state, and that state isn't in this checkout,
    so an apply would re-create the live stack. The `.tf` carries the change as a labelled
    NOT-APPLIED note. The put-only `craicgpt-publish` IAM **can't** `CreateFunction` — the
    router deploy uses the **admin** account; see Deployment below.
  - **Code comments stay English**; only LLM prompts, fixed podcast/UI templates and the HTML
    `<head>` are localised.

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
| `content_pipeline/agent/rubric_review.py` | `grade_edition`: in-pipeline deepagents **RubricMiddleware** judge on an **independent** local model (`qwen3-coder-next`, M3 :8087 — Qwen3-Coder-Next 80B-A3B, distinct from the writer; frontier fallback) → `verdict-rubric.json`; replaced the two-VM consensus. (The podcast-banter gate `grade_podcast_script` was REMOVED 2026-06-10 — too strict.) |
| `content_pipeline/agent/publish.py` | S3 publish (preview↔content), versioning, CloudFront invalidation. `publish_paper(language=…)` stores translations under `<lang>/content/…` (English stays at root); each language keeps its own `versions.json` |
| `content_pipeline/generate/writer.py` | Deterministic article writers (AI section, fun story, editor's brief, About page). `_default_generate` now wraps generation in `run_with_fallback(local=write_model DGX, fallback=FALLBACK_TEXT_MODEL M3)` — a transient DGX connection drop crosses to the M3 instead of crashing a multi-minute run; translate/brief/about/banter inherit it |
| `content_pipeline/generate/translate.py` | **Multi-lingual:** `translate_paper(paper, language)` translates a COMPILED English edition's prose into another language (reuses the writer's robust chat→JSON path), preserving URLs/images/credits/persona; stamps `edition.translated_by`; per-section English fallback on failure. Write-once, translate-many |
| `content_pipeline/agent/i18n_html.py` | **Multi-lingual:** generates `frontend/<lang>/{index,about}.html` from the English templates (translated `<title>`/`<meta>`/`<html lang>` + hreflang + lang-prefixed nav) at deploy time |
| `content_pipeline/generate/images.py` + `image_styles.py` | Image generation (LiteLLM image route) + day-stable art-style rotation + the **render tiers** (`HERO`/`STANDARD`/`THUMBNAIL`, `render_spec_for`) and `NEGATIVE_PROMPT`. `generate_image`/`save_image` carry `size`/`steps`/`seed`/`negative_prompt` via `extra_body` — the ONLY four parameters the ComfyUI shim honours; anything else is silently ignored and returns a full-cost image with HTTP 200, so verify by wall-clock, never by a 200. The saved filename hashes the prompt **and** the render spec, or a 512px thumbnail collides with a 1024px hero |
| `content_pipeline/generate/image_gag.py` | **The wit.** One small chat→JSON call per article turning the story into a one-line VISUAL GAG for its cartoon. Fail-soft: a failed or blank gag returns `None` and the caller falls back to the literal prompt (an image is required by `validate_paper`; a gag is not). Told the moto vertical, never left to infer it |
| `content_pipeline/generate/audio.py` | Deterministic narration: M3 mlx-audio voice clones (Graham/Tom + parody-persona registry via `has_clone`/`resolve_voice`), chunk→synth→stitch, **per-language** `_phonetic` (the English craic→"crack" / spoken-URL rules must not touch other prose; falls back to the English map) + `chunk_text` splits on CJK sentence punctuation (`。！？`), **mastering chain** (`_rms_normalize` per-chunk leveling → `_crossfade_concat` equal-power seams → `master_wav`: de-box EQ + two-pass EBU-R128 loudness + true-peak limiter; reserved `mode='apple'` Match-EQ seam), multi-voice podcast + 80s call-sign bookend (`render_podcast`) |
| `content_pipeline/generate/jingle.py` | The show's **80s call-sign** sting — our own Am–F–C–G hook voiced through Apple's sampled GM instruments, bounced offline to `assets/jingle_80s_{intro,outro}.wav` (renderer in `jingle_src/`); owned, zero-copyright. The stdlib *Whiskey in the Jar* Karplus-Strong synth remains as a graceful fallback |
| `content_pipeline/generate/podcast_script.py` | Dad↔son podcast script, **one clip per article** (each reader's `pre` link + verbatim reading + `post` hand-off-by-name in ONE TTS piece → far fewer transition seams): clean two-host cold-open (Graham + date, Tom breaks in) + ALTERNATING reads (Graham/Tom) + parody guests framed by FIXED `GUEST_WELCOME`/`GUEST_ACK`/`GUEST_SIGNOFF` templates (seniority host welcomes; guest reads in own voice) + only the host links are gated + Tom's minimal slang (`build_podcast_script`); plus the deterministic **<180s** `build_tldr_script` headline bulletin. **Multi-lingual:** the fixed framing (`_L10N`) + the date phrase are localised per language; a translated edition opens with `translation_preamble` (the spoken "machine-translated by `<model>`" note naming `edition.translated_by`); the TL;DR budget counts **characters** for spaceless CJK (`_CJK_LANGS`) instead of words |
| `content_pipeline/generate/narration.py` | `narrate_paper(paper, language=…)` — the narration step: per-article audio (best-effort, alternating voices) + the podcast (banter UNGATED since 2026-06-10; render failure stays soft) + the deterministic TL;DR bulletin + trace events. **Loops every language** (driven by `language` or `edition.language`); voice clones are reused cross-lingually; the banter is generated in-language per edition |
| `content_pipeline/generate/personas.py` | Parody-journalist roster (assigned day-stable to each fun item) + satire disclaimer + `persona_voice_key` (persona → voice-clone key the narrator resolves) + podcast hand-off helpers (`PERSONA_SENIORITY` / `introducer_for` — younger→Tom, older→Graham — and `real_name` to decode the punny byline) |
| `content_pipeline/research/curation.py` | `curate_candidates`, `validate_source_link` (browser-UA link check), dedupe, diversity |
| `content_pipeline/research/feeds.py` + `ai_sources.py` + `fun_sources.py` | Deterministic RSS/Atom harvest. Fun desk (Craic & Throttle): Irish + British comedians (female-first) + Honda moto channels + Honda-filtered UK bike press (`FUN_FEED_FILTERS`); 24/48/96h freshness ladder, ranked by YouTube view count (`_views`). **The moto vertical:** `MOTO_SOURCES` / `is_moto_source` mark the bike outlets, `MOTO_EXCLUDE_TERMS` drops Honda **car** stories at harvest (RideApart et al. cover cars too), and the flag rides onto each item as `_vertical` so the writer AND the illustrator both know it is a bike |
| `content_pipeline/research/recency.py` | Exclude stories from the last few live editions |
| `content_pipeline/compile.py` | `build_paper` (schema v3) + `build_layout` (interleaves fun among AI shorts) |
| `content_pipeline/providers/litellm.py` | `get_litellm_llm` (ChatOpenAI → LiteLLM proxy) + `run_with_fallback` (local-first→frontier) |
| `content_pipeline/content_config.py` | All config from env vars; singleton `content_cfg` |
| `content_pipeline/notifications.py` | Telegram lifecycle alerts (generated / published / HELD) to both agents' channels |
| `frontend/index.html` + `static_assets/{style.css,main.js}` | Tabloid layout, version picker, "Under the Hood" drawer. `main.js` is **i18n**: reads the language from the path (`/<lang>/`), fetches `/<lang>/content/…`, renders the masthead **language switcher** (sets the `cg_lang` cookie) + the translated-page footer note |
| `infra/cloudfront/router.js` + `deploy-router.sh` + `README.md` | **NEW edge language router.** CloudFront **Function** (viewer-request): auto-detect lang on a prefix-less request (cookie→Accept-Language→en, **302**) + alias `/en/*`→`/*` + rewrite `/<lang>/`→`…/index.html`. Carries the **503-cookie gotcha** fix (use the `cookies` structure, not a `set-cookie` header). `deploy-router.sh` ships it via **AWS CLI** (admin creds — the put-only IAM can't `CreateFunction`), **not** `terraform apply` |
| `terraform/frontend/` | IaC for S3, CloudFront, ACM, Route53. The language router is **NOT applied from here** (no backend → local state not in this checkout); `modules/cloudfront/main.tf` carries it as a labelled NOT-APPLIED note — the live router is the AWS-CLI deploy above |

---

## Output JSON Schema (paper_content.json — `pipeline_version: "3.0"`)

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO8601",
  "pipeline_version": "3.0",
  "edition": { "approved_by": null, "approved_at": null, "language": "en", "available_languages": ["en","de","es","it","ja","fr"], "translated_by": null,
               "cartoon_style": { "name": "beano-comic", "label": "Beano-style British comic" } },
  "editors_brief": { "title": "", "body": "" },
  "ai": {
    "headliner":    { "title": "", "standfirst": "", "body": "", "source_url": "", "image_url": "", "audio_url": "", "_text_model": "", "_image_model": "", "_audio_model": "" },
    "subarticles":  [ { "title": "", "body": "", "source_url": "", "image_url": "", "audio_url": "", "_text_model": "" } ],
    "shorts":       [ { "title": "", "body": "", "source_url": "", "image_url": "", "audio_url": "", "_text_model": "", "_image_model": "", "_image_gag": "", "_image_tier": "thumbnail" } ]
  },
  "fun": [ { "title": "", "body": "", "source_url": "", "source": "<creator credit>", "image_url": "", "audio_url": "", "_text_model": "", "_image_model": "" } ],
  "about": { "title": "", "body": "" },
  "podcast": { "audio_url": "", "transcript": "", "_voices": ["graham","tom"], "_text_model": "", "_tts_model": "" },
  "podcast_tldr": { "audio_url": "", "transcript": "", "_voices": ["graham","tom"], "_kind": "tldr", "_tts_model": "" },
  "layout": ["ai.headliner", "ai.subarticles.0", "ai.shorts.0", "fun.0", "..."],
  "context": { "agent_trace": [ { "kind": "", "name": "", "detail": {} } ], "files": ["..."] }
}
```

Every article now carries `image_url` — **including the 10 AI shorts**, which render as a
floated 512px spot thumbnail (`.card--ai.card--short .card-img`). Illustrated items also carry
the additive `_image_gag` (the visual joke, reused as `image_alt` because it describes what is
actually in the frame) and `_image_tier` (`hero`/`standard`/`thumbnail`).

> **`publish.py` gotcha:** the image-upload walk is a literal list of slots. Shorts were added
> to it in 2026-08; a slot missing from that list keeps its local `/tmp` path in the published
> JSON and 404s for every reader. `tests/test_publish.py` guards it.

`audio_url` (per item), `podcast` and `podcast_tldr` are **additive and optional** — the narration
step adds them after validation; an edition without audio still validates and renders. The full
show and the TL;DR both top & tail with our own **80s call-sign jingle** (Apple sampled
instruments, bounced offline); `podcast_tldr` is a deterministic, word-budgeted **<180s** two-voice headline bulletin.

Any article may also carry an additive, optional **`_qc`** marker
(`{"flag": "fabrication"|"dead_link", "reason": "...", "by": "per-article gate"}`). The per-article
gate (`agent/article_review.py::auto_remediate`) is **advisory** (2026-06-19): it never drops an
article or hard-holds the edition — it stamps a flagged story with `_qc`, the edition publishes, the
frontend renders a **quality-control warning banner** (`main.js::qcStamp` + `.qc-stamp`), and Graham
is alerted (`notifications.notify_flagged`) to spot-check. This replaced the old promote-then-floor
hard-hold that blacked out the whole multilingual edition over one fabricated headliner.

Counts (resolved): **1 headliner + 2 subarticles + 10 shorts** (AI) + **up to 5 fun**
— all 18 illustrated. 
(a thin pool publishes short — the fun desk never holds the paper). Each
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
| `CRAICGPT_LANGUAGES` (multi-lingual: the daily set) | No | `en,de,es,it,ja,fr` |
| `CRAICGPT_SOURCE_LANGUAGE` (always generated natively; the rest are translations) | No | `en` |
| `FALLBACK_TEXT_MODEL` (local cross-box) | No | `m3/mlx/qwen3.6-35b-a3b-unsloth-8bit` |
| `SERPER_API_KEY` | Yes (web_search) | — |
| `MIN_AI_SOURCES` (hard floor) / `MIN_FUN_SOURCES` (target only since 2026-06-11) | No | `11` / `4` |
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

No service restart is needed for **engine code** (the Conductor worker spawns a fresh
`python -m content_pipeline.agent.cli …` per task — it picks up the new checkout each run).
The autonomous schedule (`craicgpt_daily_0500` @05:00 generate-and-judge,
`craicgpt_publish_gate_poll` @06–08, UTC) does the rest — the rubric judge now runs
**in-pipeline** at generation time, so the old agent-VM `craicgpt-review.timer` is retired.
The daily workflow `craicgpt_daily_content` (v3) chains **generate → narrate → gate**.

### CRITICAL GOTCHA — two SEPARATE worker services on `.75` (this cost real debugging time)

There are **two** Conductor worker systemd units on `.75`. They are NOT interchangeable:

| Service | Runs | Owns | Code lives at |
|---------|------|------|---------------|
| **`grazlab-fleet-worker-conductor.service`** | `python -m conductor.workers.fleet_worker` | the **craicgpt** tasks: `craicgpt_generate_daily`, `craicgpt_narrate`, `craicgpt_publish_gate` | `/home/ubuntu/grazlab-llm-fleet` |
| `conductor-workers.service` | `/opt/conductor-workers/workers.py` | the **vault-provision** worker (proxmox / vault tasks) — **no craicgpt** | `/opt/conductor-workers/` |

- **Engine code** (this repo, what the craicgpt task *shells out to*): `git -C /opt/craicgpt.ie pull` — no restart (a fresh subprocess per task).
- **Fleet worker code** (the task wrappers / shell-outs themselves, in `grazlab-llm-fleet`):
  the running `fleet_worker` process **holds the old code in memory** until restarted, so a
  change there is `git -C /home/ubuntu/grazlab-llm-fleet pull` **+**
  `sudo systemctl restart grazlab-fleet-worker-conductor.service`. Restarting
  `conductor-workers.service` does **nothing** for craicgpt — it's the wrong service.
- **Task-defs / workflows** are (re)registered with
  `CONDUCTOR_URL=http://192.168.50.75:8080/api python3 conductor/register-workflow.py`
  (in `grazlab-llm-fleet`). Conductor **API :8080**, **UI :5000**.

### The CloudFront language router (deploy via AWS CLI, not Terraform)

The `/en/`, `/de/`, … edge router (`infra/cloudfront/router.js`) is deployed **imperatively**:

```bash
# on a box with the ADMIN AWS account (creds pulled inline from 1Password — never printed).
cd infra/cloudfront
./deploy-router.sh                                   # build + publish the function (safe)
DIST_ID=E1DJEM9WBUG1C1 ./deploy-router.sh --attach   # also wire it onto the default behavior
```

- **NOT `terraform apply`:** `terraform/frontend` has no backend → local state, and that
  state isn't in this checkout → an apply would re-create the live stack. The `.tf`
  (`modules/cloudfront/main.tf`) carries the change as a labelled **NOT-APPLIED** note.
- **IAM:** the put-only `craicgpt-publish` user **can't** `CreateFunction`, so the deploy
  uses the **admin** account. The pipeline role itself got an added inline policy
  **`craicgpt-router-mgmt`** (CloudFront function lifecycle + get/update the specific
  distribution `E1DJEM9WBUG1C1`) so it can manage the router for invalidations/lifecycle.
- The **503-cookie gotcha** (raw `set-cookie` header on a generated response → CloudFront
  validation failure) is already fixed in `router.js` (the `cookies` structure). Verify with
  `curl -sI https://craicgpt.ie/ | grep -i location` → `/en/` (or the detected language).

**Frontend:** `aws s3 sync frontend/ s3://craicgpt-ie-production/ --delete` (the publish
gate also syncs `frontend/` after each live publish so the shell never lags the content).
The per-language HTML shells (`frontend/<lang>/{index,about}.html`) are (re)generated from the
English templates by `python -m content_pipeline.agent.i18n_html frontend` before the sync.

**Infrastructure:** `cd terraform/frontend && terraform init && terraform plan && terraform apply`
— **but mind the local-state caveat above**; the live stack was applied from another host, so
this checkout has no state for it and the language router is deployed by the AWS-CLI script, not here.

---

## Tutorial Documentation

See `docs/` for the deep-agent tutorial (rewritten for v3):

1. `docs/01-overview.md` — Architecture and quick start
2. `docs/02-lcel-and-chains.md` — LCEL, structured output, and local-first fallback
3. `docs/03-langgraph-workflow.md` — `create_deep_agent`, the research/write harness, HITL & trace
4. `docs/04-multi-provider-setup.md` — One LiteLLM proxy, the grazlab fleet, `run_with_fallback`
5. `docs/05-tools-and-agents.md` — `@tool`, deepagents `SubAgent` delegation, deterministic-vs-LLM
6. `docs/06-narration-and-audio.md` — the narration pass: deterministic TTS + the (ungated) dad↔son podcast
7. `docs/07-multilingual.md` — write-once translate-many, the CloudFront language router, deploy & ops
