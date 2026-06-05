"""
content_pipeline/research/fun_sources.py
========================================
Curated Irish-creator registry — the fun desk's primary source pool.

Graham's call (June 2026): the fun section becomes an **Irish-creator digest**.
Instead of trawling the open web for "good news" (which the agentic researcher
under-gathered and occasionally fabricated, see the 2026-06-04 HOLD), we harvest
the *recent uploads* of a hand-picked roster of Irish comedians, sketch groups,
streamers and gift shops. Every one publishes a free, dated YouTube Atom feed —
real URLs, fresh items daily, no LLM under-searching, no 429s. Exactly the model
this codebase prefers (``deciding-deterministic-vs-llm``). Harvested items SEED
the fun candidate pool; the writer then rewrites each in Graham's house voice and
the same validate / recency / floor pipeline applies.

ATTRIBUTION (Graham's hard rule): **credit the creator**. Each item's
``source_url`` is the creator's own video URL (straight from their feed — never
invented), and the creator's NAME is carried onto the published piece as the
credit/byline. We riff on their recent upload in the Scripting Paddy's voice; we
do NOT impersonate the creator, and we always point readers back to the original.

Each entry is ``(creator_name, feed_url)`` — same shape as ``ai_sources.AI_FEEDS``.
The URLs are YouTube channel Atom feeds (``?channel_id=`` form). Dead/changed
feeds are skipped at runtime (best-effort), so a stale URL degrades gracefully.
The set below was verified to return entries at build time.
"""

from __future__ import annotations

# ── Sketch / comedy groups ─────────────────────────────────────────────────────────
_GROUPS: list[tuple[str, str]] = [
    ("Foil Arms and Hog", "https://www.youtube.com/feeds/videos.xml?channel_id=UCzb-6smlTg5UPirLdsdQ_cQ"),
    ("The 2 Johnnies", "https://www.youtube.com/feeds/videos.xml?channel_id=UCEoAZQQeiUUSDycxk8FpT9w"),
]

# ── Stand-ups, sketch makers & character comedians ────────────────────────────────
_COMEDIANS: list[tuple[str, str]] = [
    ("Sir Stevo Timothy", "https://www.youtube.com/feeds/videos.xml?channel_id=UC2hgRzkWZmGkigghCUXDzVA"),
    ("Darren Conway", "https://www.youtube.com/feeds/videos.xml?channel_id=UCu8gOe5Yji7CP3SsYt_N1ag"),
    ("Enya Martin (Giz a Laugh)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCDHeLXnlxW9umjunqdDUD2g"),
    ("Tadhg Fleming", "https://www.youtube.com/feeds/videos.xml?channel_id=UCs1VCnBrIBgeoyEqULhVRaA"),
    ("Eoin Ruane (JaffaMan)", "https://www.youtube.com/feeds/videos.xml?channel_id=UC4BzcTBYXWoySWpskq3GGiA"),
    ("Michael Fry", "https://www.youtube.com/feeds/videos.xml?channel_id=UCW6sLbjZBlnjHOlvJxvatUw"),
    ("Clisare", "https://www.youtube.com/feeds/videos.xml?channel_id=UC4zJAMaYN592qQhMR2OfX_Q"),
    ("Killian Sundermann", "https://www.youtube.com/feeds/videos.xml?channel_id=UCDzyKW-ROqsUB5zcnnlr0rw"),
    ("Tommy Tiernan", "https://www.youtube.com/feeds/videos.xml?channel_id=UCWfX0nD5LDx0rvxHUWWWQUw"),
    ("Joanne McNally", "https://www.youtube.com/feeds/videos.xml?channel_id=UCDqGzmXLXY6ThhYeDUhtrSQ"),
    ("Dara O Briain", "https://www.youtube.com/feeds/videos.xml?channel_id=UCuT05VACCGW5L7yLE8JRF9Q"),
    ("Graham Norton", "https://www.youtube.com/feeds/videos.xml?channel_id=UC4PziMH5MvvsmqM0VCZTy-g"),
    ("Chris Kent", "https://www.youtube.com/feeds/videos.xml?channel_id=UCMkiptOA5pvabk0xRXkFO5g"),
    ("Emma Doran", "https://www.youtube.com/feeds/videos.xml?channel_id=UCGIahMu72QcVerSNto3QLJg"),
    ("Jason Byrne", "https://www.youtube.com/feeds/videos.xml?channel_id=UC5zWtDx_hWs0_M6ujl-lAAQ"),
    ("Vittorio Angelone", "https://www.youtube.com/feeds/videos.xml?channel_id=UC8Z9r-XcBZUlAi_S3UeRnGA"),
    ("Shane Todd", "https://www.youtube.com/feeds/videos.xml?channel_id=UCVV37nPgufHvyB3wrEmFDlQ"),
    ("Neil Delamere", "https://www.youtube.com/feeds/videos.xml?channel_id=UCCgHSZq5REE2OuxB0a-htkQ"),
    ("Gearoid Farrelly", "https://www.youtube.com/feeds/videos.xml?channel_id=UCi9DBEkHZbKStUFCGM35SWA"),
]

# ── Streamers / gaming creators ─────────────────────────────────────────────────
_STREAMERS: list[tuple[str, str]] = [
    ("Jacksepticeye", "https://www.youtube.com/feeds/videos.xml?channel_id=UCYzPXprvl5Y-Sf0g4vX-m6g"),
    ("RTGame", "https://www.youtube.com/feeds/videos.xml?channel_id=UCRC6cNamj9tYAO6h_RXd5xA"),
    ("CallMeKevin", "https://www.youtube.com/feeds/videos.xml?channel_id=UCdoPCztTOW7BJUPk2h5ttXA"),
    ("Daithi De Nogla", "https://www.youtube.com/feeds/videos.xml?channel_id=UCvPW1W4WlpTgNezZzwIstLA"),
]

# ── Irish brands with a sense of humour (gift shops / merch) ──────────────────────
_BRANDS: list[tuple[str, str]] = [
    ("Hairy Baby", "https://www.youtube.com/feeds/videos.xml?channel_id=UCl_Gar3QS2Sd1HU2fQOAr3Q"),
    ("The Irish Store", "https://www.youtube.com/feeds/videos.xml?channel_id=UCFOAMZcgYEcKSUgWSUunhJg"),
    ("Carroll's Irish Gifts", "https://www.youtube.com/feeds/videos.xml?channel_id=UCnnTFBblVHEHzKeR7TqiEJw"),
]

# The full harvest set. Order doesn't matter — harvest caps per-feed and the
# curation step picks the final N afterwards.
FUN_FEEDS: list[tuple[str, str]] = _GROUPS + _COMEDIANS + _STREAMERS + _BRANDS
