"""The masthead follows the family header standard (thegeekwiththepeak.com map #208).

One language control, in the masthead, as a globe icon button, on the front page and on
About alike. From 320px up the document is never wider than its viewport and every masthead
control stays a 44px touch target: both measured in real layout, because a control that
outgrows or is squeezed by the masthead is invisible to a string assertion.
"""

from pathlib import Path

import pytest

from tests.phone_overflow import (
    WIDTHS,
    find_chrome,
    measure,
    overflowing,
    spilling,
    undersized,
)

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PAGES = ("index.html", "about.html")


@pytest.mark.parametrize("page", PAGES)
def test_the_nav_has_no_second_language_control(page):
    html = (FRONTEND / page).read_text(encoding="utf-8")
    assert "nav-languages" not in html
    assert 'data-i18n="navLang"' not in html
    assert "#lang-switcher" not in html.split("<nav", 1)[1].split("</nav>", 1)[0]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_loads_the_script_that_mounts_the_switcher(page):
    html = (FRONTEND / page).read_text(encoding="utf-8")
    assert '<script src="/static_assets/main.js">' in html
    assert '<div class="account">' in html


def test_the_switcher_mounts_in_the_masthead_as_a_globe():
    js = (FRONTEND / "static_assets" / "main.js").read_text(encoding="utf-8")
    assert "document.querySelector('.site-header .account')" in js
    assert "ic-globe" in js
    assert "initNavLanguages" not in js
    assert "navLang" not in js


def test_switching_language_on_about_stays_on_about():
    js = (FRONTEND / "static_assets" / "main.js").read_text(encoding="utf-8")
    assert "return `/${lang}/about.html`" in js


def test_no_page_is_wider_than_a_phone_or_its_buttons_smaller_than_a_thumb():
    if find_chrome() is None:
        pytest.skip("no Chrome/Chromium to measure layout with")
    before = sorted(p.name for p in FRONTEND.iterdir())
    rows = measure(FRONTEND, [f"/{page}" for page in PAGES])
    assert len(rows) == len(PAGES) * len(WIDTHS)
    assert overflowing(rows) == []
    assert undersized(rows) == []
    assert spilling(rows) == []  # no nav label wider than its own tab or pill
    # the theme toggle and the language switcher, on both pages at every width
    assert {r.controls for r in rows} == {2}
    with pytest.raises(RuntimeError, match="did not load the site shell"):
        measure(FRONTEND, ["/no-such-page.html"])
    # frontend/ is what gets deployed: the check must leave nothing behind in it.
    assert sorted(p.name for p in FRONTEND.iterdir()) == before
