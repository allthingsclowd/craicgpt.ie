"""
content_pipeline/generate/translate.py
======================================
Translate a finished English edition into another language — the multi-lingual
desk's editing step.

TUTORIAL: write-once, translate-many (deterministic frame, probabilistic fill)
------------------------------------------------------------------------------
The English edition is the single editorial source of truth: it is researched,
written and **rubric-judged** once. Rather than re-run that whole agentic
pipeline per language (5× the research + judgement, and the parody personas are
Irish/UK figures that don't re-cast), we take the COMPILED English ``paper`` and
translate only its *prose fields* into each target language with one small
``plain chat → JSON`` call per section — the exact same robust contract the
writer uses (:func:`writer._default_generate` + :func:`writer.loads_lenient`).

Everything mechanical is preserved byte-for-byte: ``source_url``, ``image_url``
(images are language-agnostic and SHARED across editions), ``audio_url``, every
``_*model`` attribution, ``layout``, the creator ``source`` credit and the
``persona`` name. Only what a human would *read* is translated.

Honesty: each translated edition is stamped with ``edition.translated_by`` (the
model that did the translation) and ``edition.source_language`` — surfaced to the
reader as a light-hearted footer note + a spoken apology on the podcast, in the
spirit of the project's "the attribution reflects reality" rule.

The ``generate(prompt) -> dict`` call is injected, so this is unit-testable
offline and trivially parallelisable across fleet boxes.
"""

from __future__ import annotations

import copy
import functools
import logging
import os
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.generate.writer import _default_generate, loads_lenient  # noqa: F401  (loads_lenient re-exported for tests)

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]

# Human-readable names for the prompt ("translate into German"). The keys are the
# ISO-639-1 codes used in the URL prefix / CRAICGPT_LANGUAGES. Covers the
# Qwen3-TTS-supported set (audio-capable) plus a few common text-only languages.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English", "de": "German", "es": "Spanish", "it": "Italian",
    "ja": "Japanese", "fr": "French", "ko": "Korean", "pt": "Portuguese",
    "ru": "Russian", "zh": "Chinese", "nl": "Dutch", "pl": "Polish",
    "hi": "Hindi", "ar": "Arabic",
}

# Translation can be token-denser than the source (notably CJK), so the AI-section
# call — headliner + subarticles + ten shorts as one JSON object — gets more
# headroom than the writer's 8000, or the lenient parser drops the tail shorts.
_TRANSLATE_MAX_TOKENS = int(os.getenv("CRAICGPT_TRANSLATE_MAX_TOKENS", "12000"))

# Which prose fields get translated, per item kind. Everything else is preserved.
_HEAD_FIELDS = ("title", "standfirst", "body")
_AI_FIELDS = ("title", "body")
_FUN_FIELDS = ("title", "body", "byline", "satire_disclaimer")
_SIMPLE_FIELDS = ("title", "body")


def language_name(code: str) -> str:
    """Human-readable language name for a code, falling back to the code itself."""
    return LANGUAGE_NAMES.get(code, code)


# ─────────────────────────────────────────────────────────────────────────────
# The translation call (mirrors writer._default_generate, with a bigger cap)
# ─────────────────────────────────────────────────────────────────────────────
def _default_translate(prompt: str) -> dict:
    """The real translation LLM call: the multilingual write model, lenient-parsed."""
    return _default_generate(prompt, max_tokens=_TRANSLATE_MAX_TOKENS)


_TRANSLATE_PROMPT = (
    "You are a professional newspaper translator. Translate the JSON below into "
    "{language}. Rules:\n"
    "- Translate ONLY the string VALUES; keep every key and the JSON structure identical.\n"
    "- Keep the playful, witty, gently-cynical register of the original — this is a "
    "comic newspaper, not a press release.\n"
    "- Do NOT translate or alter: URLs, code, or the brand names 'CraicGPT' and "
    "'The Craic Gazette'. Keep people's and creators' proper names as they are.\n"
    "- Output ONLY the translated JSON (no markdown, no commentary), the SAME shape.\n\n"
    "JSON to translate:\n{payload}"
)


def _translate_block(payload: Any, language: str, generate: Generate) -> Any:
    """Translate a JSON-serialisable block (dict or list of dicts of strings).

    Returns the model's parsed JSON in the same shape. Raises on an unparseable
    response (the caller turns that into a per-section English fallback)."""
    import json

    prompt = _TRANSLATE_PROMPT.format(
        language=language_name(language),
        payload=json.dumps(payload, ensure_ascii=False),
    )
    return generate(prompt)


def _pluck(item: dict, fields: tuple[str, ...]) -> dict:
    """The translatable subset of an item (only present, non-empty string fields)."""
    return {f: item[f] for f in fields if isinstance(item.get(f), str) and item.get(f)}


def _merge_back(target: dict, translated: Any, fields: tuple[str, ...]) -> None:
    """Copy translated string fields onto ``target`` in place (English stays if missing)."""
    if not isinstance(translated, dict):
        return
    for f in fields:
        val = translated.get(f)
        if isinstance(val, str) and val.strip():
            target[f] = val


# ─────────────────────────────────────────────────────────────────────────────
# Per-section translation (each guarded → falls back to English, never crashes)
# ─────────────────────────────────────────────────────────────────────────────
def _translate_ai(ai: dict, language: str, generate: Generate) -> bool:
    """Translate the AI section in place. Returns True on success."""
    head = ai.get("headliner") or {}
    subs = ai.get("subarticles") or []
    shorts = ai.get("shorts") or []
    payload = {
        "headliner": _pluck(head, _HEAD_FIELDS),
        "subarticles": [_pluck(s, _AI_FIELDS) for s in subs],
        "shorts": [_pluck(s, _AI_FIELDS) for s in shorts],
    }
    out = _translate_block(payload, language, generate)
    _merge_back(head, out.get("headliner"), _HEAD_FIELDS)
    for tgt, tr in zip(subs, out.get("subarticles") or []):
        _merge_back(tgt, tr, _AI_FIELDS)
    for tgt, tr in zip(shorts, out.get("shorts") or []):
        _merge_back(tgt, tr, _AI_FIELDS)
    return True


def _translate_fun(fun: list, language: str, generate: Generate) -> bool:
    """Translate the fun desk in place. Returns True on success."""
    if not fun:
        return True
    payload = {"fun": [_pluck(f, _FUN_FIELDS) for f in fun]}
    out = _translate_block(payload, language, generate)
    for tgt, tr in zip(fun, out.get("fun") or []):
        _merge_back(tgt, tr, _FUN_FIELDS)
    return True


def _translate_simple(obj: Optional[dict], language: str, generate: Generate) -> bool:
    """Translate a ``{title, body}`` block (editor's brief / about page) in place."""
    if not obj or not (obj.get("title") or obj.get("body")):
        return True
    out = _translate_block(_pluck(obj, _SIMPLE_FIELDS), language, generate)
    _merge_back(obj, out, _SIMPLE_FIELDS)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def translate_paper(
    paper: dict,
    language: str,
    *,
    generate: Optional[Generate] = None,
) -> dict:
    """Return a deep copy of ``paper`` with its prose translated into ``language``.

    The source (English) edition is returned essentially unchanged (only its
    ``edition`` language fields are normalised). For any other language each prose
    section is translated independently; a section whose translation can't be
    parsed **falls back to the English text** and is noted in
    ``edition.translation_holds`` — a translation failure degrades to readable
    English, it never crashes the run or produces a broken page (translations
    inherit the English rubric verdict, so they are never re-judged or HELD).
    """
    out = copy.deepcopy(paper)
    edition = out.setdefault("edition", {})
    edition["language"] = language
    edition["source_language"] = content_cfg.source_language
    if not edition.get("available_languages"):
        edition["available_languages"] = list(content_cfg.languages)

    # The source language is generated natively — nothing to translate.
    if language == content_cfg.source_language:
        return out

    gen = generate or _default_translate
    edition["translated_by"] = content_cfg.write_model

    holds: list[str] = []
    sections: list[tuple[str, Callable[[], bool]]] = [
        ("ai", lambda: _translate_ai(out.get("ai") or {}, language, gen)),
        ("fun", lambda: _translate_fun(out.get("fun") or [], language, gen)),
        ("editors_brief", lambda: _translate_simple(out.get("editors_brief"), language, gen)),
        ("about", lambda: _translate_simple(out.get("about"), language, gen)),
    ]
    for name, fn in sections:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — degrade to English, never crash
            logger.warning("[translate] %s → %s failed, keeping English: %s", name, language, exc)
            holds.append(name)

    if holds:
        edition["translation_holds"] = holds
    return out
