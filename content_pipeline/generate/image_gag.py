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
import re
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]

# `gag` is required, so the writer's blank-output re-sampling re-rolls an empty one.
#
# `caption` is declared but deliberately NOT required. `writer._required_keys` derives the
# blank-check set from `required`, so a blank caption there would re-roll three times AND
# burn a cross-box fallback to the M3 — per image, eighteen times an edition. Mandatoriness
# is enforced in build_gag instead, with one escalated retry.
#
# Declaring a non-required property is legal here only because this schema has no
# `"strict": True` (unlike writer._article_schema, where strict + additionalProperties:false
# forces every declared property into `required`). additionalProperties:false still means the
# field must be declared to be emittable at all.
SCHEMA_GAG = {
    "type": "json_schema",
    "json_schema": {
        "name": "image_gag",
        "schema": {
            "type": "object",
            "properties": {"gag": {"type": "string"}, "caption": {"type": "string"}},
            "required": ["gag"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class Gag:
    """A visual joke plus the words to letter into it.

    ``caption`` is the EXACT string the image model is told to draw. Supplying it is the
    whole point: the previous prompt told the model to letter "the exact words in quotes"
    and never gave it any, so it invented letterforms — which is how the 2026-08-26 hero
    ended up reading "STEMIVALIINGS MONIS AII APOR!". A diffusion model asked to invent
    text produces mush; asked to copy a given string, it renders it.
    """

    gag: str
    caption: str = ""

    def __bool__(self) -> bool:          # keeps `if gag:` reading naturally at the call site
        return bool(self.gag)

# NOTE ON NEGATION: the "do not" rules below are FINE here. This is a text-to-text LLM call
# (Qwen3.8), which handles negation normally. Do NOT copy this style into the FLUX image
# prompt in image_styles.py — the Mistral encoder there reads negation as things to DRAW, and
# every fragment on that side must be phrased positively. Two different models, two different
# rules; conflating them is what produced a nine-NO text ban that summoned a "STOP" sign.
_GAG_PROMPT = (
    "You are the cartoonist for a daily satirical newspaper about AI and comedy.\n\n"
    "Read this story and invent ONE visual gag for its cartoon — a single funny image that "
    "makes a joke ABOUT the story. Not an illustration of it: a joke. Then write the words "
    "that appear IN that picture.\n\n"
    "THE GAG:\n"
    "- One sentence, max 30 words, describing what is IN THE FRAME.\n"
    "- Concrete and drawable: name the characters, what they are doing, the setting. "
    "'a nervous scientist holding up a stop sign to a giant robot brain on wheels', "
    "NOT 'a metaphor for caution in AI development'.\n"
    "- The joke must come from THIS story's specific details, not generic tech imagery. "
    "No server rooms, no glowing circuit boards, no people pointing at charts.\n"
    "- Do NOT reach for national stereotypes. No leprechauns, shamrocks, pots of gold, "
    "green top hats or rainbows. The paper is Irish; the joke does not have to be, and a "
    "story about a chip foundry or a funding round has nothing to do with Ireland.\n"
    "- Warm and silly, never cruel. Nothing grim, political, or frightening.\n"
    "{vertical}\n"
    "THE CAPTION — the words drawn inside the picture:\n"
    "- MAX {max_words} WORDS. Shorter is better; every word has to be hand-lettered.\n"
    "- It must be something IN the scene: what a character SAYS, or what a sign, banner or "
    "screen in the frame READS.\n"
    "- It has to land the joke with the picture. A caption that would fit any story is a "
    "wasted caption — use this story's specifics.\n"
    "- Do not repeat the headline back. The headline is printed above the picture already.\n"
    "- Plain characters only: A-Z, digits, and . , ! ? ' - Do not add quote marks yourself.\n\n"
    "Output ONLY compact JSON (no markdown): {{\"gag\":\"...\",\"caption\":\"...\"}}\n\n"
    "Story:\nTITLE: {title}\n{body}"
)

_CAPTION_RETRY = (
    "\n\nYour previous caption was rejected: {problems}. "
    "Rewrite ONLY the caption, obeying the rules above. Keep the same gag."
)

# Characters a caption may contain. Anything else is a sign the model wandered off into
# glyphs the renderer will smear — "ANNAKED" and friends. ASCII letters, digits, spaces and
# the punctuation that actually appears in comic lettering.
# Colons and semicolons were missing from the first version and cost a needless retry on the
# live 2026-08-26 run ("unrenderable characters: [':', '>']") — a colon is perfectly ordinary
# comic lettering. Keep the list to punctuation a sign painter would actually letter; the
# point is to catch the stray Cyrillic or CJK glyph that the renderer smears, not to police
# style.
_CAPTION_OK = re.compile(r"^[A-Za-z0-9 .,:;!?'\-&%$£€]+$")


def caption_problems(caption: str, max_words: int) -> list[str]:
    """What is wrong with ``caption``, as a list of reasons — empty list means it is fine.

    Returns the EVIDENCE rather than a bool so the retry can quote the problem back to the
    model and the tests can name it, the same shape as ``writer.car_words_in``.
    """
    text = " ".join(str(caption or "").split())
    problems: list[str] = []
    if not text:
        problems.append("empty")
        return problems
    words = text.split()
    if len(words) > max_words:
        problems.append(f"{len(words)} words, limit is {max_words}")
    if '"' in text or "\u201c" in text or "\u201d" in text:
        problems.append("contains quote marks (the prompt adds those)")
    if not _CAPTION_OK.match(text):
        bad = sorted({c for c in text if not _CAPTION_OK.match(c)})
        problems.append(f"unrenderable characters: {bad}")
    return problems


_MOTO_LINE = (
    "- THIS IS A MOTORCYCLE STORY. Any Honda in the frame is a BIKE with two wheels "
    "and a rider in a helmet — never a car.\n"
)


def build_gag(item: dict, *, max_caption_words: int = 8,
              generate: Optional[Generate] = None) -> Optional[Gag]:
    """Return a :class:`Gag` (joke + the words to letter) for ``item``, or ``None``.

    ``item`` is a compiled article dict (title / body, optionally ``_vertical``).
    ``max_caption_words`` is the tier's budget — a 768px thumbnail cannot carry what a
    1024px hero can, so the caller passes ``RenderSpec.caption_words`` rather than this
    module guessing.

    ``generate`` is injectable for tests; the default is the writer's hardened chat->JSON
    path, so this inherits its guided decoding, re-sampling on a blank field, and cross-box
    fallback rather than reimplementing any of it.

    A bad caption costs ONE escalated retry with the problem quoted back. If it is still
    unusable we return the gag with an empty caption and the caller renders the picture
    wordless — shipping nonsense lettering is worse than shipping none, and every other
    step in this pipeline degrades rather than raises.
    """
    from content_pipeline.generate.writer import _default_generate, _schema_bound

    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or item.get("summary") or "").strip()
    if not title and not body:
        return None

    gen = generate or _default_generate
    bound = _schema_bound(gen, SCHEMA_GAG)
    base = _GAG_PROMPT.format(
        title=title,
        body=body[:900],
        max_words=max_caption_words,
        vertical=_MOTO_LINE if item.get("_vertical") == "moto" else "",
    )

    def _ask(prompt: str) -> Optional[dict]:
        try:
            return bound(prompt)
        except Exception as exc:  # noqa: BLE001 — a missing gag must never sink an edition
            logger.warning("[gag] generation failed for %r: %s", title[:60], exc)
            return None

    data = _ask(base)
    if data is None:
        return None

    gag = str((data or {}).get("gag") or "").strip()
    if not gag:
        logger.warning("[gag] empty gag for %r", title[:60])
        return None

    caption = " ".join(str((data or {}).get("caption") or "").split())
    problems = caption_problems(caption, max_caption_words)
    if problems:
        logger.warning("[gag] caption rejected for %r (%s); retrying once",
                       title[:60], "; ".join(problems))
        retry = _ask(base + _CAPTION_RETRY.format(problems="; ".join(problems)))
        if retry:
            candidate = " ".join(str(retry.get("caption") or "").split())
            if not caption_problems(candidate, max_caption_words):
                caption = candidate
                problems = []
        if problems:
            logger.warning("[gag] caption still unusable for %r — wordless fallback", title[:60])
            caption = ""

    return Gag(gag=gag, caption=caption)
