# ADR 0001 — Per-article publish gate (drop the hallucination, publish the rest)

- **Status:** Accepted (implemented `feat/per-article-gate`)
- **Date:** 2026-06-15

## Context

The publish gate was **edition-level**: the rubric judge returns ONE verdict for the
whole paper, so a single hallucinated article holds the *entire* edition. On
2026-06-15 the AI **headliner** was fabricated ("US Commerce Dept ordered Anthropic
to kill non-existent models… 'Pliny the Liberator'") while the shorts and fun items
were all fine — and the whole edition was held, so we shipped nothing.

Two distinct problems:
1. **All-or-nothing.** One bad article ⇒ zero content. We want to drop the bad
   article(s) and publish the valid rest.
2. **The passive-publish hole.** A *judgement* (rubric) HOLD passive-publishes after
   the HITL window if the edition is **structurally** valid. Today's fabricated
   edition *was* structurally valid (live snapped URL, image, body), so the
   safety gate's own timeout **auto-published the hallucination** at ~08:15. The
   gate overrode its own catch.

Hallucinations come in two shapes, caught differently:
- **Dead/fabricated link** → deterministic (`_check_links` / `validate_source_link`).
- **Fabricated content** (real-looking live source, invented claims) → only the LLM
  judge reading the article catches it. Today's was this kind.

## Decision

A **per-article gate** that runs at **generation time** (before the edition rubric and
before narration), reusing the existing hard-hold path:

1. **Bad set** = dead-link refs (deterministic) ∪ fabricated refs (one **batched**
   per-article LLM grade — `article_review.grade_articles`, thinking-off for clean
   JSON, local-first w/ frontier fallback, bounded call count). The grade **fails
   safe**: no usable verdict ⇒ hard hold.
2. **Drop & publish the rest** (`article_review.auto_remediate`): drop the bad
   articles by layout ref, **rebuild the index-based layout**, and publish the clean
   edition — provided it still clears the structural floors (`MIN_SUBARTICLES=2`,
   `MIN_SHORTS=8`; fun has no floor).
3. **Headliner** is special (can't just be dropped): a fabricated headliner is
   replaced by **promoting** the best valid story (image-bearing subarticle/fun). If
   none qualifies, or the cleaned edition is below floor, **HARD hold**.
4. **Hard vs soft hold.** An unfixable fabrication raises `EditionHeld` → `status=failed`,
   which the gate **never publishes** and which **cannot passive-publish**. This is the
   fix for problem 2: a fabrication hold is now hard, not a soft judgement hold.
5. **Podcast on published content.** Because the gate runs in `run_edition` before the
   draft is written, the preview draft is already de-fabricated, so the narration step
   (which reads that draft) covers only the surviving, published articles — no separate
   change needed.

The edition rubric (`rubric_review`) **stays** as the harmless/defamation/attribution
backstop on the *cleaned* edition; the per-article gate handles the fabrication axis.

## Alternatives considered

- **Deterministic-drop only** (no per-article LLM): cheaper, but would NOT have caught
  today's case (live URL + fabricated claims). Rejected — it's the main failure mode.
- **Per-article grading at gate time** (every 10-min poll): wasteful (LLM per poll) and
  doesn't fix podcast-on-published. Rejected for **generation-time** (one grade, clean
  draft, reuses `EditionHeld`).
- **Per-article LLM call per article** (N calls): runaway-cost risk (the gemma-490-call
  lesson). Rejected for **one batched call** returning the fabricated refs.

## Consequences

- Reuses the proven `EditionHeld` → `status=failed` hard-hold path; no gate rewrite.
- Fixes a latent bug: `remove_items` (human remediate) didn't rebuild the layout.
- Injectable (`link_ok`, `grade`, `remediate`) ⇒ fully offline unit tests.
- A fabricated headliner with only 2 subarticles still hard-holds (promotion would
  drop below the sub floor) — honest: an unfixable lead is a human/regenerate case.
- **Follow-up:** the daily Conductor chain (generate → narrate → gate) already narrates
  the cleaned draft because the gate runs inside generation — confirm the worker order
  on `.75`/grazlab-llm-fleet. Optionally tune `MIN_SUBARTICLES` to let a promoted
  headliner survive with one remaining subarticle.

## Files

`content_pipeline/agent/article_review.py` (grade_articles, auto_remediate),
`compile.recompile_layout`, `review.drop_refs` (+ `remove_items` layout fix),
`editor_in_chief.run_edition` (`remediate=` hook), `cli.cmd_run` (wires `auto_remediate`).
Tests: `tests/test_article_review.py`, `tests/test_article_remediation.py`.
