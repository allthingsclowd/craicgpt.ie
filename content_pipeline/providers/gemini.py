"""
content_pipeline/providers/gemini.py
======================================
Google Gemini provider for the CraicGPT pipeline.

TUTORIAL: ChatGoogleGenerativeAI
----------------------------------
langchain-google-genai wraps Google's Generative Language API. Under the hood
it uses the `google-generativeai` Python SDK, but LangChain exposes it through
the same BaseChatModel interface as Claude and OpenAI.

Authentication: GOOGLE_API_KEY environment variable.
Get a free key at: https://aistudio.google.com/app/apikey
Docs: https://python.langchain.com/docs/integrations/chat/google_generative_ai/

Model choices (as of early 2026):
  gemini-2.0-flash       — Fast, cheap, surprisingly capable. Our default.
  gemini-2.0-flash-lite  — Even cheaper, slightly less capable.
  gemini-1.5-pro         — Larger context window (1M tokens!), slower.
  gemini-ultra           — Most capable, most expensive.

TUTORIAL: Why model choices matter for a comparator site
  Different models produce noticeably different writing styles, tones, and
  factual recall. That variation is literally the content of this website!
"""

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)


def get_gemini_llm() -> BaseChatModel:
    """
    Return a configured ChatGoogleGenerativeAI instance.

    Returns:
        A ChatGoogleGenerativeAI instance ready for use in LCEL chains.

    Raises:
        ValueError: If GOOGLE_API_KEY is not set.
    """
    if not cfg.providers.google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/app/apikey "
            "and add it to .env (local) or GitHub Actions secrets (CI)."
        )

    logger.info(
        f"[provider:gemini] Initialising model={cfg.providers.gemini_model} "
        f"temperature={cfg.providers.temperature}"
    )

    return ChatGoogleGenerativeAI(
        model=cfg.providers.gemini_model,
        google_api_key=cfg.providers.google_api_key,
        temperature=cfg.providers.temperature,
        max_output_tokens=cfg.providers.max_tokens,
        # TUTORIAL: convert_system_message_to_human=True is needed because
        # Gemini doesn't natively support a "system" role in its chat API.
        # LangChain handles this by prepending the system message as a human
        # turn. Always check provider-specific quirks like this!
        convert_system_message_to_human=True,
        timeout=60,
        max_retries=3,
    )
