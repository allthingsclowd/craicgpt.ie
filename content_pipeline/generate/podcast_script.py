"""
content_pipeline/generate/podcast_script.py
===========================================
Build the script for the daily **dad↔son podcast**: Graham and Tom take turns reading the
articles aloud, with short linking banter, so it plays as a flowing two-handed discussion
— topped and tailed by the 80s call-sign jingle + signature.

TUTORIAL: deterministic frame, probabilistic filling — ONE clip per article
---------------------------------------------------------------------------
The audio is built from FEW, LONG clips, not many short ones: every short back-and-forth
turn used to be a separate TTS synthesis, and the SEAMS between clips are where the clone
degrades. So each article is now ONE clip — the reader's opening link + the *verbatim*
reading + their closing hand-off, all in one voice — and a parody guest reads in their own
voice between a fixed welcome and sign-off.

Two of the three layers are DETERMINISTIC and never touch an LLM:
  1. the signature intro/outro + the fixed guest welcome/ack/sign-off, and
  2. the article READINGS — the exact text the edition rubric already approved (no
     paraphrase → no new claims, no attribution drift).
Only the host LINKS (the one-line pre/post around each host read) are PROBABILISTIC — a
single ``write_model`` call drafts them all at once (Tom's character stays consistent).
They are the ONLY generated content, so they are the only thing the deepagents rubric has
to gate before a word is voiced (see ``rubric_review.grade_podcast_script``). Same split
as the rest of the paper: code does the mechanics, the rubric judges the judgement.
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
    """A clean, professional two-host cold-open, with the edition's live date folded in.

    Graham introduces himself and the date; Tom breaks in to introduce himself; then
    they're straight into it. (The old elongated 'GOOOOD morning' read as a shout — a
    speaking-voice clone can't sing, so stretching the vowels just sounded off.) The
    brand reads as 'Crack Gee Pee Tee' via audio._phonetic, and 'craic' as 'crack'.
    """
    return [
        ("graham",
         f"Good morning, and welcome to CraicGPT — the AI news with a bit of craic. I'm "
         f"Graham, the Scripting Paddy, and today is {_date_phrase(date_iso)}."),
        ("tom",
         "And I'm Tom — the voice of reason, allegedly. Right, let's get into it."),
    ]


SIGNATURE_OUTRO: list[Turn] = [
    ("graham", "And sure look, that's enough craic for one day. Come back to us tomorrow "
               "at craicgpt.ie for another podcast."),
    ("tom", "See yiz!"),
    ("graham", "God bless."),
]

# Deterministic guest framing — kept SIMPLE (Graham's call): a one-line host welcome,
# the guest's one-line thanks, and a one-line sign-off. No LLM, so nothing to gate. The
# guest reads in their OWN cloned voice between the thanks and the sign-off, so the whole
# guest segment is ONE clip (thanks + verbatim reading + sign-off) — no seams mid-guest.
GUEST_WELCOME = ("And now we have a guest presenter, {persona}, to lighten the mood. "
                 "Hi {persona}, welcome to CraicGPT — we're delighted to have you with us today.")
GUEST_ACK = "Tom, Graham — thanks for having me."
GUEST_SIGNOFF = "And that's me — back to you, lads."

# The banter prompt. CHANGED to the "one clip per article" model: every short back-and-
# forth turn used to be its own TTS clip, and the SEAMS between clips are where the clone's
# quality fell apart. So each reader's whole segment is now recorded as ONE piece — their
# opening link + the verbatim reading + their closing hand-off — and the LLM writes only
# those two short links per host-read article (the readings + the guest framing are not its
# job). Far fewer seams; the links are still the only thing the rubric gate has to judge.
_BANTER_PROMPT = (
    "You are scripting a warm, witty Irish podcast — one FLOWING conversation between "
    "GRAHAM (the dad: patient, funny, gently cynical, teaching-minded, 'the Scripting "
    "Paddy') and his cheeky, curious 14-year-old son TOM. Tom is quick and funny but "
    "talks like a NORMAL bright teenager: keep his slang MINIMAL and timeless (an "
    "occasional 'gas', 'deadly', 'no way') — never trendy meme-speak, it dates badly. "
    "Clean and PG throughout; cheeky, never cruel; nothing grim.\n"
    "The hosts TAKE TURNS reading the articles aloud (each line below says who reads it). "
    "To keep the audio smooth we record each reader's whole segment as ONE piece, so for "
    "EACH article READ BY A HOST you write just two short links:\n"
    "  • \"pre\": how that reader OPENS — ONE warm sentence reacting to the bit just before "
    "(the previous reader's story, or the guest who just spoke), then easing into THIS "
    "article. Do NOT hand over to anyone in the pre (handing over is the PREVIOUS reader's "
    "job) — just react and lead in. Leave it EMPTY (\"\") for the FIRST article — it follows "
    "the intro.\n"
    "  • \"post\": how that reader CLOSES — ONE sentence: a quick take on THIS article, then "
    "hand over to the NEXT speaker BY NAME (e.g. 'over to you, Tom'). For the LAST article, "
    "wind down toward the sign-off instead of handing over.\n"
    "GUEST articles are read by a parody guest in their OWN voice and are topped by a FIXED "
    "welcome — that is NOT yours to write, so DO NOT emit an item for a guest. But the host "
    "article RIGHT AFTER a guest should have its \"pre\" react to that guest.\n"
    "Never summarise or read an article — the reader reads the body itself. ONE sentence "
    "per field, plain and natural, so it flows straight into (and out of) the reading.\n"
    "Output ONLY compact JSON (no markdown), exactly:\n"
    '{{"items":[{{"ref":"<the ref>","pre":"...","post":"..."}}]}}\n'
    "Include an item ONLY for host-read articles.\n\n"
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
    """The verbatim text read for an article: headline, standfirst, then body (plain)."""
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _guest_voice(item: dict) -> Optional[str]:
    """The parody guest's voice key IFF their clone is deployed — so they read their own
    article in their own cloned voice. ``None`` for non-parody / undeployed."""
    persona = item.get("persona")
    if not persona:
        return None
    from content_pipeline.generate.audio import has_clone
    from content_pipeline.generate.personas import persona_voice_key
    vk = persona_voice_key(persona)
    return vk if has_clone(vk) else None


def _digest(plan: list[dict]) -> str:
    """A compact, token-light digest of the articles in reading order — each one's position,
    who voices it (a host, or a parody GUEST who reads in their OWN voice + which host
    welcomes them), and a snippet — so the LLM can write host links that flow and react to
    the guests."""
    lines = []
    n = len(plan)
    for j, p in enumerate(plan):
        pos = "FIRST" if j == 0 else ("LAST" if j == n - 1 else f"#{j + 1}")
        snippet = (p["item"].get("standfirst") or p["item"].get("body") or "")[:150]
        if p["role"] == "guest":
            role = (f"GUEST '{p['persona']}' reads this in their OWN voice (welcomed by "
                    f"{p['introducer'].upper()} via a FIXED line — write NO item for this one)")
        else:
            role = f"read by {p['voice'].upper()}"
        lines.append(f"[{p['ref']} | {pos} | {role}] {p['item'].get('title', '')} — {snippet}")
    return "\n".join(lines)[:6000]


def _text_field(value: Any) -> str:
    """Coerce one LLM link field to a clean one-line string — tolerant of a plain string
    or a list of ``{text}``/strings from an older/looser shape (local models wander)."""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        parts = [(_text_field(e.get("text")) if isinstance(e, dict) else _text_field(e))
                 for e in value]
        return " ".join(p for p in parts if p)
    return ""


def _script_text(turns: list[Turn]) -> str:
    """Render turns as a speaker-tagged transcript (also the downloadable transcript)."""
    return "\n".join(f"{who.upper()}: {text}" for who, text in turns)


def _plan(pairs: list[tuple[str, dict]]) -> list[dict]:
    """Decide who voices each article. A parody item whose clone is DEPLOYED is a ``guest``
    (reads in their OWN voice, welcomed by the seniority host); everything else is a
    ``host`` read that alternates Graham/Tom. Guests don't consume a host-alternation slot,
    so consecutive host reads still ping-pong. Returns one plan dict per article."""
    from content_pipeline.generate.personas import introducer_for
    plan: list[dict] = []
    host_i = 0
    for ref, item in pairs:
        gv = _guest_voice(item)
        persona = item.get("persona")
        if persona and gv:
            plan.append({"ref": ref, "item": item, "role": "guest", "voice": gv,
                         "persona": persona, "introducer": introducer_for(persona)})
        else:
            plan.append({"ref": ref, "item": item, "role": "host",
                         "voice": _reader_for(host_i), "persona": persona})
            host_i += 1
    return plan


def build_podcast_script(paper: dict, *, generate: Optional[Generate] = None,
                         limit: Optional[int] = None) -> dict:
    """Assemble the dad↔son podcast script for ``paper`` — the "one clip per article" model.

    Each article becomes ONE rendered clip: the reader's opening link + the VERBATIM
    reading + their closing hand-off, all in the reader's single voice. That's far fewer
    seams than the old before/read/after split (every extra turn was a separate TTS clip,
    and the seams between clips were where the clone degraded). A parody guest with a
    deployed clone gets a FIXED host welcome (one clip) then reads in their OWN voice (one
    clip: thanks + verbatim reading + sign-off).

    Returns ``{turns, script_text, banter_text, refs}``:
      * ``turns`` — ``[(voice, text), …]`` for :func:`audio.render_podcast` (1 clip each).
      * ``script_text`` — the full speaker-tagged transcript (publishable alongside audio).
      * ``banter_text`` — ONLY the model-written links (what the rubric gate judges); the
        fixed welcomes/acks and the verbatim readings are NOT in it.
      * ``refs`` — the article refs included, in order.
    """
    from content_pipeline.generate.personas import character_read_intro
    pairs = [(ref, _resolve_ref(paper, ref)) for ref in _ordered_refs(paper)]
    pairs = [(ref, item) for ref, item in pairs if item]
    if limit is not None:
        pairs = pairs[:limit]
    plan = _plan(pairs)

    # ONE LLM call drafts the host links (pre/post) for every HOST-read article (keeps Tom's
    # character consistent). Guests are framed by fixed templates, so the LLM skips them.
    banter_by_ref: dict[str, dict] = {}
    if any(p["role"] == "host" for p in plan):
        gen = generate or _default_generate
        try:
            data = gen(_BANTER_PROMPT.format(digest=_digest(plan)))
            for entry in (data.get("items") or []):
                if isinstance(entry, dict) and entry.get("ref"):
                    banter_by_ref[str(entry["ref"])] = entry
        except Exception as exc:  # noqa: BLE001 — links are best-effort; readings still play
            logger.warning("[podcast] banter generation failed (%s); readings only", exc)

    turns: list[Turn] = list(build_signature_intro(paper.get("date") or ""))
    banter_snippets: list[str] = []
    for p in plan:
        reading = _reading(p["item"])
        if p["role"] == "guest":
            # fixed welcome (introducing host) + the guest's own-voice clip (one piece)
            turns.append((p["introducer"], GUEST_WELCOME.format(persona=p["persona"])))
            turns.append((p["voice"], "\n\n".join([GUEST_ACK, reading, GUEST_SIGNOFF])))
        else:
            b = banter_by_ref.get(p["ref"], {})
            pre, post = _text_field(b.get("pre")), _text_field(b.get("post"))
            banter_snippets += [s for s in (pre, post) if s]   # only the LLM text is gated
            body = reading
            if p.get("persona"):   # parody item with NO deployed clone → host reads in character
                intro = character_read_intro(p["persona"])
                body = f"{intro}\n\n{reading}" if intro else reading
            turns.append((p["voice"], "\n\n".join(s for s in (pre, body, post) if s)))
    turns += SIGNATURE_OUTRO

    return {
        "turns": turns,
        "script_text": _script_text(turns),
        "banter_text": "\n".join(banter_snippets),
        "refs": [p["ref"] for p in plan],
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
