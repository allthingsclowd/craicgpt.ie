# Journal — 2026-06-10 — The morning the paper went silent

**Repo / branch:** `craicgpt.ie` / `grazzer` @ `7e60743` (PR #62) + `grazlab-llm-fleet` / `main` @ `cedcb82` (PR #120)
**Model / agent:** `claude-fable-5[1m]` via Claude Code
**Duration:** ~2.5 h active investigation + fixes, plus ~70 min of M3 TTS re-narration running in the background.

## What I asked it to do

"Yesterday you fixed 2 articles missing audio — today NO audio was published. Investigate."

## What it did

- **Diagnosed two compounding root causes** from the Conductor API, `.75` journals, and S3/live JSON:
  1. **The gate raced narration and won by 6 minutes.** Six-language mornings mean generate
     ends 05:47 and EN narration 06:11 — but the gate poll window opens 06:00 and promoted
     everything audio-less at 06:05. `_already_live` compared only `generated_at` (narration
     doesn't change it) → "already-live" forever → finished audio stranded in `/tmp` on `.75`.
  2. **A fleet deploy killed the rest.** The 06:56 UTC rollout of fleet #118 restarted
     `grazlab-fleet-worker-conductor.service` mid-narrate (SIGKILL mid-Spanish);
     `lease_extend=false` + `retryCount: 0` = orphaned task, no retry, workflow headed for a
     4.5 h timeout.
- **Remediated without wasting TTS:** EN + DE drafts were already fully narrated on disk —
  published them straight to live (`cli publish` / `_publish_paper_live(language=…)`).
  Re-narrated es/it/ja/fr detached on `.75`. All six languages verified 18/18 readings + TL;DR.
- **Fixed both causes for good:** craicgpt **#62** — narration-aware `_already_live`
  (TDD, three new tests, 119 green; merged + deployed). Fleet **#120** —
  `bin/safe-restart-fleet-worker.sh` + `make restart-worker-conductor` + narrate
  `retryCount 0→1`; taskdef re-registered and verified live on Conductor.
- **Filed what it didn't fix:** #63 (`available_languages` stuck at `["en"]`),
  #64 (translated banter generation emits placeholders → rubric holds the whole podcast;
  es/it/ja/fr shipped without the main podcast today — readings + TL;DR are fine).

## Where it stumbled

1. **First Conductor terminate call 404'd** — guessed `POST …/terminate`, the OSS API wants
   `DELETE /api/workflow/{id}?reason=…`. One retry, no harm.
2. **A background pytest raced a file edit** and reported phantom failures from the pre-edit
   file; a clean re-run was green. Don't fire the suite in the same breath as the fix.
3. **The fleet PR body briefly over-claimed validation** ("it correctly listed the stuck
   workflow" — the guard query was only tested *after* termination). Caught and corrected
   in an edit, but it shouldn't have been written.

## The real lesson

The race wasn't a bug introduced by anyone — it was **designed in and then outgrown**. The
narrate taskdef literally documents "enriches the LOCAL drafts so the gate uploads the audio
when it promotes" — true when EN-only narration finished by ~05:50, silently false the day
multilingual multiplied narrate's duration ~6×. Nobody re-audited the gate window when the
duration profile changed.

## The one change I'm proposing

**When a pipeline stage's duration profile changes materially (more languages, bigger model,
new sequential loop), grep for every consumer of that stage's *completion timing* — cron
windows, poll schedules, timeouts — and re-verify each.** Local to this repo's docs/memory
for now (captured in the project memory's incident note); if it bites a second time it
becomes a skill.

---

## Afternoon addendum — the banter saga, and the gate that didn't survive it

Fixing #64 ("translated banter emits placeholders → podcast dropped") turned into a
live demonstration of judge non-determinism. Four PRs in:

- **#66** — a held banter degrades to the banter-less podcast (strip, don't sink) + a
  deterministic 300-char guard on links. Proven in production the same hour.
- **#67** — clear the stale `podcast_hold` a re-run leaves behind.
- **#68 / #69** — two rubric scopings, each found by watching a real hold land: the judge
  held banter for naming the sanctioned parody bylines ('Ronald Dump' et al.), then held
  the Japanese banter for *not being English*.

Then the judge held the Italian banter a third way (a borderline tone call), and Graham
made the call the data supported: **"remove that gate as that's too strict" → PR #70.**
Three distinct false-hold modes in one afternoon vs zero real harms caught. The banter now
ships as written — governed by the prompt's register, the length guard, and the edition
rubric upstream. `grade_podcast_script` / `PODCAST_RUBRIC` are gone.

**Final state:** all six languages live with 18/18 readings + full banter podcast + TL;DR,
no holds. **The lesson:** an LLM judge over another LLM's *style* (not facts, not safety
of approved text) buys you mostly variance; every layer that actually protected the show
today was deterministic.

One process stumble worth owning: a `git add -A` briefly committed an untracked personal
PDF to the feature branch — caught pre-PR, commit amended, remote branch replaced. Stage
files explicitly; `-A` in a repo with personal clutter is a footgun.
