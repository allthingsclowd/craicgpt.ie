# `shared/enrich` — content-enhancement agent

Attach a **real, recent, CITED** real-world hook to a course item — a breach, an
exploited CVE, an in-the-wild campaign that genuinely illustrates the ATT&CK
tactic (or lesson topic) being taught — framed as a one-line teaching tie-in in
Graham's voice.

Course-agnostic: it takes any item dict with some text and a `topic` string.

## The design in one line

> The **LLM does the judgement** (which real incident fits, how to phrase the
> tie-in); the **code does the plumbing** (build the prompt, parse the reply,
> enforce integrity, route the call, stamp attribution).

This is the house pattern — the same fence as the CraicGPT sibling's
`generate/image_gag.py`.

## Integrity over output

A fabricated hook is worse than no hook: a course that cites a breach which never
happened has lied to its students, and offensive-security students will check. So:

- If the model can't recall a genuinely relevant recent incident, it **declines**
  (`found: false`) and `enrich_item` returns `None`.
- A reply missing a citation, or carrying a placeholder URL (`example.com`…), is
  rejected → `None`.
- An optional injected `verify_url` live-checks the citation; a dead link → `None`.
- `None` means **the caller keeps the item unchanged.** Enrichment is a
  nice-to-have; correctness is not negotiable. The function never raises on a
  model/transport error.

## Usage

```python
from shared.enrich import enrich_item

hook = enrich_item(
    {"title": "Password spraying", "body": "Trying common passwords across many accounts."},
    topic="Valid Accounts (ATT&CK T1078)",
)
if hook:                       # None when nothing genuine was found
    item["_enrichment"] = hook.as_dict()
    # -> {"headline": "...", "tie_in": "...", "source_url": "https://...", "_model": "..."}
```

The LLM boundary is injected, so tests run fully offline:

```python
from shared.enrich.enrich import LLMResponse

class Stub:
    def complete(self, prompt):
        return LLMResponse(
            text='{"found": true, "headline": "The 2024 X breach",'
                 ' "tie_in": "One stolen login, no MFA — exactly this tactic.",'
                 ' "source_url": "https://www.cisa.gov/advisory/x"}',
            model="stub/model",
        )

enrich_item(item, topic="Valid Accounts", llm=Stub())
```

## Model routing

Local-first with a cross-box fallback, routed **by name** through LiteLLM
(`base_url`/key from env). No frontier model anywhere — "fallback" is the other
grazlab box. Defaults are visible and env-overridable:

| Env var | Default |
|---|---|
| `ENRICH_MODEL` | `dgx/vllm/qwen3.8-27b-nvfp4` |
| `ENRICH_FALLBACK_MODEL` | `m3/mlx/qwen3.8-27b-8bit` |
| `LITELLM_BASE_URL` | `https://llm.grazlab.thescriptingpaddy.com/v1` |
| `LITELLM_API_KEY` | `sk-no-key-required` |
| `ENRICH_REQUEST_TIMEOUT` | `120` |

`default_llm()` is a **factory** (reads env at call time — no module-level
singleton), and it imports the LLM SDK **lazily inside the run path**, so
importing this package needs nothing beyond the stdlib.

## Network CLI (not run in tests)

```bash
python -m shared.enrich <module-dir> --topic "Valid Accounts (T1078)" [--write] [--no-verify]
```

Walks `<module-dir>` for `*.json` course items, enriches each against `--topic`,
does a live citation HEAD-check (browser UA, so bot-blocking advisory hosts don't
false-negative), prints the result, and with `--write` stashes the blurb under the
item's `_enrichment` key. This is the only code path that touches the network;
everything under `enrich.py` is pure and offline-testable.

## Tests

`tests/test_enrich.py` — offline, deterministic, stubbed LLM. Covers the happy
path (a valid cited hook → well-formed `Enrichment`) and the integrity paths (a
decline, a placeholder/uncited source, a failing verifier → `None`, no fabrication).
