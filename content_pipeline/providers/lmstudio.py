"""
content_pipeline/providers/lmstudio.py
========================================
LM Studio (local, OpenAI-compatible) provider for the CraicGPT pipeline.

TUTORIAL: ChatOpenAI with a Custom base_url
--------------------------------------------
This is the KEY teaching moment of the whole pipeline: LangChain's ChatOpenAI
class can point at ANY OpenAI-compatible API endpoint, not just OpenAI's cloud.

LM Studio runs on your home machine and exposes an OpenAI-compatible server at:
    http://localhost:1234/v1

By changing just `base_url` (and optionally `model`), the exact same LCEL chain
code that called GPT-4 now calls your local Llama 3.2, Phi-4, Mistral, etc.

This is the portability that makes LangChain powerful for comparing providers:
  - Same chain code
  - Same prompt templates
  - Same output parsers
  - Just a different `base_url` and model name

Setting up LM Studio:
  1. Download LM Studio: https://lmstudio.ai/
  2. Download a model (e.g. "meta-llama/llama-3.2-3b-instruct")
  3. Go to "Local Server" tab → Start Server
  4. Confirm it's running at http://localhost:1234

The model name in LM Studio's API is usually shown in the server UI —
set LM_STUDIO_MODEL env var to match, or use "local-model" as a wildcard.
"""

import logging

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)


def get_lmstudio_llm() -> BaseChatModel:
    """
    Return a ChatOpenAI instance pointing at LM Studio's local server.

    TUTORIAL: The magic is in `base_url`. Swapping this to a different URL
    (e.g. an Ollama server at http://localhost:11434/v1) requires zero other
    code changes. The LangChain interface is completely provider-agnostic.

    Returns:
        A ChatOpenAI instance configured for LM Studio.

    Raises:
        ValueError: If the LM Studio server URL is clearly invalid.
    """
    logger.info(
        f"[provider:lmstudio] Initialising model={cfg.providers.lm_studio_model} "
        f"base_url={cfg.providers.lm_studio_base_url} "
        f"temperature={cfg.providers.temperature}"
    )

    # TUTORIAL: When using LM Studio (or Ollama), you need to disable the
    # OpenAI client's SSL verification on localhost — there's no HTTPS cert.
    # The `http_client` parameter lets you pass a custom httpx client.
    import httpx

    http_client = httpx.Client(
        # Trust localhost connections without a valid SSL cert.
        verify=False,
        timeout=120.0,  # Local inference can be slow — be generous here.
    )

    return ChatOpenAI(
        model=cfg.providers.lm_studio_model,
        base_url=cfg.providers.lm_studio_base_url,
        # LM Studio accepts any non-empty string as the API key.
        api_key=cfg.providers.lm_studio_api_key,
        temperature=cfg.providers.temperature,
        max_tokens=cfg.providers.max_tokens,
        # TUTORIAL: max_retries=1 for local models — if the server is down,
        # fail fast rather than retrying. The orchestrator handles local LLM
        # failures gracefully (shows "unavailable" in the comparator).
        max_retries=1,
        http_client=http_client,
    )
