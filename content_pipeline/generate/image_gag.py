"""
content_pipeline/generate/image_gag.py
=======================================
Turn an article into a one-line VISUAL GAG for its cartoon.

Why this exists
---------------
``image_styles.build_image_prompt`` used to hand the diffusion model a style
descriptor, the headline, and 140 characters of body. That reliably produced a
LITERAL picture — "OpenAI pauses training" got a stock-photo server room. Graham's
brief is that each cartoon be "something witty and funny related to the article",
and a joke is not something a truncation can produce: somebody has to *think of it*.

TUTORIAL: which side of the fence this lands on
-----------------------------------------------
This repo does mechanical work in code and asks the model only for judgement (see
``editor_in_chief`` and ``subagents``). Inventing a joke is judgement, so it is an
LLM call. But note what is NOT asked of the model here:

* it does not choose the art style (a day-stable constant, in code)
* it does not choose the render size or step count (a tier table, in code)
* it does not know whether the story is a motorcycle story — it is TOLD, from the
  deterministic ``_vertical`` flag, because a model asked to infer that gets it
  wrong and draws a car (issue #104)

So the model contributes exactly one thing: the idea. Everything around it stays
reproducible.

Fail-soft
---------
A gag is a nice-to-have; an image is not. ``review.validate_paper`` REQUIRES an
image on the headliner and every fun story, so this module never raises — a failed
or empty gag returns ``None`` and the caller falls back to the literal prompt.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]

# One required field, so the writer's existing blank-output re-sampling applies:
# a response with an empty `gag` is re-rolled rather than accepted.
SCHEMA_GAG = {
    "type": "json_schema",
    "json_schema": {
        "name": "image_gag",
        "schema": {
            "type": "object",
            "properties": {"gag": {"type": "string"}},
            "required": ["gag"],
            "additionalProperties": False,
        },
    },
}

_GAG_PROMPT = (
    "You are the cartoonist for The Craic Gazette, an Irish satirical daily.\n\n"
    "Read this story and invent ONE visual gag for its cartoon — a single funny "
    "image that makes a joke ABOUT the story. Not an illustration of it: a joke.\n\n"
    "RULES:\n"
    "- One sentence, max 30 words, describing what is IN THE FRAME.\n"
    "- Concrete and drawable: name the characters, what they are doing, the setting. "
    "'a nervous scientist holding up a stop sign to a giant robot brain on wheels', "
    "NOT 'a metaphor for caution in AI development'.\n"
    "- The joke must come from THIS story's specific details, not generic tech imagery. "
    "No server rooms, no glowing circuit boards, no people pointing at charts.\n"
    "- Warm and silly, never cruel. Nothing grim, political, or frightening.\n"
    "- Describe NO text, words, signs or logos — the picture has to work wordlessly.\n"
    "{vertical}"
    "Output ONLY compact JSON (no markdown): {{\"gag\":\"...\"}}\n\n"
    "Story:\nTITLE: {title}\n{body}"
)

_MOTO_LINE = (
    "- THIS IS A MOTORCYCLE STORY. Any Honda in the frame is a BIKE with two wheels "
    "and a rider in a helmet — never a car.\n"
)


def build_gag(item: dict, *, generate: Optional[Generate] = None) -> Optional[str]:
    """Return a one-line visual gag for ``item``, or ``None`` if we couldn't get one.

    ``item`` is a compiled article dict (title / body, optionally ``_vertical``).
    ``generate`` is injectable for tests; the default is the writer's hardened
    chat->JSON path, so this inherits its guided decoding, re-sampling on a blank
    field, and cross-box fallback rather than reimplementing any of it.
    """
    from content_pipeline.generate.writer import _default_generate, _schema_bound

    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or item.get("summary") or "").strip()
    if not title and not body:
        return None

    gen = generate or _default_generate
    prompt = _GAG_PROMPT.format(
        title=title,
        body=body[:900],
        vertical=_MOTO_LINE if item.get("_vertical") == "moto" else "",
    )
    try:
        data = _schema_bound(gen, SCHEMA_GAG)(prompt)
    except Exception as exc:  # noqa: BLE001 — a missing gag must never sink an edition
        logger.warning("[gag] generation failed for %r: %s", title[:60], exc)
        return None

    gag = str((data or {}).get("gag") or "").strip()
    if not gag:
        logger.warning("[gag] empty gag for %r", title[:60])
        return None
    return gag
