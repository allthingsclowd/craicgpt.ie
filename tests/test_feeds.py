"""Tests for the curated-feed harvester — deterministic AI-source discovery.

The 2026-06-04 HOLD (the agent gathered only 7 AI candidates) showed the AI desk
can't rely on the agent's yield alone. feeds.harvest pulls recent items from
Graham's curated RSS/Atom sources deterministically, seeding a rich, REAL pool.
All offline — the feed fetch is injected.
"""

from content_pipeline.research import feeds

_RSS = (
    "<?xml version='1.0'?><rss version='2.0'><channel><title>Pub</title>"
    "<item><title>RSS One</title><link>https://ex/rss1</link>"
    "<description>&lt;p&gt;Body one&lt;/p&gt;</description>"
    "<pubDate>Tue, 03 Jun 2026 14:00:00 GMT</pubDate></item>"
    "<item><title>Ancient</title><link>https://ex/old</link><description>old</description>"
    "<pubDate>Mon, 01 Jan 2018 00:00:00 GMT</pubDate></item>"
    "</channel></rss>"
)

_ATOM = (
    "<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><title>Blog</title>"
    "<entry><title>Atom One</title><link href='https://ex/atom1' rel='alternate'/>"
    "<summary>Atom body</summary><updated>2026-06-03T14:00:00Z</updated></entry></feed>"
)


def test_parse_rss():
    items = feeds.parse_feed(_RSS, "Pub")
    assert [i.title for i in items] == ["RSS One", "Ancient"]
    one = items[0]
    assert one.url == "https://ex/rss1"
    assert one.summary == "Body one"          # HTML stripped
    assert one.source == "Pub"
    assert one.published is not None and one.published.year == 2026


def test_parse_atom():
    items = feeds.parse_feed(_ATOM, "Blog")
    assert len(items) == 1
    assert items[0].url == "https://ex/atom1"  # href from rel=alternate
    assert items[0].summary == "Atom body"
    assert items[0].published is not None and items[0].published.year == 2026


def test_parse_garbage_is_empty():
    assert feeds.parse_feed("not xml at all", "x") == []
    assert feeds.parse_feed("", "x") == []


def test_harvest_excludes_ancient_keeps_undated():
    xml = (
        "<rss version='2.0'><channel>"
        "<item><title>Undated A</title><link>https://u/a</link></item>"
        "<item><title>Ancient</title><link>https://u/old</link>"
        "<pubDate>Mon, 01 Jan 2018 00:00:00 GMT</pubDate></item>"
        "<item><title>Undated B</title><link>https://u/b</link></item>"
        "</channel></rss>"
    )
    items = feeds.harvest([("Src", "https://feed")], since_hours=48, max_per_feed=10,
                          fetch=lambda url: xml)
    titles = [i.title for i in items]
    assert "Undated A" in titles and "Undated B" in titles
    assert "Ancient" not in titles          # >48h old → excluded


def test_harvest_caps_per_feed():
    xml = "<rss version='2.0'><channel>" + "".join(
        f"<item><title>It {i}</title><link>https://u/{i}</link></item>" for i in range(10)
    ) + "</channel></rss>"
    items = feeds.harvest([("Src", "https://feed")], since_hours=48, max_per_feed=3,
                          fetch=lambda url: xml)
    assert len(items) == 3


def test_harvest_skips_dead_feeds():
    items = feeds.harvest([("Dead", "https://x"), ("Dead2", "https://y")], fetch=lambda url: None)
    assert items == []


def test_harvest_ai_candidates_shape():
    xml = ("<rss version='2.0'><channel>"
           "<item><title>Cand</title><link>https://c/1</link>"
           "<description>desc</description></item></channel></rss>")
    cands = feeds.harvest_ai_candidates(max_per_feed=5, fetch=lambda url: xml)
    assert cands and all({"title", "summary", "source_url", "_source"} <= set(c) for c in cands)
    assert cands[0]["source_url"] == "https://c/1"
