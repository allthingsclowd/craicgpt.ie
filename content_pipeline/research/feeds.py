"""
content_pipeline/research/feeds.py
==================================
Deterministic discovery of recent AI items from a curated set of RSS/Atom feeds.

Why feeds, not just search: the agentic web-search researcher under-gathered (7
candidates vs the 13 target on 2026-06-04), which — with the never-fabricate
floor — risks a chronically-held, stale site. Curated source feeds (lab/company
news, publications, Substacks, arXiv) are deterministic: real dated URLs, dozens
of fresh items daily, no LLM under-searching, no 429s. That's exactly the model
this codebase prefers (``deciding-deterministic-vs-llm``). Harvested items SEED
the AI candidate pool; the LLM then ranks + writes (its strength), and the same
validate / recency / floor pipeline applies.

Stdlib only (``xml.etree``) — no new dependency. Network I/O is injected as
``fetch`` so this is unit-testable offline. Dead or garbled feeds are skipped
(best-effort), so a stale URL degrades gracefully rather than erroring.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional
from xml.etree import ElementTree as ET

from content_pipeline.research.ai_sources import AI_FEEDS

logger = logging.getLogger(__name__)

# ``url -> raw feed XML text`` (or None if the feed is missing / unreachable).
FetchText = Callable[[str], Optional[str]]


@dataclass
class FeedItem:
    """One entry parsed from a feed."""

    title: str
    summary: str
    url: str
    source: str
    published: Optional[datetime] = None


def _default_fetch_text(url: str) -> Optional[str]:
    """Fetch a feed over HTTPS with a browser UA. Non-200/error → None (skip)."""
    import httpx

    from content_pipeline.content_config import WEB_USER_AGENT

    try:
        r = httpx.get(url, timeout=12, follow_redirects=True, headers={
            "User-Agent": WEB_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        })
        return r.text if r.status_code == 200 else None
    except Exception:  # noqa: BLE001 — dead feed / network / TLS → treat as absent
        return None


def _local(tag: str) -> str:
    """Strip an XML namespace: ``{http://www.w3.org/2005/Atom}entry`` -> ``entry``."""
    return tag.rsplit("}", 1)[-1].lower()


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _parse_dt(s: str) -> Optional[datetime]:
    """Parse an RSS (RFC822) or Atom (ISO8601) date to an aware UTC datetime."""
    s = (s or "").strip()
    if not s:
        return None
    try:  # RSS pubDate, e.g. 'Tue, 03 Jun 2026 14:00:00 GMT'
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:  # Atom updated/published, e.g. '2026-06-03T14:00:00Z'
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_feed(xml_text: str, source: str) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom into FeedItems (tolerant, namespace-agnostic)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[FeedItem] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):  # RSS <item> / Atom <entry>
            continue
        title = summary = url = guid = pub = ""
        for child in node:
            t = _local(child.tag)
            if t == "title":
                title = _text(child)
            elif t in ("description", "summary", "content") and not summary:
                summary = _strip_html(_text(child))
            elif t == "link":
                href, rel = child.get("href"), (child.get("rel") or "alternate").lower()
                if href and rel == "alternate":
                    url = href
                elif href and not url:
                    url = href
                elif _text(child):
                    url = _text(child)
            elif t == "guid" and not guid:
                guid = _text(child)
            elif t in ("pubdate", "published", "updated", "date") and not pub:
                pub = _text(child)
        url = url or (guid if guid.startswith("http") else "")
        if title and url:
            items.append(FeedItem(title=title, summary=summary[:500],
                                  url=url.strip(), source=source, published=_parse_dt(pub)))
    return items


def harvest(feeds: Optional[list] = None, *, since_hours: int = 48,
            max_per_feed: int = 4, fetch: Optional[FetchText] = None) -> list[FeedItem]:
    """Fetch + parse the curated feeds; return recent items (best-effort).

    Items newer than ``since_hours`` are kept; undated items are kept (up to
    ``max_per_feed``, assuming feeds list newest-first). Each feed contributes at
    most ``max_per_feed`` items. Dead/garbled feeds are skipped."""
    feeds = feeds if feeds is not None else AI_FEEDS
    fetcher = fetch or _default_fetch_text
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    out: list[FeedItem] = []
    ok_feeds = 0
    for source, url in feeds:
        parsed = parse_feed(fetcher(url) or "", source)
        if not parsed:
            continue
        ok_feeds += 1
        kept = 0
        for it in parsed:
            if it.published is not None and it.published < cutoff:
                continue
            out.append(it)
            kept += 1
            if kept >= max_per_feed:
                break
    logger.info("[feeds] harvested %d items from %d/%d feeds (last %dh)",
                len(out), ok_feeds, len(feeds), since_hours)
    return out


def harvest_ai_candidates(*, since_hours: int = 48, max_per_feed: int = 4,
                          fetch: Optional[FetchText] = None) -> list[dict]:
    """Harvest the curated AI feeds as AI-candidate dicts ready to merge into the
    AI desk pool: ``{title, summary, source_url, _source}``."""
    return [
        {"title": it.title, "summary": it.summary, "source_url": it.url, "_source": it.source}
        for it in harvest(since_hours=since_hours, max_per_feed=max_per_feed, fetch=fetch)
    ]
