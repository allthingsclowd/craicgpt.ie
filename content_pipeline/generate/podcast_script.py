"""
content_pipeline/generate/podcast_script.py
===========================================
Build the script for the daily **dad↔son podcast**: Graham and Tom take turns reading the
articles aloud, with short linking banter, so it plays as a flowing two-handed discussion
— topped and tailed by the 80s call-sign jingle + signature.

TUTORIAL: deterministic frame, probabilistic filling — ONE clip per article
---------------------------------------------------------------------------
The audio is built from FEW, LONG clips, not many short ones: every short back-and-forth
turn used to be a separate TTS synthesis, and the SEAMS between clips are where the clone
degrades. So each article is now ONE clip — the reader's opening link + the *verbatim*
reading + their closing hand-off, all in one voice — and a parody guest reads in their own
voice between a fixed welcome and sign-off.

Two of the three layers are DETERMINISTIC and never touch an LLM:
  1. the signature intro/outro + the fixed guest welcome/ack/sign-off, and
  2. the article READINGS — the exact text the edition rubric already approved (no
     paraphrase → no new claims, no attribution drift).
Only the host LINKS (the one-line pre/post around each host read) are PROBABILISTIC — a
single ``write_model`` call drafts them all at once (Tom's character stays consistent).
They are the ONLY generated content, so they are the only thing the deepagents rubric has
to gate before a word is voiced (see ``rubric_review.grade_podcast_script``). Same split
as the rest of the paper: code does the mechanics, the rubric judges the judgement.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

Generate = Callable[[str], dict]
Turn = tuple[str, str]  # (voice, text)

# The two hosts TAKE TURNS reading the articles — Graham (dad) opens, then they
# alternate so the show plays as a two-handed discussion, not a monologue.
_PODCAST_READERS: tuple[str, str] = ("graham", "tom")


def _reader_for(index: int) -> str:
    return _PODCAST_READERS[index % len(_PODCAST_READERS)]

# ── Fixed signature (the audio branding; same every day) — LOCALISED ──────────
# NB: "Craic" is left spelled correctly here (this is also the on-screen transcript);
# the TTS layer pronounces it "crack" (English only) — see audio._phonetic. English is
# canonical + the guaranteed fallback; the other languages are FROZEN translations,
# review-pending (decision: reuse the voice clones cross-lingually, review post-deploy).
_MONTHS: dict[str, list[str]] = {
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"],
}
_DATE_FORMAT = {"de": "{day}. {month} {year}", "es": "{day} de {month} de {year}",
                "it": "{day} {month} {year}", "fr": "{day} {month} {year}"}
_DATE_FALLBACK = {"en": "today", "de": "heute", "es": "hoy", "it": "oggi",
                  "fr": "aujourd'hui", "ja": "本日"}


def _date_phrase(date_iso: str, language: str = "en") -> str:
    """Human-spoken date from the edition's OWN date (no clock — stays deterministic).

    English: ``2026-05-12`` → ``Tuesday the 12th of May, 2026``. Other languages use a
    localised numeric form (``12. Mai 2026`` / ``12 de mayo de 2026`` / ``2026年5月12日``).
    """
    from datetime import datetime
    try:
        d = datetime.strptime((date_iso or "").strip(), "%Y-%m-%d")
    except ValueError:
        return _DATE_FALLBACK.get(language, "today")
    if language == "ja":
        return f"{d.year}年{d.month}月{d.day}日"
    if language in _MONTHS:
        return _DATE_FORMAT[language].format(day=d.day, month=_MONTHS[language][d.month - 1],
                                             year=d.year)
    suffix = "th" if 11 <= d.day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return d.strftime(f"%A the {d.day}{suffix} of %B, %Y")


# All the deterministic fixed framing, per language. ``{date}``/``{persona}``/``{model}``
# are filled at build time. Guest reads in their OWN cloned voice between ack and sign-off.
_L10N: dict[str, dict[str, Any]] = {
    "en": {
        "intro": [("graham", "Good morning, and welcome to CraicGPT — the AI news with a bit of "
                             "craic. I'm Graham, the Scripting Paddy, and today is {date}."),
                  ("tom", "And I'm Tom — the voice of reason, allegedly. Right, let's get into it.")],
        "outro": [("graham", "And sure look, that's enough craic for one day. Come back to us "
                            "tomorrow at craicgpt.ie for another podcast."),
                  ("tom", "See yiz!"), ("graham", "God bless.")],
        "guest_welcome": "And now we have a guest presenter, {persona}, to lighten the mood. "
                         "Hi {persona}, welcome to CraicGPT — we're delighted to have you with us today.",
        "guest_ack": "Tom, Graham — thanks for having me.",
        "guest_signoff": "And that's me — back to you, lads.",
        "tldr_intro": [("graham", "Good morning! Here's your quick CraicGPT headline round-up "
                                 "for {date}."),
                       ("tom", "Right, let's rattle through them!")],
        "tldr_outro": [("graham", "And that's your headlines. The full show and every story are "
                                "at craicgpt.ie — back tomorrow."), ("tom", "See yiz!")],
        "preamble": "",   # English is the source — no translation note
    },
    "de": {
        "intro": [("graham", "Guten Morgen und willkommen bei CraicGPT — KI-News mit einem "
                             "Augenzwinkern. Ich bin Graham, der Scripting Paddy, und heute ist {date}."),
                  ("tom", "Und ich bin Tom — angeblich die Stimme der Vernunft. Also, legen wir los.")],
        "outro": [("graham", "Und damit soll's für heute genug sein. Schaut morgen wieder bei "
                            "craicgpt.ie für einen neuen Podcast vorbei."),
                  ("tom", "Macht's gut!"), ("graham", "Bis bald.")],
        "guest_welcome": "Und jetzt haben wir einen Gast, {persona}, zur Auflockerung. Hallo "
                         "{persona}, willkommen bei CraicGPT — schön, dass du da bist.",
        "guest_ack": "Tom, Graham — danke für die Einladung.",
        "guest_signoff": "Und das war's von mir — zurück zu euch.",
        "tldr_intro": [("graham", "Guten Morgen! Hier ist eure schnelle CraicGPT-Schlagzeilenrunde "
                                 "für {date}."), ("tom", "Also, dann mal flott durch!")],
        "tldr_outro": [("graham", "Und das waren die Schlagzeilen. Die ganze Show und alle Storys "
                                "gibt's auf craicgpt.ie — morgen geht's weiter."), ("tom", "Macht's gut!")],
        "preamble": "Kurz vorweg: Diese Folge wurde von {model} aus dem Englischen übersetzt — "
                    "für etwaige Patzer bitte den Roboter tadeln, nicht uns.",
    },
    "es": {
        "intro": [("graham", "Buenos días y bienvenidos a CraicGPT — las noticias de IA con un "
                             "poco de chispa. Soy Graham, el Scripting Paddy, y hoy es {date}."),
                  ("tom", "Y yo soy Tom — la voz de la razón, supuestamente. Venga, vamos al lío.")],
        "outro": [("graham", "Y con esto lo dejamos por hoy. Volved mañana a craicgpt.ie para "
                            "otro podcast."), ("tom", "¡Hasta pronto!"), ("graham", "Cuidaos.")],
        "guest_welcome": "Y ahora tenemos a un invitado, {persona}, para animar la cosa. Hola "
                         "{persona}, bienvenido a CraicGPT — encantados de tenerte hoy.",
        "guest_ack": "Tom, Graham — gracias por invitarme.",
        "guest_signoff": "Y eso es todo por mi parte — os devuelvo la palabra.",
        "tldr_intro": [("graham", "¡Buenos días! Aquí va vuestro resumen rápido de titulares de "
                                 "CraicGPT para {date}."), ("tom", "Venga, ¡vamos al grano!")],
        "tldr_outro": [("graham", "Y esos son los titulares. El programa completo y todas las "
                                "historias están en craicgpt.ie — mañana más."), ("tom", "¡Hasta pronto!")],
        "preamble": "Un aviso rápido: este episodio lo tradujo del inglés {model} — si algo suena "
                    "raro, la culpa es del robot, no nuestra.",
    },
    "it": {
        "intro": [("graham", "Buongiorno e benvenuti a CraicGPT — le notizie sull'IA con un po' "
                             "di brio. Sono Graham, lo Scripting Paddy, e oggi è {date}."),
                  ("tom", "E io sono Tom — la voce della ragione, a quanto pare. Dai, cominciamo.")],
        "outro": [("graham", "E direi che per oggi può bastare. Tornate domani su craicgpt.ie "
                            "per un altro podcast."), ("tom", "Alla prossima!"), ("graham", "State bene.")],
        "guest_welcome": "E ora abbiamo un ospite, {persona}, per alleggerire l'atmosfera. Ciao "
                         "{persona}, benvenuto a CraicGPT — felici di averti con noi oggi.",
        "guest_ack": "Tom, Graham — grazie per avermi invitato.",
        "guest_signoff": "E con questo ho finito — torno a voi.",
        "tldr_intro": [("graham", "Buongiorno! Ecco il vostro riepilogo veloce dei titoli di "
                                 "CraicGPT per {date}."), ("tom", "Forza, sbrighiamoci!")],
        "tldr_outro": [("graham", "E questi erano i titoli. Lo show completo e tutte le storie "
                                "sono su craicgpt.ie — a domani."), ("tom", "Alla prossima!")],
        "preamble": "Una nota al volo: questo episodio è stato tradotto dall'inglese da {model} — "
                    "per ogni imprecisione, prendetevela col robot, non con noi.",
    },
    "fr": {
        "intro": [("graham", "Bonjour et bienvenue sur CraicGPT — l'actu de l'IA avec un brin "
                             "d'humour. Je suis Graham, le Scripting Paddy, et nous sommes le {date}."),
                  ("tom", "Et moi c'est Tom — la voix de la raison, paraît-il. Allez, c'est parti.")],
        "outro": [("graham", "Et voilà, ce sera tout pour aujourd'hui. Revenez demain sur "
                            "craicgpt.ie pour un nouveau podcast."), ("tom", "À bientôt !"),
                  ("graham", "Portez-vous bien.")],
        "guest_welcome": "Et maintenant nous avons un invité, {persona}, pour détendre "
                         "l'atmosphère. Bonjour {persona}, bienvenue sur CraicGPT — ravis de "
                         "t'avoir avec nous aujourd'hui.",
        "guest_ack": "Tom, Graham — merci de m'avoir invité.",
        "guest_signoff": "Et voilà pour moi — je vous rends l'antenne.",
        "tldr_intro": [("graham", "Bonjour ! Voici votre tour d'horizon express des titres "
                                 "CraicGPT pour le {date}."), ("tom", "Allez, on enchaîne !")],
        "tldr_outro": [("graham", "Et voilà les titres. L'émission complète et tous les articles "
                                "sont sur craicgpt.ie — à demain."), ("tom", "À bientôt !")],
        "preamble": "Petite précision : cet épisode a été traduit de l'anglais par {model} — en "
                    "cas d'imperfection, blâmez le robot, pas nous.",
    },
    "ja": {
        "intro": [("graham", "おはようございます。AIニュースをちょっと楽しくお届けするCraicGPTへ"
                             "ようこそ。スクリプティング・パディーことグラハムです。今日は{date}です。"),
                  ("tom", "そして僕がトム、いちおう常識担当です。さあ、始めましょう。")],
        "outro": [("graham", "さて、今日はこのへんで。また明日、craicgpt.ie でお会いしましょう。"),
                  ("tom", "またね！"), ("graham", "それでは。")],
        "guest_welcome": "さて、ここでゲストの{persona}さんをお迎えします。{persona}さん、"
                         "CraicGPTへようこそ。来てくれて嬉しいです。",
        "guest_ack": "トム、グラハム、呼んでくれてありがとう。",
        "guest_signoff": "では、二人にお返しします。",
        "tldr_intro": [("graham", "おはようございます。{date}のCraicGPTヘッドライン速報です。"),
                       ("tom", "では、さくっといきましょう！")],
        "tldr_outro": [("graham", "以上、ヘッドラインでした。フル版と全記事は craicgpt.ie で。"
                                "また明日。"), ("tom", "またね！")],
        "preamble": "お知らせです。このエピソードは{model}が英語から翻訳しました。おかしな点が"
                    "あればロボットのせいということで、どうかご容赦を。",
    },
}


def _l10n(language: str) -> dict[str, Any]:
    """The fixed-framing bundle for a language, falling back to English."""
    return _L10N.get(language, _L10N["en"])


def build_signature_intro(date_iso: str, language: str = "en") -> list[Turn]:
    """A clean two-host cold-open, with the edition's live date folded in (localised)."""
    date = _date_phrase(date_iso, language)
    return [(who, text.format(date=date)) for who, text in _l10n(language)["intro"]]


def signature_outro(language: str = "en") -> list[Turn]:
    """The localised sign-off turns."""
    return list(_l10n(language)["outro"])


SIGNATURE_OUTRO: list[Turn] = _L10N["en"]["outro"]   # back-compat: the English sign-off


def guest_welcome(language: str = "en") -> str:
    return _l10n(language)["guest_welcome"]


def guest_ack(language: str = "en") -> str:
    return _l10n(language)["guest_ack"]


def guest_signoff(language: str = "en") -> str:
    return _l10n(language)["guest_signoff"]


# Back-compat: the English fixed guest framing under its original names.
GUEST_WELCOME = _L10N["en"]["guest_welcome"]
GUEST_ACK = _L10N["en"]["guest_ack"]
GUEST_SIGNOFF = _L10N["en"]["guest_signoff"]


def translation_preamble(paper: dict, language: str) -> str:
    """The spoken 'this was machine-translated from English' note, in ``language``.

    Empty for the source language or when no translation model is recorded — so it only
    ever rides on a genuinely translated edition. Names the real model (honest attribution).
    """
    if language == content_cfg.source_language:
        return ""
    model = ((paper.get("edition") or {}).get("translated_by") or "").strip()
    if not model:
        return ""
    return (_l10n(language).get("preamble") or "").format(model=model)

# The banter prompt. CHANGED to the "one clip per article" model: every short back-and-
# forth turn used to be its own TTS clip, and the SEAMS between clips are where the clone's
# quality fell apart. So each reader's whole segment is now recorded as ONE piece — their
# opening link + the verbatim reading + their closing hand-off — and the LLM writes only
# those two short links per host-read article (the readings + the guest framing are not its
# job). Far fewer seams; the links are still the only thing the rubric gate has to judge.
_BANTER_PROMPT = (
    "You are scripting a warm, witty Irish podcast — one FLOWING conversation between "
    "GRAHAM (the dad: patient, funny, gently cynical, teaching-minded, 'the Scripting "
    "Paddy') and his cheeky, curious 14-year-old son TOM. Tom is quick and funny but "
    "talks like a NORMAL bright teenager: keep his slang MINIMAL and timeless (an "
    "occasional 'gas', 'deadly', 'no way') — never trendy meme-speak, it dates badly. "
    "Clean and PG throughout; cheeky, never cruel; nothing grim.\n"
    "The hosts TAKE TURNS reading the articles aloud (each line below says who reads it). "
    "To keep the audio smooth we record each reader's whole segment as ONE piece, so for "
    "EACH article READ BY A HOST you write just two short links:\n"
    "  • \"pre\": how that reader OPENS — ONE warm sentence reacting to the bit just before "
    "(the previous reader's story, or the guest who just spoke), then easing into THIS "
    "article. Do NOT hand over to anyone in the pre (handing over is the PREVIOUS reader's "
    "job) — just react and lead in. Leave it EMPTY (\"\") for the FIRST article — it follows "
    "the intro.\n"
    "  • \"post\": how that reader CLOSES — ONE sentence: a quick take on THIS article, then "
    "hand over to the NEXT speaker BY NAME (e.g. 'over to you, Tom'). For the LAST article, "
    "wind down toward the sign-off instead of handing over.\n"
    "GUEST articles are read by a parody guest in their OWN voice and are topped by a FIXED "
    "welcome — that is NOT yours to write, so DO NOT emit an item for a guest. But the host "
    "article RIGHT AFTER a guest should have its \"pre\" react to that guest.\n"
    "Never summarise or read an article — the reader reads the body itself. ONE sentence "
    "per field, plain and natural, so it flows straight into (and out of) the reading.\n"
    "Output ONLY compact JSON (no markdown), exactly:\n"
    '{{"items":[{{"ref":"<the ref>","pre":"...","post":"..."}}]}}\n'
    "Include an item ONLY for host-read articles.\n\n"
    "Articles in reading order:\n{digest}"
)


def _banter_prompt(language: str = "en") -> str:
    """The banter prompt; for a non-English edition, append a directive to write the host
    links in that language (the readings are already translated). Gated per language."""
    if language == content_cfg.source_language:
        return _BANTER_PROMPT
    from content_pipeline.generate.translate import language_name
    name = language_name(language)
    directive = (f"\n\nIMPORTANT: write GRAHAM's and TOM's links (the \"pre\"/\"post\" fields) "
                 f"entirely in {name}. The article readings are already in {name}; keep the same "
                 f"warm, witty register.")
    return _BANTER_PROMPT.replace("\n\nArticles in reading order:\n{digest}",
                                  directive + "\n\nArticles in reading order:\n{digest}")


def _resolve_ref(paper: dict, ref: str) -> Optional[dict]:
    """Resolve a layout ref like ``ai.headliner`` / ``ai.shorts.0`` / ``fun.0`` to an item."""
    node: Any = paper
    for part in ref.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node if isinstance(node, dict) else None


def _ordered_refs(paper: dict) -> list[str]:
    """Article refs in reading order: the layout if present, else a sensible default."""
    layout = [r for r in (paper.get("layout") or []) if isinstance(r, str)]
    if layout:
        return layout
    refs = ["ai.headliner"]
    refs += [f"ai.subarticles.{i}" for i in range(len(paper.get("ai", {}).get("subarticles") or []))]
    refs += [f"ai.shorts.{i}" for i in range(len(paper.get("ai", {}).get("shorts") or []))]
    refs += [f"fun.{i}" for i in range(len(paper.get("fun") or []))]
    return refs


def _reading(item: dict) -> str:
    """The verbatim text read for an article: headline, standfirst, then body (plain)."""
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _guest_voice(item: dict) -> Optional[str]:
    """The parody guest's voice key IFF their clone is deployed — so they read their own
    article in their own cloned voice. ``None`` for non-parody / undeployed."""
    persona = item.get("persona")
    if not persona:
        return None
    from content_pipeline.generate.audio import has_clone
    from content_pipeline.generate.personas import persona_voice_key
    vk = persona_voice_key(persona)
    return vk if has_clone(vk) else None


def _digest(plan: list[dict]) -> str:
    """A compact, token-light digest of the articles in reading order — each one's position,
    who voices it (a host, or a parody GUEST who reads in their OWN voice + which host
    welcomes them), and a snippet — so the LLM can write host links that flow and react to
    the guests."""
    lines = []
    n = len(plan)
    for j, p in enumerate(plan):
        pos = "FIRST" if j == 0 else ("LAST" if j == n - 1 else f"#{j + 1}")
        snippet = (p["item"].get("standfirst") or p["item"].get("body") or "")[:150]
        if p["role"] == "guest":
            role = (f"GUEST '{p['persona']}' reads this in their OWN voice (welcomed by "
                    f"{p['introducer'].upper()} via a FIXED line — write NO item for this one)")
        else:
            role = f"read by {p['voice'].upper()}"
        lines.append(f"[{p['ref']} | {pos} | {role}] {p['item'].get('title', '')} — {snippet}")
    return "\n".join(lines)[:6000]


def _text_field(value: Any) -> str:
    """Coerce one LLM link field to a clean one-line string — tolerant of a plain string
    or a list of ``{text}``/strings from an older/looser shape (local models wander)."""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        parts = [(_text_field(e.get("text")) if isinstance(e, dict) else _text_field(e))
                 for e in value]
        return " ".join(p for p in parts if p)
    return ""


# A link is ONE sentence (the prompt insists); on translated editions the local model
# sometimes rambles meta-commentary into the field instead (#64). Anything past this cap
# is dropped deterministically — better a clean hand-off-less seam than voiced rambling.
_MAX_LINK_CHARS = 300


def _valid_link(text: str) -> str:
    """The link text if it is plausibly a one-liner, else ``""`` (dropped, logged)."""
    if len(text) > _MAX_LINK_CHARS:
        logger.warning("[podcast] dropping over-long banter link (%d chars > %d)",
                       len(text), _MAX_LINK_CHARS)
        return ""
    return text


def _script_text(turns: list[Turn]) -> str:
    """Render turns as a speaker-tagged transcript (also the downloadable transcript)."""
    return "\n".join(f"{who.upper()}: {text}" for who, text in turns)


def _plan(pairs: list[tuple[str, dict]]) -> list[dict]:
    """Decide who voices each article. A parody item whose clone is DEPLOYED is a ``guest``
    (reads in their OWN voice, welcomed by the seniority host); everything else is a
    ``host`` read that alternates Graham/Tom. Guests don't consume a host-alternation slot,
    so consecutive host reads still ping-pong. Returns one plan dict per article."""
    from content_pipeline.generate.personas import introducer_for
    plan: list[dict] = []
    host_i = 0
    for ref, item in pairs:
        gv = _guest_voice(item)
        persona = item.get("persona")
        if persona and gv:
            plan.append({"ref": ref, "item": item, "role": "guest", "voice": gv,
                         "persona": persona, "introducer": introducer_for(persona)})
        else:
            plan.append({"ref": ref, "item": item, "role": "host",
                         "voice": _reader_for(host_i), "persona": persona})
            host_i += 1
    return plan


def _edition_language(paper: dict, language: Optional[str]) -> str:
    """Resolve the edition's language: an explicit override, else the paper's own
    ``edition.language``, else the configured source language (English)."""
    return language or (paper.get("edition") or {}).get("language") or content_cfg.source_language


def build_podcast_script(paper: dict, *, generate: Optional[Generate] = None,
                         limit: Optional[int] = None, language: Optional[str] = None,
                         include_banter: bool = True) -> dict:
    """Assemble the dad↔son podcast script for ``paper`` — the "one clip per article" model.

    Each article becomes ONE rendered clip: the reader's opening link + the VERBATIM
    reading + their closing hand-off, all in the reader's single voice. That's far fewer
    seams than the old before/read/after split (every extra turn was a separate TTS clip,
    and the seams between clips were where the clone degraded). A parody guest with a
    deployed clone gets a FIXED host welcome (one clip) then reads in their OWN voice (one
    clip: thanks + verbatim reading + sign-off).

    Returns ``{turns, script_text, banter_text, refs}``:
      * ``turns`` — ``[(voice, text), …]`` for :func:`audio.render_podcast` (1 clip each).
      * ``script_text`` — the full speaker-tagged transcript (publishable alongside audio).
      * ``banter_text`` — ONLY the model-written links (what the rubric gate judges); the
        fixed welcomes/acks and the verbatim readings are NOT in it.
      * ``refs`` — the article refs included, in order.
    """
    from content_pipeline.generate.personas import character_read_intro
    lang = _edition_language(paper, language)
    pairs = [(ref, _resolve_ref(paper, ref)) for ref in _ordered_refs(paper)]
    pairs = [(ref, item) for ref, item in pairs if item]
    if limit is not None:
        pairs = pairs[:limit]
    plan = _plan(pairs)

    # ONE LLM call drafts the host links (pre/post) for every HOST-read article (keeps Tom's
    # character consistent), in the edition's language. Guests are framed by fixed templates,
    # so the LLM skips them. The links are gated per language (grade_podcast_script).
    # ``include_banter=False`` skips the LLM entirely — the deterministic skeleton (framing +
    # verbatim readings) with nothing to gate; the narrator's fallback when a banter is HELD.
    banter_by_ref: dict[str, dict] = {}
    if include_banter and any(p["role"] == "host" for p in plan):
        gen = generate or _default_generate
        try:
            data = gen(_banter_prompt(lang).format(digest=_digest(plan)))
            for entry in (data.get("items") or []):
                if isinstance(entry, dict) and entry.get("ref"):
                    banter_by_ref[str(entry["ref"])] = entry
        except Exception as exc:  # noqa: BLE001 — links are best-effort; readings still play
            logger.warning("[podcast] banter generation failed (%s); readings only", exc)

    # A translated edition opens with a spoken 'machine-translated from English' note (after
    # the jingle, before the cold-open). Deterministic — not part of the gated banter.
    turns: list[Turn] = []
    preamble = translation_preamble(paper, lang)
    if preamble:
        turns.append(("graham", preamble))
    turns += build_signature_intro(paper.get("date") or "", lang)
    banter_snippets: list[str] = []
    for p in plan:
        reading = _reading(p["item"])
        if p["role"] == "guest":
            # fixed welcome (introducing host) + the guest's own-voice clip (one piece)
            turns.append((p["introducer"], guest_welcome(lang).format(persona=p["persona"])))
            turns.append((p["voice"], "\n\n".join([guest_ack(lang), reading, guest_signoff(lang)])))
        else:
            b = banter_by_ref.get(p["ref"], {})
            pre = _valid_link(_text_field(b.get("pre")))
            post = _valid_link(_text_field(b.get("post")))
            banter_snippets += [s for s in (pre, post) if s]   # only the LLM text is gated
            body = reading
            if p.get("persona"):   # parody item with NO deployed clone → host reads in character
                intro = character_read_intro(p["persona"], lang)
                body = f"{intro}\n\n{reading}" if intro else reading
            turns.append((p["voice"], "\n\n".join(s for s in (pre, body, post) if s)))
    turns += signature_outro(lang)

    return {
        "turns": turns,
        "script_text": _script_text(turns),
        "banter_text": "\n".join(banter_snippets),
        "refs": [p["ref"] for p in plan],
    }


def _default_generate(prompt: str) -> dict:
    """Default banter LLM call — reuses the writer's local-first JSON generator."""
    from content_pipeline.generate.writer import _default_generate as _gen
    return _gen(prompt)


# ─────────────────────────────────────────────────────────────────────────────
# TL;DR — the <180s two-voice headline bulletin (deterministic; same jingle)
# ─────────────────────────────────────────────────────────────────────────────
# A fast "headlines podcast": Graham and Tom ALTERNATE reading the day's headlines
# (each item's already-approved title + a one-line gloss), topped & tailed by the
# SAME trad jingle as the full show. Fully DETERMINISTIC — no LLM, no banter to gate —
# and word-budgeted to the speaking time left after the jingle, so it reliably lands
# under the cap even if the voice clone reads slowly.
TLDR_BUDGET_WPM = 135          # a deliberately conservative read-rate FLOOR (real speech
                               # is faster) so the budget never overshoots the cap
TLDR_JINGLE_SECONDS = 26       # the trad bookend (intro + outro) eats into the time budget


def build_tldr_intro(date_iso: str, language: str = "en") -> list[Turn]:
    date = _date_phrase(date_iso, language)
    return [(who, text.format(date=date)) for who, text in _l10n(language)["tldr_intro"]]


def tldr_outro(language: str = "en") -> list[Turn]:
    """The localised TL;DR sign-off turns."""
    return list(_l10n(language)["tldr_outro"])


TLDR_OUTRO: list[Turn] = _L10N["en"]["tldr_outro"]   # back-compat: the English outro


def _first_sentence(text: str, *, max_chars: int = 140) -> str:
    """A one-line gloss: the first sentence (or a clipped clause) of the standfirst/body."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    s = re.split(r"(?<=[.!?])\s+", t, maxsplit=1)[0]
    if len(s) > max_chars:
        s = s[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return s


def _headline_beat(item: dict, reader: str) -> Turn:
    """One headline read: the (clipped) title + a one-line gloss, in ``reader``'s voice."""
    title = (" ".join(str(item.get("title", "")).split()).rstrip("."))[:100]
    gloss = _first_sentence(item.get("standfirst") or item.get("body") or "")
    return (reader, f"{title}." if not gloss else f"{title}. {gloss}")


TLDR_BUDGET_CPS = 7.0          # CJK read-rate FLOOR (chars/sec) for spaceless scripts (ja/zh)
_CJK_LANGS = ("ja", "zh")


def _speaking_units(text: str, language: str) -> int:
    """Approximate spoken length: characters for spaceless CJK, else whitespace words."""
    if language in _CJK_LANGS:
        return len(re.sub(r"\s+", "", text))
    return len(text.split())


def _count_units(turns: list[Turn], language: str) -> int:
    return sum(_speaking_units(t, language) for _, t in turns)


def _tldr_budget(max_seconds: int, language: str) -> int:
    """Spoken-unit budget left after the jingle bookend (chars for CJK, words otherwise)."""
    secs = max(0, max_seconds - TLDR_JINGLE_SECONDS)
    if language in _CJK_LANGS:
        return int(secs * TLDR_BUDGET_CPS)
    return int(secs * TLDR_BUDGET_WPM / 60.0)


def build_tldr_script(paper: dict, *, max_seconds: int = 180,
                      limit: Optional[int] = None, language: Optional[str] = None) -> dict:
    """Assemble the sub-``max_seconds`` TL;DR headline bulletin for ``paper``.

    Graham and Tom ALTERNATE reading each headline (the edition's own, already-approved
    title + a one-line gloss). Deterministic — no LLM — and budgeted to the speaking time
    left after the jingle bookend (by WORDS for space-delimited languages, by CHARACTERS
    for spaceless CJK), so it reliably lands under ``max_seconds``. A translated edition
    opens with the spoken translation note. Returns the same shape as
    :func:`build_podcast_script`; ``banter_text`` is empty (nothing is model-written).
    """
    lang = _edition_language(paper, language)
    budget = _tldr_budget(max_seconds, lang)

    pairs = [(ref, _resolve_ref(paper, ref)) for ref in _ordered_refs(paper)]
    pairs = [(ref, item) for ref, item in pairs if item]
    if limit is not None:
        pairs = pairs[:limit]

    turns: list[Turn] = []
    preamble = translation_preamble(paper, lang)
    if preamble:
        turns.append(("graham", preamble))
    turns += build_tldr_intro(paper.get("date") or "", lang)
    outro = tldr_outro(lang)
    used = _count_units(turns, lang) + _count_units(outro, lang)  # reserve preamble+intro+outro
    refs: list[str] = []
    for i, (ref, item) in enumerate(pairs):
        beat = _headline_beat(item, _reader_for(i))
        w = _speaking_units(beat[1], lang)
        if refs and used + w > budget:   # always keep at least one headline
            break
        turns.append(beat)
        used += w
        refs.append(ref)
    turns += outro

    return {
        "turns": turns,
        "script_text": _script_text(turns),
        "banter_text": "",      # deterministic — no LLM banter, nothing to gate
        "refs": refs,
    }
