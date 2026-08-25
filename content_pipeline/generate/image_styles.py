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

TEXT: THE CLAUSE NO LONGER ENFORCES ANYTHING
--------------------------------------------
:data:`NO_TEXT_CLAUSE` was written when the image model could not render legible
text. FLUX.2 [dev] can, and it does so whether or not it is asked: measured
2026-08-25, all four style candidates returned a road sign reading "STOP" in clean
capitals while carrying BOTH the full clause AND a negative prompt listing
``text, letters, words, signage``. So the clause no longer buys wordless art — it
buys UNCONTROLLED text. Whether to embrace deliberate captions or keep steering
against them is issue #106; until that lands the clause stays, because steering
against is still better than not trying.

RENDER TIERS
------------
Images are not all worth the same money. FLUX.2 [dev] costs ~727 s at its baked
28 steps and ~201 s at 8, and the paper makes 18 images a day against a 190-minute
task cap — so the step count is per-item, not one global setting. See
:data:`HERO` / :data:`STANDARD` / :data:`THUMBNAIL` and :func:`render_spec_for`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import gcd

# The exact no-typography framing (was inline in editor_in_chief._image_prompt).
# Centralised here so every style is guaranteed text-free in one place.
NO_TEXT_CLAUSE = (
    "IMPORTANT: absolutely NO text, NO letters, NO words, NO numbers, NO signage, "
    "NO logos, NO brand names, NO screens showing text, NO watermarks, NO captions "
    "anywhere in the frame. A clean image with zero typography."
)

# What to keep OUT of the frame. The ComfyUI shim honours `negative_prompt`
# (verified 2026-08-25: it produced a genuinely different image, not a cache hit),
# and it is a far stronger lever than a "do not draw X" clause inside the positive
# prompt, because diffusion models are poor at negation. Two jobs here:
#   - ROUNDNESS, which is Graham's standing brief for the cartoons ("no sharp edges")
#   - the text suppression that NO_TEXT_CLAUSE alone no longer achieves
NEGATIVE_PROMPT = (
    "sharp edges, hard corners, angular, jagged, spiky, harsh geometry, "
    "photorealistic, photograph, gritty, grim, dark, horror, scary, gore, "
    "text, letters, words, numbers, signage, watermark, caption, subtitles"
)


@dataclass(frozen=True)
class RenderSpec:
    """How much render one image slot is worth: output size and sampler steps.

    Both are per-request on the ComfyUI route and nothing else is reachable
    (issue #105), so this dataclass IS the complete cost dial.
    """

    size: str
    steps: int

    @property
    def est_seconds(self) -> float:
        """Rough wall-clock, from the 2026-08-25 measurements.

        ~26 s/step at 1024x1024 and ~7 s/step at 512x512, plus a fixed ~14 s of text
        encode + VAE decode + transfer that dominates once steps get small. Used to
        budget an edition BEFORE spending three hours discovering it does not fit.
        """
        w, _, h = self.size.partition("x")
        per_step = 26.0 if int(w) * int(h) > 512 * 512 else 7.0
        return self.steps * per_step + 14.0


# The three tiers. Graham's call, 2026-08-25: the page-leading images get the full
# 28 steps; everything else is bought down. 3x28 + 5x8 + 10x8@512 lands the whole
# edition around 65 minutes of images, inside the existing 190-minute cap and the
# existing 06:00-08:00 publish-gate window — no cron changes needed (issue #101).
HERO = RenderSpec("1024x1024", 28)        # the headliner + both subarticles
STANDARD = RenderSpec("1024x1024", 8)     # the Craic & Throttle desk
THUMBNAIL = RenderSpec("512x512", 8)      # the ten AI shorts

_TIERS = {"hero": HERO, "standard": STANDARD, "thumbnail": THUMBNAIL}


def render_spec_for(tier: str) -> RenderSpec:
    """Look up a tier by name, defaulting to STANDARD for anything unknown.

    Defaults rather than raises on purpose: a new slot type appearing upstream
    should cost a middling image, not crash the edition.
    """
    return _TIERS.get(tier, STANDARD)


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


def build_image_prompt(item: dict, style: dict, gag: str | None = None) -> str:
    """Compose an image prompt: the story's subject, rendered in ``style``.

    With a ``gag`` (see :mod:`image_gag`) the picture depicts the JOKE — which is
    the whole point of the cartoon brief. Without one we fall back to the literal
    title-plus-gist framing, which is what the paper did before and is still a
    perfectly serviceable illustration; a missing gag must never cost us an image,
    because ``review.validate_paper`` requires one.
    """
    title = item.get("title", "")
    moto = _MOTO_IMAGE_CLAUSE if item.get("_vertical") == "moto" else ""
    if gag:
        scene = f"{gag} A visual joke about: {title}."
    else:
        gist = (item.get("body") or item.get("summary") or "")[:140]
        scene = f"depicting the scene of: {title}. {gist}"
    return f"{style['descriptor']}, {scene}{moto}\n{NO_TEXT_CLAUSE}"


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
