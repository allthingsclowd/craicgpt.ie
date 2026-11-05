"""The masthead follows the family header standard (thegeekwiththepeak.com map #208).

One language control, in the masthead, as a globe icon button; and from 320px up the
document is never wider than its viewport, measured in real layout because a control that
outgrows the masthead is horizontal scroll on a phone and invisible to a string assertion.
"""

from pathlib import Path

import pytest

from tests.phone_overflow import WIDTHS, find_chrome, measure, overflowing

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_the_nav_has_no_second_language_control():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "nav-languages" not in html
    assert 'data-i18n="navLang"' not in html


def test_the_switcher_mounts_in_the_masthead_as_a_globe():
    js = (FRONTEND / "static_assets" / "main.js").read_text(encoding="utf-8")
    assert "document.querySelector('.site-header .account')" in js
    assert "ic-globe" in js
    assert "initNavLanguages" not in js


def test_no_page_is_wider_than_a_phone_or_tablet():
    if find_chrome() is None:
        pytest.skip("no Chrome/Chromium to measure layout with")
    rows = measure(FRONTEND, ["/index.html", "/about.html"])
    assert len(rows) == 2 * len(WIDTHS)
    assert overflowing(rows) == []
    with pytest.raises(RuntimeError, match="did not load the site shell"):
        measure(FRONTEND, ["/no-such-page.html"])
