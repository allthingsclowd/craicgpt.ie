"""
content_pipeline/agent/editor_in_chief.py
==========================================
The Editor-in-Chief — a LangChain **deep agent** that plans the edition and
delegates to its researchers. It does RESEARCH only (reliably writing candidate
files); the harness then writes the articles deterministically (see
:mod:`content_pipeline.generate.writer`).

TUTORIAL: create_deep_agent in three lines
-------------------------------------------
A deep agent is the planning tool (``write_todos``), a virtual filesystem, and
subagent delegation (``task``) wrapped around a tool-calling model. We pass our
four subagents and the house system prompt; deepagents wires the rest. The model
is any LangChain chat model — here, a local open-source Qwen3.6 reached through
the grazlab LiteLLM proxy, with a frontier fallback supplied by the caller.

Open source only: no LangSmith, no hosted platform. The agent's plan, subagent
hand-offs, and tool calls are captured by ``trace.TraceRecorder`` for the
"Under the Hood" visualiser — that is our observability story.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from content_pipeline.agent.subagents import EDITOR_IN_CHIEF_PROMPT, SUBAGENTS
from content_pipeline.agent.trace import TraceRecorder, extract_trace
from content_pipeline.compile import build_paper
from content_pipeline.content_config import content_cfg
from content_pipeline.generate.image_styles import assign_styles, build_image_prompt
from content_pipeline.generate.personas import (
    ROSTER,
    SATIRE_DISCLAIMER,
    assign_personas,
    persona_byline,
    voice_brief,
)
from content_pipeline.generate.writer import (
    loads_lenient,
    write_about,
    write_ai_section,
    write_editors_brief,
    write_fun_story,
)
from content_pipeline.research import feeds, recency
from content_pipeline.research.curation import (
    Story,
    _default_fetch,
    curate_candidates,
    is_excluded_by_keywords,
    story_key_set,
    validate_source_link,
)
from content_pipeline.providers.litellm import get_litellm_llm

logger = logging.getLogger(__name__)

EDITION_FILE = "/draft/edition.json"


class EditionHeld(RuntimeError):
    """Raised when an edition can't be produced from REAL, fresh, link-validated
    sources and must be HELD rather than published.

    The 2026-06-04 incident: web search 429'd, the researcher fabricated stories
    and URLs, and nothing validated them — a thin, fabricated edition went live.
    The newsroom's rule now: below the per-desk integrity floor (too few reachable,
    not-recently-published sources), HOLD the whole edition and alert. ``reasons``
    is the human-readable cause list, surfaced to Graham over Telegram.
    """

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons) or ["edition held"]
        super().__init__("; ".join(self.reasons))

# The editor's CV — the version-controlled source the daily About page is rewritten
# from (in Father Ted's voice). Lives at content_pipeline/data/editor_cv.md.
_CV_PATH = Path(__file__).resolve().parent.parent / "data" / "editor_cv.md"


def _read_editor_cv() -> str:
    """Read the committed CV markdown; empty string if missing (degrade gracefully)."""
    try:
        return _CV_PATH.read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        logger.warning("[run_edition] could not read editor CV at %s (%s)", _CV_PATH, exc)
        return ""


def build_brain(model_name: Optional[str] = None) -> BaseChatModel:
    """Return the tool-calling model that drives the agent loop.

    Defaults to the configured brain route (DGX vLLM Qwen3.6 — confirmed
    tool-calling-capable). Construction does no network I/O.
    """
    return get_litellm_llm(model_name or content_cfg.brain_model)


def build_editor_in_chief(
    *,
    model: Optional[BaseChatModel] = None,
    checkpointer: Any | None = None,
):
    """Assemble the Editor-in-Chief deep agent.

    Args:
        model: The tool-calling chat model. Defaults to :func:`build_brain`.
        checkpointer: Optional LangGraph checkpointer. Pass a durable
            ``SqliteSaver`` in production so a paused (awaiting-approval) run
            survives a restart; omit for a one-shot run.

    Returns:
        A compiled LangGraph deep agent. Invoke with
        ``{"messages": [{"role": "user", "content": <brief>}]}`` and a
        ``thread_id`` config.
    """
    # Lazy import so the rest of the package (and most tests) don't need the
    # deepagents stack imported.
    from deepagents import create_deep_agent

    brain = model or build_brain()
    logger.info("[editor-in-chief] assembling deep agent on %s",
                getattr(brain, "model_name", brain))

    # NB: deepagents already includes a SummarizationMiddleware in its default
    # stack, so we don't add our own (it would trip the duplicate-middleware
    # check). We keep context bounded instead via small tool outputs (see
    # agent/tools.py) and a modest per-call max_tokens (content_config), with the
    # built-in summarizer as the backstop on long research loops.
    return create_deep_agent(
        model=brain,
        system_prompt=EDITOR_IN_CHIEF_PROMPT,
        subagents=SUBAGENTS,
        checkpointer=checkpointer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Running an edition
# ─────────────────────────────────────────────────────────────────────────────
EDITION_RESEARCH_BRIEF = (
    "Produce the RESEARCH for CraicGPT's edition for {date} (today is {date}).\n\n"
    "Plan with write_todos, then delegate via the task tool: ask the "
    "fun-news-researcher and the ai-landscape-researcher to gather candidates and "
    "WRITE them as JSON arrays to research/fun_candidates.json (items: "
    '{{"title","summary","source_url","continent"}}) and research/ai_candidates.json '
    '(items: {{"title","summary","source_url","why_it_matters","key_points","conclusion"}}, '
    "where key_points is a list of 2-4 concrete facts and conclusion is the story's "
    "outcome/takeaway read from the article body via fetch_page). Validate the links. Once BOTH "
    "research files exist, STOP — the edition is written automatically from your "
    "research. You do NOT write the articles or any draft yourself."
)


def _extract_file(files: dict, path: str) -> Optional[str]:
    """Read a virtual-FS file's content (paths are stored absolute, e.g. /draft/…)."""
    entry = files.get(path) or files.get(path.lstrip("/"))
    return entry.get("content") if entry else None


def _read_candidates(files: dict, path: str) -> list:
    """Parse a research candidate file (a JSON array) tolerantly."""
    raw = _extract_file(files, path)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):  # tolerate {"candidates": [...]} shapes
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def _search_failures(messages: list) -> list[str]:
    """Distinct ``SEARCH_FAILED: <reason>`` sentinels the web_search tool emitted
    into the agent's message stream.

    The 2026-06-04 hallucination gave NO signal that search had degraded. The tool
    now returns ``SEARCH_FAILED: <why>`` (Brave 429 / 401 / network …) instead of
    silently-empty results; surfacing those here lets a HOLD say *why* search
    failed — which is exactly what the operator asked for.
    """
    out: list[str] = []
    for m in messages or []:
        content = getattr(m, "content", None)
        if content is None and isinstance(m, dict):
            content = m.get("content")
        text = content if isinstance(content, str) else json.dumps(content, default=str)
        for match in re.finditer(r"SEARCH_FAILED:\s*([^\n\"\\]+)", text):
            reason = match.group(1).strip()
            if reason and reason not in out:
                out.append(reason)
    return out


def _validate_ai_candidates(
    candidates: list, *, fetch, exclude_keys: Optional[set] = None
) -> tuple[list, list[str]]:
    """Deterministically clean the AI candidates the way the fun desk is cleaned:
    drop grim/political stories, anything already published recently, duplicate
    URLs, and any whose ``source_url`` doesn't resolve.

    The AI desk previously got NO curation — fabricated URLs sailed straight into
    ``write_ai_section``. We filter here (preserving each candidate's rich dict
    shape — why_it_matters / key_points / conclusion — we never rewrite it) so the
    writer only ever sees real, reachable, fresh sources. Cheapest checks first
    (keyword, recency, dedupe) before the network link-check. Returns
    ``(survivors, dropped_notes)``.
    """
    exclude_keys = exclude_keys or set()
    survivors: list = []
    dropped: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if not isinstance(c, dict):
            continue
        title = c.get("title") or "(untitled)"
        url = c.get("source_url", "")
        probe = Story(title=title, summary=c.get("summary") or c.get("body", ""),
                      source_url=url)
        if is_excluded_by_keywords(probe):
            dropped.append(f"{title}: grim/political")
            continue
        if exclude_keys and (story_key_set(title, url) & exclude_keys):
            dropped.append(f"{title}: already covered in the last few days")
            continue
        key = url.strip().rstrip("/").lower()
        if not key or key in seen:
            dropped.append(f"{title}: empty/duplicate source_url")
            continue
        if not validate_source_link(url, fetch=fetch):
            dropped.append(f"{title}: source link unreachable")
            continue
        seen.add(key)
        survivors.append(c)
    return survivors, dropped


_ANIMAL_HINTS = (
    "animal", "wildlife", "nature", "species", "conservation", "penguin", "whale",
    "dolphin", "tiger", "lion", "panda", "turtle", "elephant", "bird", "shark",
    "puppy", "dog", "cat", "zoo", "sea lion",
)


def _is_animal_story(story: Story) -> bool:
    cat = (story.category or "").lower()
    text = f"{story.title} {story.summary}".lower()
    return any(h in cat for h in _ANIMAL_HINTS) or any(h in text for h in _ANIMAL_HINTS)


def _cap_animal_stories(stories: list, limit: int = 1) -> list:
    """Keep at most ``limit`` animal/wildlife stories (highest-scored), for topic
    diversity — the researcher tends to over-index on cute creatures."""
    animals = sorted((s for s in stories if _is_animal_story(s)), key=lambda s: s.score, reverse=True)
    others = [s for s in stories if not _is_animal_story(s)]
    return others + animals[:limit]


def _curate_fun(fun_candidates: list, *, fetch, exclude_keys: Optional[set] = None) -> list:
    """Build Story objects from the fun candidates and curate to N: grim/political
    filter, recency exclusion, dedupe, LINK VALIDATION (drops unreachable sources
    via ``fetch``), and continent diversity. Returns the picked, link-validated
    stories.

    Passing ``fetch`` is what makes :func:`curate_candidates` actually HEAD-check
    the links — without it (the old behaviour) dead/fabricated fun URLs were never
    caught here.
    """
    stories = [
        Story(
            title=c.get("title", ""),
            summary=c.get("summary") or c.get("body", ""),
            source_url=c.get("source_url", ""),
            continent=c.get("continent"),
            category=c.get("category"),
        )
        for c in fun_candidates
        if isinstance(c, dict)
    ]
    stories = _cap_animal_stories(stories)  # at most one wildlife story
    return curate_candidates(
        stories, content_cfg.num_fun_stories, fetch=fetch, exclude_keys=exclude_keys
    )


def _write_fun(picked: list, date_iso: str, *, generate=None) -> list:
    """Assign personas and write each already-curated fun story in its voice."""
    personas = assign_personas(len(picked), seed=date_iso)
    out: list[dict] = []
    for i, story in enumerate(picked):
        persona = personas[i] if i < len(personas) else (personas[-1] if personas else "")
        story_dict = {"title": story.title, "summary": story.summary, "source_url": story.source_url}
        try:
            written = write_fun_story(story_dict, persona, voice_brief(persona), generate=generate)
        except Exception as exc:  # noqa: BLE001 — one bad rewrite shouldn't sink the edition
            logger.warning("[run_edition] fun rewrite failed (%s); using the raw story", exc)
            written = {"title": story.title, "body": story.summary, "source_url": story.source_url}
        written["persona"] = persona
        written["kind"] = "article"
        out.append(written)
    return out


def _finalize_fun(fun: list, date_iso: str) -> None:
    """Stamp persona / byline / satire disclaimer on each fun story.

    The editor writes the prose in a persona voice but doesn't reliably populate
    the structured fields. We assign a day-stable persona where the editor left
    one blank, always set the byline, and ALWAYS set the satire disclaimer (a
    legal requirement — every persona piece must carry it).
    """
    assigned = assign_personas(len(fun), seed=date_iso) if fun else []
    for i, item in enumerate(fun):
        if not isinstance(item, dict):
            continue
        # Keep the editor's choice only if it's a real roster persona; otherwise
        # (blank, or an off-roster invention) assign one deterministically.
        if item.get("persona") not in ROSTER and i < len(assigned):
            item["persona"] = assigned[i]
        if item.get("persona"):
            item["byline"] = persona_byline(item["persona"])
        item["satire_disclaimer"] = SATIRE_DISCLAIMER


def _generate_images(
    ai: dict, fun: list, date_iso: str, *, generate=None, image_model: Optional[str] = None
) -> Optional[str]:
    """Generate images in the harness: the 3 AI leads + every fun story.

    Each image is rendered in a DIFFERENT art style — a day-stable rotation (see
    :mod:`content_pipeline.generate.image_styles`) — so one edition showcases the
    model's range while every image stays relevant to its story. Generation is done
    here (not by the agent, which invents stock URLs), overwriting any image_url the
    editor set and stamping ``image_alt``, ``_image_model`` and ``_image_style``.
    ``generate`` is injectable for tests: ``prompt -> (local_path, model)``; default
    calls :func:`generate.images.save_image`. A failed image clears image_url rather
    than crashing the edition. Returns the image model actually used.
    """
    def _default(prompt: str):
        from content_pipeline.generate.images import save_image

        return save_image(prompt)

    gen = generate or _default
    used_model = image_model

    targets: list[dict] = []
    if isinstance(ai.get("headliner"), dict):
        targets.append(ai["headliner"])
    targets += [s for s in ai.get("subarticles", []) if isinstance(s, dict)]
    targets += [f for f in fun if isinstance(f, dict)]

    styles = assign_styles(len(targets), seed=date_iso)
    for item, style in zip(targets, styles):
        try:
            path, model = gen(build_image_prompt(item, style))
            item["image_url"] = path
            item["image_alt"] = item.get("title", "")
            item["_image_model"] = model or image_model
            item["_image_style"] = style["name"]
            used_model = model or used_model
        except Exception as exc:  # noqa: BLE001 — a bad image must not sink the edition
            logger.warning("[run_edition] image generation failed: %s", exc)
            item["image_url"] = None
    return used_model


def _stamp_attribution(
    ai: dict,
    fun: list,
    *,
    text_model: Optional[str],
    image_model: Optional[str],
    extras: Optional[list] = None,
) -> None:
    """Stamp `_text_model` (and `_image_model` for illustrated fun items).

    Uses ``setdefault`` so any model-supplied attribution is preserved; otherwise
    records the configured routes that actually ran (honest "generated by" note).
    ``extras`` covers the text-only synthesis pieces (the editor's brief, the about
    page) so they carry a "generated by" note too.
    """
    text_model = text_model or content_cfg.brain_model
    image_model = image_model or content_cfg.image_model

    items = [ai.get("headliner")] + list(ai.get("subarticles", [])) + list(ai.get("shorts", []))
    for item in items:
        if isinstance(item, dict):
            item.setdefault("_text_model", text_model)
    for item in fun:
        if isinstance(item, dict):
            item.setdefault("_text_model", text_model)
            if item.get("image_url"):
                item.setdefault("_image_model", image_model)
    for item in extras or []:
        if isinstance(item, dict) and item:
            item.setdefault("_text_model", text_model)


def _write_brief(ai: dict, fun: list, generate) -> dict:
    """The whole-edition Editor's Brief, guarded so a failure never sinks the edition."""
    try:
        return write_editors_brief(ai, fun, generate=generate)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[run_edition] editor's brief failed (%s); omitting", exc)
        return {}


def _write_about(generate) -> dict:
    """The daily Father-Ted About page, guarded; empty if the CV is missing or it fails."""
    cv = _read_editor_cv()
    if not cv:
        return {}
    try:
        return write_about(cv, generate=generate)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[run_edition] about page failed (%s); omitting", exc)
        return {}


def _trace_images(trace: TraceRecorder, ai: dict, fun: list, image_model: Optional[str]) -> None:
    """Record one generate_image event per illustrated item, showing the style rotation."""
    if image_model:
        trace.model_route("image", image_model)
    items = [ai.get("headliner")] + list(ai.get("subarticles", [])) + list(fun)
    for item in items:
        if isinstance(item, dict) and item.get("image_url") and item.get("_image_style"):
            trace.tool_call("generate_image", f"style={item['_image_style']}",
                            result=item.get("image_alt", ""))


def run_edition(
    date_iso: str,
    *,
    generated_at: str,
    agent: Any | None = None,
    brief: Optional[str] = None,
    thread_id: Optional[str] = None,
    recursion_limit: int = 200,
    trace: Optional[TraceRecorder] = None,
    text_model: Optional[str] = None,
    image_model: Optional[str] = None,
    link_fetch=None,
    recent_keys=None,
    ai_feed_fetch=None,
    image_generate=None,
    write_generate=None,
) -> dict:
    """Run an edition and return a schema-v3 paper dict.

    Flow: the deep agent does **research only** (reliably writing candidate JSON
    files to its virtual filesystem). The harness then writes the articles from
    those candidates via small plain-chat→JSON calls — the AI section in one call
    and each fun story in its assigned persona's voice — because the agent's
    single giant write_file kept getting mangled by the vLLM tool-call parser.
    Finally we add images, stamp attribution, and :func:`compile.build_paper`.

    A pre-written ``draft/edition.json`` (e.g. from an injected test agent) is
    honoured directly as a shortcut.

    Args:
        agent: compiled deep agent (injected in tests); defaults to a fresh one.
        write_generate: injectable ``prompt -> dict`` for the article writer.
        image_generate: injectable ``prompt -> (path, model)`` for images.
        link_fetch: injectable ``url -> http_status`` for source-link validation
            (tests pass a stub; defaults to a real browser-UA HEAD/GET).
        recent_keys: pre-computed set of recently-published story-keys to exclude
            (tests pass a set; ``None`` fetches the last 6 live editions; pass an
            empty set to disable the recency check).
        ai_feed_fetch: injectable ``url -> feed_xml`` for the curated AI-source
            harvest (tests pass a stub; ``None`` fetches the live feeds).

    Raises:
        EditionHeld: if too few real, fresh, link-validated sources survive on a
            desk (below the integrity floor) — the edition is HELD, never published.
    """
    trace = trace or TraceRecorder()
    if agent is None:
        from langgraph.checkpoint.memory import InMemorySaver

        agent = build_editor_in_chief(checkpointer=InMemorySaver())
    brief = brief or EDITION_RESEARCH_BRIEF.format(date=date_iso)

    config = {
        "configurable": {"thread_id": thread_id or date_iso},
        "recursion_limit": recursion_limit,
    }
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": brief}]}, config=config)
    except Exception as exc:  # noqa: BLE001 — proceed with whatever files were written
        logger.warning("[run_edition] research run errored (%s); using files written so far", exc)
        result = {"messages": [], "files": {}}
    files = result.get("files", {})
    trace.model_route("research-brain", content_cfg.brain_model)

    raw = _extract_file(files, EDITION_FILE)
    if raw:
        # Shortcut: a full edition was already written (e.g. an injected test agent).
        edition = loads_lenient(raw)
        ai = dict(edition.get("ai", {}))
        fun = list(edition.get("fun", []))
    else:
        # Real path: write the edition deterministically from the research candidates,
        # but FIRST clean them — drop grim/political, recently-published, and
        # unreachable-source stories on BOTH desks — and HOLD the whole edition if too
        # few REAL, FRESH sources survive. Fabrication is thereby structurally
        # impossible: the writer only ever sees reachable sources, and a degraded
        # search HOLDs (never fills the gap with invented stories, as on 2026-06-04).
        ai_c = _read_candidates(files, "/research/ai_candidates.json")
        fun_c = _read_candidates(files, "/research/fun_candidates.json")
        # Augment the AI desk with a deterministic harvest of Graham's curated
        # source feeds (lab/company news, publications, Substacks, arXiv) — real,
        # dated items — so it never starves on the agent's yield alone (2026-06-04:
        # the agent wrote only 7 → HELD). Best-effort; merged then de-duped /
        # link-validated / recency-filtered downstream like any candidate.
        try:
            harvested = feeds.harvest_ai_candidates(
                since_hours=content_cfg.ai_feed_hours, fetch=ai_feed_fetch)
            if harvested:
                logger.info("[run_edition] +%d AI candidates from curated feeds", len(harvested))
                trace.tool_call("harvest_ai_feeds", f"{len(harvested)} items",
                                result="curated RSS/Atom sources")
            ai_c = ai_c + harvested
        except Exception as exc:  # noqa: BLE001 — harvest is best-effort
            logger.warning("[run_edition] AI feed harvest failed (%s); agent candidates only", exc)
        search_fails = _search_failures(result.get("messages", []))
        if not ai_c and not fun_c:
            reasons = ["no research candidates were gathered"]
            if search_fails:
                reasons.append("web search degraded: " + "; ".join(search_fails))
            raise EditionHeld(reasons)

        # Recency: don't reheat the last few days' stories/headlines. Best-effort —
        # a missing edition or a fetch error never blocks generation.
        n_recent = 0
        if recent_keys is None:
            try:
                editions = recency.fetch_recent_editions(date_iso, days=6)
                recent_keys = recency.recent_story_keys(editions)
                n_recent = len(editions)
                if recent_keys:
                    logger.info("[run_edition] excluding %d story-key(s) from the last "
                                "%d edition(s)", len(recent_keys), n_recent)
            except Exception as exc:  # noqa: BLE001 — recency is best-effort
                logger.warning("[run_edition] recency lookup failed (%s); not excluding", exc)
                recent_keys = set()

        fetch = link_fetch or _default_fetch
        ai_valid, ai_dropped = _validate_ai_candidates(ai_c, fetch=fetch, exclude_keys=recent_keys)
        fun_picks = _curate_fun(fun_c, fetch=fetch, exclude_keys=recent_keys)

        held: list[str] = []
        if len(ai_valid) < content_cfg.min_ai_sources:
            held.append(
                f"only {len(ai_valid)} usable AI source(s) — need "
                f">= {content_cfg.min_ai_sources} (from {len(ai_c)} candidate(s); "
                f"{len(ai_dropped)} dropped as grim / recent / dupe / unreachable)")
        if len(fun_picks) < content_cfg.min_fun_sources:
            held.append(
                f"only {len(fun_picks)} usable fun source(s) — need "
                f">= {content_cfg.min_fun_sources} (from {len(fun_c)} candidate(s))")
        if held:
            if recent_keys:
                held.append(f"(fresh-only: stories from the last {n_recent or 'few'} "
                            f"edition(s) were excluded)")
            if search_fails:
                held.append("web search degraded: " + "; ".join(search_fails))
            logger.error("[run_edition] HOLDING %s — %s", date_iso, "; ".join(held))
            raise EditionHeld(held)

        trace.vfs("read", f"/research/ai_candidates.json "
                          f"({len(ai_c)} candidates, {len(ai_valid)} usable)")
        trace.vfs("read", f"/research/fun_candidates.json "
                          f"({len(fun_c)} candidates, {len(fun_picks)} picked)")
        logger.info("[run_edition] writing from %d AI + %d fun usable candidates",
                    len(ai_valid), len(fun_picks))
        trace.model_route("write", content_cfg.write_model)
        _t0 = time.perf_counter()
        ai = write_ai_section(
            ai_valid,
            num_subarticles=content_cfg.num_ai_subarticles,
            num_shorts=content_cfg.num_ai_shorts,
            generate=write_generate,
        )
        trace.structured_output(
            "write_ai_section",
            f"1 headliner + {len(ai.get('subarticles', []))} subs + "
            f"{len(ai.get('shorts', []))} shorts in {int((time.perf_counter() - _t0) * 1000)} ms",
        )
        fun = _write_fun(fun_picks, date_iso, generate=write_generate)

    # Deterministic safety net: enforce the resolved counts (13 AI / 5 fun).
    ai["subarticles"] = (ai.get("subarticles") or [])[: content_cfg.num_ai_subarticles]
    ai["shorts"] = (ai.get("shorts") or [])[: content_cfg.num_ai_shorts]
    fun = fun[: content_cfg.num_fun_stories]

    # Deterministically finalise persona/byline/disclaimer (the editor applies the
    # voice but doesn't reliably fill these fields), generate each fun story's
    # image in the harness (the editor invents stock URLs rather than using the
    # FLUX tool output), then stamp model attribution.
    _finalize_fun(fun, date_iso)
    image_model = _generate_images(ai, fun, date_iso, generate=image_generate, image_model=image_model)
    _trace_images(trace, ai, fun, image_model)

    # Editor-in-Chief synthesis (best-effort — a failure here must not sink the
    # edition): a whole-edition brief in Graham's voice, and the daily Father-Ted
    # About page rewritten from the committed CV.
    editors_brief = _write_brief(ai, fun, write_generate)
    if editors_brief.get("body"):
        trace.structured_output("editors_brief", "whole-edition synthesis in the editor's voice")
    about = _write_about(write_generate)
    if about.get("body"):
        trace.structured_output("about", "Father-Ted bio rewritten from the CV")
    _stamp_attribution(ai, fun, text_model=text_model, image_model=image_model,
                       extras=[editors_brief, about])

    # Tell the story in order: the agent's research play-by-play first (from its
    # actual messages), then the newsroom's deterministic synthesis recorded on
    # ``trace`` (model routes, structured-output writes, image styles, brief, about).
    agent_trace = extract_trace(result.get("messages", [])) + trace.as_list()

    return build_paper(
        date_iso,
        generated_at,
        ai=ai,
        fun=fun,
        editors_brief=editors_brief,
        about=about,
        context={"agent_trace": agent_trace, "files": list(files)},
    )
