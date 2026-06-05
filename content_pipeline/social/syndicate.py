"""
content_pipeline/social/syndicate.py
====================================
Generate per-platform social posts from a published edition.

After the approving-craicgpt-editions agents publish the live edition, they post
an update to the channels. This builds the platform-tailored copy deterministically
(headliner + a fun-story teaser + the link + the headliner image); the agents post
it via their own channel tools (Bluesky / Mastodon / X). Pure / offline.
"""

from __future__ import annotations

from typing import Any, Optional


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_posts(paper: dict[str, Any], *, site: str = "https://craicgpt.ie") -> dict[str, Optional[str]]:
    """Return ``{x, mastodon, bluesky, image_url}`` ready for the agents to post.

    - ``x`` is capped at 280 chars.
    - ``mastodon`` / ``bluesky`` get a slightly longer form + hashtags.
    - ``image_url`` is the headliner image (or None).
    """
    headliner = (paper.get("ai") or {}).get("headliner") or {}
    title = headliner.get("title", "Today's edition")
    image_url = headliner.get("image_url")

    fun = paper.get("fun") or []
    teaser = ""
    if fun:
        f = fun[0]
        persona = f.get("persona")
        teaser = f" Plus {f.get('title', '')}" + (f" (as told by {persona})" if persona else "")

    x = _trim(f"📰 {title}.{teaser} — today on The Craic Gazette. {site}", 280)
    long = (
        f"📰 The Craic Gazette — {title}.{teaser}\n\n"
        f"Ireland's funniest + what actually changed in AI, written overnight "
        f"by open-source models. No humans in the loop, no doom in the feed.\n{site}\n\n"
        f"#AI #GoodNews #Ireland"
    )
    return {
        "x": x,
        "mastodon": _trim(long, 500),
        "bluesky": _trim(long, 300),
        "image_url": image_url,
    }
