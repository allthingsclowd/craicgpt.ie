# ADR 0003 — Ground the rubric judge on an OKF research bundle

- **Status:** Accepted (June 2026)
- **Context:** craicgpt edition pipeline; mirrored in thegeekwiththepeak (its ADR 0001).
- **Supersedes nothing; complements** ADR 0001 (per-article gate) and ADR 0002
  (fun-desk resilience).

## Context

The edition is gated by an **independent rubric judge** (`rubric_review.grade_edition`,
a one-shot `deepagents` `RubricMiddleware` grader on `qwen3-coder-next`, a different
family from the qwen3.6 writer). Its `grading_view` showed the grader only the
**compiled edition** — the `ai_candidates.json` / `fun_candidates.json` research the
deep agent gathered was never threaded in.

So the judge checked claims against its **training data**. A fresh AI story (a model
released after its cutoff, a just-broken event) read as "made up" or "unverifiable",
and the rubric had to lean on a "NEVER fail because you cannot verify" plea — brittle,
and worse whenever the judge model was swapped.

## Decision

Serialize the edition's **curated, link-validated research** as an
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
(OKF v0.1) bundle and hand it to the judge as ground truth.

- New module `content_pipeline/okf/` — a stdlib-only builder (no PyYAML; markdown +
  YAML frontmatter, one concept per finding). The craicgpt mapper turns each
  validated AI candidate into an `AI Story` concept (carrying why-it-matters, key
  points, conclusion, source) and each curated fun pick into a `Fun Story` concept
  (carrying the creator credit).
- `editor_in_chief.run_edition` builds the bundle from the curated `ai_valid` +
  `fun_picks` (the very candidates the articles are written from, so every published
  claim has a backing concept) and attaches it to `paper["edition"]["okf"]` — so it
  rides with the edition (in-flight to the judge, and persisted as provenance). No new
  Conductor box: craicgpt keeps orchestration in the engine; Conductor is a thin
  trigger.
- `rubric_review.grading_view` prepends the flattened bundle as an authoritative
  ground-truth block; `EDITION_RUBRIC` now names the bundle as the judge's
  verification source. The judge stays a publish-**safety** gate — it can now confirm
  the desk is substantive and real instead of guessing.

The judge remains independent: the bundle is *research*, not the writer's reasoning.

## Consequences

- Fresh stories no longer false-HOLD; the fix is **model-agnostic** (survives a judge
  swap — the original trigger).
- The bundle persists on the published paper as a provenance record of what grounded
  the verdict.
- An edition with no research emits **no** bundle (an empty one would read as "all
  unsupported"); the integrity floors already hold that case.
- Also fixed the stale `rubric_review` module docstring (it claimed the judge was the
  writer's qwen3.6 "INTERIM"; the live default is the independent `qwen3-coder-next`).
- Format only — no dependency on Google's `enrichment-agent` or the `mdcode`/`kcmd`
  toolchain.
