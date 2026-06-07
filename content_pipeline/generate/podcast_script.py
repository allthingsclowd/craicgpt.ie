"""
content_pipeline/generate/podcast_script.py
===========================================
Build the script for the daily **dad↔son podcast**: Graham reads each article, with
Tom (his curious, cheeky 14-year-old) and Graham bantering before and after — topped
and tailed by the fixed "Craic of Dawn" signature.

TUTORIAL: deterministic frame, probabilistic filling
----------------------------------------------------
Two of the three layers are DETERMINISTIC and never touch an LLM:
  1. the signature intro/outro (fixed audio branding), and
  2. the article READINGS — Graham reads each article's *verbatim* body, the exact
     text the edition rubric already approved (no paraphrase → no new claims, no
     attribution drift).
Only the BANTER is PROBABILISTIC — a single ``write_model`` call drafts every
before/after exchange at once (Tom's character stays consistent). Because it's the only
generated content, it is the only thing the deepagents rubric has to gate before a word
is voiced (see ``rubric_review.grade_podcast_script``). Same split as the rest of the
paper: code does the mechanics, the rubric judges the judgement.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]
Turn = tuple[str, str]  # (voice, text)

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
    ("graham", "And sure look, that's enough craic for one day. We'll do it all again tomorrow."),
    ("tom", "See yiz!"),
    ("graham", "God bless."),
]

_BANTER_PROMPT = (
    "You are scripting a warm, witty Irish podcast: GRAHAM (the dad — patient, funny, "
    "gently cynical, teaching-minded, 'the Scripting Paddy') explains today's news to "
    "TOM, his loveable, cheeky, curious 14-year-old son. Graham reads each article aloud "
    "himself; you write only the SHORT banter around each one.\n"
    "For EACH article below write:\n"
    "  • before: 1-2 short turns to tee it up — usually Tom asking a naive or cheeky "
    "question, Graham setting it up in a line.\n"
    "  • after: 1-2 short turns — Tom's quick reaction or a daft follow-up, Graham landing "
    "a one-line takeaway.\n"
    "One sentence per turn. Kind, funny, doom-free, PG — Tom is cheeky but never cruel or "
    "disrespectful; nothing grim. Refer to the article by what it's about, don't read it.\n"
    "Output ONLY compact JSON (no markdown), exactly:\n"
    '{{"items":[{{"ref":"<the ref>","before":[{{"who":"tom|graham","text":"..."}}],'
    '"after":[{{"who":"tom|graham","text":"..."}}]}}]}}\n\n'
    "Articles:\n{digest}"
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
    """The verbatim text Graham reads for an article: headline, standfirst, then body."""
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _digest(pairs: list[tuple[str, dict]]) -> str:
    """A compact, token-light digest of the articles for the banter prompt."""
    lines = []
    for ref, item in pairs:
        snippet = (item.get("standfirst") or item.get("body") or "")[:160]
        lines.append(f"[{ref}] {item.get('title', '')} — {snippet}")
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
    for ref, item in pairs:
        b = banter_by_ref.get(ref, {})
        before = _turns_from_banter(b.get("before"))
        after = _turns_from_banter(b.get("after"))
        banter_turns += before + after
        turns += before
        turns.append(("graham", _reading(item)))   # verbatim reading, in Graham's voice
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
