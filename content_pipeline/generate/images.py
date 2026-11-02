"""
content_pipeline/generate/images.py
====================================
Image generation via the grazlab LiteLLM proxy (primary route + a PER-IMAGE fallback).

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
from typing import TYPE_CHECKING, Any, Optional

from content_pipeline.content_config import content_cfg

if TYPE_CHECKING:  # pragma: no cover
    from content_pipeline.generate.image_styles import RenderSpec

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

    # The timeout is NOT optional. Without it the SDK applies its 600 s default — on
    # 2026-08-26 that was SHORTER than a 28-step flux render (~720 s): the client hung up
    # mid-render, the fallback fired, and ComfyUI kept rendering the abandoned job anyway.
    # See content_cfg.image_request_timeout. Since #154 this is only the CEILING: each
    # request carries its own, much shorter, per-image deadline (image_deadline).
    # max_retries=0 is deliberate. The SDK defaults to 2, and on 2026-08-26 that turned a
    # 600 s timeout into a 30-minute stall: three attempts, each launching a SEPARATE
    # 12-minute ComfyUI render, all discarded. Retrying an image generation is not free the
    # way retrying a chat call is — the GPU has already done the work. `generate_image`
    # already walks to the fallback route, which is the retry that actually helps — and
    # since #154 it does so per image, on a model that shares the 2.1 encoder + VAE.
    return OpenAI(
        base_url=content_cfg.litellm_base_url,
        api_key=content_cfg.litellm_api_key,
        timeout=content_cfg.image_request_timeout,
        max_retries=0,
    )


def image_deadline(spec: "RenderSpec", route: str) -> float:
    """The per-image deadline for one render of ``spec`` on ``route``, in seconds.

    ``max(factor x est_seconds, floor)``, capped just under the client ceiling. Graham's
    policy (fleet #222): a stuck render costs minutes, then THAT image is re-rendered on
    the fallback model. Before #154 every attempt waited the full 1800 s, so one hung
    model load cost 30 min on the primary plus 30 on the fallback.
    """
    d = max(content_cfg.image_deadline_factor * spec.est_seconds_for(route),
            content_cfg.image_deadline_floor_s)
    return min(d, content_cfg.image_request_timeout - 1)


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
    spec: Optional["RenderSpec"] = None,
) -> GeneratedImage:
    """Generate one image for ``prompt`` via the LiteLLM proxy.

    Args:
        prompt: The image description (the editor builds this from the story).
        model: Image route; defaults to the spec's primary (``spec.model``), else
            ``content_cfg.image_model`` (``m3/comfy/qwen-image-2.1``).
        size: Output dimensions. Free-form on the ComfyUI route, but BOTH numbers
            must be multiples of 16 or the shim 400s (it checks before queueing, so
            a bad size costs no GPU time).
        steps: Sampler steps, used only without a ``spec``. With one, steps are per
            ROUTE (``spec.wire_steps``): 2.1 takes the tier's 40, and a fixed-schedule
            route (Turbo) is sent none at all.
        seed: Fixed seed for a reproducible render. Omitting it means a fresh random
            one, deliberately: ComfyUI caches on an unchanged graph, so a pinned seed
            with an unchanged prompt returns the CACHED picture rather than re-rendering.
        negative_prompt: What to keep OUT of the frame. A far stronger lever than a
            "do not draw X" clause inside the positive prompt — diffusion models are
            poor at negation.
        client: An OpenAI-compatible client (injected in tests). Defaults to a
            client bound to the LiteLLM proxy.
        fallback_model: The route that re-renders THIS image if the primary fails or
            hits its deadline; defaults to ``spec.fallback_model``, else
            ``content_cfg.image_fallback_model``.
        spec: The tier's :class:`RenderSpec`. Supplies size, per-route steps, the
            routes, and each attempt's deadline (:func:`image_deadline`).

    Returns:
        A :class:`GeneratedImage` carrying the base64 PNG and the model used.
    """
    if spec is not None:
        size = spec.size  # the tier owns the canvas
    model = model or (spec.model if spec is not None else content_cfg.image_model)
    if fallback_model is not None:
        fb = fallback_model
    else:
        fb = spec.fallback_model if spec is not None else content_cfg.image_fallback_model
    cli = client if client is not None else _default_client()
    # Try the primary route, then the fallback — PER IMAGE (Graham, fleet #222) — so one
    # image failure doesn't hold the whole edition on missing images (review.validate_paper
    # requires them). Both routes are the SAME ComfyUI process on the M3, so this covers a
    # per-model failure or a stuck render, not the shim being down. Since #154 the pair is
    # Qwen-Image 2.1 + 2.1-Turbo, which share one encoder and VAE: crossing over costs no
    # model-set reload (the old FLUX<->qwen-image swap moved ~93 GB each way, fleet #219).
    #
    # Do NOT pass response_format. Re-verified 2026-08-24 against the ComfyUI route: LiteLLM
    # rejects it with `UnsupportedParamsError` in ~0.05 s and the request never reaches the
    # M3. (The original 2026-06 note blamed the Ollama image routes; those are retired, but
    # the constraint survived the migration for a different reason, at a different layer.)
    # tests/test_images.py locks this.
    routes = [model] + ([fb] if fb and fb != model else [])

    # steps/seed/negative_prompt are NOT typed kwargs on the OpenAI SDK, so they must
    # travel in extra_body or they are dropped before the wire. DANGER: the shim ignores
    # anything it does not recognise and returns HTTP 200 with a FULL-COST image, so a
    # typo (`num_steps`, `num_inference_steps`) is indistinguishable from success.
    # Verify any change here by WALL-CLOCK, never by a 200. The reachable parameters are
    # exactly steps / seed / size / negative_prompt — cfg, sampler and scheduler are
    # baked into the ComfyUI workflow and cannot be reached from a request (issue #105).
    from content_pipeline.generate.image_styles import wire_steps_for

    last_exc: Optional[Exception] = None
    for route in routes:
        # Steps are per ROUTE: a fixed-schedule route (Turbo) gets none on the wire.
        route_steps = spec.wire_steps(route) if spec is not None else wire_steps_for(route, steps)
        extra: dict[str, Any] = {}
        if route_steps is not None:
            extra["steps"] = route_steps
        if seed is not None:
            extra["seed"] = seed
        if negative_prompt:
            extra["negative_prompt"] = negative_prompt
        logger.info("[images] generating model=%s size=%s steps=%s", route, size, route_steps)
        try:
            kwargs: dict[str, Any] = {"model": route, "prompt": prompt, "size": size}
            if extra:
                kwargs["extra_body"] = extra
            if spec is not None:
                # The per-image deadline rides on the request (an openai SDK per-call
                # option), so this attempt gives up in minutes and the next route gets
                # the image. NB the shim does not cancel an abandoned job, so the fallback
                # may queue behind it briefly — the floor in image_deadline covers that.
                kwargs["timeout"] = image_deadline(spec, route)
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
    spec: Optional["RenderSpec"] = None,
) -> tuple[str, str]:
    """Generate an image for ``prompt`` and save it to the scratch dir.

    Returns ``(local_path, model_used)`` — ``model_used`` is the route that actually drew
    it, the fallback included. Shared by the editor tool and the harness's deterministic
    per-item image step. With a ``spec`` the tier decides size, routes, steps and deadline.

    The filename is content-addressed over the prompt AND the full render spec, not the
    prompt alone. That matters now one prompt can be rendered at two tiers: hashing the
    prompt only would make a 512x512 8-step thumbnail collide with a 1024x1024 28-step
    hero and silently serve whichever landed first.
    """
    import hashlib
    import os

    if spec is not None:
        size, steps = spec.size, spec.steps
    img = generate_image(prompt, model=model, size=size, steps=steps, seed=seed,
                         negative_prompt=negative_prompt, client=client, spec=spec)
    os.makedirs(content_cfg.image_dir, exist_ok=True)
    # The route that drew it is part of the key too: a Turbo fallback must never be
    # mistaken for (or overwrite) the 2.1 picture of the same request.
    key = f"{prompt}|{size}|{steps}|{seed}|{negative_prompt or ''}|{img.model}"
    fname = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] + ".png"
    path = os.path.join(content_cfg.image_dir, fname)
    with open(path, "wb") as fh:
        fh.write(img.to_bytes())
    return path, img.model
