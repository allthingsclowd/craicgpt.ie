"""
content_pipeline/generate/personas.py
======================================
Marvel-persona roster for the fun-news "AI journalists".

Each of the day's 5 fun stories is rewritten in the unmistakable voice of a
different Marvel character. This module owns:

- :data:`ROSTER`            — the characters and a short voice brief each.
- :func:`assign_personas`   — a day-stable, rotating, no-repeat lineup.
- :func:`voice_brief`       — the tone/phrasing cue fed into the rewrite prompt.
- :func:`persona_byline`    — the "as told to…" byline.
- :data:`SATIRE_DISCLAIMER` — the visible parody notice (legal decision: real
  names are fine *with* a clear satire disclaimer).

LEGAL NOTE: these names are third-party trademarks used here for **parody /
satire**. The disclaimer must render visibly with every persona-written piece;
do not publish a persona story without it.
"""

from __future__ import annotations

import hashlib

# ─────────────────────────────────────────────────────────────────────────────
# The roster: character → voice brief (tone + signature phrasing for the prompt)
# ─────────────────────────────────────────────────────────────────────────────
ROSTER: dict[str, str] = {
    "Spider-Man": (
        "Wisecracking, self-deprecating, motor-mouthed teenager from Queens. "
        "Quips mid-sentence, breaks tension with a joke, drops 'with great power…' riffs."
    ),
    "The Incredible Hulk": (
        "Short, smashing, third-person, simple declaratives. ALL-CAPS for emphasis. "
        "Big feelings, bigger fists. 'HULK LIKE GOOD NEWS.'"
    ),
    "Iron Man": (
        "Glib billionaire genius. Sardonic, name-drops his own tech, ends on a smug one-liner. "
        "Treats every story like a product launch he's narrating."
    ),
    "Thor": (
        "Grandiose Asgardian Shakespeare-by-way-of-Marvel. 'Verily', 'tis a most worthy tale', "
        "calls mundane objects by epic names (a kettle is 'this vessel of boiling fury')."
    ),
    "Deadpool": (
        "Fourth-wall-breaking, chaotic, footnote-loving. Talks to the reader directly, "
        "mocks the format, keeps it PG-13 for the Gazette."
    ),
    "Doctor Strange": (
        "Portentous, mystical, faintly condescending. Frames a bake sale as a ripple "
        "across the multiverse. 'In one of fourteen million futures…'"
    ),
    "Captain America": (
        "Earnest, square-jawed, civic-minded. Old-fashioned decency, gentle 'language!' "
        "energy, finds the moral uplift in everything."
    ),
    "Black Widow": (
        "Cool, dry, economical. Understated wit, reads the room, lands the story like "
        "a debrief with one perfectly raised eyebrow."
    ),
    "Groot": (
        "Says only variations of 'I am Groot' — the rewriter renders the story as a "
        "deadpan 'translation' beneath each Groot line."
    ),
    "Rocket Raccoon": (
        "Irritable, scheming, sweary-but-bleeped. Thinks everyone's an idiot, "
        "secretly delighted by the good news, won't admit it."
    ),
    "Scarlet Witch": (
        "Melancholic, reality-bending, lyrical. Reshapes the facts into something "
        "wistful and a little uncanny."
    ),
    "Star-Lord": (
        "'80s-pop-soundtrack swagger, outdated Earth references, legend-in-his-own-mind "
        "narration that slightly overpromises."
    ),
}

SATIRE_DISCLAIMER: str = (
    "Parody. Written by AI in the satirical voice of a fictional character; "
    "not affiliated with, endorsed by, or sourced from the trademark holder."
)


def _seed_int(seed: str) -> int:
    """Deterministic integer from an arbitrary seed string (e.g. an ISO date)."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


def assign_personas(n: int, *, seed: str) -> list[str]:
    """Return ``n`` distinct characters, day-stable and rotating by ``seed``.

    Same seed → same lineup (reproducible re-runs); different seed → a different
    rotation. Never repeats a character, and caps at the roster size.
    """
    characters = list(ROSTER.keys())
    n = min(n, len(characters))
    rng = _seed_int(seed)
    # Deterministic rotation + offset stride derived from the seed.
    start = rng % len(characters)
    stride = 1 + (rng // len(characters)) % (len(characters) - 1)
    while _gcd(stride, len(characters)) != 1:
        stride += 1  # ensure the stride visits every index (full cycle)
    order = [characters[(start + i * stride) % len(characters)] for i in range(len(characters))]
    return order[:n]


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def voice_brief(character: str) -> str:
    """The tone/phrasing cue for ``character``, injected into the rewrite prompt."""
    return ROSTER.get(character, "")


def persona_byline(character: str) -> str:
    """The byline for a persona-written piece."""
    return f"As told to The Craic Gazette by {character}"
