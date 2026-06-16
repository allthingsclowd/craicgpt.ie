"""
content_pipeline/research/fun_sources.py
========================================
Curated creator registry — the Craic & Throttle desk's primary source pool.

Graham's calls: June 2026 — the fun section becomes a creator digest (harvest a
hand-picked roster's recent uploads instead of trawling the open web, which
under-gathered and occasionally fabricated, see the 2026-06-04 HOLD). 2026-06-11 —
the roster EXPANDS beyond Irish creators: **British comedians (with a deliberate
bias for female comedians)** and **ALL things Honda motorcycles** (official Honda
moto channels + UK bike-press RSS keyword-filtered to Honda). Every source
publishes a free, dated RSS/Atom feed — real URLs, fresh items daily, no LLM
under-searching, no 429s. Exactly the model this codebase prefers
(``deciding-deterministic-vs-llm``). Harvested items SEED the fun candidate pool;
the writer then rewrites each in Graham's house voice and the same validate /
recency pipeline applies (the desk count is a target, never a floor).

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
# ── British comedians — FEMALE-FIRST (Graham's 2026-06-11 bias) ───────────────────
# Acts with no active personal channel are covered by their OFFICIAL podcast/show
# channel (credit the channel name — it IS the creator credit). All feeds verified
# live 2026-06-11 (HTTP 200, entries present, recent uploads).
_BRIT_FEMALE_COMEDIANS: list[tuple[str, str]] = [
    ("Sarah Millican", "https://www.youtube.com/feeds/videos.xml?channel_id=UCsJd3oh_1pgv5gN7DwYxwqQ"),
    ("Katherine Ryan", "https://www.youtube.com/feeds/videos.xml?channel_id=UCtn5D6gXAzr5mRkuNwbJPtg"),
    ("Rosie Jones", "https://www.youtube.com/feeds/videos.xml?channel_id=UCsqXEi_M22X6seJM2yTS0VA"),
    ("Ignore That Feeling (Fern Brady & Alison Spittle)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCtVUDIntTxokVtpV7GWXf0g"),
    ("Big Kick Energy (Maisie Adam & Suzi Ruffell)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCMgOyzY6h6JjhSLQCdAV10w"),
    ("Catherine Bohart", "https://www.youtube.com/feeds/videos.xml?channel_id=UCw9a6NNBtjzXpM8_AloWLPQ"),
]

# ── British comedy — shows, podcasts & the lads ────────────────────────────────────
_BRIT_COMEDY: list[tuple[str, str]] = [
    ("Taskmaster", "https://www.youtube.com/feeds/videos.xml?channel_id=UCT5C7yaO3RVuOgwP8JVAujQ"),
    ("Off Menu (Ed Gamble & James Acaster)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCgFAyHxA0MBioGICaiU6amA"),
    ("Michael McIntyre", "https://www.youtube.com/feeds/videos.xml?channel_id=UCUFrBvQ96A-KeU6NgpemQXA"),
    ("Romesh Ranganathan", "https://www.youtube.com/feeds/videos.xml?channel_id=UCxXd7HRiscuMWX3tlkjBHxA"),
    ("The Romesh Ranganathan Show", "https://www.youtube.com/feeds/videos.xml?channel_id=UClEwNmkntT7j4aNTBHBLNug"),
    ("Live At The Apollo", "https://www.youtube.com/feeds/videos.xml?channel_id=UCodptbjdNf75jEmin8sFZrg"),
    ("BBC Comedy Greats", "https://www.youtube.com/feeds/videos.xml?channel_id=UC7foTxErVJKorAitAcJuqDA"),
]

# ── Honda motorcycles — official channels (Graham rides these) ─────────────────────
# NB: the real Honda UK channel is "HondaVideo" (mixed cars+bikes → keyword-filtered
# below); the @hondaukmootorcycles channel claiming "Official Honda UK Motorcycles"
# is an impersonator/clip-farm — verified and rejected 2026-06-11.
_HONDA_MOTO: list[tuple[str, str]] = [
    ("Honda Motorcycles Europe", "https://www.youtube.com/feeds/videos.xml?channel_id=UCEIR3GF5KiYoOVLIWCTnX-w"),
    ("Honda UK", "https://www.youtube.com/feeds/videos.xml?channel_id=UC2AZ6JaAKk9n5CjBOPUCh7A"),
    ("Honda Racing HRC", "https://www.youtube.com/feeds/videos.xml?channel_id=UCmG3C3Z2IVZmsj8yj7PJljA"),
    ("Honda Powersports", "https://www.youtube.com/feeds/videos.xml?channel_id=UCg5wc0GIeSaBlKBOSD5MWVw"),
]

# ── Bike press (general feeds — Honda items only, via FUN_FEED_FILTERS) ────────────
# Diversified 2026-06-16 (was MoreBikes-heavy): adding verified outlets so the moto
# slice never collapses to one feed and carries strong Honda / CB1000GT coverage.
# All URLs verified to return 200 + Honda items at build time; MCN 301-redirects to
# its live RSS (httpx follow_redirects handles it).
_BIKE_PRESS: list[tuple[str, str]] = [
    ("MCN", "https://www.motorcyclenews.com/news/rss/"),
    ("Visordown", "https://www.visordown.com/rss"),
    ("Superbike News", "https://superbike-news.co.uk/feed/"),
    ("MoreBikes", "https://www.morebikes.co.uk/feed/"),
    ("RideApart", "https://www.rideapart.com/rss/articles/all/"),
    ("Adventure Bike Rider", "https://www.adventurebikerider.com/feed/"),
    ("Devitt", "https://www.devittinsurance.com/blog/feed/"),
]

# ── Comedian blogs with live RSS (rare beasts) ─────────────────────────────────────
_COMEDY_BLOGS: list[tuple[str, str]] = [
    ("Stewart Lee", "https://www.stewartlee.co.uk/feed/"),
    ("Sarah Millican's blog", "https://sarahmillican.co.uk/feed/"),
]

# Press feeds are GENERAL outlets — only their keyword matches may enter the fun
# pool (source name -> required keyword, matched case-insensitively against
# title+summary). Creator channels are never filtered; Honda UK's mixed cars+bikes
# channel only contributes its motorcycle uploads.
FUN_FEED_FILTERS: dict[str, str] = {
    "MCN": "honda",
    "Visordown": "honda",
    "Superbike News": "honda",
    "MoreBikes": "honda",
    "RideApart": "honda",
    "Adventure Bike Rider": "honda",
    "Devitt": "honda",
    "Honda UK": "motorcycle",
}

# curation step picks the final N afterwards.
FUN_FEEDS: list[tuple[str, str]] = (
    _GROUPS + _COMEDIANS + _STREAMERS + _BRANDS
    + _BRIT_FEMALE_COMEDIANS + _BRIT_COMEDY
    + _HONDA_MOTO + _BIKE_PRESS + _COMEDY_BLOGS
)

# CB1000GT bias (Graham, 2026-06-16): the new Honda sports-tourer arriving in the UK
# this year — boost it to the top of the moto slice. Used by feeds.harvest_fun_candidates.
CB1000GT_KEYWORDS: tuple[str, ...] = ("cb1000gt", "cb1000 gt", "cb1000")

# NON-COMEDY sources = the motorcycle outlets/brands (press + Honda channels). Used to
# detect when the fun desk has lost its COMEDIAN/creator content and shipped a
# motorcycle-only "comedy" desk (the 2026-06-16 silent collapse) → alert, don't ship quietly.
NON_COMEDY_SOURCES: frozenset[str] = frozenset(
    {name for name, _ in _BIKE_PRESS} | {name for name, _ in _HONDA_MOTO}
)


def is_comedy_source(name: str | None) -> bool:
    """True if a published fun item's credit is a comedian/creator (not a bike
    outlet/brand). Press + Honda-channel credits are motorcycle filler, not comedy."""
    return bool(name) and name not in NON_COMEDY_SOURCES


def fun_desk_alert(fun_items: list[dict] | None, date_iso: str) -> str | None:
    """Return an alert string when the fun desk shipped with NO comedian/creator
    items (motorcycle/press only) — the 2026-06-16 silent collapse — else None. The
    fun desk has no count floor (it publishes thin on purpose), so this is how a
    creators-missing edition gets surfaced instead of shipping quietly."""
    items = fun_items or []
    if any(is_comedy_source((f or {}).get("source")) for f in items):
        return None
    return (f"🎭 CraicGPT fun desk — NO comedian items for {date_iso}: the comedy/"
            f"creator feeds produced nothing; the desk shipped {len(items)} motorcycle/"
            f"press item(s) only. Likely a transient feed-harvest failure — check the "
            f"[feeds] WARN logs for skipped feeds.")
