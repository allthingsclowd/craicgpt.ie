# Journal — 2026-06-11 — The day the paper didn't show up, and the desk that fixed it

**Repo / branch:** `craicgpt.ie` / `grazzer` @ `b195e82` (PR #72) + fleet issue #121
**Model / agent:** `claude-fable-5[1m]` via Claude Code
**Duration:** ~1.5 h diagnosis + build, ~3.5 h unattended pipeline, Graham off biking throughout.

## What happened

The 05:00 run **HELD the edition** — no paper all day. Root cause: the fun-feed harvest
transiently failed at 05:00 (it returned 10 candidates when re-run at 10:30), the code fell
back to the agent's 1-item research file, the ≥4 integrity floor tripped, and **nothing in
the chain retries** — not the harvest, not the Conductor task (workers return `ok:false`
but COMPLETE), not the gate (it just waits for a draft that never comes).

## What Graham asked for

Not a patch — a redefinition: British comedians too (**bias female**), **ALL things Honda
motorcycles**, retitle the category, prefer 24 h-fresh ranked by views/likes, never repeat,
and **worst case publish with what you have** — "the difficulty should be choosing".

## What shipped (PR #72)

- **23 new live-verified feeds** (a subagent resolved + verified every channel ID and
  rejected 12 inactive/fan channels — including an **impersonator** "Honda UK Motorcycles"
  clip-farm with Vietnamese TikTok hashtags. Verify-before-trust earns its keep).
- **Freshness ladder** (24→48→96 h, one fetch, client-side banding) + **view-count ranking**
  (`media:statistics` parsed onto `FeedItem.views`). Deterministic, no LLM.
- **Harvest retried ×3** (exception OR empty — both presented identically at 05:00).
- **The fun floor became a target**: thin/empty publishes short, traced honestly; validator
  count-floor removed. AI floor, link validation, no-repeat, no-fabrication: unchanged.
- **CRAIC & THROTTLE** kicker + writer prompts.

Result: the very next run produced **16 view-ranked candidates** and a full 5-item desk
(Taskmaster + Sarah Millican alongside the Irish regulars); published live in all six
languages with complete audio by 15:16 UTC.

## Where it stumbled

1. Missed `test_integrity_guardrails.py` in the TDD sweep — it still asserted the old
   fun-floor HOLD and failed the full suite once. Grep for the BEHAVIOUR you're changing
   across ALL test files before declaring red→green done.
2. Two background pytest runs raced file edits again (same as yesterday). Foreground the
   suite when the working tree is hot.

## The one change I'm proposing

**A worker that catches its subprocess failure and returns `ok:false` is lying to its
orchestrator.** Conductor's entire visual/retry model keys on task *status* — failure flags
in output data are invisible. Filed as fleet#121 with a v4 workflow design (fail properly,
SWITCH on holds → visible `message_graham`, FORK_JOIN_DYNAMIC per language with
`concurrentExecLimit` for the shared GPU). If approved, the pattern goes into the
`managing-with-conductor` skill — that's the generalisable piece.
