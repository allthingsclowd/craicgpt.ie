"""
content_pipeline/research/recency.py
=====================================
Avoid republishing the same stories two days running.

Before writing a new edition the newsroom fetches the last few *published*
editions from the live site and builds the set of story-keys (normalised source
URL + normalised title) already covered. Curation then drops any candidate that
collides — so the day's headliner and stories are fresh, not yesterday's reheated.

Deterministic + best-effort: a missing day (fewer than N editions exist yet) or a
fetch error is a quiet skip, never a block on generation. Network I/O is injected
as ``fetch_json`` so this is unit-testable offline. The public CDN URL is used
(no AWS creds needed) so it works the same on .75 as anywhere.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.research.curation import story_key_set

logger = logging.getLogger(__name__)

# ``url -> parsed JSON dict`` (or None if the day is missing / unreadable).
FetchJson = Callable[[str], Optional[dict]]


def published_edition_url(date_iso: str, *, base_url: Optional[str] = None,
                          content_prefix: Optional[str] = None) -> str:
    """The public URL of a published edition's JSON (mirrors cli._load_edition)."""
    base = (base_url or content_cfg.site_base_url).rstrip("/")
    prefix = content_prefix or content_cfg.content_prefix
    y, m, d = date_iso.split("-")
    return f"{base}/{prefix}/{y}/{m}/{d}/paper_content.json"


def _default_fetch_json(url: str) -> Optional[dict]:
    """Fetch + parse a published edition over HTTPS with a browser UA. Any
    non-200 / network error / parse failure → None (the day is treated as absent)."""
    import httpx

    from content_pipeline.content_config import WEB_USER_AGENT

    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": WEB_USER_AGENT})
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001 — missing day / network / parse → absent
        return None


def _prior_dates(date_iso: str, days: int) -> list[str]:
    """The ``days`` ISO dates immediately BEFORE ``date_iso`` (newest first)."""
    y, m, d = (int(x) for x in date_iso.split("-"))
    start = date(y, m, d)
    return [(start - timedelta(days=i)).isoformat() for i in range(1, days + 1)]


def fetch_recent_editions(date_iso: str, *, days: int = 6,
                          fetch_json: Optional[FetchJson] = None) -> list[dict]:
    """Fetch up to ``days`` published editions immediately before ``date_iso``.

    Missing days (404 / not-yet-published) are skipped, so this returns however
    many of the last ``days`` editions actually exist (newest first)."""
    fetch = fetch_json or _default_fetch_json
    out: list[dict] = []
    for d_iso in _prior_dates(date_iso, days):
        data = fetch(published_edition_url(d_iso))
        if isinstance(data, dict):
            out.append(data)
    return out


def _edition_items(edition: dict) -> list[dict]:
    """Every story-bearing item in a published edition (headliner, subarticles,
    shorts, fun) — the things that carry a title + source_url."""
    ai = edition.get("ai") or {}
    items: list[dict] = []
    head = ai.get("headliner")
    if isinstance(head, dict):
        items.append(head)
    for section in (ai.get("subarticles"), ai.get("shorts"), edition.get("fun")):
        for it in section or []:
            if isinstance(it, dict):
                items.append(it)
    return items


def recent_story_keys(editions: list[dict]) -> set[str]:
    """Union of story-keys (normalised url + title) across the given editions."""
    keys: set[str] = set()
    for ed in editions or []:
        for it in _edition_items(ed):
            keys |= story_key_set(it.get("title", ""), it.get("source_url", ""))
    return keys


def recent_keys(date_iso: str, *, days: int = 6,
                fetch_json: Optional[FetchJson] = None) -> set[str]:
    """Convenience: fetch the last ``days`` editions and return their story-keys."""
    return recent_story_keys(fetch_recent_editions(date_iso, days=days, fetch_json=fetch_json))
