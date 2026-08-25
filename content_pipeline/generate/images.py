"""
content_pipeline/generate/images.py
====================================
Image generation via the grazlab LiteLLM proxy (primary route + approved fallback).

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
    steps: Optional[int] = None,
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
    client: Optional[Any] = None,
    fallback_model: Optional[str] = None,
) -> GeneratedImage:
    """Generate one image for ``prompt`` via the LiteLLM proxy.

    Args:
        prompt: The image description (the editor builds this from the story).
        model: Image route; defaults to ``content_cfg.image_model``.
        size: Output dimensions. Free-form on the ComfyUI route, but BOTH numbers
            must be multiples of 16 or the shim 400s (it checks before queueing, so
            a bad size costs no GPU time).
        steps: Sampler steps. The workflow bakes 28; passing fewer is the single
            biggest cost lever available — 1024x1024 measured 727 s at 28 steps and
            201 s at 8 (issue #105).
        seed: Fixed seed for a reproducible render. Omitting it means a fresh random
            one, deliberately: ComfyUI caches on an unchanged graph, so a pinned seed
            with an unchanged prompt returns the CACHED picture rather than re-rendering.
        negative_prompt: What to keep OUT of the frame. A far stronger lever than a
            "do not draw X" clause inside the positive prompt — diffusion models are
            poor at negation.
        client: An OpenAI-compatible client (injected in tests). Defaults to a
            client bound to the LiteLLM proxy.

    Returns:
        A :class:`GeneratedImage` carrying the base64 PNG and the model used.
    """
    model = model or content_cfg.image_model
    fb = fallback_model if fallback_model is not None else content_cfg.image_fallback_model
    cli = client if client is not None else _default_client()
    # Try the primary route, then the approved fallback — a DIFFERENT M3 server (Ollama),
    # so an mlx outage doesn't hold the whole edition on missing images. NB: do NOT pass
    # response_format — the Ollama image routes reject it (LiteLLM 400).
    routes = [model] + ([fb] if fb and fb != model else [])

    # steps/seed/negative_prompt are NOT typed kwargs on the OpenAI SDK, so they must
    # travel in extra_body or they are dropped before the wire. DANGER: the shim ignores
    # anything it does not recognise and returns HTTP 200 with a FULL-COST image, so a
    # typo (`num_steps`, `num_inference_steps`) is indistinguishable from success.
    # Verify any change here by WALL-CLOCK, never by a 200. The reachable parameters are
    # exactly steps / seed / size / negative_prompt — cfg, sampler and scheduler are
    # baked into the ComfyUI workflow and cannot be reached from a request (issue #105).
    extra: dict[str, Any] = {}
    if steps is not None:
        extra["steps"] = steps
    if seed is not None:
        extra["seed"] = seed
    if negative_prompt:
        extra["negative_prompt"] = negative_prompt

    last_exc: Optional[Exception] = None
    for route in routes:
        logger.info("[images] generating model=%s size=%s steps=%s", route, size, steps)
        try:
            kwargs: dict[str, Any] = {"model": route, "prompt": prompt, "size": size}
            if extra:
                kwargs["extra_body"] = extra
            resp = cli.images.generate(**kwargs)
            datum = resp.data[0]
            return GeneratedImage(
                model=route,
                prompt=prompt,
                b64_png=getattr(datum, "b64_json", None),
                url=getattr(datum, "url", None),
            )
        except Exception as exc:  # noqa: BLE001 — try the fallback route before giving up
            logger.warning("[images] model=%s failed (%s)%s", route, exc,
                           "; trying fallback" if route != routes[-1] else "")
            last_exc = exc
    raise last_exc if last_exc else RuntimeError("no image route attempted")


def save_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    size: str = "1024x1024",
    steps: Optional[int] = None,
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
    client: Optional[Any] = None,
) -> tuple[str, str]:
    """Generate an image for ``prompt`` and save it to the scratch dir.

    Returns ``(local_path, model_used)``. Shared by the editor tool and the harness's
    deterministic per-item image step.

    The filename is content-addressed over the prompt AND the full render spec, not the
    prompt alone. That matters now one prompt can be rendered at two tiers: hashing the
    prompt only would make a 512x512 8-step thumbnail collide with a 1024x1024 28-step
    hero and silently serve whichever landed first.
    """
    import hashlib
    import os

    img = generate_image(prompt, model=model, size=size, steps=steps, seed=seed,
                         negative_prompt=negative_prompt, client=client)
    os.makedirs(content_cfg.image_dir, exist_ok=True)
    spec = f"{prompt}|{size}|{steps}|{seed}|{negative_prompt or ''}"
    fname = hashlib.sha256(spec.encode("utf-8")).hexdigest()[:16] + ".png"
    path = os.path.join(content_cfg.image_dir, fname)
    with open(path, "wb") as fh:
        fh.write(img.to_bytes())
    return path, img.model
