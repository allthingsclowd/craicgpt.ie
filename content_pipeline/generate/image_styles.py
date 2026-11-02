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

TEXT: SUPPLIED, NEVER INVENTED
------------------------------
:data:`NO_TEXT_CLAUSE` was written when the image model could not render legible
text. FLUX.2 [dev] could, and did so whether or not it was asked (2026-08-25: a
"STOP" sign on every style candidate despite a nine-NO text ban). So the clause
never bought wordless art — it bought UNCONTROLLED text.

The policy since: every tier may carry a short caption, but the caption is SUPPLIED
verbatim by the gag step and the model is only asked to COPY it
(:func:`build_image_prompt`). That policy is model-neutral and survived the move to
Qwen-Image 2.1 (2026-11-02, #154): in the fleet #221 bake-off 2.1 copied the supplied
captions exactly 4/4, Turbo 7/8. :data:`TEXT_STEP_FLOOR` stays as the physical floor
for any route that takes steps.

⚠️ TRANSLATIONS SHARE THESE IMAGES. A hero bubble written in English appears
verbatim on the de/es/it/ja/fr editions, because a translated edition reuses the
English image URLs. That is accepted rather than solved: the alternative was never
wordless art, only uncontrolled English signage nobody chose.

RENDER TIERS AND ROUTES
-----------------------
Images are not all worth the same money, and steps are per MODEL, not one number.
The tiers (:data:`HERO` / :data:`STANDARD` / :data:`THUMBNAIL`) carry size, steps and
caption budget, and name their routes: the leads and the fun desk render on
Qwen-Image 2.1 (40 steps) with 2.1-Turbo as the per-image fallback; the AI shorts
render on Turbo (a fixed 8-step schedule) with 2.1 behind them. :class:`RouteProfile`
holds each route's cost model and step rule. History: on FLUX.2 [dev] (2026-08-24 →
2026-11-02) a 28-step hero cost ~411-727 s, which is why the tiers once bought steps
down — and why 8 steps cost limbs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Optional

# The exact no-typography framing (was inline in editor_in_chief._image_prompt).
# Centralised here so every style is guaranteed text-free in one place.
# Say what we WANT, never what we want to avoid. LESSON FROM FLUX (kept on Qwen-Image 2.1,
# because it costs nothing and text encoders generally treat negation as content): FLUX.2's
# Mistral encoder treats English
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
# NO NEGATIVE PROMPT. Qwen-Image 2.1 runs at cfg 1.0 (guidance-free) in the fleet graph, so
# there is no unconditional pass for a negative embedding to attach to — the same position
# FLUX.2 [dev] was in. HISTORY (FLUX): FLUX.2 [dev] is guidance-distilled: the unconditional pathway is
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
    so a future route that runs true CFG (cfg > 1) can reintroduce one here."""
    return ""


# Text is permitted only on renders with enough steps to letter it cleanly.
# Graham's call, 2026-08-25: "text is allowed on the 20+ [step] images".
#
# HISTORY (FLUX): the threshold is a real quality boundary, not a round number. FLUX.2 [dev] is a
# guidance-distilled 28-step model; at 8 steps letterforms come out mangled, and a
# misspelled word reads as broken in a way a misshapen elbow never does. So the
# 28-step heroes may carry a speech bubble and the 8-step fun/shorts renders stay
# wordless.
TEXT_STEP_FLOOR = 20

# What to ASK for when text is allowed. Deliberately modest: a few hand-lettered
# words in a bubble is where a Beano panel's joke lives, but a paragraph is where
# a diffusion model's spelling falls apart.
# UNUSED since the caption became supplied (build_image_prompt); kept for its lesson.
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
class RouteProfile:
    """What one image ROUTE costs and how it takes steps — steps are per model, not global.

    Cost is ``steps x (per_px_step x pixels + per_step) + fixed`` seconds: linear in pixels
    per step, plus a fixed text-encode + VAE-decode + transfer tail.

    ``fixed_steps`` marks a route whose step count is baked into its graph (Turbo's
    ManualSigmas schedule): the request carries no ``steps`` and the tier's number is
    ignored. ``tier_steps`` lets a route keep its own per-tier table (FLUX, kept as a
    rollback) instead of the tier's default.
    """

    per_px_step: float
    per_step: float
    fixed: float
    fixed_steps: Optional[int] = None
    tier_steps: Optional[dict] = None


# Qwen-Image 2.1 (7B DiT, cfg 1.0, 40 steps). Fitted 2026-11-02 to the TOP of the measured
# ranges, so the budget is the slow end: 1024²/40 = 148-175 s (fleet #221 bake-off) and
# 512²/40 = 73 s (generating-local-images skill, 2026-11-01). → 4.2 s/step at 1024²,
# 1.6 s/step at 512², ~8 s fixed. Gives 175 s for a 1024² hero.
QWEN21 = RouteProfile(per_px_step=3.23e-6, per_step=0.78, fixed=8.0)
# 2.1-Turbo: the same DiT, so the same per-step cost, on a fixed 8-step sigma schedule.
# Check: 1024²/8 → 41 s against the bake-off's 34-41 s. 768²/8 → ~30 s.
QWEN21_TURBO = RouteProfile(per_px_step=3.23e-6, per_step=0.78, fixed=8.0, fixed_steps=8)
# FLUX.2 [dev] — NOT on craicgpt's path since #154; kept so `IMAGE_MODEL=m3/comfy/flux-2-dev`
# is a working rollback with its own step table and honest estimates (14.2 s/step at
# 1024², 2026-08-26, after the fleet #166 graph fix).
FLUX2_DEV = RouteProfile(per_px_step=1.3e-5, per_step=0.6, fixed=14.0,
                         tier_steps={"hero": 28, "standard": 20, "thumbnail": 20})

_ROUTE_PROFILES = {
    "qwen-image-2.1": QWEN21,
    "qwen-image-2.1-turbo": QWEN21_TURBO,
    "flux-2-dev": FLUX2_DEV,
}


def profile_for(route: str) -> RouteProfile:
    """The profile for a LiteLLM route name (matched on its last path segment).

    An unknown route gets the Qwen-Image 2.1 profile: the tier's own steps and a 2.1-shaped
    estimate. Defaults rather than raises, like :func:`render_spec_for`.
    """
    return _ROUTE_PROFILES.get((route or "").rsplit("/", 1)[-1], QWEN21)


@dataclass(frozen=True)
class RenderSpec:
    """How much render one image slot is worth: size, steps, caption budget — and the
    ROUTES it renders on.

    ``size``/``steps``/``seed``/``negative_prompt`` are the only per-request knobs the
    ComfyUI shim honours (issue #105). ``steps`` is the tier's step count on a route that
    takes steps (Qwen-Image 2.1); a fixed-schedule route (Turbo) ignores it — see
    :meth:`steps_for`.

    The routes are read from ``content_cfg`` at call time (so an env change or a test's
    monkeypatch is seen): the thumbnail tier has its own pair, everything else shares
    ``IMAGE_MODEL`` / ``IMAGE_FALLBACK_MODEL``.
    """

    size: str
    steps: int
    allows_text: bool = False
    caption_words: int = 5
    tier: str = "standard"

    @property
    def model(self) -> str:
        """The PRIMARY route for this tier."""
        from content_pipeline.content_config import content_cfg

        if self.tier == "thumbnail":
            return content_cfg.image_thumbnail_model
        return content_cfg.image_model

    @property
    def fallback_model(self) -> str:
        """The route that re-renders THIS image when the primary fails or times out."""
        from content_pipeline.content_config import content_cfg

        if self.tier == "thumbnail":
            return content_cfg.image_thumbnail_fallback_model
        return content_cfg.image_fallback_model

    def steps_for(self, route: str) -> int:
        """The steps ``route`` will actually run for this tier."""
        prof = profile_for(route)
        if prof.fixed_steps:
            return prof.fixed_steps
        if prof.tier_steps and self.tier in prof.tier_steps:
            return prof.tier_steps[self.tier]
        return self.steps

    def wire_steps(self, route: str) -> Optional[int]:
        """The ``steps`` to SEND: ``None`` for a fixed-schedule route, whose graph would
        otherwise be asked to re-space a sigma schedule it was distilled on."""
        return None if profile_for(route).fixed_steps else self.steps_for(route)

    def est_seconds_for(self, route: str) -> float:
        """Rough wall-clock for one render of this tier on ``route``, slot idle.

        Used to budget an edition BEFORE spending an hour discovering it does not fit, and
        to set the per-image deadline (``images.image_deadline``). Linear in PIXELS, not a
        size bucket — the bucket version once treated 768² as costing the same as 1024².
        """
        prof = profile_for(route)
        w, _, h = self.size.partition("x")
        per_step = prof.per_px_step * (int(w) * int(h)) + prof.per_step
        return self.steps_for(route) * per_step + prof.fixed

    @property
    def est_seconds(self) -> float:
        """The estimate on this tier's PRIMARY route."""
        return self.est_seconds_for(self.model)


# The three tiers, re-set for Qwen-Image 2.1 on 2026-11-02 (#154).
#
# Every tier asks for 40 steps on 2.1. Not a cost dial being ignored — a deliberate choice:
#   * 40 is 2.1's own default, and the ONLY step count the bake-off (fleet #221) measured
#     caption fidelity at (4/4 exact). 2.1 is NOT guidance-distilled the way FLUX was, and
#     under-sampling is what cost FLUX limbs and letters at 8 steps (2026-08-26). Dropping
#     below 40 would trade a measured bar for an unmeasured one.
#   * It is affordable: 8 x 1024²@40 (~175 s) = ~23 min. The 10 shorts render on TURBO
#     (Graham, 2026-11-02) at ~30 s each = ~5 min, so a whole edition is ~28 min of images
#     against ~61 min on FLUX.
#   * THUMBNAIL keeps 40 because 40 is what its FALLBACK (2.1) runs; Turbo ignores it.
#
# The tiers still differ where it matters: canvas (768² for the shorts) and the caption
# word budget (12 / 8 / 5). Sizes are multiples of 32, which the 2.1 routes require.
HERO = RenderSpec("1024x1024", 40, allows_text=True, caption_words=12, tier="hero")
STANDARD = RenderSpec("1024x1024", 40, allows_text=True, caption_words=8, tier="standard")
THUMBNAIL = RenderSpec("768x768", 40, allows_text=True, caption_words=5, tier="thumbnail")

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
