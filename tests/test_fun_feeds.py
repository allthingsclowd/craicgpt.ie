"""Tests for the Irish-creator fun harvester — deterministic fun-source discovery.

Graham's June 2026 call: the fun desk is now an Irish-creator digest. Instead of
the agent's good-news web trawl (which under-gathered and once fabricated, the
2026-06-04 HOLD), ``feeds.harvest_fun_candidates`` pulls each creator's freshest
YouTube uploads from their public Atom feed — real, dated video URLs.

ATTRIBUTION (Graham's hard rule, exercised below): credit the creator. Each
candidate's ``source_url`` is the creator's own video URL (from the feed entry,
never invented) and ``source`` carries the creator's NAME so it can be stamped
onto the published piece. All offline — the feed fetch is injected.
"""

from datetime import datetime, timedelta, timezone

from content_pipeline.research import feeds
from content_pipeline.research.fun_sources import FUN_FEEDS

# A "fresh" timestamp computed at runtime (a couple of hours ago) so the recency
# window in harvest_fun_candidates always includes it — the test never goes stale on
# a baked-in date. The second entry is fixed in the deep past (always excluded).
_FRESH_DT = datetime.now(timezone.utc) - timedelta(hours=2)
_FRESH = _FRESH_DT.strftime("%Y-%m-%dT%H:%M:%S+00:00")

# A representative YouTube channel Atom feed: rel=alternate watch URL + <published>.
# (YouTube nests the blurb in <media:group><media:description>, which parse_feed
# doesn't descend into, so summary is legitimately empty — title + url carry it.)
_YT_ATOM = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<feed xmlns:yt='http://www.youtube.com/xml/schemas/2015' "
    "xmlns:media='http://search.yahoo.com/mrss/' "
    "xmlns='http://www.w3.org/2005/Atom'>"
    "<title>Foil Arms and Hog</title>"
    "<entry><id>yt:video:VID1</id><yt:videoId>VID1</yt:videoId>"
    "<title>Every Irish Mammy on the Phone</title>"
    "<link rel='alternate' href='https://www.youtube.com/watch?v=VID1'/>"
    f"<published>{_FRESH}</published>"
    "<media:group><media:description>An accurate guide.</media:description></media:group>"
    "</entry>"
    "<entry><id>yt:video:OLD</id><yt:videoId>OLD</yt:videoId>"
    "<title>Ancient Sketch</title>"
    "<link rel='alternate' href='https://www.youtube.com/watch?v=OLD'/>"
    "<published>2019-01-01T00:00:00+00:00</published></entry>"
    "</feed>"
)


def test_fun_feeds_registry_shape():
    # Every entry is (creator_name, https feed URL); names are unique. The roster
    # mixes YouTube channel Atom feeds with press/blog RSS (2026-06-11 expansion).
    assert FUN_FEEDS, "the creator roster is empty"
    assert all(isinstance(name, str) and name and url.startswith("https://")
               for name, url in FUN_FEEDS)
    names = [name for name, _ in FUN_FEEDS]
    assert len(names) == len(set(names)), "duplicate creator in FUN_FEEDS"
    # The 2026-06-11 expansion is present: female-first Brit comedy + Honda moto.
    assert any("Millican" in n for n in names)
    assert any("Honda" in n for n in names)
    # Every press-feed filter points at a real roster source.
    from content_pipeline.research.fun_sources import FUN_FEED_FILTERS
    assert set(FUN_FEED_FILTERS) <= set(names)


def test_parse_youtube_atom_entry():
    items = feeds.parse_feed(_YT_ATOM, "Foil Arms and Hog")
    titles = [i.title for i in items]
    assert titles == ["Every Irish Mammy on the Phone", "Ancient Sketch"]
    one = items[0]
    assert one.url == "https://www.youtube.com/watch?v=VID1"  # rel=alternate watch URL
    assert one.source == "Foil Arms and Hog"
    assert one.published is not None and one.published.year == _FRESH_DT.year


def test_harvest_fun_candidates_attribution_invariant():
    # The whole ballgame: source = the creator's NAME (the credit/byline), and
    # source_url = the creator's own video URL straight from their feed entry.
    cands = feeds.harvest_fun_candidates(max_per_feed=5, fetch=lambda url: _YT_ATOM)
    assert cands, "no fun candidates harvested"
    assert all(
        {"title", "summary", "source_url", "source", "_creator"} <= set(c) for c in cands
    )
    first = cands[0]
    assert first["source"] == "Foil Arms and Hog"        # credit = creator name
    assert first["_creator"] == "Foil Arms and Hog"      # internal hint mirrors it
    assert first["source_url"] == "https://www.youtube.com/watch?v=VID1"  # the entry's video URL


def test_harvest_fun_candidates_excludes_stale_uploads():
    # The 2019 video is older than the default window → never surfaces (so the desk
    # riffs on what's actually fresh, never reheats an ancient upload).
    cands = feeds.harvest_fun_candidates(max_per_feed=5, fetch=lambda url: _YT_ATOM)
    assert cands and all("OLD" not in c["source_url"] for c in cands)


def test_harvest_fun_candidates_caps_per_feed():
    many = "".join(
        f"<entry><title>Clip {i}</title>"
        f"<link rel='alternate' href='https://www.youtube.com/watch?v=C{i}'/></entry>"
        for i in range(8)
    )
    xml = (
        "<feed xmlns='http://www.w3.org/2005/Atom'><title>Creator</title>"
        f"{many}</feed>"
    )
    cands = feeds.harvest_fun_candidates(max_per_feed=2, fetch=lambda url: xml)
    # 28 creators all served the same feed; each capped at 2 → at most 2 per feed.
    per_feed = {}
    for c in cands:
        per_feed[c["source"]] = per_feed.get(c["source"], 0) + 1
    assert per_feed and max(per_feed.values()) <= 2


def test_harvest_fun_candidates_skips_dead_feeds():
    assert feeds.harvest_fun_candidates(fetch=lambda url: None) == []


# ── 2026-06-11 expansion: freshness ladder, views ranking, press-feed filter ──
def _yt_feed(name, entries):
    """Build a minimal channel Atom feed. entries = [(vid, title, dt_iso, views|None)]."""
    parts = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<feed xmlns:yt='http://www.youtube.com/xml/schemas/2015' "
        "xmlns:media='http://search.yahoo.com/mrss/' xmlns='http://www.w3.org/2005/Atom'>",
        f"<title>{name}</title>",
    ]
    for vid, title, dt, views in entries:
        stats = (f"<media:community><media:statistics views='{views}'/>"
                 "</media:community>") if views is not None else ""
        parts.append(
            f"<entry><id>yt:video:{vid}</id><yt:videoId>{vid}</yt:videoId>"
            f"<title>{title}</title>"
            f"<link rel='alternate' href='https://www.youtube.com/watch?v={vid}'/>"
            f"<published>{dt}</published>"
            f"<media:group><media:description>d</media:description>{stats}</media:group>"
            "</entry>")
    parts.append("</feed>")
    return "".join(parts)


def _iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def test_parse_feed_extracts_youtube_view_counts():
    xml = _yt_feed("Sarah Millican", [("V1", "Tour vlog", _iso(2), 123456)])
    items = feeds.parse_feed(xml, "Sarah Millican")
    assert items[0].views == 123456
    # absent statistics → views stays None (never invented)
    xml2 = _yt_feed("Sarah Millican", [("V2", "Old clip", _iso(2), None)])
    assert feeds.parse_feed(xml2, "Sarah Millican")[0].views is None


def test_fun_ladder_prefers_the_freshest_band_that_fills_the_pool():
    """Graham's freshness rule: prefer the last 24 h; widen (48 h, 96 h) only when
    the pool is thin (weekends). One fetch pass; banding is client-side."""
    xml = _yt_feed("Foil Arms and Hog", [
        ("F1", "Fresh sketch", _iso(2), 10),
        ("D1", "Two days back", _iso(60), 999),
        ("D2", "Three days back", _iso(70), 5),
    ])
    fetch = lambda url: xml  # noqa: E731
    one_feed = [("Foil Arms and Hog", "https://www.youtube.com/feeds/videos.xml?channel_id=X")]

    # Pool target met by the 24 h band alone → ONLY the fresh item comes back.
    fresh = feeds.harvest_fun_candidates(feeds_list=one_feed, fetch=fetch,
                                         min_pool=1, max_per_feed=5)
    assert [c["title"] for c in fresh] == ["Fresh sketch"]

    # Thin 24 h band → ladder widens until the pool target is met (96 h here).
    wide = feeds.harvest_fun_candidates(feeds_list=one_feed, fetch=fetch,
                                        min_pool=3, max_per_feed=5)
    assert {c["title"] for c in wide} == {"Fresh sketch", "Two days back", "Three days back"}


def test_fun_candidates_ranked_by_views_within_the_band():
    xml = _yt_feed("RTGame", [
        ("A", "Modest video", _iso(3), 50),
        ("B", "Banger video", _iso(4), 50_000),
        ("C", "Unstated views", _iso(5), None),
    ])
    out = feeds.harvest_fun_candidates(
        feeds_list=[("RTGame", "https://www.youtube.com/feeds/videos.xml?channel_id=Y")],
        fetch=lambda url: xml, min_pool=1, max_per_feed=5)
    assert [c["title"] for c in out] == ["Banger video", "Modest video", "Unstated views"]


def test_press_feeds_are_keyword_filtered():
    """The bike-press RSS feeds are general — only the Honda items may enter the
    fun pool (FUN_FEED_FILTERS maps source name → required keyword)."""
    from content_pipeline.research import fun_sources
    rss = (
        "<?xml version='1.0'?><rss version='2.0'><channel><title>MCN</title>"
        f"<item><title>Honda Fireblade review</title><link>https://mcn/h1</link>"
        f"<pubDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>"
        f"<item><title>Ducati launch</title><link>https://mcn/d1</link>"
        f"<pubDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>"
        "</channel></rss>")
    import unittest.mock as mock
    with mock.patch.dict(fun_sources.FUN_FEED_FILTERS, {"MCN": "honda"}):
        out = feeds.harvest_fun_candidates(
            feeds_list=[("MCN", "https://www.motorcyclenews.com/rss")],
            fetch=lambda url: rss, min_pool=1, max_per_feed=5)
    assert [c["title"] for c in out] == ["Honda Fireblade review"]
