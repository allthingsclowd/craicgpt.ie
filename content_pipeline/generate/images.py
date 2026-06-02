"""
content_pipeline/generate/images.py
====================================
FLUX image generation via the grazlab LiteLLM proxy.

The proxy exposes the OpenAI **images** API (``/v1/images/generations``), so an
image is one ``client.images.generate(...)`` call away — the same OpenAI-shaped
interface used for chat. We pull the base64 PNG and record which model produced
it (for the published attribution note).

The OpenAI client is injected, so the parsing logic is unit-testable offline.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)


@dataclass
class GeneratedImage:
    """A generated image plus the model that made it."""

    b64_png: str
    model: str
    prompt: str

    def to_bytes(self) -> bytes:
        """Decode the base64 PNG to raw bytes (for saving / uploading)."""
        return base64.b64decode(self.b64_png)


def _default_client() -> Any:
    """Build an OpenAI client pointed at the LiteLLM proxy (lazy import)."""
    from openai import OpenAI

    return OpenAI(
        base_url=content_cfg.litellm_base_url,
        api_key=content_cfg.litellm_api_key,
    )


def generate_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    size: str = "1024x1024",
    client: Optional[Any] = None,
) -> GeneratedImage:
    """Generate one image for ``prompt`` via the LiteLLM proxy.

    Args:
        prompt: The image description (the editor builds this from the story).
        model: Image route; defaults to the configured FLUX route.
        size: Output dimensions.
        client: An OpenAI-compatible client (injected in tests). Defaults to a
            client bound to the LiteLLM proxy.

    Returns:
        A :class:`GeneratedImage` carrying the base64 PNG and the model used.
    """
    model = model or content_cfg.image_model
    cli = client if client is not None else _default_client()
    logger.info("[images] generating model=%s size=%s", model, size)
    resp = cli.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        response_format="b64_json",
    )
    b64 = resp.data[0].b64_json
    return GeneratedImage(b64_png=b64, model=model, prompt=prompt)
