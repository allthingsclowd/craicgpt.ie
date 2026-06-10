"""
content_pipeline/generate/narration.py
======================================
The **narration step** — runs after the edition is written/validated and enriches it
with audio:

  1. a per-article **reading** (accessibility: every piece is listenable) — the Editor's
     own sections in Graham's voice, the desk articles ALTERNATING Graham/Tom — setting
     ``audio_url`` on each item; and
  2. the daily **dad↔son podcast** — built by :mod:`podcast_script`, its banter gated by
     :func:`rubric_review.grade_podcast_script`, rendered by :func:`audio.render_podcast`.

Per-article audio is best-effort (a TTS hiccup nulls one item's ``audio_url``, like a
failed image — it never holds the edition). The podcast is the one piece that can be HELD:
if the LLM banter fails the rubric, no podcast is attached and the reason is recorded.

All heavy collaborators are injected so the wiring is unit-testable offline.
"""

from __future__ import annotations

import logging
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
    grade: Optional[Callable] = None,
    render_podcast: Optional[Callable] = None,
) -> dict:
    """Enrich ``paper`` in place with per-article audio + a gated podcast; return it.

    Collaborators default to the real implementations but are injectable for tests:
      * ``narrate_article(item, voice=…) -> (path, model)``
      * ``build_script(paper, limit=…) -> {turns, script_text, banter_text, refs}``
      * ``grade(banter_text) -> {"verdict", "reasons", …}``
      * ``render_podcast(turns) -> (path, model)``
    """
    # Lazy imports keep this module importable (and tested) without the TTS/LLM stack.
    if narrate_article is None:
        from content_pipeline.generate.audio import narrate_article as narrate_article
    if build_script is None:
        from content_pipeline.generate.podcast_script import build_podcast_script as build_script
    if build_tldr is None:
        from content_pipeline.generate.podcast_script import build_tldr_script as build_tldr
    if grade is None:
        from content_pipeline.agent.rubric_review import grade_podcast_script as grade
    if render_podcast is None:
        from content_pipeline.generate.audio import render_podcast as render_podcast

    # The edition's language drives spoken-form fixes, localised podcast framing, and the
    # in-language banter — an explicit override, else the paper's own edition.language.
    lang = language or (paper.get("edition") or {}).get("language") or content_cfg.source_language

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
    desk_i = 0
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
        try:
            path, model = narrate_article(item, voice=v, language=lang)
            item["audio_url"] = path
            item["_audio_voice"] = v
            item["_audio_model"] = model
        except Exception as exc:  # noqa: BLE001 — a per-item TTS failure is soft
            logger.warning("[narrate] reading failed for %r: %s", item.get("title"), exc)
            item["audio_url"] = None

    # ── 2. The dad↔son podcast (banter gated before it's voiced) ──────────────
    script = build_script(paper, limit=limit, language=lang)
    banter = (script.get("banter_text") or "").strip()
    verdict = grade(banter) if banter else {"verdict": "APPROVE", "reasons": [],
                                            "result": "no_banter", "judge_model": None}

    if verdict.get("verdict") == "APPROVE":
        try:
            path, tts_model = render_podcast(script["turns"], language=lang)
            paper["podcast"] = {
                "audio_url": path,
                "transcript": script.get("script_text", ""),
                "_voices": ["graham", "tom"],
                "_text_model": content_cfg.write_model,
                "_tts_model": tts_model,
                "rubric": verdict,
            }
        except Exception as exc:  # noqa: BLE001 — render failure → no podcast, never fatal
            logger.warning("[narrate] podcast render failed: %s", exc)
            paper["podcast"] = None
    else:
        # The HOLD only ever condemns the LLM-written links — the framing and the verbatim
        # readings are deterministic and already edition-approved. So don't sink the whole
        # podcast (#64: flaky translated banter was costing es/it/ja/fr their podcast):
        # rebuild WITHOUT banter and ship that, exactly like the no_banter path. The hold
        # stays on record (edition.podcast_hold + rubric.hold_reasons) for transparency.
        logger.warning("[narrate] podcast banter HELD by rubric: %s — rendering banter-less",
                       verdict.get("reasons"))
        paper.setdefault("edition", {})["podcast_hold"] = verdict.get("reasons") or ["rubric HOLD"]
        try:
            stripped = build_script(paper, limit=limit, language=lang, include_banter=False)
            path, tts_model = render_podcast(stripped["turns"], language=lang)
            paper["podcast"] = {
                "audio_url": path,
                "transcript": stripped.get("script_text", ""),
                "_voices": ["graham", "tom"],
                "_text_model": None,            # nothing model-written survives the strip
                "_tts_model": tts_model,
                # Approved by construction (zero LLM text aboard), like no_banter — but
                # honest about what was held and why.
                "rubric": {"verdict": "APPROVE", "result": "banter_stripped",
                           "hold_reasons": verdict.get("reasons") or [],
                           "judge_model": verdict.get("judge_model")},
            }
        except Exception as exc:  # noqa: BLE001 — render failure → no podcast, never fatal
            logger.warning("[narrate] banter-less podcast render failed: %s", exc)
            paper["podcast"] = None

    # ── 2b. The <180s TL;DR headline bulletin (deterministic; same jingle) ────
    # No LLM banter → nothing to gate; it's independent of the main podcast's verdict.
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
    #       vs the probabilistic, rubric-gated podcast (the teaching split, Goal 5).
    trace = paper.setdefault("context", {}).setdefault("agent_trace", [])
    n_audio = sum(1 for it in targets if it.get("audio_url"))
    trace.append({"kind": "audio", "name": "narrate articles",
                  "detail": {"info": f"{n_audio} article(s) read by Graham & Tom (alternating) — "
                                     "deterministic TTS: chunk → synth → stitch → S3"}})
    pod_rubric = (paper.get("podcast") or {}).get("rubric") or {}
    if paper.get("podcast") and pod_rubric.get("result") == "banter_stripped":
        trace.append({"kind": "podcast", "name": "daily podcast — banter held, stripped",
                      "detail": {"info": "banter held by rubric ("
                                         + "; ".join(verdict.get("reasons") or [])
                                         + ") — shipped the deterministic framing + verbatim "
                                           "readings without it"}})
    elif paper.get("podcast"):
        trace.append({"kind": "podcast", "name": "daily podcast",
                      "detail": {"info": f"dad↔son banter passed the rubric "
                                         f"({verdict.get('judge_model')}); rendered Graham + Tom "
                                         "over verbatim readings"}})
    elif verdict.get("verdict") == "APPROVE":
        trace.append({"kind": "podcast", "name": "daily podcast — render failed",
                      "detail": {"info": "banter passed the rubric but the audio render failed"}})
    else:
        trace.append({"kind": "podcast", "name": "daily podcast — held",
                      "detail": {"info": "banter held by rubric: "
                                         + "; ".join(verdict.get("reasons") or [])}})
    if paper.get("podcast_tldr"):
        trace.append({"kind": "podcast", "name": "TL;DR headline bulletin",
                      "detail": {"info": "a <180s two-voice headline round-up — "
                                         "deterministic reads, same trad jingle"}})
    return paper
