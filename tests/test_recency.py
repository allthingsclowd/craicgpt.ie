"""Tests for the recency check — don't reheat the last few days' stories.

Before writing, the newsroom fetches the last ~6 published editions and builds
the set of story-keys already covered; curation drops any candidate that
collides. All offline — the JSON fetch is injected.
"""

from content_pipeline.research import recency


def test_prior_dates_are_the_six_days_before_newest_first():
    assert recency._prior_dates("2026-06-08", 6) == [
        "2026-06-07", "2026-06-06", "2026-06-05",
        "2026-06-04", "2026-06-03", "2026-06-02",
    ]


def test_published_edition_url_uses_cdn_content_path():
    url = recency.published_edition_url(
        "2026-06-08", base_url="https://craicgpt.ie", content_prefix="content")
    assert url == "https://craicgpt.ie/content/2026/06/08/paper_content.json"


def test_fetch_recent_editions_skips_missing_days():
    # Only two of the prior six days exist; the rest 404 (→ None) and are skipped.
    existing = {
        "https://craicgpt.ie/content/2026/06/07/paper_content.json": {"date": "2026-06-07"},
        "https://craicgpt.ie/content/2026/06/05/paper_content.json": {"date": "2026-06-05"},
    }
    eds = recency.fetch_recent_editions(
        "2026-06-08", days=6, fetch_json=lambda url: existing.get(url))
    assert [e["date"] for e in eds] == ["2026-06-07", "2026-06-05"]


def test_recent_story_keys_covers_every_section():
    edition = {
        "ai": {
            "headliner": {"title": "Head One", "source_url": "https://h/1"},
            "subarticles": [{"title": "Sub A", "source_url": "https://s/a"}],
            "shorts": [{"title": "Short X", "source_url": "https://x/1"}],
        },
        "fun": [{"title": "Fun Otters", "source_url": "https://f/1"}],
    }
    keys = recency.recent_story_keys([edition])
    assert "url:https://h/1" in keys and "title:head one" in keys
    assert "url:https://s/a" in keys      # subarticle
    assert "url:https://x/1" in keys      # short
    assert "url:https://f/1" in keys and "title:fun otters" in keys


def test_recent_keys_convenience_combines_fetch_and_extract():
    existing = {
        "https://craicgpt.ie/content/2026/06/07/paper_content.json": {
            "ai": {"headliner": {"title": "Yesterday Lead", "source_url": "https://y/1"}},
            "fun": [],
        },
    }
    keys = recency.recent_keys("2026-06-08", days=6, fetch_json=lambda url: existing.get(url))
    assert "url:https://y/1" in keys and "title:yesterday lead" in keys
