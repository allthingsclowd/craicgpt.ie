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
    # Every entry is (creator_name, channel-Atom URL); names are unique.
    assert FUN_FEEDS, "the Irish-creator roster is empty"
    assert all(
        isinstance(name, str) and url.startswith(
            "https://www.youtube.com/feeds/videos.xml?channel_id=")
        for name, url in FUN_FEEDS
    )
    names = [name for name, _ in FUN_FEEDS]
    assert len(names) == len(set(names)), "duplicate creator in FUN_FEEDS"


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
