"""
content_pipeline/agent/i18n_html.py
===================================
Generate the per-language HTML shells (``frontend/<lang>/index.html`` +
``about.html``) from the English source templates.

The English page is the template AND the live root page (served at the S3 root,
exposed as ``/en/`` via the CloudFront alias). For every OTHER language this writes
a sibling copy with:

  * ``<html lang="xx">`` — so crawlers and screen readers get the real language,
  * a translated ``<title>`` + ``<meta name="description">`` — the SEO-critical,
    server-rendered bits client-side JS can't reliably set for bots,
  * language-prefixed nav links (``index.html``/``about.html`` → ``/<lang>/…``), and
  * the static, visible body chrome ``main.js`` never touches (the kicker strip,
    the newsletter band, the Under-the-Hood toggle, the footer note) — see ``CHROME``.

The ``hreflang`` alternates block is identical on every language's page, so it
carries over from the template untouched. The article CONTENT (and a handful of
runtime-injected strings) are localised by the translated ``paper_content.json``
and ``main.js``'s i18n table respectively; this file owns the static ``<head>``,
nav, and the surrounding chrome — everything a search crawler reads without JS.

Pure string templating (stdlib ``re``) — no Jinja, no extra dependency — so it's
trivially unit-testable and runs as a step of ``frontend.sync_frontend``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

PAGES = ("index.html", "about.html")

# Translated <title> + <meta description> per page per language. The body chrome is
# localised at runtime (main.js); these are the crawler-facing head tags. English is
# the template's own value (never generated). Frozen, review-pending.
META: dict[str, dict[str, dict[str, str]]] = {
    "index.html": {
        "de": {"title": "The Craic Gazette — Irlands intelligenteste KI-Zeitung",
               "description": "Eine tägliche irische Zeitung mit lustigen Weltnachrichten und "
                              "KI-Berichterstattung, geschrieben von Open-Source-LLMs und "
                              "orchestriert von einem LangChain-Deep-Agent."},
        "es": {"title": "The Craic Gazette — El periódico de IA más inteligente de Irlanda",
               "description": "Un periódico irlandés diario de noticias divertidas del mundo y "
                              "cobertura del panorama de la IA, escrito por LLMs de código abierto "
                              "y orquestado por un agente profundo de LangChain."},
        "it": {"title": "The Craic Gazette — Il giornale di IA più intelligente d'Irlanda",
               "description": "Un quotidiano irlandese di notizie divertenti dal mondo e analisi "
                              "sul panorama dell'IA, scritto da LLM open-source e orchestrato da "
                              "un deep agent LangChain."},
        "ja": {"title": "The Craic Gazette — アイルランドで一番人工知能な新聞",
               "description": "世界の楽しいニュースとAIの動向を毎日お届けするアイルランドの新聞。"
                              "オープンソースのLLMが執筆し、LangChainのディープエージェントが"
                              "編成しています。"},
        "fr": {"title": "The Craic Gazette — Le journal d'IA le plus intelligent d'Irlande",
               "description": "Un quotidien irlandais de nouvelles légères du monde et de "
                              "couverture de l'actualité de l'IA, écrit par des LLM open source et "
                              "orchestré par un agent profond LangChain."},
    },
    "about.html": {
        "de": {"title": "Über den Redakteur — The Craic Gazette",
               "description": "Über Graham Land, Chefredakteur der Craic Gazette — mehr oder "
                              "weniger ehrlich vorgestellt in der Stimme von Father Ted."},
        "es": {"title": "Sobre el editor — The Craic Gazette",
               "description": "Sobre Graham Land, redactor jefe de The Craic Gazette — presentado, "
                              "más o menos honestamente, con la voz de Father Ted."},
        "it": {"title": "Informazioni sul redattore — The Craic Gazette",
               "description": "Su Graham Land, caporedattore della Craic Gazette — presentato, "
                              "più o meno onestamente, con la voce di Father Ted."},
        "ja": {"title": "編集長について — The Craic Gazette",
               "description": "クレイク・ガゼット編集長グラハム・ランドについて。ファーザー・テッドの"
                              "声で、多かれ少なかれ正直にご紹介します。"},
        "fr": {"title": "À propos du rédacteur — The Craic Gazette",
               "description": "À propos de Graham Land, rédacteur en chef de The Craic Gazette — "
                              "présenté, plus ou moins honnêtement, avec la voix de Father Ted."},
    },
}

# Translated VISIBLE body chrome — the static, server-rendered strings around the
# article content that main.js does NOT touch (the kicker strip, the newsletter band,
# the Under-the-Hood toggle, the footer note). English is the template's own value.
# Frozen, review-pending. A language missing here keeps the English chrome (never fatal).
CHROME: dict[str, dict[str, str]] = {
    "de": {
        "today_label": "HEUTE",
        "tagline": "Eine irische Tageszeitung, ohne den Weltuntergang",
        "masthead_price": "GRATIS (wie Freiheit, nicht wie Freibier)",
        "masthead_subtitle": "Der ganze Craic, der zu halluzinieren lohnt",
        "edition_draft": "v3 · Entwurf",
        "change_date": "📅 Datum ändern",
        "about_title": "Über den Redakteur", "about_subtitle": "Wer steckt hinter all dem Craic?",
        "nav_today": "Heute", "nav_ai": "KI-Desk", "nav_craic": "Craic",
        "nav_lang": "Sprachen", "nav_listen": "Hören",
        "nav_older": "◀ Älter", "nav_newer": "Neuer ▶",
        "kicker_text": "Irlands Lustigstes, plus was sich in der KI wirklich geändert hat — über "
                       "Nacht von Open-Source-Modellen geschrieben. Keine Menschen im Spiel, kein "
                       "Weltuntergang im Feed.",
        "newsletter_title": "Der Craic, direkt in dein Postfach",
        "newsletter_sub": "Ein ausführlicherer täglicher KI-Newsletter mit Grahams Sicht. Demnächst.",
        "hood_toggle": "Ein Blick unter die Haube — wie ein LangChain-Deep-Agent das gebaut hat",
        "footer_note": "Bei der Herstellung dieser Zeitung wurden keine Halluzinationen verletzt.",
    },
    "es": {
        "today_label": "HOY",
        "tagline": "Un diario irlandés, sin el fatalismo",
        "masthead_price": "GRATIS (como en libertad, no como en cerveza)",
        "masthead_subtitle": "Todo el craic digno de alucinar",
        "edition_draft": "v3 · borrador",
        "change_date": "📅 cambiar fecha",
        "about_title": "Sobre el editor", "about_subtitle": "¿Quién está detrás de todo este craic?",
        "nav_today": "Hoy", "nav_ai": "Mesa IA", "nav_craic": "Craic",
        "nav_lang": "Idiomas", "nav_listen": "Escuchar",
        "nav_older": "◀ Anterior", "nav_newer": "Siguiente ▶",
        "kicker_text": "Lo más divertido de Irlanda, además de lo que realmente cambió en la IA — "
                       "escrito durante la noche por modelos de código abierto. Sin humanos de por "
                       "medio, sin fatalismo en el feed.",
        "newsletter_title": "El Craic, en tu bandeja de entrada",
        "newsletter_sub": "Un boletín diario de IA más extenso con la opinión de Graham. Próximamente.",
        "hood_toggle": "Bajo el capó — cómo un agente profundo de LangChain creó esto",
        "footer_note": "Ninguna alucinación resultó herida en la elaboración de este periódico.",
    },
    "it": {
        "today_label": "OGGI",
        "tagline": "Un quotidiano irlandese, senza catastrofismo",
        "masthead_price": "GRATIS (come libertà, non come birra)",
        "masthead_subtitle": "Tutto il craic che vale la pena allucinare",
        "edition_draft": "v3 · bozza",
        "change_date": "📅 cambia data",
        "about_title": "Informazioni sul redattore", "about_subtitle": "Chi c’è dietro tutto questo craic?",
        "nav_today": "Oggi", "nav_ai": "Desk IA", "nav_craic": "Craic",
        "nav_lang": "Lingue", "nav_listen": "Ascolta",
        "nav_older": "◀ Precedente", "nav_newer": "Successiva ▶",
        "kicker_text": "Il meglio dell'umorismo irlandese, più ciò che è davvero cambiato nell'IA — "
                       "scritto nella notte da modelli open-source. Nessun umano in mezzo, nessuna "
                       "catastrofe nel feed.",
        "newsletter_title": "Il Craic, nella tua casella di posta",
        "newsletter_sub": "Un dispaccio quotidiano di IA più esteso con il punto di vista di Graham. "
                          "Presto disponibile.",
        "hood_toggle": "Sotto il cofano — come un deep agent LangChain ha costruito tutto questo",
        "footer_note": "Nessuna allucinazione è stata maltrattata nella realizzazione di questo giornale.",
    },
    "ja": {
        "today_label": "本日",
        "tagline": "アイルランドの日刊紙、暗い話題は抜きで",
        "masthead_price": "無料（自由の意味で、ビールではなく）",
        "masthead_subtitle": "幻覚するに値するすべてのクレイク",
        "edition_draft": "v3 · 下書き",
        "change_date": "📅 日付を変更",
        "about_title": "編集長について", "about_subtitle": "このクレイクの裏にいるのは誰？",
        "nav_today": "本日", "nav_ai": "AIデスク", "nav_craic": "クレイク",
        "nav_lang": "言語", "nav_listen": "聴く",
        "nav_older": "◀ 前の号", "nav_newer": "次の号 ▶",
        "kicker_text": "アイルランド一おもしろいニュースに、AIで実際に変わったこと——オープンソースの"
                       "モデルが夜通し執筆。人間は関与せず、暗い話題もなし。",
        "newsletter_title": "クレイクを、あなたの受信箱に",
        "newsletter_sub": "グラハムの視点を交えた、より読み応えのある毎日のAIダイジェスト。近日公開。",
        "hood_toggle": "仕組みを見る——LangChainのディープエージェントがこれをどう作ったか",
        "footer_note": "この新聞の制作において、幻覚（ハルシネーション）は一切傷つけられていません。",
    },
    "fr": {
        "today_label": "AUJOURD'HUI",
        "tagline": "Un quotidien irlandais, sans la sinistrose",
        "masthead_price": "GRATUIT (comme la liberté, pas comme la bière)",
        "masthead_subtitle": "Tout le craic digne d’être halluciné",
        "edition_draft": "v3 · brouillon",
        "change_date": "📅 changer de date",
        "about_title": "À propos du rédacteur", "about_subtitle": "Qui se cache derrière tout ce craic ?",
        "nav_today": "Aujourd'hui", "nav_ai": "Bureau IA", "nav_craic": "Craic",
        "nav_lang": "Langues", "nav_listen": "Écouter",
        "nav_older": "◀ Précédente", "nav_newer": "Suivante ▶",
        "kicker_text": "Le plus drôle d'Irlande, plus ce qui a vraiment changé dans l'IA — écrit "
                       "pendant la nuit par des modèles open source. Aucun humain dans la boucle, "
                       "aucune sinistrose dans le fil.",
        "newsletter_title": "Le Craic, dans votre boîte mail",
        "newsletter_sub": "Une dépêche IA quotidienne plus complète avec l'avis de Graham. Bientôt "
                          "disponible.",
        "hood_toggle": "Sous le capot — comment un agent profond LangChain a créé tout ça",
        "footer_note": "Aucune hallucination n'a été blessée pendant la fabrication de ce journal.",
    },
}

# (element-locating regex, chrome key) — each localises one element's inner text in place.
# Class-anchored so a minimal template (or the About page) simply matches nothing.
_CHROME_RULES: list[tuple[str, str]] = [
    (r'(<span class="kicker-label">).*?(</span>)', "today_label"),
    (r'(<span class="kicker-text">).*?(</span>)', "kicker_text"),
    (r'(<h3 class="newsletter-title">).*?(</h3>)', "newsletter_title"),
    (r'(<p class="newsletter-sub">).*?(</p>)', "newsletter_sub"),
    (r'(<span class="hood-toggle-text">).*?(</span>)', "hood_toggle"),
    # Masthead chrome + About title band. These carry class/id attributes alongside
    # data-i18n, so anchor loosely on the data-i18n value (main.js also sets them at
    # runtime via t()). index.html elements simply don't match on the About page and
    # vice-versa. See issue #131.
    (r'(<span[^>]*data-i18n="tagline"[^>]*>).*?(</span>)', "tagline"),
    (r'(<span[^>]*data-i18n="mastheadPrice"[^>]*>).*?(</span>)', "masthead_price"),
    (r'(<span[^>]*data-i18n="mastheadSubtitle"[^>]*>).*?(</span>)', "masthead_subtitle"),
    (r'(<span[^>]*data-i18n="editionDraft"[^>]*>).*?(</span>)', "edition_draft"),
    (r'(<label[^>]*data-i18n="changeDate"[^>]*>).*?(</label>)', "change_date"),
    # Prev/next edition paging buttons (#134). Visible text only — the aria-label is set
    # at runtime by main.js (the buttons need JS to function). data-i18n-anchored.
    (r'(<button[^>]*data-i18n="navOlder"[^>]*>).*?(</button>)', "nav_older"),
    (r'(<button[^>]*data-i18n="navNewer"[^>]*>).*?(</button>)', "nav_newer"),
    (r'(<h1[^>]*data-i18n="aboutTitle"[^>]*>).*?(</h1>)', "about_title"),
    (r'(<p[^>]*data-i18n="aboutSubtitle"[^>]*>).*?(</p>)', "about_subtitle"),
    # The three-layout shell-nav labels (data-i18n-anchored so the About page's
    # cross-page nav localises too). main.js also applies these at runtime via t().
    (r'(<span data-i18n="navToday">).*?(</span>)', "nav_today"),
    (r'(<span data-i18n="navAi">).*?(</span>)', "nav_ai"),
    (r'(<span data-i18n="navCraic">).*?(</span>)', "nav_craic"),
    (r'(<span data-i18n="navLang">).*?(</span>)', "nav_lang"),
    (r'(<span data-i18n="navListen">).*?(</span>)', "nav_listen"),
]
# The footer note is a unique sentence shared by index + about — a plain string swap.
_FOOTER_NOTE_EN = "No hallucinations were harmed in the making of this newspaper."


def build_localized_html(template: str, lang: str, *, title: str, description: str) -> str:
    """Return ``template`` localised to ``lang``: html-lang + translated head + nav prefix
    + translated visible body chrome (kicker strip, newsletter band, hood toggle, footer note)."""
    html = re.sub(r'<html lang="[^"]*">', f'<html lang="{lang}">', template, count=1)
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)
    html = re.sub(r'(<meta name="description" content=")[^"]*(">)',
                  lambda m: m.group(1) + description + m.group(2), html, count=1)
    # Language-prefix the internal nav links (leave external/hreflang absolute URLs alone).
    html = html.replace('href="about.html"', f'href="/{lang}/about.html"')
    html = html.replace('href="index.html"', f'href="/{lang}/"')
    # Localise the visible chrome main.js never touches. A language without a CHROME entry
    # keeps the English chrome; an element absent from the page is a no-op.
    chrome = CHROME.get(lang)
    if chrome:
        for pattern, key in _CHROME_RULES:
            text = chrome.get(key)
            if not text:
                continue
            html = re.sub(pattern, lambda m, t=text: m.group(1) + t + m.group(2),
                          html, count=1, flags=re.S)
        if chrome.get("footer_note"):
            html = html.replace(_FOOTER_NOTE_EN, chrome["footer_note"])
    return html


def generate_localized_pages(frontend_dir: str,
                             languages: Optional[list[str]] = None,
                             source_language: Optional[str] = None) -> list[str]:
    """Write ``frontend/<lang>/{index,about}.html`` for every non-source language.

    Idempotent: regenerates from the current English templates each call (so it stays
    in lockstep with hand-edits to the source pages). Returns the written paths. A
    missing template or a language with no META entry is skipped (logged), never fatal."""
    languages = languages or content_cfg.languages
    source_language = source_language or content_cfg.source_language
    written: list[str] = []
    for page in PAGES:
        tpath = os.path.join(frontend_dir, page)
        try:
            with open(tpath, encoding="utf-8") as fh:
                template = fh.read()
        except OSError as exc:
            logger.warning("[i18n_html] template %s unreadable: %s", tpath, exc)
            continue
        for lang in languages:
            if lang == source_language:
                continue
            meta = META.get(page, {}).get(lang)
            if not meta:
                logger.warning("[i18n_html] no %s metadata for %s — skipped", page, lang)
                continue
            out = build_localized_html(template, lang, **meta)
            dest_dir = os.path.join(frontend_dir, lang)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, page)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(out)
            written.append(dest)
    logger.info("[i18n_html] generated %d localized page(s)", len(written))
    return written


if __name__ == "__main__":  # `python -m content_pipeline.agent.i18n_html [frontend_dir]`
    import sys

    logging.basicConfig(level=logging.INFO)
    out = generate_localized_pages(sys.argv[1] if len(sys.argv) > 1 else "frontend")
    print("\n".join(out))

