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
    """A generated image plus the model that made it.

    The proxy may return the image inline (``b64_png``) or as a ``url`` depending
    on the backend (Ollama image routes vary), so we carry whichever we got.
    """

    model: str
    prompt: str
    b64_png: Optional[str] = None
    url: Optional[str] = None

    def to_bytes(self) -> bytes:
        """Return the raw PNG bytes (decoding b64, or fetching the URL)."""
        if self.b64_png:
            return base64.b64decode(self.b64_png)
        if self.url:
            import httpx

            return httpx.get(self.url, timeout=60, follow_redirects=True).content
        raise ValueError("GeneratedImage has neither b64_png nor url")


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
    # NB: do NOT pass response_format — the Ollama image routes reject it
    # (LiteLLM 400 UnsupportedParamsError). Read whichever field comes back.
    resp = cli.images.generate(model=model, prompt=prompt, size=size)
    datum = resp.data[0]
    return GeneratedImage(
        model=model,
        prompt=prompt,
        b64_png=getattr(datum, "b64_json", None),
        url=getattr(datum, "url", None),
    )


def save_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    client: Optional[Any] = None,
) -> tuple[str, str]:
    """Generate an image for ``prompt`` and save it to the scratch dir.

    Returns ``(local_path, model_used)``. Content-addressed filename so repeat
    prompts don't pile up. Shared by the editor tool and the harness's
    deterministic per-fun-story image step.
    """
    import hashlib
    import os

    img = generate_image(prompt, model=model, client=client)
    os.makedirs(content_cfg.image_dir, exist_ok=True)
    fname = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] + ".png"
    path = os.path.join(content_cfg.image_dir, fname)
    with open(path, "wb") as fh:
        fh.write(img.to_bytes())
    return path, img.model
