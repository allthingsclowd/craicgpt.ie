"""
content_pipeline/generate/image_styles.py
==========================================
Art-direction for the daily illustrations.

THE HOUSE LOOK IS A CARTOON, AND IT ROTATES DAILY
-------------------------------------------------
Every picture in the paper is a cartoon: funny, colourful, and round — no sharp
edges (Graham's brief). Four looks are in rotation, and the WHOLE EDITION shares
one of them, cycling day by day: Beano/Dandy, The Simpsons, Saturday-morning flat
2D, and plasticine stop-motion.

The rotation moved from the image axis to the DAY axis on 2026-08-25. Previously
each image in an edition got a different style, which showed the model's range but
made the paper look incoherent — a newspaper where every picture is drawn by a
different hand. One style per edition reads as designed, and a returning reader
still sees the full range across a week. See :func:`style_for_edition`, which
counts days rather than hashing them so the cycle genuinely rotates.

TEXT: ALLOWED WHERE IT CAN BE LETTERED CLEANLY
----------------------------------------------
:data:`NO_TEXT_CLAUSE` was written when the image model could not render legible
text. FLUX.2 [dev] can, and it does so whether or not it is asked: measured
2026-08-25, all four style candidates returned a road sign reading "STOP" in clean
capitals while carrying BOTH the full clause AND a negative prompt banning
``text, letters, words, signage``. So the clause never bought wordless art — it
bought UNCONTROLLED text.

Graham's call: text is allowed on the 28-step renders. The threshold
(:data:`TEXT_STEP_FLOOR`) is a real quality boundary — at 8 steps letterforms come
out mangled, and a misspelled word reads as broken in a way a misshapen elbow never
does. So the hero tier may carry a short speech bubble (:data:`TEXT_CLAUSE`) and
the 8-step fun and shorts renders stay wordless.

⚠️ TRANSLATIONS SHARE THESE IMAGES. A hero bubble written in English appears
verbatim on the de/es/it/ja/fr editions, because a translated edition reuses the
English image URLs. That is accepted rather than solved: the alternative was never
wordless art, only uncontrolled English signage nobody chose.

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
from datetime import date

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
_NEGATIVE_BASE = (
    "sharp edges, hard corners, angular, jagged, spiky, harsh geometry, "
    "photorealistic, photograph, gritty, grim, dark, horror, scary, gore"
)
_NEGATIVE_TEXT = (
    ", text, letters, words, numbers, signage, watermark, caption, subtitles"
)

# Text-free by default; the hero tier drops the text bans (see TEXT_STEP_FLOOR).
NEGATIVE_PROMPT = _NEGATIVE_BASE + _NEGATIVE_TEXT


def negative_prompt_for(spec: "RenderSpec | None" = None) -> str:
    """The negative prompt for a slot — text bans included unless text is allowed."""
    return _NEGATIVE_BASE if (spec and spec.allows_text) else NEGATIVE_PROMPT


# Text is permitted only on renders with enough steps to letter it cleanly.
# Graham's call, 2026-08-25: "text is allowed on the 20+ [step] images".
#
# The threshold is a real quality boundary, not a round number. FLUX.2 [dev] is a
# guidance-distilled 28-step model; at 8 steps letterforms come out mangled, and a
# misspelled word reads as broken in a way a misshapen elbow never does. So the
# 28-step heroes may carry a speech bubble and the 8-step fun/shorts renders stay
# wordless.
TEXT_STEP_FLOOR = 20

# What to ASK for when text is allowed. Deliberately modest: a few hand-lettered
# words in a bubble is where a Beano panel's joke lives, but a paragraph is where
# a diffusion model's spelling falls apart.
TEXT_CLAUSE = (
    "You MAY include a short hand-lettered speech bubble or a few words of comic "
    "signage if it sharpens the joke — at most FIVE words, spelled correctly, in "
    "clear cartoon lettering. Never a paragraph, never body text, never a watermark. "
    "If the gag works without words, use none."
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
    def allows_text(self) -> bool:
        """Whether this render has enough steps to letter text legibly."""
        return self.steps >= TEXT_STEP_FLOOR

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
    {"name": "beano-comic", "label": "Beano-style British comic",
     "descriptor": "A bold British comic-strip cartoon in the classic Beano and Dandy "
                   "style: thick rounded ink outlines, halftone dot shading, a bright "
                   "primary 1960s comic palette, rubbery exaggerated characters built "
                   "from soft round shapes, slapstick energy"},
    {"name": "simpsons-flat", "label": "flat 2D TV cartoon",
     "descriptor": "A flat 2D American television cartoon in the instantly recognisable "
                   "style of The Simpsons: yellow-skinned characters with large round "
                   "white eyes and overbites, bold black outlines, flat saturated colour "
                   "fills, simple rounded shapes, sitcom staging"},
    {"name": "saturday-morning", "label": "Saturday-morning cartoon",
     "descriptor": "A 1960s-70s Saturday-morning television cartoon: flat colour fills, "
                   "thick soft outlines, limited-animation shapes, a warm retro palette "
                   "of orange, mustard and teal, rounded friendly characters"},
    {"name": "plasticine", "label": "plasticine stop-motion",
     "descriptor": "A soft claymation and plasticine stop-motion scene: rounded modelled "
                   "figures with visible thumbprint texture, chunky tactile shapes, warm "
                   "studio lighting, every form moulded with no sharp edges"},
]


# The moto vertical, for the ILLUSTRATOR. Fixing only the prose still ships a drawing of
# a car: the image model sees just a title + a short gist, and "Honda CB1000GT" renders a
# saloon perfectly happily. `_vertical` is stamped deterministically in
# editor_in_chief._write_fun from the creator credit — never inferred here.
_MOTO_IMAGE_CLAUSE = (
    " The subject is a MOTORCYCLE — two wheels, a rider in a helmet. It is NOT a car: "
    "no car, no saloon, no hatchback, no SUV, no four wheels, no steering wheel, no car doors."
)


def build_image_prompt(item: dict, style: dict, gag: str | None = None,
                       spec: "RenderSpec | None" = None) -> str:
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
    text_rule = TEXT_CLAUSE if (spec and spec.allows_text) else NO_TEXT_CLAUSE
    return f"{style['descriptor']}, {scene}{moto}\n{text_rule}"


def _seed_int(seed: str) -> int:
    """Deterministic integer from a seed string (e.g. an ISO date)."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


def style_for_edition(seed: str) -> dict:
    """The ONE cartoon style the whole edition is drawn in, chosen by ``seed``.

    Graham's call, 2026-08-25: rotate the four candidates **daily** rather than
    within an edition. Two reasons, and they pull the same way:

    * **Editorially** a paper whose every picture is a different art style looks
      incoherent. One style per edition reads as designed, the way a comic does.
    * **As a tutorial** "today's paper is drawn in X, come back tomorrow for
      another" is a clearer lesson than four styles at once, and it still shows
      the model's full range across a week.

    This is a TRUE rotation off the date's ordinal, not a hash. A hash-mod is
    effectively random, and random clusters: the first attempt here put seven
    consecutive editions in plasticine while still looking evenly distributed over a
    year. Counting days instead guarantees every style appears once per cycle and
    never twice running, which is what "rotate" actually means to a reader.

    Same date → same style, so re-running a given edition reproduces its look
    exactly. A seed that is not an ISO date (tests, ad-hoc calls) falls back to the
    hash, which is fine when there is no sequence to preserve.
    """
    if not STYLE_PRESETS:
        raise ValueError("STYLE_PRESETS is empty — the paper cannot be illustrated")
    try:
        ordinal = date.fromisoformat(seed[:10]).toordinal()
    except (ValueError, TypeError):
        ordinal = _seed_int(seed)
    return STYLE_PRESETS[ordinal % len(STYLE_PRESETS)]


def assign_styles(n: int, *, seed: str) -> list[dict]:
    """``n`` copies of the edition's single style — one entry per illustrated slot.

    Kept as the harness's call shape (it zips this against the target list) even
    though every entry is now identical. Previously this rotated a coprime stride
    ACROSS the slots so each image in one edition looked different; that variety
    moved to the day axis (see :func:`style_for_edition`).
    """
    if n <= 0 or not STYLE_PRESETS:
        return []
    return [style_for_edition(seed)] * n
