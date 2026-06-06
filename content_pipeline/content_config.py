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


# A real browser User-Agent. Searching / fetching / validating links from a bot
# UA ("CraicGPT/1.0") gets blocked or 429'd from the datacenter IP; present as a
# normal browser instead. (The 2026-06-04 hallucination traced back to 429s.)
WEB_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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
    # The *writing* model — generates the article prose. Qwen3.6 on the DGX (vLLM).
    # The M3 mlx qwen3.6 route was never a reliable backend (500 connection errors), so
    # the writer uses the DGX vLLM qwen3.6 — the same healthy route as the brain.
    write_model: str = field(
        default_factory=lambda: os.getenv(
            "WRITE_MODEL", "dgx/vllm/qwen3.6-35b-a3b-fp8"
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
    # The image model. HiDream-O1 (MLX on the M3 Ultra) is the approved default:
    # it renders brand text/wordmarks far more reliably than FLUX.2 Klein (which
    # scrawled garbled faux-text whenever a subject had proper nouns), so it's our
    # path to images that can eventually carry tasteful typography. Until then we
    # still prompt text-free (see generate/image_styles.py). Approved fallback:
    # z-image-turbo. Target: a Qwen-Image route, once promoted in the fleet catalog.
    image_model: str = field(
        default_factory=lambda: os.getenv("IMAGE_MODEL", "m3/mlx/hidream-o1-image-dev")
    )
    # Approved image FALLBACK — used when the primary image route is down. z-image-turbo
    # is on the M3 OLLAMA server, a DIFFERENT process than hidream (M3 mlx), so it survives
    # an mlx outage. (hidream's mlx backend 500'd 2026-06-06 → editions HELD on missing
    # images, which host validation requires — so a working fallback is load-bearing.)
    image_fallback_model: str = field(
        default_factory=lambda: os.getenv("IMAGE_FALLBACK_MODEL", "m3/ollama/z-image-turbo")
    )
    # ── Web search: Serper.dev (Google SERP) API. Replaced Brave (2026-06): Brave
    # killed its free API tier in Feb 2026 (→ metered + a small monthly credit), so the
    # agent's ~80 searches/run blew the quota and 429'd. Serper is cheaper ($0.30–1 /1k)
    # with a 2,500/mo free tier. Key from 1Password AgentCredentials (item "serper.dev",
    # field "API Key") → SERPER_API_KEY in /etc/craicgpt.env on the host. Never commit it.
    serper_api_key: str = field(
        default_factory=lambda: os.getenv("SERPER_API_KEY", "")
    )
    # ── Integrity floors: minimum REAL, link-validated candidates per desk before
    # we'll write an edition. Below these the run HOLDS rather than fabricate/thin.
    # AI default 11 = the structural floor in review.py (headliner 1 + MIN_SUBARTICLES
    # 2 + MIN_SHORTS 8): below it the page literally can't be valid, so we HOLD at
    # research time with a clear reason instead of limping to a gate HOLD. Fun
    # default 4 = review.MIN_FUN.
    min_ai_sources: int = field(
        default_factory=lambda: int(os.getenv("MIN_AI_SOURCES", "11"))
    )
    min_fun_sources: int = field(
        default_factory=lambda: int(os.getenv("MIN_FUN_SOURCES", "4"))
    )
    # How far back the curated AI-source feed harvest looks (hours). 48h covers
    # weekends/quiet days so the AI desk reliably clears its floor from real, dated
    # items (see research/feeds.py + research/ai_sources.py).
    ai_feed_hours: int = field(
        default_factory=lambda: int(os.getenv("AI_FEED_HOURS", "48"))
    )
    # How far back the Irish-creator fun harvest looks (hours). Wider than the AI
    # window (96h ≈ 4 days) because creators upload only a few times a week — too
    # narrow a window leaves fewer than 5 DISTINCT creators with fresh content, and
    # the desk collapses to 2-3 sources. With per-creator diversity selection, a
    # wider pool is what lets every edition field five different creators.
    fun_feed_hours: int = field(
        default_factory=lambda: int(os.getenv("FUN_FEED_HOURS", "96"))
    )
    # Fallback model — used ONLY when the primary local call fails or fails validation.
    # NB: the grazlab LiteLLM proxy has NO frontier route (`claude-sonnet-4-6` was a DEAD
    # route → HTTP 400), so the fallback is the OTHER box's qwen3.6 (M3 mlx) — a real
    # cross-box safety net for when the DGX is down.
    fallback_text_model: str = field(
        default_factory=lambda: os.getenv(
            "FALLBACK_TEXT_MODEL", "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit"
        )
    )
    # The RUBRIC JUDGE — grades the finished edition (harmless / on-brand / attributed)
    # via a deepagents RubricMiddleware, replacing the old two-VM (openclaw+hermes)
    # consensus. The grader needs STRUCTURED TOOL-CALLING *and* a model strong enough to
    # drive the RubricMiddleware reviewer-agent loop to a clean stop.
    #
    # INTERIM (June 2026): the judge is the WRITER's qwen3.6 on the DGX (vLLM) — local +
    # reliable (it drives the agent loop and terminates), but NOT independent (the author
    # marks its own homework). An independent local judge is the goal; it is paused on a
    # model problem:
    #   • gemma-4-12b-it-nothink (a *different* family → would be independent) tool-calls
    #     cleanly and fast PER CALL, but a 12B does NOT terminate the deepagents reviewer
    #     loop — on a real edition one grade_edition invoke made 490+ LLM calls with no
    #     verdict, which would also hang the autonomous run. Being fixed offline (repro +
    #     validation test in rubric_review.py "Switching the judge").
    #   • Path back to independent: the gemma fix, OR a capable non-writer LOCAL route
    #     (~30B+ that drives the agent loop). NB the proxy has NO frontier route.
    #
    # TO CHANGE IT (no code edit needed): set the JUDGE_MODEL env var (on the host, in
    #   /etc/craicgpt.env) to another route that (a) emits real tool_calls and (b)
    #   TERMINATES the grader loop in a handful of calls (not hundreds) — see
    #   rubric_review.py "Switching the judge".
    judge_model: str = field(
        default_factory=lambda: os.getenv("JUDGE_MODEL", "dgx/vllm/qwen3.6-35b-a3b-fp8")
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
