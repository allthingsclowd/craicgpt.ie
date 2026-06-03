"""
content_pipeline/content_config.py
==================================
Configuration for the **daily content engine** (the fun-news + AI-landscape
paper), kept deliberately separate from the legacy comparator config in
``config.py``.

TUTORIAL: One integration point, many models
---------------------------------------------
Everything routes through the grazlab **LiteLLM proxy**, which speaks the
OpenAI wire format for both chat *and* image generation. So the whole fleet —
Qwen3.6 on the M3 Ultra, Qwen3-Coder, a frontier fallback, FLUX.2 Klein for
images — is reachable by changing a single ``model`` string. We never hard-code
an engine URL; we name a route and let LiteLLM place it on the right box.

All values are environment-driven (12-factor). Defaults match the current
grazlab catalog so a bare ``source .env`` Just Works on the homelab.
"""

import os
from dataclasses import dataclass, field


@dataclass
class ContentConfig:
    """Model routes and endpoints for the daily content engine."""

    # ── LiteLLM proxy (single integration point) ──────────────────────────────
    # Public HTTPS, no auth required (LiteLLM accepts a dummy key).
    litellm_base_url: str = field(
        default_factory=lambda: os.getenv(
            "LITELLM_BASE_URL", "https://llm.grazlab.thescriptingpaddy.com/v1"
        )
    )
    litellm_api_key: str = field(
        default_factory=lambda: os.getenv("LITELLM_API_KEY", "sk-no-key-required")
    )

    # ── Model routes (names from grazlab catalog/models.yaml) ─────────────────
    # The *writing* model — generates the article prose. Qwen3.6 per Graham.
    write_model: str = field(
        default_factory=lambda: os.getenv(
            "WRITE_MODEL", "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit"
        )
    )
    # The *research brain* — drives the agentic websearch/curation tool loop.
    # Needs reliable tool-calling. The DGX vLLM Qwen3.6 route is confirmed
    # tool-calling-capable (and is itself Qwen3.6); the M3 mlx coder route is a
    # good alternative when that engine is up. The fallback wrapper covers either
    # being down.
    brain_model: str = field(
        default_factory=lambda: os.getenv(
            "BRAIN_MODEL", "dgx/vllm/qwen3.6-35b-a3b-fp8"
        )
    )
    # The image model — FLUX.2 Klein. Approved fallback: z-image-turbo.
    image_model: str = field(
        default_factory=lambda: os.getenv("IMAGE_MODEL", "m3/ollama/flux2-klein")
    )
    # Frontier safety net. Used ONLY when a local call fails or fails validation.
    fallback_text_model: str = field(
        default_factory=lambda: os.getenv(
            "FALLBACK_TEXT_MODEL", "claude-sonnet-4-6"
        )
    )

    # ── Generation parameters ─────────────────────────────────────────────────
    temperature: float = field(
        default_factory=lambda: float(os.getenv("CONTENT_TEMPERATURE", "0.8"))
    )
    # Per-call output cap. Kept well below the model's context window so a long
    # agentic run (accumulated tool outputs) doesn't blow the input+output total.
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("CONTENT_MAX_TOKENS", "4096"))
    )
    # Summarise the running history once it crosses this many input tokens, to
    # keep long research loops under the model's context window (DGX Qwen3.6 is
    # ~98k; 60k leaves comfortable headroom for the next prompt + output).
    summarize_at_tokens: int = field(
        default_factory=lambda: int(os.getenv("CONTENT_SUMMARIZE_AT_TOKENS", "60000"))
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("CONTENT_REQUEST_TIMEOUT", "180"))
    )

    # ── Daily composition (resolved during grilling: 13 AI + 5 fun) ───────────
    num_ai_shorts: int = field(
        default_factory=lambda: int(os.getenv("NUM_AI_SHORTS", "10"))
    )
    num_ai_subarticles: int = field(
        default_factory=lambda: int(os.getenv("NUM_AI_SUBARTICLES", "2"))
    )
    num_fun_stories: int = field(
        default_factory=lambda: int(os.getenv("NUM_FUN_STORIES", "5"))
    )

    # ── Publishing ────────────────────────────────────────────────────────────
    # Draft editions land under this prefix (noindex) pending human approval;
    # approved editions are promoted to the live ``content/`` prefix.
    preview_prefix: str = field(
        default_factory=lambda: os.getenv("S3_PREVIEW_PREFIX", "preview")
    )
    content_prefix: str = field(
        default_factory=lambda: os.getenv("S3_CONTENT_PREFIX", "content")
    )
    s3_bucket: str = field(
        default_factory=lambda: os.getenv("S3_BUCKET", "craicgpt-ie-production")
    )
    aws_region: str = field(
        default_factory=lambda: os.getenv("AWS_REGION", "eu-west-1")
    )
    cloudfront_distribution_id: str = field(
        default_factory=lambda: os.getenv("CLOUDFRONT_DISTRIBUTION_ID", "")
    )
    site_base_url: str = field(
        default_factory=lambda: os.getenv("SITE_BASE_URL", "https://craicgpt.ie")
    )
    # Local scratch dir where the image tool writes generated PNGs before publish
    # uploads them. Keeps base64 out of the agent's context window.
    image_dir: str = field(
        default_factory=lambda: os.getenv("CRAICGPT_IMAGE_DIR", "/tmp/craicgpt-images")
    )

    # ── Operator notifications (Telegram) ─────────────────────────────────────
    # The .75 engine fans edition-lifecycle alerts (generated / published / held)
    # out to BOTH agents' channels so a silent HOLD can never go unseen again.
    # Each agent has its OWN bot (own token); both DM the same operator chat
    # (Graham). A per-agent chat id can override the shared default. Any channel
    # whose token+chat are unset is silently skipped (fail-soft).
    telegram_openclaw_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_OPENCLAW_BOT_TOKEN", "")
    )
    telegram_hermes_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_HERMES_BOT_TOKEN", "")
    )
    # Operator's Telegram chat id (the bots' allowlisted recipient).
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )
    telegram_openclaw_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_OPENCLAW_CHAT_ID", "")
    )
    telegram_hermes_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_HERMES_CHAT_ID", "")
    )


# Module-level singleton, mirroring the ``cfg`` pattern in config.py.
content_cfg = ContentConfig()
