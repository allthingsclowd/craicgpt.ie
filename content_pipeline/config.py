"""
content_pipeline/config.py
==========================
Central configuration for the CraicGPT content pipeline.

TUTORIAL: Configuration Design Pattern
---------------------------------------
All configuration lives here, driven entirely by environment variables. This makes
the pipeline portable: it runs identically on a developer's laptop, the GitHub
Actions self-hosted runner, or any CI/CD system — only the environment changes.

Environment variables are set in three places (in order of precedence):
  1. GitHub Actions secrets / vars  (production runs)
  2. A local .env file              (development — never committed)
  3. The defaults below             (safe fallbacks for testing)

Usage:
    from content_pipeline.config import cfg
    print(cfg.s3_bucket)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (local development only — ignored in CI).
# The .env file is in the repo root, one level up from this package.
_repo_root = Path(__file__).parent.parent
load_dotenv(_repo_root / ".env", override=False)


# ─────────────────────────────────────────────────────────────────────────────
# Provider Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderConfig:
    """
    Holds all configuration for a single LLM provider.

    TUTORIAL: Why dataclasses?
    frozen=True makes instances immutable — once loaded from env vars, the
    config cannot be accidentally mutated at runtime. Good for reliability.
    """

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    claude_model: str = field(
        default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    )

    # ── Google / Gemini ───────────────────────────────────────────────────────
    google_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "")
    )
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    )

    # ── LM Studio (OpenAI-compatible local endpoint) ──────────────────────────
    # TUTORIAL: LangChain's ChatOpenAI class can target ANY OpenAI-compatible
    # API by overriding base_url. LM Studio exposes this at localhost:1234/v1.
    # This means the same chain code works for OpenAI cloud and local models!
    lm_studio_base_url: str = field(
        default_factory=lambda: os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    )
    lm_studio_api_key: str = field(
        # LM Studio doesn't require a real key, but the SDK needs something.
        default_factory=lambda: os.getenv("LM_STUDIO_API_KEY", "lm-studio")
    )
    lm_studio_model: str = field(
        # "auto" tells LM Studio to use whichever model is currently loaded.
        default_factory=lambda: os.getenv("LM_STUDIO_MODEL", "local-model")
    )

    # ── LLM generation parameters ─────────────────────────────────────────────
    # TUTORIAL: Temperature controls creativity vs. consistency.
    #   0.0 = deterministic (same input → same output every time)
    #   1.0 = very creative / unpredictable
    # For newspaper content we want punchy and creative: 0.8 is a sweet spot.
    temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.8"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "1024"))
    )


@dataclass(frozen=True)
class AWSConfig:
    """AWS configuration for S3 publishing."""
    s3_bucket: str = field(
        default_factory=lambda: os.getenv("S3_BUCKET", "craicgpt-ie-production")
    )
    s3_content_prefix: str = field(
        # Content stored at: content/YYYY/MM/DD/paper_content.json
        default_factory=lambda: os.getenv("S3_CONTENT_PREFIX", "content")
    )
    aws_region: str = field(
        default_factory=lambda: os.getenv("AWS_REGION", "eu-west-1")
    )
    cloudfront_distribution_id: str = field(
        default_factory=lambda: os.getenv("CLOUDFRONT_DISTRIBUTION_ID", "")
    )


@dataclass(frozen=True)
class NewsConfig:
    """Configuration for the research / news-fetching agent."""
    # City used for weather lookups (wttr.in accepts city names or lat,lon).
    weather_location: str = field(
        default_factory=lambda: os.getenv("WEATHER_LOCATION", "Dublin")
    )
    # Number of news headlines to fetch and inject into content prompts.
    num_headlines: int = field(
        default_factory=lambda: int(os.getenv("NUM_HEADLINES", "5"))
    )
    # Search query for DuckDuckGo news tool.
    news_query: str = field(
        default_factory=lambda: os.getenv(
            "NEWS_QUERY", "Ireland tech AI news today"
        )
    )


@dataclass(frozen=True)
class PipelineConfig:
    """
    Top-level config object — the single source of truth for the pipeline.

    TUTORIAL: Composition over inheritance.
    Rather than one giant config class, we compose from focused sub-configs.
    Each sub-config is responsible for one concern (providers, AWS, news...).
    """
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    news: NewsConfig = field(default_factory=NewsConfig)

    # Pipeline behaviour flags.
    dry_run: bool = field(
        # dry_run=True skips the S3 upload — useful for local testing.
        default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true"
    )
    skip_local_llm: bool = field(
        # Set to true in CI if LM Studio isn't running on the runner.
        default_factory=lambda: os.getenv("SKIP_LOCAL_LLM", "false").lower() == "true"
    )
    pipeline_version: str = "2.0"


# ─────────────────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────────────────

# Import this anywhere in the pipeline:
#   from content_pipeline.config import cfg
cfg = PipelineConfig()
