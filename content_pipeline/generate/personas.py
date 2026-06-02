"""
content_pipeline/generate/personas.py
======================================
The Craic Gazette's roster of parody "AI journalists".

Each fun story is written in the unmistakable voice of a well-known public
figure, bylined under a punny misspelling of their name (e.g. Donald Trump's
voice → "Ronald Dump"). This module owns:

- :data:`ROSTER`            — journalist name → voice brief (the real person's
                              tone + signature phrases for the rewrite prompt).
- :func:`assign_personas`   — a day-stable, rotating, no-repeat lineup.
- :func:`voice_brief`       — the style cue fed into the rewrite prompt.
- :func:`persona_byline`    — the "as told to…" byline.
- :data:`SATIRE_DISCLAIMER` — the visible parody notice.

LEGAL NOTE: these are parody/satire impressions of public figures for comedic
commentary; the bylines are deliberate misspellings. The disclaimer must render
visibly with every persona-written piece.
"""

from __future__ import annotations

import hashlib

# ─────────────────────────────────────────────────────────────────────────────
# The roster: parody-journalist name → voice brief (real figure's style + phrases)
# ─────────────────────────────────────────────────────────────────────────────
ROSTER: dict[str, str] = {
    "Ronald Dump": (
        "In the style of Donald Trump: bombastic, superlative-addicted, "
        "stream-of-consciousness. Brags constantly, insults rivals, treats every "
        "story as a personal win. Phrases: 'Believe me', 'many people are saying', "
        "'tremendous', 'the best, the greatest, nobody does it better', 'Fake News', "
        "'Sad!', 'bigly'. Veers off-topic, then circles back to himself."
    ),
    "Bonio": (
        "In the style of Bono (U2): grandiose activist-poet, sweeping metaphors, "
        "spiritual undertones, self-referential about his good causes. Phrases: "
        "'One love, one people', 'the ones without a voice', 'grace', 'until the "
        "end of the world', 'we can change this — together'. Earnest to the point "
        "of pomposity; finds the soul of every story."
    ),
    "Jeremy Clarkscone": (
        "In the style of Jeremy Clarkson: exasperated, hyperbolic petrolhead, "
        "anti-bureaucracy rants, vivid crude comparisons, cheerful incompetence. "
        "Phrases: 'the fastest / biggest / most powerful … IN THE WORLD', 'how "
        "hard can it be?', 'and on that bombshell', 'the government wants a form "
        "for that', a dramatic 'But'. Mock-outraged, secretly delighted."
    ),
    "Roy Mean": (
        "In the style of Roy Keane: blunt, withering, no-nonsense Cork enforcer. "
        "Contempt for softness and excuses; demands character and standards. "
        "Phrases: 'I don't care', 'no character', 'that's not acceptable', 'in my "
        "day', 'who do they think they are?', 'cribbing and moaning'. Short, hard "
        "sentences. Unimpressed by everyone."
    ),
    "Mary Whitemouse": (
        "In the style of Mary Whitehouse: prim, scandalised moral campaigner, "
        "formally eloquent but dripping with distaste, forever defending decency "
        "and 'the children'. Phrases: 'filth', 'the permissive society', 'what "
        "message does this send our children?', 'standards have fallen', 'I am "
        "appalled'. Finds a moral crisis in everything — even good news."
    ),
    "Hannah Pi": (
        "In the style of Hannah Fry: warm, witty mathematician who finds the "
        "hidden pattern in everything and loves a counterintuitive twist. Phrases: "
        "'surprisingly', 'you'd think X — but actually', 'it all comes down to the "
        "numbers', 'the data tells a different story', 'here's the lovely bit'. "
        "Demystifying, curious, gently delighted by probability."
    ),
    "A-Dell": (
        "In the style of Adele: warm, candid, working-class London, emotional and "
        "self-deprecating, swings from funny to raw. Phrases: 'right', 'innit', "
        "'I'm an absolute mess', 'bless', 'I had a little cry', 'me and the boy'. "
        "Big feelings, dry jokes, treats the reader like a mate over a cuppa."
    ),
    "Ciara Brightly": (
        "In the style of Ciara Kightley (Irish lifestyle influencer): bubbly, "
        "upbeat Dublin content-creator energy, relatable, aspirational-but-grounded. "
        "Phrases: 'lads', 'okay so', 'literally obsessed', 'not gonna lie', '10 out "
        "of 10', 'unsponsored but obsessed', 'come with me'. GRWM framing, lots of "
        "warmth, the odd 'grand'."
    ),
}

SATIRE_DISCLAIMER: str = (
    "Parody. Written by AI as a satirical impression of a public figure; the "
    "byline is a deliberate misspelling. Not affiliated with, endorsed by, or "
    "sourced from the person depicted."
)


def _seed_int(seed: str) -> int:
    """Deterministic integer from an arbitrary seed string (e.g. an ISO date)."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


def assign_personas(n: int, *, seed: str) -> list[str]:
    """Return ``n`` distinct journalists, day-stable and rotating by ``seed``.

    Same seed → same lineup (reproducible re-runs); different seed → a different
    rotation. Never repeats, caps at the roster size.
    """
    characters = list(ROSTER.keys())
    n = min(n, len(characters))
    rng = _seed_int(seed)
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
