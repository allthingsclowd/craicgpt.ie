"""
content_pipeline/generate/podcast_script.py
===========================================
Build the script for the daily **dad↔son podcast**: Graham and Tom TAKE TURNS reading
the articles aloud and banter before and after each one, so it plays as a flowing
two-handed discussion — topped and tailed by the trad jingle + "Craic of Dawn" signature.

TUTORIAL: deterministic frame, probabilistic filling
----------------------------------------------------
Two of the three layers are DETERMINISTIC and never touch an LLM:
  1. the signature intro/outro (fixed audio branding), and
  2. the article READINGS — Graham and Tom take turns reading each article's *verbatim*
     body, the exact text the edition rubric already approved (no paraphrase → no new
     claims, no attribution drift).
Only the BANTER is PROBABILISTIC — a single ``write_model`` call drafts every
before/after exchange at once (Tom's character stays consistent). Because it's the only
generated content, it is the only thing the deepagents rubric has to gate before a word
is voiced (see ``rubric_review.grade_podcast_script``). Same split as the rest of the
paper: code does the mechanics, the rubric judges the judgement.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]
Turn = tuple[str, str]  # (voice, text)

# The two hosts TAKE TURNS reading the articles — Graham (dad) opens, then they
# alternate so the show plays as a two-handed discussion, not a monologue.
_PODCAST_READERS: tuple[str, str] = ("graham", "tom")


def _reader_for(index: int) -> str:
    return _PODCAST_READERS[index % len(_PODCAST_READERS)]

# ── Fixed signature (the "Craic of Dawn" audio branding; same every day) ──────
# NB: "Craic" is left spelled correctly here (this is also the on-screen transcript);
# the TTS layer pronounces it "crack" — so "craic of dawn" lands as the "crack of dawn"
# pun (see audio._phonetic).
def _date_phrase(date_iso: str) -> str:
    """Human-spoken date from the edition's OWN date (no clock — stays deterministic).

    ``2026-05-12`` → ``Tuesday the 12th of May, 2026``.
    """
    from datetime import datetime
    try:
        d = datetime.strptime((date_iso or "").strip(), "%Y-%m-%d")
    except ValueError:
        return "today"
    suffix = "th" if 11 <= d.day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return d.strftime(f"%A the {d.day}{suffix} of %B, %Y")


def build_signature_intro(date_iso: str) -> list[Turn]:
    """The lively, exaggerated cold-open jingle — with the edition's live date folded in.

    Elongated vowels + exclamation push the clone as 'big' as a speaking-voice clone goes
    (it can't literally sing). The brand reads as 'Crack Gee Pee Tee' via audio._phonetic.
    """
    return [
        ("graham",
         f"Gooooooood moooorning, CraicGPT! Helloooo everyone — today is {_date_phrase(date_iso)}, "
         f"and Tom and I are here with your daily A.I. update. This is where we put the A.I. back "
         f"in craic, with a sliver of Irish humour!"),
        ("tom", "Howya! Let's get into it."),
    ]


SIGNATURE_OUTRO: list[Turn] = [
    ("graham", "And sure look, that's enough craic for one day. Come back to us tomorrow "
               "at craicgpt.ie for another podcast."),
    ("tom", "See yiz!"),
    ("graham", "God bless."),
]

_BANTER_PROMPT = (
    "You are scripting a warm, witty Irish podcast that should feel like one flowing "
    "CONVERSATION between GRAHAM (the dad — patient, funny, gently cynical, teaching-"
    "minded, 'the Scripting Paddy') and TOM, his loveable, cheeky, curious 14-year-old "
    "son. They TAKE TURNS reading the articles aloud — each article below says who reads "
    "it — and you write only the SHORT banter that links them into a discussion.\n"
    "For EACH article write:\n"
    "  • before: 1-2 short turns that tee it up — the host who is NOT reading it hands "
    "over to the one who is (a natural 'go on, you take this one' invite), ideally "
    "nodding back to what they were just talking about so it flows on.\n"
    "  • after: 1-2 short turns — a quick reaction or daft follow-up, then a one-line "
    "takeaway that leads into the NEXT topic.\n"
    "Make it continuous: each item connects to the one before and the one after, not a "
    "list of standalone bits. One sentence per turn. Kind, funny, doom-free, PG — Tom is "
    "cheeky but never cruel; nothing grim. Refer to the article by what it's about; do "
    "NOT read it (the hosts read the body themselves).\n"
    "Output ONLY compact JSON (no markdown), exactly:\n"
    '{{"items":[{{"ref":"<the ref>","before":[{{"who":"tom|graham","text":"..."}}],'
    '"after":[{{"who":"tom|graham","text":"..."}}]}}]}}\n\n'
    "Articles in reading order:\n{digest}"
)


def _resolve_ref(paper: dict, ref: str) -> Optional[dict]:
    """Resolve a layout ref like ``ai.headliner`` / ``ai.shorts.0`` / ``fun.0`` to an item."""
    node: Any = paper
    for part in ref.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node if isinstance(node, dict) else None


def _ordered_refs(paper: dict) -> list[str]:
    """Article refs in reading order: the layout if present, else a sensible default."""
    layout = [r for r in (paper.get("layout") or []) if isinstance(r, str)]
    if layout:
        return layout
    refs = ["ai.headliner"]
    refs += [f"ai.subarticles.{i}" for i in range(len(paper.get("ai", {}).get("subarticles") or []))]
    refs += [f"ai.shorts.{i}" for i in range(len(paper.get("ai", {}).get("shorts") or []))]
    refs += [f"fun.{i}" for i in range(len(paper.get("fun") or []))]
    return refs


def _reading(item: dict) -> str:
    """The verbatim text read for an article: headline, standfirst, then body.

    For a PARODY item (one written in a roster persona) we prepend a short spoken
    'character' framing — our no-clone way to flag a character bit — while the body
    stays verbatim (it's already written in that persona's voice). See
    :func:`personas.character_read_intro`.
    """
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    body = "\n\n".join(p.strip() for p in parts if p and p.strip())
    persona = item.get("persona")
    if persona:
        from content_pipeline.generate.personas import character_read_intro
        intro = character_read_intro(persona)
        if intro:
            return f"{intro}\n\n{body}"
    return body


def _digest(pairs: list[tuple[str, dict]]) -> str:
    """A compact, token-light digest of the articles — with each one's reader and
    position — so the banter prompt can write hand-offs and flowing transitions."""
    lines = []
    n = len(pairs)
    for i, (ref, item) in enumerate(pairs):
        pos = "first" if i == 0 else ("last" if i == n - 1 else f"#{i + 1}")
        snippet = (item.get("standfirst") or item.get("body") or "")[:160]
        lines.append(f"[{ref} | {pos} | read by {_reader_for(i).upper()}] "
                     f"{item.get('title', '')} — {snippet}")
    return "\n".join(lines)[:6000]


def _turns_from_banter(entries: Any) -> list[Turn]:
    """Coerce a list of ``{who, text}`` into ``(voice, text)`` turns (voice → graham/tom)."""
    out: list[Turn] = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        who = str(e.get("who", "graham")).strip().lower()
        who = who if who in ("graham", "tom") else "graham"
        text = str(e.get("text", "")).strip()
        if text:
            out.append((who, text))
    return out


def _script_text(turns: list[Turn]) -> str:
    """Render turns as a speaker-tagged transcript (also the downloadable transcript)."""
    return "\n".join(f"{who.upper()}: {text}" for who, text in turns)


def build_podcast_script(paper: dict, *, generate: Optional[Generate] = None,
                         limit: Optional[int] = None) -> dict:
    """Assemble the dad↔son podcast script for ``paper``.

    Returns ``{turns, script_text, banter_text, refs}``:
      * ``turns`` — ``[(voice, text), …]`` ready for :func:`audio.render_podcast`.
      * ``script_text`` — the full speaker-tagged transcript (publishable alongside audio).
      * ``banter_text`` — ONLY the model-written banter (what the rubric gate judges).
      * ``refs`` — the article refs included, in order.
    """
    pairs = [(ref, _resolve_ref(paper, ref)) for ref in _ordered_refs(paper)]
    pairs = [(ref, item) for ref, item in pairs if item]
    if limit is not None:
        pairs = pairs[:limit]

    # One LLM call drafts banter for every article (keeps Tom's character consistent).
    banter_by_ref: dict[str, dict] = {}
    if pairs:
        gen = generate or _default_generate
        try:
            data = gen(_BANTER_PROMPT.format(digest=_digest(pairs)))
            for entry in (data.get("items") or []):
                if isinstance(entry, dict) and entry.get("ref"):
                    banter_by_ref[str(entry["ref"])] = entry
        except Exception as exc:  # noqa: BLE001 — banter is best-effort; readings still play
            logger.warning("[podcast] banter generation failed (%s); readings only", exc)

    turns: list[Turn] = list(build_signature_intro(paper.get("date") or ""))
    banter_turns: list[Turn] = []
    for i, (ref, item) in enumerate(pairs):
        reader = _reader_for(i)                     # alternate who reads each article
        b = banter_by_ref.get(ref, {})
        before = _turns_from_banter(b.get("before"))
        after = _turns_from_banter(b.get("after"))
        banter_turns += before + after
        turns += before
        turns.append((reader, _reading(item)))      # verbatim reading, alternating voice
        turns += after
    turns += SIGNATURE_OUTRO

    return {
        "turns": turns,
        "script_text": _script_text(turns),
        "banter_text": _script_text(banter_turns),
        "refs": [ref for ref, _ in pairs],
    }


def _default_generate(prompt: str) -> dict:
    """Default banter LLM call — reuses the writer's local-first JSON generator."""
    from content_pipeline.generate.writer import _default_generate as _gen
    return _gen(prompt)


# ─────────────────────────────────────────────────────────────────────────────
# TL;DR — the <180s two-voice headline bulletin (deterministic; same jingle)
# ─────────────────────────────────────────────────────────────────────────────
# A fast "headlines podcast": Graham and Tom ALTERNATE reading the day's headlines
# (each item's already-approved title + a one-line gloss), topped & tailed by the
# SAME trad jingle as the full show. Fully DETERMINISTIC — no LLM, no banter to gate —
# and word-budgeted to the speaking time left after the jingle, so it reliably lands
# under the cap even if the voice clone reads slowly.
TLDR_BUDGET_WPM = 135          # a deliberately conservative read-rate FLOOR (real speech
                               # is faster) so the budget never overshoots the cap
TLDR_JINGLE_SECONDS = 26       # the trad bookend (intro + outro) eats into the time budget


def build_tldr_intro(date_iso: str) -> list[Turn]:
    return [
        ("graham", f"Good morning! Here's your quick CraicGPT headline round-up for "
                   f"{_date_phrase(date_iso)}."),
        ("tom", "Right, let's rattle through them!"),
    ]


TLDR_OUTRO: list[Turn] = [
    ("graham", "And that's your headlines. The full show and every story are at "
               "craicgpt.ie — back tomorrow."),
    ("tom", "See yiz!"),
]


def _first_sentence(text: str, *, max_chars: int = 140) -> str:
    """A one-line gloss: the first sentence (or a clipped clause) of the standfirst/body."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    s = re.split(r"(?<=[.!?])\s+", t, maxsplit=1)[0]
    if len(s) > max_chars:
        s = s[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return s


def _headline_beat(item: dict, reader: str) -> Turn:
    """One headline read: the (clipped) title + a one-line gloss, in ``reader``'s voice."""
    title = (" ".join(str(item.get("title", "")).split()).rstrip("."))[:100]
    gloss = _first_sentence(item.get("standfirst") or item.get("body") or "")
    return (reader, f"{title}." if not gloss else f"{title}. {gloss}")


def _count_words(turns: list[Turn]) -> int:
    return sum(len(t.split()) for _, t in turns)


def build_tldr_script(paper: dict, *, max_seconds: int = 180,
                      limit: Optional[int] = None) -> dict:
    """Assemble the sub-``max_seconds`` TL;DR headline bulletin for ``paper``.

    Graham and Tom ALTERNATE reading each headline (the edition's own, already-approved
    title + a one-line gloss). Deterministic — no LLM — and word-budgeted to the speaking
    time left after the jingle bookend, so it reliably lands under ``max_seconds``.
    Returns the same shape as :func:`build_podcast_script`; ``banter_text`` is empty
    (nothing is model-written, so there's nothing for the rubric to gate).
    """
    budget_words = max(0, int((max_seconds - TLDR_JINGLE_SECONDS) * TLDR_BUDGET_WPM / 60.0))

    pairs = [(ref, _resolve_ref(paper, ref)) for ref in _ordered_refs(paper)]
    pairs = [(ref, item) for ref, item in pairs if item]
    if limit is not None:
        pairs = pairs[:limit]

    intro = list(build_tldr_intro(paper.get("date") or ""))
    turns: list[Turn] = list(intro)
    used = _count_words(intro) + _count_words(TLDR_OUTRO)  # reserve the outro's words
    refs: list[str] = []
    for i, (ref, item) in enumerate(pairs):
        beat = _headline_beat(item, _reader_for(i))
        w = len(beat[1].split())
        if refs and used + w > budget_words:   # always keep at least one headline
            break
        turns.append(beat)
        used += w
        refs.append(ref)
    turns += TLDR_OUTRO

    return {
        "turns": turns,
        "script_text": _script_text(turns),
        "banter_text": "",      # deterministic — no LLM banter, nothing to gate
        "refs": refs,
    }
