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
    via ``fetch``), and PER-CREATOR diversity. Returns the picked, link-validated
    stories.

    Passing ``fetch`` is what makes :func:`curate_candidates` actually HEAD-check
    the links — without it (the old behaviour) dead/fabricated fun URLs were never
    caught here. The per-creator diversity key (``creator``) is what makes the desk
    read as five DIFFERENT creators rather than two uploads from the same one (the
    "only 3 distinct sources" complaint): one piece per creator before any second.
    """
    stories = [
        Story(
            title=c.get("title", ""),
            summary=c.get("summary") or c.get("body", ""),
            source_url=c.get("source_url", ""),
            continent=c.get("continent"),
            category=c.get("category"),
            creator=c.get("_creator") or c.get("source"),
        )
        for c in fun_candidates
        if isinstance(c, dict)
    ]
    stories = _cap_animal_stories(stories)  # at most one wildlife story
    return curate_candidates(
        stories, content_cfg.num_fun_stories, fetch=fetch, exclude_keys=exclude_keys,
        # One per creator (fall back to URL for any candidate with no creator name).
        diversity_key=lambda s: s.creator or s.source_url,
    )


def _write_fun(picked: list, date_iso: str, credit_by_url: dict, *, generate=None) -> list:
    """Rewrite each already-curated fun item in an assigned CELEBRITY VOICE, while
    CREDITING the creator.

    Each piece is a parody "guest columnist": a day-stable persona from the roster
    (see generate/personas.py) writes in their comic voice about the creator's
    upload. ``credit_by_url`` maps a normalised source_url to the creator's NAME —
    curation returns bare ``Story`` objects (title/summary/url only), so we re-attach
    the creator here. Both are carried onto the item: ``source`` (the real creator
    credit, alongside their validated ``source_url``) and ``persona`` (the voice; the
    harness stamps the byline + satire disclaimer in :func:`_finalize_fun`). We never
    impersonate the creator and never invent a URL.
    """
    personas = assign_personas(len(picked), seed=date_iso)
    out: list[dict] = []
    for i, story in enumerate(picked):
        creator = credit_by_url.get(_norm_url(story.source_url), "")
        persona = personas[i] if i < len(personas) else None
        story_dict = {"title": story.title, "summary": story.summary, "source_url": story.source_url}
        try:
            written = write_fun_story(story_dict, creator, persona=persona, generate=generate)
        except Exception as exc:  # noqa: BLE001 — one bad rewrite shouldn't sink the edition
            logger.warning("[run_edition] fun rewrite failed (%s); using the raw story", exc)
            written = {"title": story.title, "body": story.summary, "source_url": story.source_url}
        written["kind"] = "article"
        written["source_url"] = story.source_url  # fidelity: the validated picked URL, not the writer's guess
        written["source"] = creator               # credit: the creator's name (Graham's attribution rule)
        if persona:
            written["persona"] = persona          # voice: stamped with a byline + disclaimer in _finalize_fun
        out.append(written)
    return out


# ── Source-link fidelity (AI desk) ────────────────────────────────────────────
# The deterministic writer (an LLM) sometimes invents or mangles a story's
# source_url even when told to reuse the candidate's — and a single hallucinated
# URL then trips the publish gate's link-check and HOLDs the whole edition (the
# 2026-06-04 17:00 run: 4/18 written AI URLs were unreachable, all writer-invented
# OpenAI slugs). Candidates were already link-validated upstream, so we snap every
# written article back onto one: keep it if it already cites a validated URL, else
# map it to the best title-matched candidate — so the writer can NEVER introduce an
# unreachable/invented link.
_TITLE_STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "for", "with", "is",
               "at", "as", "by", "its", "new", "how", "why", "what", "from", "are"}


def _title_tokens(title: str) -> set:
    return {w for w in re.sub(r"[^\w\s]", " ", (title or "").lower()).split()
            if len(w) > 2 and w not in _TITLE_STOP}


def _norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def _snap_ai_sources(ai: dict, candidates: list) -> dict:
    """Force every written AI article's source_url onto a VALIDATED candidate URL.

    Faithful items (already citing a validated candidate) are kept; a hallucinated
    or mangled URL is mapped to the best title-matched candidate; an ungrounded
    sub/short (no shared title token with any candidate) is dropped. The headliner
    is never dropped — it falls back to the top candidate. Guarantees a written
    article cannot carry an unreachable link into the publish gate.
    """
    valid: dict = {}
    cand: list = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        u = (c.get("source_url") or "").strip()
        if u:
            valid[_norm_url(u)] = u
            cand.append((_title_tokens(c.get("title", "")), u))

    def resolve(item, *, headliner=False):
        if not isinstance(item, dict):
            return None
        if _norm_url(item.get("source_url", "")) in valid:
            item["source_url"] = valid[_norm_url(item["source_url"])]  # canonicalise to the candidate's
            return item
        toks = _title_tokens(item.get("title", ""))
        best_u, best = None, 0
        for ctoks, cu in cand:
            n = len(toks & ctoks)
            if n > best:
                best_u, best = cu, n
        if best >= 1:
            item["source_url"] = best_u
            return item
        if headliner:  # never DROP the headliner — but never keep the writer's URL
            # Fall back to the top validated candidate; if there are none (an edition
            # that will be HELD anyway), blank it rather than smuggle an unverified
            # URL to the gate — a clean structural "missing source_url".
            item["source_url"] = cand[0][1] if cand else ""
            return item
        return None  # ungrounded sub/short → drop

    ai["headliner"] = resolve(ai.get("headliner") or {}, headliner=True) or (ai.get("headliner") or {})
    ai["subarticles"] = [x for x in (resolve(s) for s in ai.get("subarticles", [])) if x]
    ai["shorts"] = [x for x in (resolve(s) for s in ai.get("shorts", [])) if x]
    return ai


def _finalize_fun(fun: list, date_iso: str) -> None:
    """Stamp the voice + parody guard on each fun item.

    Every fun piece is a celebrity "guest columnist" impression (see
    :func:`_write_fun`): it credits the real creator via ``source`` AND is written in
    an assigned persona's comic VOICE. So each item carries BOTH — the creator credit
    (``source`` + the kicker + source link) and the parody guard for the impression
    (``persona`` byline + ``satire_disclaimer``). The disclaimer is explicit that the
    VOICE is the parody and the credited creator is simply the source of the clip
    (see :data:`personas.SATIRE_DISCLAIMER`), so the credit and the disclaimer no
    longer contradict — and ``review.validate_paper`` accepts both together.

    Any item missing a persona OR carrying an off-roster one (a degraded/fallback
    rewrite, or the model inventing a name) is assigned a spare, unused roster
    persona day-stably here — so a published piece always has a real byline +
    disclaimer and never an off-brand impression.
    """
    used = {it.get("persona") for it in fun
            if isinstance(it, dict) and it.get("persona") in ROSTER}
    spare = [p for p in assign_personas(len(ROSTER), seed=date_iso) if p not in used]
    for item in fun:
        if not isinstance(item, dict):
            continue
        if item.get("persona") not in ROSTER and spare:
            item["persona"] = spare.pop(0)
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
        # The fun desk is an IRISH-CREATOR digest (Graham's June 2026 call): harvest
        # the curated creators' freshest YouTube uploads deterministically and make
        # THAT the primary fun pool, REPLACING the agent's good-news trawl (which
        # under-gathered and once fabricated — the 2026-06-04 HOLD). Each candidate
        # carries the creator's own video source_url and the creator's NAME as the
        # credit. ``fun_credit`` maps source_url -> creator name so the credit
        # survives curation (which keeps only title/summary/url) onto the written
        # piece. Best-effort; if the harvest is dry we fall back to any agent fun
        # candidates so the desk degrades rather than starves.
        fun_credit: dict[str, str] = {}
        try:
            fun_c = feeds.harvest_fun_candidates(
                since_hours=content_cfg.fun_feed_hours, fetch=ai_feed_fetch)
            if fun_c:
                logger.info("[run_edition] %d fun candidates from Irish-creator feeds", len(fun_c))
                trace.tool_call("harvest_fun_feeds", f"{len(fun_c)} items",
                                result="curated Irish-creator uploads")
        except Exception as exc:  # noqa: BLE001 — harvest is best-effort
            logger.warning("[run_edition] fun feed harvest failed (%s); agent candidates only", exc)
            fun_c = []
        if not fun_c:  # degrade to the agent's fun candidates rather than starve
            fun_c = _read_candidates(files, "/research/fun_candidates.json")
        for c in fun_c:
            if isinstance(c, dict) and c.get("source_url"):
                fun_credit[_norm_url(c["source_url"])] = c.get("_creator") or c.get("source") or ""
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
        # Source-link fidelity: snap every written AI URL onto a validated candidate
        # so the writer can't slip an unreachable/invented link through to the gate.
        ai = _snap_ai_sources(ai, ai_valid)
        fun = _write_fun(fun_picks, date_iso, fun_credit, generate=write_generate)

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
