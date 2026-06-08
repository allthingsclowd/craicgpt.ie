"""Tests for the per-language HTML shell generator (offline)."""

from content_pipeline.agent.i18n_html import (
    META,
    build_localized_html,
    generate_localized_pages,
)

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>The Craic Gazette — English</title>
  <meta name="description" content="English description.">
  <link rel="alternate" hreflang="de" href="https://craicgpt.ie/de/">
</head>
<body>
  <a href="about.html">About</a>
  <a href="index.html">Home</a>
  <script src="/static_assets/main.js"></script>
</body>
</html>"""


def test_build_localized_sets_lang_title_meta_and_nav():
    out = build_localized_html(_TEMPLATE, "de", title="Deutscher Titel",
                               description="Deutsche Beschreibung.")
    assert '<html lang="de">' in out
    assert "<title>Deutscher Titel</title>" in out
    assert 'content="Deutsche Beschreibung."' in out
    assert 'href="/de/about.html"' in out                       # nav language-prefixed
    assert 'href="/de/"' in out
    # hreflang + root-absolute asset refs are left untouched
    assert 'hreflang="de" href="https://craicgpt.ie/de/"' in out
    assert 'src="/static_assets/main.js"' in out
    assert "English" not in out.split("</title>")[0]            # the English title is replaced


def test_generate_writes_non_source_pages(tmp_path):
    (tmp_path / "index.html").write_text(_TEMPLATE, encoding="utf-8")
    (tmp_path / "about.html").write_text(_TEMPLATE.replace("English", "About EN"), encoding="utf-8")
    written = generate_localized_pages(str(tmp_path), languages=["en", "de", "fr"],
                                       source_language="en")
    assert len(written) == 4                                    # de+fr × index+about (en is root)
    assert (tmp_path / "de" / "index.html").exists()
    assert (tmp_path / "fr" / "about.html").exists()
    assert not (tmp_path / "en").exists()                       # source language stays at root
    de = (tmp_path / "de" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="de">' in de
    assert META["index.html"]["de"]["title"] in de


def test_generate_skips_language_without_metadata(tmp_path):
    (tmp_path / "index.html").write_text(_TEMPLATE, encoding="utf-8")
    (tmp_path / "about.html").write_text(_TEMPLATE, encoding="utf-8")
    written = generate_localized_pages(str(tmp_path), languages=["en", "xx"], source_language="en")
    assert written == []                                        # no META for 'xx' → skipped, not fatal
