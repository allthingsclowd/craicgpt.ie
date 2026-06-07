# CraicGPT.ie — Documentation

This directory is a **deep-agent tutorial**: it explains how The Craic Gazette — an
AI-powered Irish daily newspaper — is built with LangChain + `deepagents`, generating a
fresh edition every morning, **open-source-first** (local models on a homelab fleet behind
one LiteLLM proxy, with a frontier model as fallback).

> **Architecture note.** This is the **v3 deep-agent daily paper**. Earlier designs — a
> 3-way *model comparator* (v2) and an AWS Lambda pipeline (v1) — are dead. If a doc or
> comment mentions `RunnableParallel` across Claude/Gemini/local, or Lambda/Bedrock, it's
> describing the old system. Trust this set and `CLAUDE.md`.

---

## Read in order

1. **[01-overview.md](01-overview.md)** — What it is, the end-to-end architecture (research
   → deterministic harness → in-pipeline rubric judge → publish), the directory map, and a
   local quick start.
2. **[02-lcel-and-chains.md](02-lcel-and-chains.md)** — LCEL chains, robust structured
   (JSON) output, and the **local-first / frontier-fallback** wrapper (`run_with_fallback`).
3. **[03-langgraph-workflow.md](03-langgraph-workflow.md)** — `create_deep_agent`, why the
   **harness writes the articles** (not the agent), OSS human-in-the-loop (`interrupt()` +
   checkpointer), the **in-pipeline rubric judge** + publish gate, plus the run trace.
4. **[04-multi-provider-setup.md](04-multi-provider-setup.md)** — One **LiteLLM proxy**, the
   grazlab fleet (DGX Spark + M3 Ultra), routing models by name, and per-model quirks.
5. **[05-tools-and-agents.md](05-tools-and-agents.md)** — The `@tool` decorator, deepagents
   **`SubAgent` delegation**, the deterministic-vs-LLM split, and the in-pipeline rubric judge.
6. **[06-narration-and-audio.md](06-narration-and-audio.md)** — The narration step: the
   deterministic TTS harness (voice clones, chunk→synth→stitch), the dad↔son podcast, and the
   **deepagents rubric gate** over the LLM banter — deterministic vs probabilistic, made concrete.

---

## The system in one diagram

```
Conductor @05:00 UTC ─▶ run_edition
   deep agent (research only) ─▶ research/{ai,fun}_candidates.json
   harness: curate → HOLD-or-write → snap URLs → images → compile (schema v3)
   rubric judge (in-pipeline: deepagents RubricMiddleware on qwen3-coder-next — independent)
                          │
                          ▼  draft + verdict-rubric.json → S3 preview/
   narrate: per-article reads (Graham⇄Tom + parody clones) + rubric-gated podcast + <180s TL;DR + 80s jingle
                          ▼  gate @06–08 UTC: rubric APPROVE + structural + link-check
                     content/ (live, versioned, +audio) ─▶ CloudFront ─▶ craicgpt.ie
```

Key principles you'll see throughout:

- **Research is the agent's job; mechanical work is the harness's job** — cheaper, testable,
  and fabrication-resistant.
- **HOLD over fabricate** — below the per-desk integrity floor, or when search degrades, the
  edition HOLDs and alerts; it never prints thin or invented content.
- **Honest attribution** — the published `_text_model` / `_image_model` and the trace record
  which model *actually* ran (local or fallback).
- **Decoupled via S3 state** — every stage is independently retriable; the gate is idempotent.

---

## Operations & deployment

- Operational source of truth: **[`../CLAUDE.md`](../CLAUDE.md)** (commands, key files,
  schema, env vars, deployment).
- The engine runs on the Conductor host `.75` (`/opt/craicgpt.ie`, branch `grazzer`); a
  `git pull` there is the deploy (the Conductor worker shells out per task).
- Conductor workflows/triggers and the worker live in the **`grazlab-llm-fleet`** repo
  (`conductor/workers/craicgpt/worker.py`, `conductor/triggers/schedules/`).

---

## Legacy docs

- `secrets-manager-setup.md` describes an **AWS Secrets Manager** setup from the v1/v2
  era. The live engine reads secrets from `/etc/craicgpt.env` on the host (sourced from
  1Password), **not** Secrets Manager — treat that file as historical until rewritten.
