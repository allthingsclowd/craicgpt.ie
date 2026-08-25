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
from content_pipeline.research.fun_sources import FUN_FEEDS

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
    views: Optional[int] = None  # YouTube media:statistics views — None when unstated


class _TransientFetch(Exception):
    """A retryable feed-fetch failure (timeout / 429 / 5xx) — distinct from a
    permanent one (404/403) which we don't bother retrying."""


# HTTP statuses worth a retry: rate-limit + transient server errors. A burst of
# ~30 youtube.com/feeds requests can momentarily trip 429 (the 2026-06-16 silent
# fun-desk collapse), and one retry with backoff recovers it instead of dropping
# the creator for the whole day.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _fetch_text_once(url: str) -> Optional[str]:
    """ONE fetch attempt. Returns text on 200; None on a PERMANENT failure
    (404/403/other non-200); raises :class:`_TransientFetch` on a retryable one
    (network error / 429 / 5xx)."""
    import httpx

    from content_pipeline.content_config import WEB_USER_AGENT

    try:
        r = httpx.get(url, timeout=12, follow_redirects=True, headers={
            "User-Agent": WEB_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        })
    except Exception as exc:  # noqa: BLE001 — network/TLS/timeout → retryable
        raise _TransientFetch(f"{type(exc).__name__}: {exc}") from exc
    if r.status_code == 200:
        return r.text
    if r.status_code in _RETRYABLE_STATUS:
        raise _TransientFetch(f"HTTP {r.status_code}")
    return None  # permanent (e.g. 404/403) — caller skips this feed


def _retrying_fetch(once, url: str, *, attempts: int = 3, base_delay: float = 1.0,
                    sleep=None) -> Optional[str]:
    """Retry ``once(url)`` on transient failures with exponential backoff, LOGGING
    each failure (so a feed never fails silently again). ``once`` returns text/None
    terminally and raises :class:`_TransientFetch` to signal a retry. Injectable
    ``once``/``sleep`` keep it unit-testable offline."""
    import time as _time

    sleep = sleep or _time.sleep
    for i in range(attempts):
        try:
            return once(url)  # 200 text OR permanent None — both terminal
        except _TransientFetch as exc:
            if i < attempts - 1:
                logger.warning("[feeds] transient fetch failure %s (%s) — retry %d/%d",
                               url, exc, i + 1, attempts - 1)
                sleep(base_delay * (2 ** i))
            else:
                logger.warning("[feeds] GAVE UP on %s after %d attempts: %s",
                               url, attempts, exc)
    return None


def _default_fetch_text(url: str) -> Optional[str]:
    """Fetch a feed over HTTPS with a browser UA, retrying transient failures.
    Non-200/permanent → None (the feed is skipped)."""
    return _retrying_fetch(_fetch_text_once, url)


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
        views: Optional[int] = None
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
        # YouTube nests <media:statistics views="N"> two levels down inside
        # <media:group><media:community> — grab it wherever it sits in the entry.
        for sub in node.iter():
            if _local(sub.tag) == "statistics" and sub.get("views"):
                try:
                    views = int(sub.get("views"))
                except ValueError:
                    views = None
                break
        url = url or (guid if guid.startswith("http") else "")
        if title and url:
            items.append(FeedItem(title=title, summary=summary[:500], url=url.strip(),
                                  source=source, published=_parse_dt(pub), views=views))
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
    failed: list[str] = []
    for source, url in feeds:
        parsed = parse_feed(fetcher(url) or "", source)
        if not parsed:
            failed.append(source)  # fetch failed OR feed returned nothing parseable
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
    if failed:
        # Name the dead/empty feeds — a silent collapse (2026-06-16: the comedian
        # roster vanished, leaving a motorcycle-only "comedy" desk) must be visible.
        logger.warning("[feeds] %d/%d feeds returned NO items: %s",
                       len(failed), len(feeds), failed)
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


# Graham's freshness rule (2026-06-11): prefer the last 24 h; widen only when the
# pool is thin (weekends are quieter). The pool target is what makes "thin" concrete:
# enough candidates that CHOOSING the day's five is the hard part.
FUN_FRESHNESS_LADDER_HOURS: tuple[int, ...] = (24, 48, 96)
FUN_MIN_POOL = 8


def harvest_fun_candidates(*, since_hours: Optional[int] = None, max_per_feed: int = 2,
                           fetch: Optional[FetchText] = None,
                           feeds_list: Optional[list] = None,
                           min_pool: Optional[int] = None) -> list[dict]:
    """Harvest the curated creator feeds as fun-candidate dicts ready to merge into
    the fun desk pool: ``{title, summary, source_url, source, _creator, _views}``.

    Freshness ladder (Graham, 2026-06-11): one fetch pass over the widest window,
    then client-side banding — keep the 24 h band if it already holds ``min_pool``
    candidates, else widen to 48 h, then 96 h. Passing ``since_hours`` explicitly
    pins a single window instead (legacy/operator use). Within the chosen band the
    candidates are RANKED by YouTube view count (highest first; unstated views keep
    feed order at the back) so curation picks the most-watched fresh items.

    Press feeds are keyword-filtered: ``fun_sources.FUN_FEED_FILTERS`` maps a source
    name to a required keyword (e.g. the bike-press RSS only contributes Honda
    items); creator channels pass through unfiltered.

    ATTRIBUTION (Graham's hard rule): ``source_url`` is the creator's own video URL
    (straight from the feed entry — never invented), and ``source`` carries the
    CREATOR'S NAME so it can be stamped onto the published piece as the credit. We
    also mirror the name into ``_creator`` (an internal hint) so the editor can
    thread the credit through curation, which otherwise keeps only title / summary /
    url on its ``Story`` objects. ``max_per_feed`` defaults to 2 (a creator uploads a
    handful a week — we only want their freshest), so no single creator dominates.
    """
    from content_pipeline.research.fun_sources import (
        FUN_FEED_FILTERS, MOTO_EXCLUDE_TERMS, is_moto_source,
    )

    ladder = (since_hours,) if since_hours is not None else FUN_FRESHNESS_LADDER_HOURS
    target = FUN_MIN_POOL if min_pool is None else min_pool
    items = harvest(feeds_list if feeds_list is not None else FUN_FEEDS,
                    since_hours=ladder[-1], max_per_feed=max_per_feed, fetch=fetch)

    # Press feeds contribute only their keyword matches (title or summary), and a moto
    # source never contributes a CAR story: several bike outlets also cover Honda's cars
    # and EVs, and "honda" alone lets a Civic review into a motorcycle desk.
    def _passes(it: FeedItem) -> bool:
        text = f"{it.title} {it.summary}".lower()
        kw = FUN_FEED_FILTERS.get(it.source)
        if kw and kw.lower() not in text:
            return False
        if is_moto_source(it.source) and any(t in text for t in MOTO_EXCLUDE_TERMS):
            logger.info("[feeds] dropped car story from moto source %s: %s", it.source, it.title)
            return False
        return True

    items = [it for it in items if _passes(it)]

    # Band: the narrowest ladder rung whose pool meets the target (else the widest).
    now = datetime.now(timezone.utc)
    band = items
    for hours in ladder:
        cutoff = now - timedelta(hours=hours)
        rung = [it for it in items if it.published is None or it.published >= cutoff]
        if len(rung) >= target or hours == ladder[-1]:
            band = rung
            if hours != ladder[0]:
                logger.info("[feeds] fun pool thin at %dh — widened to %dh (%d items)",
                            ladder[0], hours, len(rung))
            break

    # CB1000GT bias (Graham, 2026-06-16): the new Honda sports-tourer just landing in
    # the UK leads the moto slice. Tier 0 = an explicit CB1000GT mention, tier 1 = the
    # wider CB1000 family, tier 2 = everything else; within a tier, most-watched first
    # (unstated views to the back).
    def _cb_rank(it: FeedItem) -> int:
        text = f"{it.title} {it.summary}".lower()
        if "cb1000gt" in text or "cb1000 gt" in text:
            return 0
        if "cb1000" in text:
            return 1
        return 2

    band = sorted(band, key=lambda it: (_cb_rank(it), it.views is None, -(it.views or 0)))

    return [
        {"title": it.title, "summary": it.summary, "source_url": it.url,
         "source": it.source, "_creator": it.source, "_views": it.views}
        for it in band
    ]
