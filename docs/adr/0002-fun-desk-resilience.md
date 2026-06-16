# ADR 0002 — Fun-desk harvest resilience + Honda/CB1000GT bias

- **Status:** Accepted (implemented `feat/fun-desk-resilience`)
- **Date:** 2026-06-16

## Context

On 2026-06-16 the edition published with a "comedy" desk of **2 motorcycle items
(MoreBikes) and zero comedians** — every prior day had 5 comedian pieces. Investigation:

- **Not** the per-article gate (no `remediation` trace event) and **not** a code
  regression (the harvest code was byte-identical to the working days).
- All 51 fun feeds fetch fine now, and comedians *had* uploaded within the 96h window
  (The 2 Johnnies, Graham Norton, Vittorio). So at the 05:00 run the **YouTube creator
  feeds transiently failed to fetch** (a momentary throttle/blip on the burst of ~30
  `youtube.com/feeds` requests), while the one non-YouTube press feed (MoreBikes) survived.

Three weaknesses turned a transient blip into a silent, motorcycle-only edition:
1. **No retry** — `_default_fetch_text` returned `None` on any non-200/exception, so one
   transient 429/timeout dropped a creator for the whole day.
2. **Silent skip** — failed feeds were never named (only an aggregate count logged), so
   the collapse was invisible.
3. **No floor, no alert** — the fun desk publishes thin on purpose, so a creators-empty
   desk shipped with no notification. Graham found out by eyeballing the site.

Separately, the motorcycle slice was MoreBikes-heavy (low diversity), and the new Honda
**CB1000GT** (arriving in the UK this year) had no priority.

## Decision

**Resilience** (`research/feeds.py`):
- **Retry with backoff** on transient failures (`_TransientFetch`: network error / 408 /
  425 / 429 / 5xx); permanent failures (404/403) are not retried. Each attempt is logged.
- **Name the dead/empty feeds** — `harvest` logs `WARNING N/M feeds returned NO items:
  [names]`, so a collapse is visible.
- **Creators-missing alert** — `fun_sources.fun_desk_alert()` returns an alert when the
  shipped fun desk has no comedian/creator items; `cli.cmd_run` fires it once via Telegram.

**Honda / CB1000GT** (`research/fun_sources.py` + `feeds.harvest_fun_candidates`):
- Diversified the bike press with verified feeds: **RideApart, Adventure Bike Rider,
  Devitt** (all Honda-keyword-filtered), alongside MCN/Visordown/Superbike News/MoreBikes.
- **CB1000GT ranking boost**: fun candidates are sorted CB1000GT first (`CB1000GT_KEYWORDS`),
  then the wider CB1000 family, then by view count — so the new sports-tourer leads the
  moto slice whenever the press covers it (which they are: MCN/MoreBikes/Visordown/Bennetts/ABR
  all ran CB1000GT pieces this week).

## Consequences

- A transient YouTube throttle no longer silently empties the comedian desk; if it does
  recur, it's logged (named feeds) AND alerted, not discovered by eye.
- Injectable `once`/`sleep`/`fetch` keep all of this offline-unit-tested
  (`tests/test_feeds_resilience.py`).
- The moto slice is more diverse and CB1000GT-led.
- **Follow-up:** the craicgpt run still has no durable per-run log on `.75` (the worker
  doesn't persist the subprocess output) — the new feed WARNINGs only help if captured;
  worth piping the daily run to a log file.
