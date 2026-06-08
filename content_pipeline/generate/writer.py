"""
content_pipeline/generate/writer.py
===================================
Deterministic article writer — the harness's editing step.

Editing used to be a deep-agent subagent that wrote the whole edition as one
giant ``write_file`` tool call. The vLLM/Qwen3.6 tool-call parser kept mangling
that huge JSON-string argument (truncation, unterminated strings). So we moved
editing here: small **plain chat → JSON** calls — one for the AI section, one
per fun story. Small outputs, no tool-call serialisation, robust lenient parse.
The agent now does only research (its reliable strength).

The LLM call is injected as ``generate(prompt) -> dict`` so this is unit-testable
offline and trivially parallelisable across fleet boxes later.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.generate.personas import voice_brief

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]


def loads_lenient(raw: str) -> dict:
    """Parse JSON that may be wrapped in markdown fences or thinking-model tags."""
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Tolerate an UNCLOSED <think> preamble (thinking truncated before </think>):
    # drop everything up to the first JSON brace if one exists.
    if "<think>" in text and "{" in text:
        text = text[text.index("{"):]
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        end = text.rfind("}") + 1
        for m in re.finditer(r"\{", text):
            if m.start() >= end:
                break
            try:
                return json.loads(text[m.start():end])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"could not parse JSON from model output: {text[:120]!r}")


def _default_generate(prompt: str, *, attempts: int = 3, max_tokens: int = 8000) -> dict:
    """Plain chat completion on the write model, parsed leniently to a dict.

    Thinking mode is disabled — Qwen3.6 otherwise emits a long ``<think>`` preamble
    that consumes the output budget before any JSON appears.

    The local model occasionally returns JSON the lenient parser can't recover (an
    unterminated string, a stray control char, a truncated tail). Rather than HOLD
    the whole edition on a single bad sample, **re-sample up to ``attempts`` times**
    — the write temperature is > 0, so each retry is a genuinely different
    completion (and we nudge it up on retries to vary even if the configured
    temperature is 0). This is the same fail-soft spirit as the rest of the desk.
    """
    from content_pipeline.providers.litellm import get_litellm_llm, run_with_fallback

    def _try(model: str) -> dict:
        """Up to ``attempts`` samples on ONE model; raise on the last bad sample (or any
        invoke error) so :func:`run_with_fallback` can cross over to the other box."""
        last_err: Optional[Exception] = None
        for n in range(attempts):
            # First try at the configured temperature; retries nudge it up so the
            # re-sample differs even if the default were 0 (deterministic).
            temp = None if n == 0 else max(content_cfg.temperature, 0.4) + 0.1 * n
            llm = get_litellm_llm(
                model,
                temperature=temp,
                # Headroom for the AI section: ten 110-140 word shorts + headliner + subs
                # as one JSON object. Too tight a cap truncates the tail shorts (the
                # lenient parser then drops them, risking review.MIN_SHORTS). 8000 slack.
                # Callers translating into token-dense scripts (e.g. CJK) pass a higher cap.
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            # A connection drop / 5xx here RAISES (not a ValueError) → it leaves this loop
            # and run_with_fallback retries on the other box, instead of sinking the run.
            resp = llm.invoke(prompt)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            try:
                return loads_lenient(text)
            except ValueError as exc:
                last_err = exc
                logger.warning("[writer] %s JSON unparseable (attempt %d/%d, temp=%s); "
                               "re-sampling: %s", model, n + 1, attempts, temp, exc)
        raise last_err  # type: ignore[misc]  # attempts >= 1, so last_err is set

    # Local-first → CROSS-BOX fallback (the project's run_with_fallback pattern): a DGX blip
    # or outage — or exhausted re-samples — falls back to FALLBACK_TEXT_MODEL on the M3, so a
    # transient engine drop no longer crashes a multi-minute generation. (This is what was
    # missing: the writer used to call the DGX write_model directly, ignoring the configured
    # backup.) translate.py / the editor's brief / About / podcast banter all inherit this.
    result = run_with_fallback(
        _try, local_model=content_cfg.write_model, fallback_model=content_cfg.fallback_text_model)
    if result.fell_back:
        logger.warning("[writer] fell back to %s (primary failed: %s)",
                       result.model_used, result.error)
    return result.output


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (concise — keeps each output small and parseable)
# ─────────────────────────────────────────────────────────────────────────────
_AI_PROMPT = (
    "You are CraicGPT's AI editor. Write in Graham's house voice: Irish, witty, "
    "gently cynical, teaching-minded — never corporate-deck-speak.\n\n"
    "From the AI-landscape candidates below, write today's AI coverage and output "
    "ONLY compact JSON (no markdown), exactly this shape:\n"
    '{{"headliner": {{"title","standfirst","body","source_url"}}, '
    '"subarticles": [{n_sub} items of {{"title","body","source_url"}}], '
    '"shorts": [{n_short} items of {{"title","body","source_url"}}]}}\n'
    "Lengths: headliner body <=150 words, subarticles <=90 words. SHORTS ARE NOT "
    "ONE-LINERS: write each short as 5-6 full sentences (110-140 words) that say what "
    "happened, give the key facts or figures, and END ON THE STORY'S CONCLUSION OR "
    "TAKEAWAY — the outcome, the 'so what' — not a restatement of the headline. Draw "
    "the substance from each candidate's key_points and conclusion fields. Rank by "
    "genuine significance. Reuse each candidate's real source_url.\n\n"
    "Candidates JSON:\n{candidates}"
)

_FUN_PROMPT = (
    "Rewrite this recent video from the Irish creator {source} as a punchy Craic "
    "Gazette fun piece, written in GRAHAM'S house voice: Irish, witty, gently "
    "cynical — 'the Scripting Paddy'. You are NOT impersonating {source}; you are "
    "Graham riffing on what they've just put out and pointing readers their way.\n"
    "Max 130 words, PG-13, warm. NAME-CHECK and CREDIT the creator ({source}) in the "
    "copy. Keep their real source_url EXACTLY as given — never invent one. Output ONLY "
    'compact JSON (no markdown): {{"title","body","source_url"}}\n\n'
    "Creator's recent item JSON:\n{story}"
)

# Persona path: a celebrity "guest columnist" riffs on the creator's upload in
# their unmistakable comic voice, while STILL crediting the real creator. The piece
# carries both the creator credit (``source``) and a satire disclaimer (the voice is
# the parody). Keeps URL fidelity — the creator's real link, never invented.
_FUN_PERSONA_PROMPT = (
    "Write a punchy Craic Gazette fun piece about this recent video from the Irish "
    "creator {source}, but written ENTIRELY in the unmistakable comic voice of "
    "{persona}.\n"
    "VOICE — {persona}: {voice_brief}\n"
    "Commit fully to {persona}'s tone, rhythm and catchphrases — this is an obvious "
    "comedic impression, a celebrity guest columnist reacting to {source}'s upload. "
    "STILL CREDIT the real creator: NAME-CHECK {source} in the copy and send readers "
    "to their video. Keep their real source_url EXACTLY as given — never invent one.\n"
    "Max 130 words, PG-13, warm — affectionate parody, nothing cruel, hateful or "
    "defamatory about any real person. Output ONLY compact JSON (no markdown): "
    '{{"title","body","source_url"}}\n\n'
    "Creator's recent item JSON:\n{story}"
)


def write_ai_section(
    ai_candidates: list,
    *,
    num_subarticles: int,
    num_shorts: int,
    generate: Optional[Generate] = None,
) -> dict:
    """Write the AI section (1 headliner + N subs + M shorts) in one JSON call."""
    gen = generate or _default_generate
    prompt = _AI_PROMPT.format(
        n_sub=num_subarticles,
        n_short=num_shorts,
        # Richer candidates (key_points + conclusion) need a bigger window than the
        # old 6000 or the tail candidates silently drop out of the prompt.
        candidates=json.dumps(ai_candidates)[:12000],
    )
    data = gen(prompt)
    return {
        "headliner": data.get("headliner") or {},
        "subarticles": (data.get("subarticles") or [])[:num_subarticles],
        "shorts": (data.get("shorts") or [])[:num_shorts],
    }


def write_fun_story(
    candidate: dict,
    source: str,
    *,
    persona: Optional[str] = None,
    generate: Optional[Generate] = None,
) -> dict:
    """Rewrite one Irish creator's recent item, crediting them.

    ATTRIBUTION (Graham's hard rule): ``source`` is the CREATOR'S NAME — it is
    name-checked in the copy and returned on the ``source`` field as the credit /
    byline. The creator's real ``source_url`` is preserved verbatim (URL fidelity:
    we fall back to the candidate's URL if the model omits it, and never invent one).

    ``persona`` (optional) is a parody-journalist from :mod:`personas` — when given,
    the piece is written in that celebrity's comic VOICE (a guest columnist riffing
    on the creator's upload) and the persona name is returned on the item so the
    harness can stamp the byline + satire disclaimer. Without a persona it's Graham's
    own house voice (the legacy/fallback path).
    """
    gen = generate or _default_generate
    if persona:
        prompt = _FUN_PERSONA_PROMPT.format(
            source=source,
            persona=persona,
            voice_brief=voice_brief(persona),
            story=json.dumps(candidate)[:1500],
        )
    else:
        prompt = _FUN_PROMPT.format(
            source=source,
            story=json.dumps(candidate)[:1500],
        )
    data = gen(prompt)
    out = {
        "title": data.get("title", ""),
        "body": data.get("body", ""),
        "source_url": data.get("source_url") or candidate.get("source_url", ""),
        "source": source,  # credit: the creator's name, carried onto the piece
    }
    if persona:
        out["persona"] = persona  # the harness stamps byline + satire disclaimer
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Editor-in-Chief synthesis: the daily brief + the About page
# ─────────────────────────────────────────────────────────────────────────────
_BRIEF_PROMPT = (
    "You are Graham — Editor-in-Chief of CraicGPT, a daily Irish AI newspaper. "
    "Write today's EDITOR'S BRIEF: one witty, cheeky, gently-cynical Irish summary "
    "of the WHOLE edition in your house voice (teaching-minded, never "
    "corporate-deck-speak). Weave the AI desk's top stories together with the fun "
    "desk's highlights into a single 'here's the state of play today' note — connect "
    "threads, tease what's inside, land a punchline. 150-220 words, one or two short "
    "paragraphs.\n"
    'Output ONLY compact JSON (no markdown): {{"title","body"}}\n\n'
    "Today's edition (digest):\n{digest}"
)

_ABOUT_PROMPT = (
    "Write CraicGPT's 'About the Editor' page for Graham Land in the UNMISTAKABLE "
    "VOICE OF FATHER TED CRILLY (from the TV series 'Father Ted'): exasperated but "
    "well-meaning, faintly scheming, forever managing some small disaster with "
    "wounded dignity. Channel the 'Now, Dougal…' asides and the famous 'the money "
    "was just resting in my account' energy — grand schemes that never quite come "
    "off. Read it as Ted proudly introducing the parish to its editor.\n\n"
    "HARD RULE: stay HONEST to the CV below. Exaggerate the REAL facts for comic "
    "effect, but INVENT NOTHING — every job, company, achievement, qualification and "
    "the home lab must be real. 250-350 words, 2-4 short paragraphs.\n"
    'Output ONLY compact JSON (no markdown): {{"title","body"}}\n\n'
    "CV:\n{cv}"
)


def _edition_digest(ai: dict, fun: list) -> str:
    """A compact, token-light digest of the written edition for the brief prompt."""
    lines: list[str] = []
    head = ai.get("headliner") or {}
    if isinstance(head, dict) and head:
        lines.append(f"HEADLINER: {head.get('title', '')} — {head.get('standfirst', '')}")
    for s in ai.get("subarticles", []) or []:
        if isinstance(s, dict):
            lines.append(f"AI: {s.get('title', '')}")
    for s in ai.get("shorts", []) or []:
        if isinstance(s, dict):
            lines.append(f"AI brief: {s.get('title', '')}")
    for f in fun or []:
        if isinstance(f, dict):
            lines.append(f"FUN ({f.get('persona', '')}): {f.get('title', '')}")
    return "\n".join(lines)[:4000]


def write_editors_brief(ai: dict, fun: list, *, generate: Optional[Generate] = None) -> dict:
    """Synthesise the whole edition into Graham's Editor's Brief (one small JSON call).

    Consumes only titles + the headliner standfirst (a digest), so the prompt stays
    small regardless of how long the articles themselves are.
    """
    gen = generate or _default_generate
    data = gen(_BRIEF_PROMPT.format(digest=_edition_digest(ai, fun)))
    return {
        "title": data.get("title") or "The Editor's Brief",
        "body": data.get("body", ""),
    }


def write_about(cv_text: str, *, generate: Optional[Generate] = None) -> dict:
    """Rewrite Graham's CV as a Father-Ted-voiced 'About the Editor' page (one JSON call)."""
    gen = generate or _default_generate
    data = gen(_ABOUT_PROMPT.format(cv=cv_text[:6000]))
    return {
        "title": data.get("title") or "About the Editor",
        "body": data.get("body", ""),
    }
