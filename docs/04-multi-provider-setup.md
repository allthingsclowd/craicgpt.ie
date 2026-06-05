# 04 — One LiteLLM Proxy, Many Models

## The core insight

In v2 the code juggled three SDKs (`ChatAnthropic`, `ChatGoogleGenerativeAI`, a localhost
`ChatOpenAI`). v3 keeps the same LangChain `ChatModel` abstraction but points it at **one
integration point**: the grazlab **LiteLLM proxy**. LiteLLM speaks the OpenAI wire format
for **both chat and image generation**, and routes by **model name** across the whole
fleet. So we never hard-code an engine URL — we name a route and let LiteLLM place it on
the right box.

```python
# content_pipeline/providers/litellm.py
from langchain_openai import ChatOpenAI

def get_litellm_llm(model, *, temperature=None, max_tokens=None, extra_body=None):
    return ChatOpenAI(
        model=model,                              # e.g. "dgx/vllm/qwen3.6-35b-a3b-fp8"
        base_url=content_cfg.litellm_base_url,    # the ONE proxy
        api_key=content_cfg.litellm_api_key,      # "sk-no-key-required" — LiteLLM accepts a dummy
        temperature=content_cfg.temperature if temperature is None else temperature,
        max_tokens=content_cfg.max_tokens if max_tokens is None else max_tokens,
        timeout=content_cfg.request_timeout,
        max_retries=2,
        **({"extra_body": extra_body} if extra_body else {}),
    )
```

Construction does **no** network I/O — the endpoint is only hit on `.invoke()`. Want a
different model? Change the string. That's the whole multi-provider story.

---

## The grazlab fleet behind the proxy

| Box | Role | Example routes |
|-----|------|----------------|
| **DGX Spark** | Research brain (reliable tool-calling) | `dgx/vllm/qwen3.6-35b-a3b-fp8` |
| **M3 Ultra (Mac Studio)** | Prose + images | `m3/mlx/qwen3.6-35b-a3b-unsloth-8bit`, `m3/mlx/hidream-o1-image-dev` |
| **Frontier provider** | Fallback only | `claude-sonnet-4-6` |

Route names come from the fleet catalog (`grazlab-llm-fleet` repo, `catalog/models.yaml`).
Promoting a new model there makes it reachable here by name — no code change. The proxy
itself is public HTTPS (`https://llm.grazlab.thescriptingpaddy.com/v1` by default), so the
same `.env` works from a laptop or the Conductor host.

---

## The three roles the engine binds

The config picks a route per *role* (override any with an env var):

```python
# content_pipeline/content_config.py
brain_model         = os.getenv("BRAIN_MODEL",        "dgx/vllm/qwen3.6-35b-a3b-fp8")          # research agent loop
write_model         = os.getenv("WRITE_MODEL",        "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit")   # article prose
image_model         = os.getenv("IMAGE_MODEL",        "m3/mlx/hidream-o1-image-dev")           # illustrations
fallback_text_model = os.getenv("FALLBACK_TEXT_MODEL", "claude-sonnet-4-6")                     # frontier safety net
```

- **brain** needs solid tool-calling (it drives the agentic search/curation loop) — the
  DGX vLLM Qwen3.6 route is confirmed tool-calling-capable.
- **write** produces the prose; Qwen3.6 on the M3 handles the small structured calls well.
- **image** is HiDream-O1 (MLX on the M3): it renders brand text/wordmarks far more
  reliably than FLUX.2 Klein (which scrawled garbled faux-text on proper nouns). Approved
  fallback: `z-image-turbo`. (We still prompt text-free for now — see `generate/image_styles.py`.)

---

## Per-model quirks you set via `extra_body`

LiteLLM forwards extra request fields to the engine. The most important one here: Qwen3.6
emits a "thinking" preamble that can eat the whole token budget before any JSON appears, so
the engine disables it:

```python
get_litellm_llm(
    "dgx/vllm/qwen3.6-35b-a3b-fp8",
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
```

This is the v3 analogue of v2's `convert_system_message_to_human=True` Gemini quirk — a
single place to encode "what this particular model needs", without leaking it into the
chain code.

---

## Local-first, frontier-fallback (the open-source-first contract)

We *want* the local models to do the work — that's the point of the project, and it's what
the published "_text_model" note should usually say. But a flaky local run shouldn't ship a
dud. `run_with_fallback` tries local, validates the output, and only on failure retries on
the frontier — recording which model actually ran (honest attribution) and why local
failed (so the eval loop can turn it into a regression case):

```python
result = run_with_fallback(
    fn=lambda model: write_with(model, inputs),
    local_model=content_cfg.write_model,
    fallback_model=content_cfg.fallback_text_model,
    validate=lambda out: bool(out and out.get("headliner")),
)
# result.model_used → stamped as the piece's _text_model; result.fell_back / result.error logged
```

If both attempts fail it raises — never a silent dud. See
[02-lcel-and-chains.md](02-lcel-and-chains.md) for the full pattern.

---

## Environment Variables Summary

```bash
# .env (local) or /etc/craicgpt.env (host) — never commit

LITELLM_BASE_URL=https://llm.grazlab.thescriptingpaddy.com/v1
LITELLM_API_KEY=sk-no-key-required

BRAIN_MODEL=dgx/vllm/qwen3.6-35b-a3b-fp8
WRITE_MODEL=m3/mlx/qwen3.6-35b-a3b-unsloth-8bit
IMAGE_MODEL=m3/mlx/hidream-o1-image-dev
FALLBACK_TEXT_MODEL=claude-sonnet-4-6

BRAVE_SEARCH_API_KEY=brv-...        # web_search (doc 05)

S3_BUCKET=craicgpt-ie-production
CLOUDFRONT_DISTRIBUTION_ID=E1...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

---

## Running your own proxy

No grazlab? Stand up LiteLLM in front of whatever you have (Ollama, vLLM, an MLX server, a
frontier key) and point `LITELLM_BASE_URL` at it. Name your routes in LiteLLM's config,
then set `BRAIN_MODEL`/`WRITE_MODEL`/`IMAGE_MODEL`/`FALLBACK_TEXT_MODEL` to those names.
The engine code doesn't change — that's the point of routing by name through one proxy.

---

## Where to Find This in the Craic Gazette

| Concept | File |
|---------|------|
| Model factory | `content_pipeline/providers/litellm.py` (`get_litellm_llm`) |
| Local-first fallback | `content_pipeline/providers/litellm.py` (`run_with_fallback`) |
| Route + parameter config | `content_pipeline/content_config.py` |
| Fleet catalog (source of route names) | `grazlab-llm-fleet` repo → `catalog/models.yaml` |

---

## Key Takeaway

> One `base_url`, many models. `get_litellm_llm("<route>")` reaches any box on the fleet by
> name; `run_with_fallback` keeps the work open-source-first and falls back to a frontier
> model only when it has to — honestly recording which one ran.
