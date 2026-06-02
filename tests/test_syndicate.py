"""Tests for social-post generation (the agents post this after publishing)."""

from content_pipeline.social.syndicate import build_posts


def _paper():
    return {
        "date": "2026-06-02",
        "ai": {"headliner": {"title": "NVIDIA Vera Rubin: The AI Factory is Open",
                             "image_url": "https://craicgpt.ie/content/2026/06/02/images/h.png"}},
        "fun": [{"title": "TEENS SMASH IT! Tamarind Power DESTROYS Plastic!", "persona": "Ronald Dump"}],
    }


def test_build_posts_has_all_platforms_with_link_and_image():
    posts = build_posts(_paper(), site="https://craicgpt.ie")
    assert {"x", "mastodon", "bluesky"} <= set(posts)
    for p in ("x", "mastodon", "bluesky"):
        assert "craicgpt.ie" in posts[p]
        assert "NVIDIA Vera Rubin" in posts[p]
    assert posts["image_url"].endswith("h.png")


def test_x_post_within_280_chars():
    posts = build_posts(_paper())
    assert len(posts["x"]) <= 280


def test_handles_missing_fun_or_image():
    posts = build_posts({"ai": {"headliner": {"title": "Just AI today"}}, "fun": []})
    assert "Just AI today" in posts["x"]
    assert posts["image_url"] is None
