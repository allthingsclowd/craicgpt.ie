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
    # A proven tool-calling route, NOT Qwen3.6 (text-only / unproven for tools).
    brain_model: str = field(
        default_factory=lambda: os.getenv(
            "BRAIN_MODEL", "m3/mlx/qwen3-coder-next-4bit"
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
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("CONTENT_MAX_TOKENS", "8192"))
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


# Module-level singleton, mirroring the ``cfg`` pattern in config.py.
content_cfg = ContentConfig()
