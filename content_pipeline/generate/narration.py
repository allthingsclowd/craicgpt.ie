"""
content_pipeline/generate/narration.py
======================================
The **narration step** — runs after the edition is written/validated and enriches it
with audio:

  1. a per-article **reading** (accessibility: every piece is listenable) — the Editor's
     own sections in Graham's voice, the desk articles ALTERNATING Graham/Tom — setting
     ``audio_url`` on each item; and
  2. the daily **dad↔son podcast** — built by :mod:`podcast_script` (LLM-written links
     over verbatim readings), rendered by :func:`audio.render_podcast`. The banter ships
     UNGATED (the per-banter rubric gate was removed 2026-06-10 as too strict — its false
     holds cost more banter than they caught harm); the edition itself is still
     rubric-judged upstream, and rambling links are dropped deterministically.

Per-article audio is best-effort (a TTS hiccup nulls one item's ``audio_url``, like a
failed image — it never holds the edition); a podcast render failure is equally soft.

All heavy collaborators are injected so the wiring is unit-testable offline.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)


def _article_targets(paper: dict) -> list[dict]:
    """Every item that should get its own reading, in a stable order.

    Includes the Editor-in-Chief sections — the Editor's Brief (the day's opener) and
    the About-the-Editor page — so they're listenable too, not just the desk articles.
    """
    ai = paper.get("ai") or {}
    targets: list[dict] = []
    brief = paper.get("editors_brief")
    if isinstance(brief, dict) and brief.get("body"):
        targets.append(brief)
    if isinstance(ai.get("headliner"), dict):
        targets.append(ai["headliner"])
    targets += [s for s in (ai.get("subarticles") or []) if isinstance(s, dict)]
    targets += [s for s in (ai.get("shorts") or []) if isinstance(s, dict)]
    targets += [f for f in (paper.get("fun") or []) if isinstance(f, dict)]
    about = paper.get("about")
    if isinstance(about, dict) and about.get("body"):
        targets.append(about)
    return targets


def narrate_paper(
    paper: dict,
    *,
    limit: Optional[int] = None,
    voice: str = "graham",
    language: Optional[str] = None,
    narrate_article: Optional[Callable] = None,
    build_script: Optional[Callable] = None,
    build_tldr: Optional[Callable] = None,
    render_podcast: Optional[Callable] = None,
    budget_s: Optional[float] = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Enrich ``paper`` in place with per-article audio + the podcast; return it.

    Collaborators default to the real implementations but are injectable for tests:
      * ``narrate_article(item, voice=…) -> (path, model)``
      * ``build_script(paper, limit=…) -> {turns, script_text, banter_text, refs}``
      * ``render_podcast(turns) -> (path, model)``

    ``budget_s`` is an aggregate wall-clock bound for this language: per-article TTS
    is fail-soft but unbounded in aggregate, so a slow M3 could otherwise run for
    hours (and time out the Conductor task / edition). Past the budget the remaining
    articles read without audio (``audio_url=None``) and the podcast render is
    skipped — partial audio, never a timeout. Narration is enrichment (the text is
    already published), so this never costs content quality."""
    # Lazy imports keep this module importable (and tested) without the TTS/LLM stack.
    if narrate_article is None:
        from content_pipeline.generate.audio import narrate_article as narrate_article
    if build_script is None:
        from content_pipeline.generate.podcast_script import build_podcast_script as build_script
    if build_tldr is None:
        from content_pipeline.generate.podcast_script import build_tldr_script as build_tldr
    if render_podcast is None:
        from content_pipeline.generate.audio import render_podcast as render_podcast

    # The edition's language drives spoken-form fixes, localised podcast framing, and the
    # in-language banter — an explicit override, else the paper's own edition.language.
    lang = language or (paper.get("edition") or {}).get("language") or content_cfg.source_language

    # Aggregate wall-clock bound for this language (per-item TTS is fail-soft but
    # unbounded in aggregate — see the docstring / the 2026-06-20 4.5h timeout).
    deadline = clock() + budget_s if budget_s else None

    # ── 1. Per-article readings (best-effort, like images) ────────────────────
    targets = _article_targets(paper)
    if limit is not None:
        targets = targets[:limit]
    # Cast the reads: the Editor's own sections (Brief, About) stay in Graham's voice; a
    # parody item with a DEPLOYED voice clone is read in that voice; the rest of the desk
    # ALTERNATES Graham/Tom so the paper is read as a two-hander.
    from content_pipeline.generate.audio import has_clone
    from content_pipeline.generate.personas import persona_voice_key
    editor_ids = {id(paper.get("editors_brief")), id(paper.get("about"))}
    # Voices are assigned in a SEQUENTIAL pre-pass (so the Graham/Tom alternation stays
    # deterministic), then the readings run CONCURRENTLY up to narrate_tts_concurrency at
    # once — capped by the shared TTS semaphore in audio.py — so the M3's multiple workers
    # stay SATURATED instead of idling between sequentially-narrated articles (the gap that
    # left --workers 4 underused). Each reading is independent (writes only its own item),
    # fail-soft, and checks the per-language budget at its own start.
    desk_i = 0
    assignments: list[tuple[dict, str]] = []
    for item in targets:
        persona = item.get("persona")
        vk = persona_voice_key(persona) if persona else None
        if id(item) in editor_ids:
            v = voice                                   # the editor reads his own sections
        elif vk and has_clone(vk):
            v = vk                                      # parody item in its own cloned voice
        else:
            v = "graham" if desk_i % 2 == 0 else "tom"  # desk articles alternate
            desk_i += 1
        assignments.append((item, v))

    def _read(item: dict, v: str) -> None:
        # Past the per-language budget the rest read without audio (partial, never a timeout).
        if deadline is not None and clock() >= deadline:
            item["audio_url"] = None
            return
        try:
            path, model = narrate_article(item, voice=v, language=lang)
            item["audio_url"] = path
            item["_audio_voice"] = v
            item["_audio_model"] = model
        except Exception as exc:  # noqa: BLE001 — a per-item TTS failure is soft
            logger.warning("[narrate] reading failed for %r: %s", item.get("title"), exc)
            item["audio_url"] = None

    n_par = max(1, content_cfg.narrate_tts_concurrency)
    if n_par == 1 or len(assignments) <= 1:
        for item, v in assignments:          # serial path (default): identical to before
            _read(item, v)
    else:
        with ThreadPoolExecutor(max_workers=min(n_par, len(assignments))) as ex:
            list(ex.map(lambda a: _read(*a), assignments))

    # ── 2. The dad↔son podcast (banter UNGATED — removed 2026-06-10) ──────────
    # The per-banter rubric gate was retired as too strict: the judge's false holds
    # (parody bylines, non-English banter, borderline tone calls) cost more banter than
    # they ever caught real harm — the banter prompt itself enforces the warm/PG register,
    # and the deterministic guard in podcast_script (_valid_link) still drops rambling
    # links before they are voiced. The whole EDITION is still rubric-judged upstream.
    script = build_script(paper, limit=limit, language=lang)
    # Drafts narrated in the gated era may carry edition.podcast_hold — stale now.
    (paper.get("edition") or {}).pop("podcast_hold", None)
    try:
        path, tts_model = render_podcast(script["turns"], language=lang)
        paper["podcast"] = {
            "audio_url": path,
            "transcript": script.get("script_text", ""),
            "_voices": ["graham", "tom"],
            "_text_model": content_cfg.write_model,
            "_tts_model": tts_model,
        }
    except Exception as exc:  # noqa: BLE001 — render failure → no podcast, never fatal
        logger.warning("[narrate] podcast render failed: %s", exc)
        paper["podcast"] = None

    # ── 2b. The <180s TL;DR headline bulletin (deterministic; same jingle) ────
    # Fully deterministic (titles + glosses) and independent of the main podcast.
    tldr = build_tldr(paper, limit=limit, language=lang)
    paper["podcast_tldr"] = None
    if tldr and tldr.get("turns"):
        try:
            tldr_path, tldr_tts = render_podcast(tldr["turns"], language=lang)
            paper["podcast_tldr"] = {
                "audio_url": tldr_path,
                "transcript": tldr.get("script_text", ""),
                "_voices": ["graham", "tom"],
                "_kind": "tldr",
                "_text_model": None,           # deterministic: titles + glosses, no LLM
                "_tts_model": tldr_tts,
            }
        except Exception as exc:  # noqa: BLE001 — TL;DR render failure is soft, like images
            logger.warning("[narrate] TL;DR render failed: %s", exc)
            paper["podcast_tldr"] = None

    # ── 3. Trace the audio build for "Under the Hood" — the deterministic readings
    #       vs the LLM-written banter (the teaching split, Goal 5).
    trace = paper.setdefault("context", {}).setdefault("agent_trace", [])
    n_audio = sum(1 for it in targets if it.get("audio_url"))
    trace.append({"kind": "audio", "name": "narrate articles",
                  "detail": {"info": f"{n_audio} article(s) read by Graham & Tom (alternating) — "
                                     "deterministic TTS: chunk → synth → stitch → S3"}})
    if paper.get("podcast"):
        trace.append({"kind": "podcast", "name": "daily podcast",
                      "detail": {"info": "rendered Graham + Tom — LLM-written links over "
                                         "verbatim readings (ungated; the edition itself is "
                                         "rubric-judged upstream)"}})
    else:
        trace.append({"kind": "podcast", "name": "daily podcast — render failed",
                      "detail": {"info": "the audio render failed; the edition ships without "
                                         "the main podcast"}})
    if paper.get("podcast_tldr"):
        trace.append({"kind": "podcast", "name": "TL;DR headline bulletin",
                      "detail": {"info": "a <180s two-voice headline round-up — "
                                         "deterministic reads, same trad jingle"}})
    return paper
