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
# Say what we WANT, never what we want to avoid. FLUX.2's Mistral encoder treats English
# negation as semantically loaded — Black Forest Labs' own guidance is "always describe what
# you want, not what you want to avoid", and their worked example is that "without glasses"
# renders glasses. The previous version of this clause was nine consecutive NOs about text,
# and every one of the four style candidates rendered a "STOP" sign anyway. The ban was
# plausibly SUMMONING the lettering it meant to forbid.
NO_TEXT_CLAUSE = (
    "A purely visual scene that tells the joke through action, expression and body language "
    "alone — plain uncluttered surfaces, blank walls, unmarked props."
)

# What to keep OUT of the frame. The ComfyUI shim honours `negative_prompt`
# (verified 2026-08-25: it produced a genuinely different image, not a cache hit),
# and it is a far stronger lever than a "do not draw X" clause inside the positive
# prompt, because diffusion models are poor at negation. Two jobs here:
#   - ROUNDNESS, which is Graham's standing brief for the cartoons ("no sharp edges")
#   - the text suppression that NO_TEXT_CLAUSE alone no longer achieves
# NO NEGATIVE PROMPT. FLUX.2 [dev] is guidance-distilled: the unconditional pathway is
# collapsed into the network, so there is no second forward pass for a negative embedding to
# attach to. Sending one is inert at best. At the cfg the shim currently runs it was actively
# harmful — the string used to read "sharp edges, hard corners, angular, jagged", and
# LETTERFORMS ARE SHARP EDGES AND HARD CORNERS, so the sampler was pushing legible type out
# of the very tier that is allowed a speech bubble.
#
# Roundness is now asked for POSITIVELY, in the style descriptors themselves — every preset
# below says "rounded", "soft outlines" or "moulded". That is the durable place for it.
NEGATIVE_PROMPT = ""


def negative_prompt_for(spec: "RenderSpec | None" = None) -> str:
    """Always empty — see NEGATIVE_PROMPT. Kept as a seam so the caller need not care, and
    so a future non-distilled route (qwen-image uses true CFG) can reintroduce one here."""
    return ""


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
# FLUX.2 renders text well, but only when asked the documented way: put the string in
# QUOTES and BIND it to a physical surface, because the model paints letters onto objects
# rather than compositing a caption. Reliability falls off past four or five words per
# quoted block, which is where the five-word cap comes from — it is the model's limit, not
# a stylistic preference.
TEXT_CLAUSE = (
    "If a few words sharpen the joke, letter them onto a surface in the scene — a speech "
    "bubble, a sign, a banner — writing the exact words in quotes, at most FIVE words, in "
    "bold hand-lettered cartoon capitals. Otherwise let the picture carry the joke alone."
)


@dataclass(frozen=True)
class RenderSpec:
    """How much render one image slot is worth: output size and sampler steps.

    Both are per-request on the ComfyUI route and nothing else is reachable
    (issue #105), so this dataclass IS the complete cost dial.
    """

    size: str
    steps: int
    allows_text: bool = False
    caption_words: int = 5

    @property
    def est_seconds(self) -> float:
        """Rough wall-clock, re-measured 2026-08-26 AFTER the ComfyUI graph fix.

        ~14 s/step at 1024x1024 and ~4 s/step at 512x512, plus a fixed ~14 s of text
        encode + VAE decode + transfer that dominates once steps get small.

        These roughly HALVED on 2026-08-26 (from 26 and 7). The flux graph had been
        running true two-pass classifier-free guidance on a guidance-distilled model —
        cfg 4.0 with no FluxGuidance node — so every image cost two model evaluations
        per step. Measured same prompt and seed, 28 steps at 1024x1024: 742 s before,
        411 s after (grazlab-llm-fleet #166).

        Used to budget an edition BEFORE spending three hours discovering it does not fit.
        """
        w, _, h = self.size.partition("x")
        # Linear in PIXELS, not a size bucket. The bucket version treated 768x768 as though
        # it cost the same as 1024x1024 and over-budgeted an edition by 20 minutes. Fitted to
        # both real measurements: 14.2 s/step at 1024x1024 and 4.0 at 512x512.
        per_step = 1.3e-5 * (int(w) * int(h)) + 0.6
        return self.steps * per_step + 14.0


# The three tiers. The page-leading images get the full 28 steps (Graham's call); the
# rest are bought down — but NOT below 20.
#
# THE 8-STEP TIERS WERE A MISTAKE, corrected 2026-08-26. FLUX.2 [dev] targets 20-50
# sampling steps; at 8 it under-samples badly, and that is what produced the missing
# limbs and the garbled small lettering ("CHAKE SOME NOISE" on a motorcycle fairing) in
# the 2026-08-26 edition. 8 was chosen purely to fit the budget, before anyone had looked
# at what it did to the pictures.
#
# What makes 20 affordable is the ComfyUI graph fix (grazlab-llm-fleet #166) — flux was
# paying double for two-pass CFG it does not need, so every render roughly halved:
#
#     3 x 1024@28  + 5 x 1024@20 + 10 x 512@20  =  ~61 min of images
#
# against ~67 min for the OLD all-8-step layout. More steps everywhere, and cheaper.
# `allows_text` is an EXPLICIT flag, not a function of the step count. It was derived from
# steps until 2026-08-26, when raising the cheap tiers from 8 to 20 silently switched text ON
# for the whole paper — Graham's decision was "text is allowed in the hero images", and that
# is an editorial choice about the page, not a side effect of a cost knob.
#
# TEXT_STEP_FLOOR still applies as a PHYSICAL floor: a tier may only opt in if it has enough
# steps to letter legibly. A test enforces that pairing.
# Word budgets scale with the canvas rather than sitting at a flat five. The evidence for
# the hero number is direct: on 2026-08-26 a THIRTEEN-word headline rendered cleanly at
# 1024x1024 / 28 steps. Five everywhere was an over-correction from a general guideline,
# contradicted by our own output.
#
# Shorts moved 512 -> 768 (2026-08-26) so lettering has pixels to land in; five words in a
# 512px frame is roughly 40px of text height, which is where FLUX letterforms smear. 768 is
# a multiple of 16, which the ComfyUI shim requires.
HERO = RenderSpec("1024x1024", 28, allows_text=True, caption_words=12)
STANDARD = RenderSpec("1024x1024", 20, allows_text=True, caption_words=8)
THUMBNAIL = RenderSpec("768x768", 20, allows_text=True, caption_words=5)

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
                   "studio lighting, every form moulded soft and rounded"},
]


# The moto vertical, for the ILLUSTRATOR. Fixing only the prose still ships a drawing of
# a car: the image model sees just a title + a short gist, and "Honda CB1000GT" renders a
# saloon perfectly happily. `_vertical` is stamped deterministically in
# editor_in_chief._write_fun from the creator credit — never inferred here.
# Same rule, and this one is load-bearing for #104. The old wording listed every car word we
# were trying to avoid ("It is NOT a car: no car, no saloon, no hatchback...") — which on this
# encoder is a list of cars to draw. Describe the motorcycle instead, positively and
# concretely, and never name the thing we do not want.
_MOTO_IMAGE_CLAUSE = (
    " The vehicle is a two-wheeled motorcycle: a rider in a full helmet and leathers sitting "
    "astride it, hands on the handlebars, both wheels visible, exhaust pipe and kickstand."
)


def build_image_prompt(item: dict, style: dict, gag: str | None = None,
                       spec: "RenderSpec | None" = None, caption: str = "") -> str:
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
        # The gag alone IS the scene. The title used to be appended here as "A visual joke
        # about: <title>", and on 2026-08-26 the model dutifully lettered the entire 13-word
        # headline into a speech bubble — well past the five-word reliability limit, and a
        # duplicate of the headline sitting directly above the picture on the page.
        scene = gag
    else:
        gist = (item.get("body") or item.get("summary") or "")[:140]
        scene = f"depicting the scene of: {title}. {gist}"
    # THE CAPTION IS SUPPLIED, NEVER REQUESTED. Asking a diffusion model to letter "the
    # exact words" without giving it any is what produced "STEMIVALIINGS MONIS AII APOR!"
    # on 2026-08-26 — it invents letterforms, and invented letterforms are mush. Give it a
    # concrete string and it copies it. TEXT_CLAUSE (the old generic ask) is gone.
    if caption and spec and spec.allows_text:
        text_rule = (
            f'The words "{caption}" appear in the picture in bold hand-lettered cartoon '
            f"capitals, on a speech bubble or a sign, spelled exactly as written here."
        )
    else:
        text_rule = NO_TEXT_CLAUSE
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
