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
from functools import partial
from typing import Any, Callable, Optional

from grazlab_content_research.candidate import Candidate

from content_pipeline.content_config import content_cfg
from content_pipeline.generate.personas import voice_brief

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]


def _normalise_keys(obj: Any) -> Any:
    """Strip stray whitespace from the EDGES of every JSON object key, recursively.

    THE 2026-08-24 FIX. The DGX's NVFP4 Qwen3.8 route occasionally emits whitespace
    *inside* the opening key — ``{\\n" title": …`` rather than ``{"title": …``.
    Measured 8/900 (0.89%) at production settings; the same weights served by MLX on
    the M3 were clean over 420 samples, so this is the serving stack, not the model.

    Two variants, and the nasty one is the SILENT one:

    * ``"\\ntitle"`` (raw control char) — *unparseable*, so the existing re-sample
      loop already caught it.
    * ``" title"`` (a space) — **perfectly valid JSON with the wrong key**. Nothing
      raised; ``data.get("title", "")`` just returned "". The short published blank,
      the LLM rubric judge approved it (an LLM does not notice a missing title), and
      the deterministic publish gate held the whole multilingual edition hours later.

    Normalising here fixes it at the one choke point every JSON caller shares —
    the writer *and* ``translate.py`` — and recovers the sample instead of paying
    for a re-roll. Only the edges are stripped, so a legitimate key that contains
    spaces is untouched.
    """
    if isinstance(obj, dict):
        return {(k.strip() if isinstance(k, str) else k): _normalise_keys(v)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalise_keys(v) for v in obj]
    return obj


def loads_lenient(raw: str) -> dict:
    """Parse JSON that may be wrapped in markdown fences or thinking-model tags.

    Object keys are whitespace-normalised on the way out — see :func:`_normalise_keys`
    for the incident that earned it.
    """
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
    # `strict=False` permits a RAW control character inside a string. The spec says
    # they must be escaped, but the whitespace-in-key defect has a second variant —
    # `{"\ntitle": …}` with a literal newline — which is otherwise unparseable, and
    # a stray newline inside a long prose `body` fails the same way. Both are benign
    # content, not corruption, so recover them here rather than pay for a re-sample.
    # (Same lesson as PR #94: stop making the model hand-escape prose into JSON.)
    try:
        return _normalise_keys(json.loads(text, strict=False))
    except json.JSONDecodeError:
        end = text.rfind("}") + 1
        for m in re.finditer(r"\{", text):
            if m.start() >= end:
                break
            try:
                return _normalise_keys(json.loads(text[m.start():end], strict=False))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"could not parse JSON from model output: {text[:120]!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Guided decoding: the PREVENTION half of the 2026-08-24 fix
# ─────────────────────────────────────────────────────────────────────────────
# `_normalise_keys` RECOVERS a mangled key; a response schema stops one being
# emitted at all. vLLM masks the logits so a token that would break the grammar is
# unreachable — the whitespace-in-key defect measured 8/900 without a schema and
# 0/200 with one, on the same route and settings. It also kills the adjacent
# anomalies from the same sweep (a capitalised "Title", a hallucinated
# "word_count"), which no amount of key-stripping would have caught.
#
# Schemas are PER ROLE on purpose. The headliner is the only item that carries a
# standfirst; requiring it everywhere would force every short and subarticle to
# grow a field the compiler then drops, and requiring it nowhere would let the
# headliner's standfirst blank out exactly the way the titles did.
def _article_schema(*required: str) -> dict:
    """A strict `response_format` for a one-article JSON call."""
    props = {
        "title": {"type": "string", "minLength": 1},
        "standfirst": {"type": "string"},
        "body": {"type": "string", "minLength": 1},
        "source_url": {"type": "string"},
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "article",
            "strict": True,
            "schema": {
                "type": "object",
                # `strict` + `additionalProperties: false` means every declared
                # property must appear in `required` for OpenAI-style guided
                # decoding, so the schema declares exactly what the role needs.
                "properties": {k: props[k] for k in required},
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


SCHEMA_HEADLINER = _article_schema("title", "standfirst", "body")
SCHEMA_ARTICLE = _article_schema("title", "body")          # subarticles + shorts
SCHEMA_FUN = _article_schema("title", "body", "source_url")


def _required_keys(schema: Optional[dict]) -> tuple[str, ...]:
    """The fields a response MUST carry non-empty, taken from the bound schema."""
    if not schema:
        return ()
    return tuple(schema["json_schema"]["schema"].get("required", ()))


def _is_usable(data: Any, required: tuple[str, ...]) -> bool:
    """True when every required field is present AND non-blank.

    This is the predicate the old code was missing entirely: it only ever asked
    "did this parse?", never "is this an article?". `review.validate_paper` asks
    the second question — but not until the whole edition is built.
    """
    if not isinstance(data, dict):
        return False
    return all(str(data.get(k) or "").strip() for k in required)


def _schema_bound(gen: "Generate", schema: dict) -> "Generate":
    """Bind a response schema to the DEFAULT generator only.

    An injected generator (the tests, and `podcast_script`'s wrapper) keeps its
    plain one-arg `Generate` contract — the schema is a wire-level constraint on a
    real LLM call, not part of the protocol every caller has to implement.
    """
    if gen is _default_generate:
        return partial(_default_generate, schema=schema)
    return gen


def _default_generate_text(prompt: str, *, max_tokens: int = 8000) -> str:
    """Plain chat completion returning RAW TEXT — no JSON parsing, no re-sampling.

    The translator needs this: asking a model to hand-escape prose into JSON is what
    froze the sister site's it/ja editions for 22 days (an apostrophe becomes an
    illegal ``\\'``), so translation now goes over a marker-delimited plain-text
    protocol and owns its own retry at the marker-parse level. Cross-box fallback is
    kept — a DGX blip still crosses to the M3 — but the JSON re-sample loop in
    :func:`_default_generate` would be meaningless here and is deliberately absent.
    """
    from content_pipeline.providers.litellm import get_litellm_llm, run_with_fallback

    def _try(model: str) -> str:
        llm = get_litellm_llm(
            model,
            temperature=None,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        resp = llm.invoke(prompt)
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    result = run_with_fallback(
        _try, local_model=content_cfg.write_model, fallback_model=content_cfg.fallback_text_model)
    if result.fell_back:
        logger.warning("[writer] text call fell back to %s (primary failed: %s)",
                       result.model_used, result.error)
    return str(result.output)


def _default_generate(
    prompt: str,
    *,
    attempts: int = 3,
    max_tokens: int = 8000,
    schema: Optional[dict] = None,
) -> dict:
    """Plain chat completion on the write model, parsed leniently to a dict.

    Thinking mode is disabled — Qwen3.6 otherwise emits a long ``<think>`` preamble
    that consumes the output budget before any JSON appears.

    The local model occasionally returns JSON the lenient parser can't recover (an
    unterminated string, a stray control char, a truncated tail). Rather than HOLD
    the whole edition on a single bad sample, **re-sample up to ``attempts`` times**
    — the write temperature is > 0, so each retry is a genuinely different
    completion (and we nudge it up on retries to vary even if the configured
    temperature is 0). This is the same fail-soft spirit as the rest of the desk.

    ``schema`` (optional) is a strict ``response_format`` for the role being
    written — see :func:`_article_schema`. Passing one does two things:

    * **prevents** the malformed output on the wire (guided decoding), and
    * declares which fields must come back **non-blank**, which is what makes the
      re-sample below *semantic* rather than merely syntactic.

    That second point is the 2026-08-24 lesson. This loop used to retry only on a
    ``ValueError`` — a response that parsed cleanly but carried an empty ``title``
    was indistinguishable from a good one, so it was accepted, published blank, and
    held the edition at the last gate. A blank article is a failed generation; it
    now costs a re-sample, and then the other box.
    """
    from content_pipeline.providers.litellm import get_litellm_llm, run_with_fallback

    required = _required_keys(schema)

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
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    **({"response_format": schema} if schema else {}),
                },
            )
            # A connection drop / 5xx here RAISES (not a ValueError) → it leaves this loop
            # and run_with_fallback retries on the other box, instead of sinking the run.
            resp = llm.invoke(prompt)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            try:
                data = loads_lenient(text)
            except ValueError as exc:
                last_err = exc
                logger.warning("[writer] %s JSON unparseable (attempt %d/%d, temp=%s); "
                               "re-sampling: %s", model, n + 1, attempts, temp, exc)
                continue
            # Parsed — but an article with a blank title is not an article. Treat it
            # as a failed sample so it is re-rolled here and, if the box keeps doing
            # it, handed to the other box by run_with_fallback below.
            if not _is_usable(data, required):
                blank = [k for k in required if not str(data.get(k) or "").strip()]
                last_err = ValueError(f"required field(s) blank or missing: {blank}")
                logger.warning("[writer] %s returned blank %s (attempt %d/%d, temp=%s); "
                               "re-sampling", model, blank, n + 1, attempts, temp)
                continue
            return data
        raise last_err  # type: ignore[misc]  # attempts >= 1, so last_err is set

    # Local-first → CROSS-BOX fallback (the project's run_with_fallback pattern): a DGX blip
    # or outage — or exhausted re-samples — falls back to FALLBACK_TEXT_MODEL on the M3, so a
    # transient engine drop no longer crashes a multi-minute generation. (This is what was
    # missing: the writer used to call the DGX write_model directly, ignoring the configured
    # backup.) translate.py / the editor's brief / About / podcast banter all inherit this.
    # `validate=` is what turns the M3 from decorative into a real safety net. The
    # default predicate is plain truthiness, and `{" title": "…", "body": "…"}` is
    # perfectly truthy — so on 2026-08-24 the corrupted articles were accepted and
    # the cross-box fallback never fired, on the one day it would have saved the
    # edition (the M3 measured 0/420 on the same prompts the DGX failed 8/900).
    result = run_with_fallback(
        _try,
        local_model=content_cfg.write_model,
        fallback_model=content_cfg.fallback_text_model,
        validate=(lambda out: _is_usable(out, required)) if required else None,
    )
    if result.fell_back:
        logger.warning("[writer] fell back to %s (primary failed: %s)",
                       result.model_used, result.error)
    return result.output


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (concise — keeps each output small and parseable)
# ─────────────────────────────────────────────────────────────────────────────
# House voice shared by every AI per-item prompt below.
_AI_VOICE = (
    "You are CraicGPT's AI editor. Write in Graham's house voice: Irish, witty, "
    "gently cynical, teaching-minded — never corporate-deck-speak. Draw the substance "
    "from the candidate's summary, key_points and conclusion fields; do not invent "
    "facts beyond them. Do NOT include a URL — the source link is added for you."
)

# ONE item per call (the RCA fix): the old single JSON call clipped the candidate
# pool to 12k chars and asked for the whole section at once, then truncated to N
# with no top-up — so a single response emitting fewer than N shorts under-filled
# the edition (held at 7 of 10, 2026-06-22). Each item is now its own small,
# robustly-parseable call, drawn from the FULL pool, so the count is reliable.
_AI_HEADLINER_PROMPT = (
    _AI_VOICE + "\n\nWrite TODAY'S LEAD AI story from this candidate. Output ONLY "
    'compact JSON (no markdown): {{"title","standfirst","body"}}. The standfirst is '
    "one punchy sentence; the body is <=150 words and ENDS ON THE STORY'S CONCLUSION "
    "OR TAKEAWAY — the 'so what', not a restatement of the headline.\n\n"
    "Candidate JSON:\n{candidate}"
)
_AI_SUBARTICLE_PROMPT = (
    _AI_VOICE + "\n\nWrite a SUPPORTING AI article from this candidate. Output ONLY "
    'compact JSON (no markdown): {{"title","body"}}. Body <=90 words, ending on the '
    "story's takeaway.\n\nCandidate JSON:\n{candidate}"
)
_AI_SHORT_PROMPT = (
    _AI_VOICE + "\n\nWrite a SHORT AI news item from this candidate. Output ONLY "
    'compact JSON (no markdown): {{"title","body"}}. SHORTS ARE NOT ONE-LINERS: write '
    "the body as 5-6 full sentences (110-140 words) that say what happened, give the "
    "key facts or figures, and END ON THE STORY'S CONCLUSION OR TAKEAWAY — the "
    "outcome, the 'so what'.\n\nCandidate JSON:\n{candidate}"
)

_FUN_PROMPT = (
    "Rewrite this recent item from the creator {source} as a punchy piece for the "
    "Craic Gazette's CRAIC & THROTTLE desk (comedy + Honda motorcycles), written in "
    "GRAHAM'S house voice: Irish, witty, gently "
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
    "Write a punchy piece for the Craic Gazette's CRAIC & THROTTLE desk (comedy + "
    "Honda motorcycles) about this recent item from the creator {source}, written "
    "ENTIRELY in the unmistakable comic voice of "
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


def _ai_candidate_url(candidate: dict) -> str:
    """The candidate's real, validated source link (the only one we ever publish)."""
    return (candidate.get("source_url") or "").strip()


def _write_ai_item(candidate: dict, template: str, gen: Generate, *, headliner: bool) -> Optional[dict]:
    """Write ONE AI item from one candidate; re-stamp its real source_url.

    Returns None (fail-soft) if the model errors or the candidate has no usable
    link, so one bad item draws the next from the pool instead of sinking the run.
    The source_url is ALWAYS the candidate's validated link — a model-emitted URL is
    never trusted (it could be invented). Library ``Candidate`` enforces that a
    written item always carries a real http(s) source link.
    """
    url = _ai_candidate_url(candidate)
    try:
        Candidate(title=candidate.get("title") or "x", summary="", url=url, source="")
    except ValueError:
        logger.warning("[writer] AI candidate has no usable source link — skipping")
        return None
    prompt = template.format(candidate=json.dumps(candidate)[:2500])
    try:
        data = gen(prompt)
    except Exception as exc:  # noqa: BLE001 — one bad item must not sink the section
        logger.warning("[writer] AI item write failed (%s) — skipping: %s", candidate.get("title"), exc)
        return None
    # Last line of defence, and the only one that also covers an INJECTED generator.
    # `.get(k, "")` used to turn a malformed response into a silently blank article
    # that the publish gate rejected hours later; drop it here instead and the loop
    # below simply draws the next candidate from the pool.
    if not (str(data.get("title") or "").strip() and str(data.get("body") or "").strip()):
        logger.warning("[writer] AI item came back blank (%s) — skipping",
                       candidate.get("title"))
        return None
    item = {"title": data["title"], "body": data["body"], "source_url": url}
    if headliner:
        item["standfirst"] = data.get("standfirst", "")
    return item


def write_ai_section(
    ai_candidates: list,
    *,
    num_subarticles: int,
    num_shorts: int,
    generate: Optional[Generate] = None,
) -> dict:
    """Write the AI section (1 headliner + N subs + M shorts), ONE call per item.

    Candidates are taken in their curated significance order (lead first). Each
    role is filled by walking the pool and writing items individually, skipping any
    that fail and drawing the next from the pool — so the section reliably reaches
    ``num_shorts`` whenever the pool holds enough writable candidates (the fix for
    the single-shot path that truncated to 7-of-10). The whole pool is available;
    nothing is clipped.
    """
    gen = generate or _default_generate
    pool = list(ai_candidates)
    cursor = 0

    def _next(template: str, schema: dict, *, headliner: bool = False) -> Optional[dict]:
        nonlocal cursor
        while cursor < len(pool):
            item = _write_ai_item(pool[cursor], template, _schema_bound(gen, schema),
                                  headliner=headliner)
            cursor += 1
            if item is not None:
                return item
        return None

    headliner = _next(_AI_HEADLINER_PROMPT, SCHEMA_HEADLINER, headliner=True) or {}
    subarticles: list[dict] = []
    while len(subarticles) < num_subarticles:
        item = _next(_AI_SUBARTICLE_PROMPT, SCHEMA_ARTICLE)
        if item is None:
            break
        subarticles.append(item)
    shorts: list[dict] = []
    while len(shorts) < num_shorts:
        item = _next(_AI_SHORT_PROMPT, SCHEMA_ARTICLE)
        if item is None:
            break
        shorts.append(item)

    if len(shorts) < num_shorts:
        logger.warning(
            "[writer] AI section produced %d/%d shorts from %d candidates "
            "(pool exhausted)", len(shorts), num_shorts, len(pool))
    return {"headliner": headliner, "subarticles": subarticles, "shorts": shorts}


def write_fun_story(
    candidate: dict,
    source: str,
    *,
    persona: Optional[str] = None,
    generate: Optional[Generate] = None,
) -> dict:
    """Rewrite one creator's recent item (comedy or Honda moto), crediting them.

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
    data = _schema_bound(gen, SCHEMA_FUN)(prompt)
    # A blank fun item holds the paper exactly like a blank AI short does
    # ("fun {i} missing title/body" in review.validate_paper). Raise so the caller's
    # existing fail-soft in editor_in_chief._write_fun_section falls back to the raw
    # story title/summary — a plain real piece beats a hole in the desk.
    if not (str(data.get("title") or "").strip() and str(data.get("body") or "").strip()):
        raise ValueError(f"fun rewrite came back blank for creator {source!r}")
    out = {
        "title": data["title"],
        "body": data["body"],
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
    gen = _schema_bound(generate or _default_generate, SCHEMA_ARTICLE)
    data = gen(_BRIEF_PROMPT.format(digest=_edition_digest(ai, fun)))
    return {
        "title": data.get("title") or "The Editor's Brief",
        "body": data.get("body", ""),
    }


def write_about(cv_text: str, *, generate: Optional[Generate] = None) -> dict:
    """Rewrite Graham's CV as a Father-Ted-voiced 'About the Editor' page (one JSON call)."""
    gen = _schema_bound(generate or _default_generate, SCHEMA_ARTICLE)
    data = gen(_ABOUT_PROMPT.format(cv=cv_text[:6000]))
    return {
        "title": data.get("title") or "About the Editor",
        "body": data.get("body", ""),
    }
