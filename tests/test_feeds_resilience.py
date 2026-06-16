"""Fun-desk harvest resilience + Honda/CB1000GT bias (2026-06-16).

Guards the fixes for the silent comedian-feed collapse: retry-on-transient,
named-feed skip logging, the CB1000GT ranking boost, and the diversified moto feeds.
All offline (injected fetch/sleep).
"""

from __future__ import annotations

import logging

from content_pipeline.research import feeds
from content_pipeline.research import fun_sources as fs


# ── retry / backoff ─────────────────────────────────────────────────────────
def test_retrying_fetch_recovers_after_transient():
    calls = {"n": 0}

    def once(url):
        calls["n"] += 1
        if calls["n"] < 3:
            raise feeds._TransientFetch("HTTP 429")
        return "<rss/>"

    out = feeds._retrying_fetch(once, "http://x", attempts=3, sleep=lambda _: None)
    assert out == "<rss/>" and calls["n"] == 3


def test_retrying_fetch_gives_up_after_attempts():
    def once(url):
        raise feeds._TransientFetch("timeout")

    out = feeds._retrying_fetch(once, "http://x", attempts=3, sleep=lambda _: None)
    assert out is None


def test_retrying_fetch_does_not_retry_permanent():
    calls = {"n": 0}

    def once(url):
        calls["n"] += 1
        return None  # permanent (e.g. 404) — terminal, no retry

    assert feeds._retrying_fetch(once, "http://x", attempts=3, sleep=lambda _: None) is None
    assert calls["n"] == 1


# ── named skip logging (the silent-collapse fix) ────────────────────────────
def test_harvest_names_failed_feeds(caplog):
    good = "<rss><channel><item><title>Honda news</title><link>https://x/1</link>"\
           "<description>honda</description></item></channel></rss>"

    def fetch(url):
        return good if "ok" in url else ""  # the others "fail"

    feeds_list = [("GoodFeed", "http://ok"), ("DeadA", "http://a"), ("DeadB", "http://b")]
    with caplog.at_level(logging.WARNING):
        feeds.harvest(feeds_list, since_hours=96, max_per_feed=2, fetch=fetch)
    msg = "\n".join(r.getMessage() for r in caplog.records)
    assert "2/3 feeds returned NO items" in msg
    assert "DeadA" in msg and "DeadB" in msg


# ── CB1000GT ranking boost ──────────────────────────────────────────────────
def test_cb1000gt_items_rank_first():
    rss = (
        "<rss><channel>"
        "<item><title>Generic Honda news</title><link>https://x/1</link>"
        "<description>honda</description></item>"
        "<item><title>New CB1000R road test</title><link>https://x/2</link>"
        "<description>honda cb1000r</description></item>"
        "<item><title>Honda CB1000GT first ride</title><link>https://x/3</link>"
        "<description>honda cb1000gt sports tourer</description></item>"
        "</channel></rss>"
    )
    out = feeds.harvest_fun_candidates(
        feeds_list=[("TestPress", "http://t")], fetch=lambda u: rss,
        max_per_feed=3, min_pool=1,
    )
    titles = [o["title"] for o in out]
    assert "CB1000GT" in titles[0]                  # GT leads
    assert "CB1000R" in titles[1]                   # then the CB1000 family
    assert titles[2] == "Generic Honda news"        # generic last


# ── diversified moto registry + comedy classification ───────────────────────
def test_new_moto_feeds_registered_and_honda_filtered():
    names = {n for n, _ in fs._BIKE_PRESS}
    for added in ("RideApart", "Adventure Bike Rider", "Devitt"):
        assert added in names
        assert fs.FUN_FEED_FILTERS.get(added) == "honda"


def test_is_comedy_source_distinguishes_press_from_creators():
    assert fs.is_comedy_source("Taskmaster") is True
    assert fs.is_comedy_source("Vittorio Angelone") is True
    assert fs.is_comedy_source("MoreBikes") is False
    assert fs.is_comedy_source("RideApart") is False
    assert fs.is_comedy_source("Honda UK") is False
    assert fs.is_comedy_source(None) is False


def test_cb1000gt_keywords_present():
    assert "cb1000gt" in fs.CB1000GT_KEYWORDS


# ── creators-missing alert ──────────────────────────────────────────────────
def test_fun_desk_alert_fires_when_only_motorcycle():
    fun = [{"source": "MoreBikes", "title": "Bike that costs a house"},
           {"source": "RideApart", "title": "Transalp"}]
    alert = fs.fun_desk_alert(fun, "2026-06-16")
    assert alert and "NO comedian items" in alert


def test_fun_desk_alert_silent_when_comedians_present():
    fun = [{"source": "MoreBikes", "title": "bike"},
           {"source": "Vittorio Angelone", "title": "skit"}]
    assert fs.fun_desk_alert(fun, "2026-06-16") is None


def test_fun_desk_alert_fires_on_empty_desk():
    assert fs.fun_desk_alert([], "2026-06-16") is not None
