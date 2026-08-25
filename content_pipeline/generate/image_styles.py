"""
content_pipeline/generate/image_styles.py
==========================================
Art-direction for the daily illustrations.

Every illustrated story gets a DIFFERENT visual style — a day-stable rotation
across a set of distinct looks (editorial photo, oil painting, retro comic, …) —
so a single edition showcases the image model's range while each image stays
relevant to its story. The rotation mirrors :func:`personas.assign_personas`:
same seed (the edition date) → same lineup, different seed → a different look,
so successive editions don't all come out the same.

TEXT-FREE FOR NOW
-----------------
The current model still can't render legible text reliably, so every preset
carries :data:`NO_TEXT_CLAUSE`. When a text-capable model (Qwen-Image) is promoted
in the fleet catalog, drop the clause and let the images carry tasteful typography.
"""

from __future__ import annotations

import hashlib
from math import gcd

# The exact no-typography framing (was inline in editor_in_chief._image_prompt).
# Centralised here so every style is guaranteed text-free in one place.
NO_TEXT_CLAUSE = (
    "IMPORTANT: absolutely NO text, NO letters, NO words, NO numbers, NO signage, "
    "NO logos, NO brand names, NO screens showing text, NO watermarks, NO captions "
    "anywhere in the frame. A clean image with zero typography."
)

# Each preset is a {name, descriptor}. Names are stamped on the item as
# ``_image_style`` (shown in the UI / Under-the-Hood). Descriptors are written so
# the subject is naturally text-free.
STYLE_PRESETS: list[dict] = [
    {"name": "editorial-photo",
     "descriptor": "A candid photorealistic editorial news photograph, documentary "
                   "style, natural available light, shallow depth of field, high detail"},
    {"name": "oil-painting",
     "descriptor": "A richly textured oil painting, visible impasto brushstrokes, "
                   "classical chiaroscuro lighting, gallery composition"},
    {"name": "retro-comic",
     "descriptor": "A bold retro British comic-strip illustration in the style of the "
                   "Beano, thick ink outlines, halftone dot shading, bright primary "
                   "1960s palette"},
    {"name": "cinematic",
     "descriptor": "A cinematic film still, anamorphic widescreen, dramatic key "
                   "lighting, moody colour grade, shallow depth of field"},
    {"name": "watercolour",
     "descriptor": "A loose watercolour illustration, soft translucent washes, "
                   "bleeding pigment, visible cold-press paper texture"},
    {"name": "isometric-3d",
     "descriptor": "A clean isometric 3D render, soft global illumination, matte clay "
                   "materials, playful miniature-diorama look"},
    {"name": "vintage-poster",
     "descriptor": "A vintage mid-century travel poster, flat screen-printed shapes, "
                   "bold geometric composition, limited two-or-three colour palette"},
    {"name": "risograph",
     "descriptor": "A risograph print, two spot-colour inks slightly mis-registered, "
                   "grainy texture, handmade zine aesthetic"},
    {"name": "paper-collage",
     "descriptor": "A cut-paper collage, layered textured paper shapes with soft drop "
                   "shadows, tactile handmade craft look"},
]


# The moto vertical, for the ILLUSTRATOR. Fixing only the prose still ships a drawing of
# a car: the image model sees just a title + a short gist, and "Honda CB1000GT" renders a
# saloon perfectly happily. `_vertical` is stamped deterministically in
# editor_in_chief._write_fun from the creator credit — never inferred here.
_MOTO_IMAGE_CLAUSE = (
    " The subject is a MOTORCYCLE — two wheels, a rider in a helmet. It is NOT a car: "
    "no car, no saloon, no hatchback, no SUV, no four wheels, no steering wheel, no car doors."
)


def build_image_prompt(item: dict, style: dict) -> str:
    """Compose a text-free image prompt: the story's subject rendered in ``style``."""
    title = item.get("title", "")
    gist = (item.get("body") or item.get("summary") or "")[:140]
    moto = _MOTO_IMAGE_CLAUSE if item.get("_vertical") == "moto" else ""
    return (
        f"{style['descriptor']}, depicting the scene of: {title}. {gist}{moto}\n"
        f"{NO_TEXT_CLAUSE}"
    )


def _seed_int(seed: str) -> int:
    """Deterministic integer from a seed string (e.g. an ISO date)."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


def assign_styles(n: int, *, seed: str) -> list[dict]:
    """Return ``n`` style presets, day-stable and rotating by ``seed``.

    Same seed → same lineup (reproducible re-runs); different seed → a different
    rotation. Uses a coprime stride so the rotation visits every preset before any
    repeat; if ``n`` exceeds the preset count it cycles the rotation.
    """
    count = len(STYLE_PRESETS)
    if count == 0 or n <= 0:
        return []
    rng = _seed_int(seed)
    start = rng % count
    stride = 1 + (rng // count) % (count - 1) if count > 1 else 1
    while count > 1 and gcd(stride, count) != 1:
        stride += 1  # ensure the stride visits every index (a full cycle)
    order = [STYLE_PRESETS[(start + i * stride) % count] for i in range(count)]
    return [order[i % count] for i in range(n)]
