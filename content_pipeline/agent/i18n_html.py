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
    server-rendered bits client-side JS can't reliably set for bots, and
  * language-prefixed nav links (``index.html``/``about.html`` → ``/<lang>/…``).

The ``hreflang`` alternates block is identical on every language's page, so it
carries over from the template untouched. The visible body chrome + the article
CONTENT are localised at runtime by ``main.js`` (the i18n table) and by the
translated ``paper_content.json`` respectively — this file only owns the static
``<head>`` + nav, which is exactly what a search crawler reads.

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


def build_localized_html(template: str, lang: str, *, title: str, description: str) -> str:
    """Return ``template`` localised to ``lang``: html-lang + translated head + nav prefix."""
    html = re.sub(r'<html lang="[^"]*">', f'<html lang="{lang}">', template, count=1)
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)
    html = re.sub(r'(<meta name="description" content=")[^"]*(">)',
                  lambda m: m.group(1) + description + m.group(2), html, count=1)
    # Language-prefix the internal nav links (leave external/hreflang absolute URLs alone).
    html = html.replace('href="about.html"', f'href="/{lang}/about.html"')
    html = html.replace('href="index.html"', f'href="/{lang}/"')
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

