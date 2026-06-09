# 07 — Multi-lingual editions (write-once, translate-many)

The Craic Gazette publishes daily in several languages
(`CRAICGPT_LANGUAGES`, default `en,de,es,it,ja,fr`). This chapter shows the pattern
— and why it's a translation pipeline, not six newsrooms.

## The core idea

English is the **single editorial source of truth**. It runs the full pipeline
(research → write → images → **rubric judge** → link-check) exactly once. Every other
language is a **faithful translation of the *compiled* English edition** — one extra
`plain chat → JSON` pass over the prose, reusing the writer's robust local-first JSON
path (`generate/translate.py` imports `writer._default_generate` + `loads_lenient`).

Why not generate each language natively from the sources? Cost (5× the agentic
research + judgement) and authenticity (the parody personas are Irish/UK figures that
don't re-cast). Translation keeps one voice, one set of facts, one approval.

```
research+write+JUDGE (English, once)
   → translate_paper(paper, "de") / ("es") / …     # prose only; URLs/images/credits preserved
   → narrate each language (clones reused; spoken "machine-translated" note)
   → gate promotes ALL languages on the ONE English verdict
```

## What gets translated — and what never does

`translate_paper` only touches user-readable prose (`editors_brief`, `ai.*`,
`fun[].{title,body,byline,satire_disclaimer}`, `about`). It preserves **verbatim**:
`source_url`, `image_url` (images are language-neutral — see sharing below),
`audio_url`, every `_*model` attribution, `layout`, the creator `source` credit and the
`persona` name. A section whose translation can't be parsed **falls back to the English
text** and is noted in `edition.translation_holds` — a translation failure degrades to
readable English, it never breaks the page (translations inherit the English verdict, so
they're never re-judged or HELD).

**Honest attribution** (the project's house rule, extended): each translation stamps
`edition.translated_by` with the real model, surfaced as a light footer note + a link to
the English original on the page, and a short spoken apology at the top of the podcast.

## Storage: English at root, translations under `/<lang>/`

To keep the proven English flow untouched, English content stays at the existing root
(`content/…`) and **`/en/` is a CloudFront alias** to it. Only translations get a real
`<lang>/content/…` prefix. Two consequences worth knowing:

- **Images are shared.** Translation happens *after* the English edition is published, so
  its `image_url`s are already absolute CDN URLs → `publish._is_local_path` skips them →
  no per-language image regeneration. Audio differs (the text differs), so it's per-language.
- **Versioning is per-language.** `publish_paper(language=…)` threads the language into
  `_write_edition_version`, so each language keeps its own `versions.json` (the earlier
  hard-coded-prefix bug would have collided them).

## Narration across languages

The Graham/Tom (and parody) **voice clones are reused cross-lingually** — same English
reference WAVs, target-language text (accept some accent drift; review post-deploy). The
language-sensitive bits are localised: `audio._phonetic` is per-language (the English
`craic`→`crack` rule must not touch other prose), `chunk_text` splits on CJK sentence
punctuation, the fixed podcast/TL;DR framing is translated, and the TL;DR speaking-budget
counts **characters** for spaceless CJK instead of words. The banter is generated **and
rubric-gated per language** — everything voiced is still judged before it's heard.

## Frontend + edge routing

`main.js` reads the language from the path (`/<lang>/`), fetches
`/<lang>/content/…paper_content.json`, localises dates + chrome, renders the masthead
**language switcher** (sets a `cg_lang` cookie, preserves the date) and the translated-page
footer note. The static `<head>` per language (translated `<title>`/`<meta>` + `<html lang>`
+ `hreflang`) is produced by `agent/i18n_html.py` at deploy time.

The **CloudFront Function** (`infra/cloudfront/router.js`) does the edge work: detect on a
prefix-less request (cookie → `Accept-Language` → `en`) and **302** to `/<lang>/`; alias
`/en/*`→`/*`; rewrite `/<lang>/`→`…/index.html`. It's deployed with
`infra/cloudfront/deploy-router.sh` (AWS CLI — **not** `terraform apply`, because the
module's state isn't in this checkout; the `.tf` carries the change as NOT-APPLIED docs).

## Try it locally

```bash
# generate + translate + publish previews for every language
python -m content_pipeline.agent.cli run --publish-draft --date 2026-06-08
# narrate one translated edition (per-article audio + localised podcast + TL;DR)
python -m content_pipeline.agent.cli narrate --date 2026-06-08 --language de --prefix preview --publish
# regenerate the per-language HTML shells from the English templates
python -m content_pipeline.agent.i18n_html frontend
```

## Deploying & operating it

The translation pipeline rides the existing engine deploy — `git -C /opt/craicgpt.ie pull` on
`.75`, no restart (each task is a fresh subprocess). Three things are new enough to trip you up.

### 1. The edge router is deployed with the AWS CLI, not `terraform apply`

The `/en/`, `/de/`, … routing is a **CloudFront Function**, and it's enacted imperatively:

```bash
cd infra/cloudfront
./deploy-router.sh                                   # build + publish the function (safe)
DIST_ID=E1DJEM9WBUG1C1 ./deploy-router.sh --attach   # wire it onto the default behavior
```

Why not Terraform? `terraform/frontend` declares **no backend** → local state, and that state
**isn't in this checkout** (the live stack was applied from another host). A `terraform apply`
from here would see an empty state and try to **re-create** the live S3/CloudFront/ACM/Route53.
So the change is enacted against the live distribution here; `modules/cloudfront/main.tf`
carries the equivalent as a clearly-labelled **NOT-APPLIED** note to reconcile/`import` later.

Two auth notes that cost real time if missed:
- **The put-only `craicgpt-publish` IAM can't `CreateFunction`** — `deploy-router.sh` uses the
  **admin** account (creds pulled inline from 1Password, never printed). The pipeline role did
  gain an inline `craicgpt-router-mgmt` policy (CloudFront function lifecycle + get/update the
  one distribution `E1DJEM9WBUG1C1`) so it can manage the router for ongoing lifecycle.
- **The 503-cookie trap:** a raw `set-cookie` *header* on a function-**generated** response
  fails CloudFront validation and the redirect 503s. The fix — already in `router.js` — is the
  response **`cookies`** structure (`{cookies:{cg_lang:{value,attributes}}}`). If you ever hand-
  edit the router and the `/` → `/en/` redirect starts 503ing, this is why.

Verify after deploy: `curl -sI https://craicgpt.ie/ | grep -i location` → `/en/` (or detected lang).

### 2. Two worker services on `.75` — restart the *right* one

This is the highest-cost operational gotcha and it isn't multilingual-specific, but you'll meet
it the first time you change anything in `grazlab-llm-fleet`. There are **two** Conductor worker
units on `.75`:

- **`grazlab-fleet-worker-conductor.service`** (`python -m conductor.workers.fleet_worker`, from
  `/home/ubuntu/grazlab-llm-fleet`) runs the **craicgpt** tasks
  (`craicgpt_generate_daily`, `craicgpt_narrate`, `craicgpt_publish_gate`).
- `conductor-workers.service` (`/opt/conductor-workers/workers.py`) runs the **vault-provision**
  worker — proxmox/vault tasks, **nothing craicgpt**.

So: **engine** code (this repo, which the task shells out to) is `git -C /opt/craicgpt.ie pull`
with no restart; but **fleet worker** code (the task wrappers themselves) needs
`git -C /home/ubuntu/grazlab-llm-fleet pull` **and**
`sudo systemctl restart grazlab-fleet-worker-conductor.service` — the running process holds the
old code in memory until restarted. Restarting `conductor-workers.service` does nothing for
craicgpt. Task-defs/workflows are (re)registered with
`CONDUCTOR_URL=http://192.168.50.75:8080/api python3 conductor/register-workflow.py`
(Conductor API on `:8080`, UI on `:5000`).

### 3. The writer now crosses boxes on a transient failure

A multilingual run is *long* — English plus five translations plus narration is many minutes of
back-to-back model calls, so a single blip used to be expensive. `writer._default_generate` now
wraps generation in `run_with_fallback(local=write_model` (DGX)`, fallback=FALLBACK_TEXT_MODEL`
(M3)`)`: a transient DGX connection drop **crosses to the M3** instead of crashing the run, and
the published `_text_model` still records which box actually answered (honest attribution).
Because `translate.py`, the editor's brief, the About page and the podcast banter all route
through `_default_generate`, they inherit the resilience for free — no extra wiring per caller.
