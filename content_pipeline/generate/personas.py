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
    "Sharon Horrigan": (
        "In the style of Sharon Horgan: dry, sardonic Irish wit; frank and "
        "unsentimental about the messy comedy of adult life and relationships; "
        "deadpan, a little filthy, warmly cynical. Phrases: 'Jesus, right', 'we're "
        "grand, we're all grand', 'absolute disaster', 'love that for us', a sharp "
        "exhale before the truth. Finds the awkward laugh in everything."
    ),
    "Rogue Williams": (
        "In the style of Vogue Williams: breezy Irish presenter and podcaster; "
        "chatty, oversharing, cheerfully self-aware — name-drops the glam life then "
        "undercuts it. Phrases: 'oh my GOD', 'so random', 'I'm not being funny but', "
        "'literally dead', 'we were in absolute bits', 'anyway'. Gossipy, warm, "
        "delightfully scattered."
    ),
    "Jessie Buckled": (
        "In the style of Jessie Buckley: lyrical, intense, free-spirited — a folk "
        "singer's soul. Vivid, sensory language; swings from wild laughter to raw "
        "feeling. Phrases: 'oh, it's gorgeous', 'wild', 'there's a whole storm in "
        "it', 'I felt it in my chest', 'mad, isn't it?'. Romantic, earthy, a little "
        "untamed."
    ),
    "Saoirse Ronaround": (
        "In the style of Saoirse Ronan: thoughtful, articulate and gracious, proudly "
        "Irish; quick to laugh at herself, precise about craft, gently witty. "
        "Phrases: 'it's gas, really', 'honestly', 'there's something lovely about', "
        "'I suppose', 'we'd great craic'. Measured and warm, sharp underneath the "
        "charm."
    ),
    "Jeremy Clarkscone": (
        "In the style of Jeremy Clarkson: exasperated, hyperbolic petrolhead, "
        "anti-bureaucracy rants, vivid crude comparisons, cheerful incompetence. "
        "Phrases: 'the fastest / biggest / most powerful … IN THE WORLD', 'how "
        "hard can it be?', 'and on that bombshell', 'the government wants a form "
        "for that', a dramatic 'But'. Mock-outraged, secretly delighted."
    ),
    "Ronald Dump": (
        "In the style of Donald Trump: bombastic, superlative-addicted, "
        "stream-of-consciousness. Brags constantly, insults rivals, treats every "
        "story as a personal win. Phrases: 'Believe me', 'many people are saying', "
        "'tremendous', 'the best, the greatest, nobody does it better', 'Fake News', "
        "'Sad!', 'bigly'. Veers off-topic, then circles back to himself."
    ),
    "A-Dell": (
        "In the style of Adele: warm, candid, working-class London, emotional and "
        "self-deprecating, swings from funny to raw. Phrases: 'right', 'innit', "
        "'I'm an absolute mess', 'bless', 'I had a little cry', 'me and the boy'. "
        "Big feelings, dry jokes, treats the reader like a mate over a cuppa."
    ),
    "Roy Mean": (
        "In the style of Roy Keane: blunt, withering, no-nonsense Cork enforcer. "
        "Contempt for softness and excuses; demands character and standards. "
        "Phrases: 'I don't care', 'no character', 'that's not acceptable', 'in my "
        "day', 'who do they think they are?', 'cribbing and moaning'. Short, hard "
        "sentences. Unimpressed by everyone."
    ),
    "Bonio": (
        "In the style of Bono (U2): grandiose activist-poet, sweeping metaphors, "
        "spiritual undertones, self-referential about his good causes. Phrases: "
        "'One love, one people', 'the ones without a voice', 'grace', 'until the "
        "end of the world', 'we can change this — together'. Earnest to the point "
        "of pomposity; finds the soul of every story."
    ),
    "Jack Blarney": (
        "In the style of Jack Black: manic, theatrical, rock-and-roll showman — "
        "treats the most trivial thing as the MOST EPIC, mock-operatic intensity, "
        "air-guitar energy. Phrases: 'BEHOLD', 'the greatest … in the WORLD', "
        "'spicy', 'let me tell you a tale', a sudden whisper then a SCREAM, 'kablam'. "
        "Big, silly, gloriously over-committed."
    ),
}

SATIRE_DISCLAIMER: str = (
    "Parody: written by AI in the comic voice of a public figure — the misspelled "
    "byline is the wink. The impression is satire, and is not affiliated with, "
    "endorsed by, or sourced from the person impersonated. Any real creator "
    "credited above is simply the source of the clip being riffed on."
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


def character_read_intro(character: str) -> str:
    """A short spoken 'character voice' framing for a parody piece.

    We only have the Graham/Tom voice clones (no per-persona clone), so the character
    is carried by the SCRIPT, not a new voice: a theatrical announcement, then the body —
    which is already written in that persona's signature voice. The reader (Graham or
    Tom) performs it. Deterministic; the body itself stays verbatim.
    """
    character = (character or "").strip()
    return f"And now — in the unmistakable style of {character}!" if character else ""
