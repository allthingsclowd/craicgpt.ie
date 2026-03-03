"""
content_pipeline/providers/claude.py
======================================
Anthropic Claude provider for the CraicGPT pipeline.

TUTORIAL: ChatAnthropic
-------------------------
langchain-anthropic wraps Anthropic's Messages API behind LangChain's standard
ChatModel interface. This means you can swap Claude for Gemini or a local model
with a single line change — the chain code upstream is identical.

Authentication: ANTHROPIC_API_KEY environment variable.
Docs: https://python.langchain.com/docs/integrations/chat/anthropic/

Key parameters:
  model      — Which Claude model to use. Current best: claude-3-5-sonnet-20241022
  temperature — 0.0 (deterministic) → 1.0 (very creative). We use 0.8 for craic.
  max_tokens  — Hard cap on output length. Claude's default is quite long; cap it
                to avoid runaway responses eating your API budget.
"""

import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)


def get_claude_llm() -> BaseChatModel:
    """
    Return a configured ChatAnthropic instance.

    TUTORIAL: Factory Functions
    ----------------------------
    We use a factory function rather than a module-level singleton so the LLM
    object is created fresh each pipeline run. This avoids stale state and
    makes it easy to inject different configs in tests.

    Returns:
        A ChatAnthropic instance ready for use in LCEL chains.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set.
    """
    if not cfg.providers.anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file (local) or GitHub Actions secrets (CI)."
        )

    logger.info(
        f"[provider:claude] Initialising model={cfg.providers.claude_model} "
        f"temperature={cfg.providers.temperature}"
    )

    # TUTORIAL: ChatAnthropic follows the same constructor pattern as
    # ChatOpenAI, ChatGoogleGenerativeAI, etc. That's the point of LangChain —
    # a consistent interface across all providers.
    return ChatAnthropic(
        model=cfg.providers.claude_model,
        api_key=cfg.providers.anthropic_api_key,
        temperature=cfg.providers.temperature,
        max_tokens=cfg.providers.max_tokens,
        # timeout and max_retries are LangChain-level settings (not Anthropic-specific).
        # They apply a consistent retry/timeout policy across all providers.
        timeout=60,
        max_retries=3,
    )
