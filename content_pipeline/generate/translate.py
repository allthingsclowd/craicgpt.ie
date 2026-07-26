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
import re
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.generate.writer import (  # noqa: F401  (loads_lenient re-exported for tests)
    _default_generate,
    _default_generate_text,
    loads_lenient,
)

logger = logging.getLogger(__name__)

# The translation seam is TEXT in, TEXT out. It used to be Callable[[str], dict] —
# which meant every test fake returned a dict and loads_lenient never ran, so the
# escaping contract that actually broke was structurally untestable. `Generate` is
# kept as an alias because other modules import it.
TranslateInvoke = Callable[[str], str]
Generate = TranslateInvoke

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

# Minimum share of translatable fields that must actually differ from English before
# a language is allowed to publish. A wholly-failed translation is byte-identical to
# a valid English paper (see translation_coverage), so without a floor it ships under
# a <lang>/ prefix and nothing notices. Generous on purpose: healthy live editions
# score 0.96-1.00, so 0.5 catches "shipped as English" without ever tripping on the
# brand names and short titles that legitimately survive translation.
MIN_TRANSLATION_COVERAGE = float(os.getenv("CRAICGPT_MIN_TRANSLATION_COVERAGE", "0.5"))

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
def _default_translate(prompt: str) -> str:
    """The real translation LLM call: the multilingual write model, RAW TEXT.

    No lenient JSON parse any more — the reply is marker-delimited prose, and
    :func:`_parse_items` owns the only parsing that happens."""
    return _default_generate_text(prompt, max_tokens=_TRANSLATE_MAX_TOKENS)


_MARKER = "===T{i}==="
_MARKER_RE = re.compile(r"^===T(\d+)===$", re.M)
_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```$")

# Marker-delimited plain text, NOT JSON. Asking a model to hand-escape prose into
# JSON string values is a trap: an apostrophe comes back as an illegal \' and a
# quoted phrase as \\\", json.loads raises, and the WHOLE language fails. That
# froze thegeekwiththepeak's it/ja editions for 22 days. craicgpt was carrying the
# same contract and surviving only on temperature-0.8 re-sampling — 6 of the last
# 10 editions shipped a field with an embedded double quote, and every one shipped
# 4-10 with a straight apostrophe. With markers the model escapes nothing.
_TRANSLATE_PROMPT = (
    "You are a professional newspaper translator. Translate the texts below into "
    "{language}. Rules:\n"
    "- Translate ONLY the natural-language prose.\n"
    "- Keep the playful, witty, gently-cynical register of the original — this is a "
    "comic newspaper, not a press release.\n"
    "- Do NOT translate or alter: URLs, code, or the brand names 'CraicGPT' and "
    "'The Craic Gazette'. Keep people's and creators' proper names as they are.\n"
    "\nOUTPUT FORMAT — output EXACTLY this and nothing else (no commentary, no code "
    "fences, no quoting, no escaping): for each item, a line containing only its "
    "marker, then that item's translation on the following line(s). Reproduce every "
    "marker exactly as given, in the same order.\n\n{items}"
)

_SINGLE_PROMPT = (
    "You are a professional newspaper translator. Translate the text below into "
    "{language}. Keep the playful, witty, gently-cynical register. Do NOT translate "
    "URLs, code, or the brand names 'CraicGPT' and 'The Craic Gazette'; keep proper "
    "names as they are. Reply with ONLY the translation — no commentary, no code "
    "fences, no quoting.\n\n{text}"
)


def _flatten(payload: Any, path: tuple = ()) -> list[tuple[tuple, str]]:
    """Every (path, text) leaf in a translate payload, in document order."""
    out: list[tuple[tuple, str]] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            out.extend(_flatten(v, (*path, k)))
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            out.extend(_flatten(v, (*path, i)))
    elif isinstance(payload, str) and payload:
        out.append((path, payload))
    return out


def _rebuild(payload: Any, mapping: dict[tuple, str], path: tuple = ()) -> Any:
    """The payload's shape with translated leaves substituted (untranslated stay English)."""
    if isinstance(payload, dict):
        return {k: _rebuild(v, mapping, (*path, k)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_rebuild(v, mapping, (*path, i)) for i, v in enumerate(payload)]
    if isinstance(payload, str):
        return mapping.get(path, payload)
    return payload


def _batch_by_item(leaves: list[tuple[tuple, str]]) -> list[list[tuple[tuple, str]]]:
    """Group leaves by the ITEM they belong to (everything but the field name).

    Per-item, NOT by character count: a headliner's standfirst is a précis of its
    body, and a fun item's body/byline/satire_disclaimer are one comic voice, so an
    item's fields must travel together or the register drifts between them.
    """
    batches: list[list[tuple[tuple, str]]] = []
    for path, text in leaves:
        item = path[:-1]
        if batches and batches[-1][0][0][:-1] == item:
            batches[-1].append((path, text))
        else:
            batches.append([(path, text)])
    return batches


def _parse_items(raw: str, expected: int) -> list[str] | None:
    """Split a marker-delimited reply into ``expected`` texts, or None if unusable.

    A PARTIAL reply is treated as failure, not salvage: reusing it would misalign
    translations against their source fields — the same silent corruption the
    unstrict ``zip`` in the old merge path allowed.
    """
    raw = _FENCE_CLOSE_RE.sub("", _FENCE_OPEN_RE.sub("", raw.strip())).strip()
    parts = _MARKER_RE.split(raw)
    if len(parts) < 3:
        return None
    found: dict[int, str] = {}
    for idx, text in zip(parts[1::2], parts[2::2]):
        found[int(idx)] = text.strip()
    if sorted(found) != list(range(expected)) or not all(found.values()):
        return None
    return [found[i] for i in range(expected)]


def _translate_batch(
    batch: list[tuple[tuple, str]], language: str, generate: TranslateInvoke
) -> dict[tuple, str]:
    """One item's fields in a single call; on an unusable reply, one call per field.

    A lone string needs no delimiters at all — the whole reply IS the translation —
    so the fallback path cannot be broken by markers or escaping.
    """
    texts = [text for _, text in batch]
    items = "\n\n".join(f"{_MARKER.format(i=i)}\n{s}" for i, s in enumerate(texts))
    out: dict[tuple, str] = {}
    try:
        parsed = _parse_items(
            generate(_TRANSLATE_PROMPT.format(language=language_name(language), items=items)),
            len(texts),
        )
    except Exception as exc:  # noqa: BLE001 — fall through to the per-field retry
        logger.warning("[translate] batch call failed (%s); retrying per field", exc)
        parsed = None
    if parsed is not None:
        return dict(zip([p for p, _ in batch], parsed, strict=True))

    logger.warning("[translate] unusable batch reply; retrying %d field(s) individually",
                   len(batch))
    for path, text in batch:
        try:
            single = generate(
                _SINGLE_PROMPT.format(language=language_name(language), text=text)).strip()
        except Exception as exc:  # noqa: BLE001 — one dud field must not sink the item
            logger.warning("[translate] field %s failed (%s); keeping English", path, exc)
            continue
        if single:
            out[path] = _FENCE_CLOSE_RE.sub("", _FENCE_OPEN_RE.sub("", single)).strip()
    return out


def _translate_block(payload: Any, language: str, generate: TranslateInvoke) -> Any:
    """Translate a JSON-serialisable block (dict, or list of dicts of strings).

    Returns the SAME SHAPE — every caller and `_merge_back` depend on that, and
    keeping it is why this is a wire-format change rather than a rewrite. What
    changed is underneath: the block is flattened to ordered (path, text) leaves,
    translated in marker-delimited per-item batches, and rebuilt. The model is never
    asked to produce or escape JSON.

    A field that could not be translated keeps its English text rather than raising,
    so a single stubborn string degrades one field instead of a whole section. The
    coverage floor in the publish path is what catches a block that mostly failed.
    """
    leaves = _flatten(payload)
    if not leaves:
        return copy.deepcopy(payload)
    mapping: dict[tuple, str] = {}
    for batch in _batch_by_item(leaves):
        mapping.update(_translate_batch(batch, language, generate))
    if not mapping:
        # Nothing at all came back — that is a section failure, and the caller's
        # try/except turns it into a translation_holds entry rather than silently
        # publishing the English block under a <lang>/ prefix.
        raise ValueError(f"no fields translated into {language}")
    return _rebuild(payload, mapping)


def _pluck(item: dict, fields: tuple[str, ...]) -> dict:
    """The translatable subset of an item (only present, non-empty string fields)."""
    return {f: item[f] for f in fields if isinstance(item.get(f), str) and item.get(f)}


def _translatable_pairs(paper: dict) -> list[tuple[str, str]]:
    """Every (path, text) this module would translate, in document order."""
    out: list[tuple[str, str]] = []

    def take(item: Any, fields: tuple[str, ...], path: str) -> None:
        if not isinstance(item, dict):
            return
        for f, v in _pluck(item, fields).items():
            out.append((f"{path}.{f}", v))

    ai = paper.get("ai") or {}
    take(ai.get("headliner"), _HEAD_FIELDS, "ai.headliner")
    for i, sub in enumerate(ai.get("subarticles") or []):
        take(sub, _AI_FIELDS, f"ai.subarticles[{i}]")
    for i, short in enumerate(ai.get("shorts") or []):
        take(short, _AI_FIELDS, f"ai.shorts[{i}]")
    for i, fun in enumerate(paper.get("fun") or []):
        take(fun, _FUN_FIELDS, f"fun[{i}]")
    take(paper.get("editors_brief"), _SIMPLE_FIELDS, "editors_brief")
    take(paper.get("about"), _SIMPLE_FIELDS, "about")
    return out


def translation_coverage(source: dict, translated: dict) -> dict:
    """How much of ``translated`` actually differs from the English ``source``.

    A wholly-failed translation is byte-identical to a valid English paper —
    :func:`_merge_back` leaves the English string in place when a field is missing —
    so ``validate_paper`` passes it and it publishes under a ``<lang>/`` prefix as
    English. Nothing else in the pipeline can tell the difference. This can.

    Deliberately a RATIO, not an exact-zero rule: brand names ('CraicGPT') and short
    titles can legitimately survive translation unchanged. Measured on a healthy
    live edition, ``de`` scored 2/51 fields identical and es/it/ja/fr scored 0/51.
    """
    before = dict(_translatable_pairs(source))
    after = dict(_translatable_pairs(translated))
    shared = [k for k in before if k in after]
    identical = [k for k in shared if before[k] == after[k]]
    total = len(shared)
    changed = total - len(identical)
    return {
        "total": total,
        "translated": changed,
        "identical": len(identical),
        "identical_fields": identical,
        "ratio": (changed / total) if total else 0.0,
    }


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
    # strict=: _rebuild returns the payload's exact shape, so a length mismatch is a
    # real bug, not something to absorb. The old unstrict zip silently left the tail
    # of a short reply in English with nothing logged.
    for tgt, tr in zip(subs, out.get("subarticles") or [], strict=True):
        _merge_back(tgt, tr, _AI_FIELDS)
    for tgt, tr in zip(shorts, out.get("shorts") or [], strict=True):
        _merge_back(tgt, tr, _AI_FIELDS)
    return True


def _translate_fun(fun: list, language: str, generate: Generate) -> bool:
    """Translate the fun desk in place. Returns True on success."""
    if not fun:
        return True
    payload = {"fun": [_pluck(f, _FUN_FIELDS) for f in fun]}
    out = _translate_block(payload, language, generate)
    for tgt, tr in zip(fun, out.get("fun") or [], strict=True):
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
