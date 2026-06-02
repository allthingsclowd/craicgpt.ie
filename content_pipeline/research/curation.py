"""
content_pipeline/research/curation.py
======================================
Deterministic curation mechanics shared by both research tracks.

The LLM decides *whether a story is fun*; this module does everything around
that decision that a plain function can do faster and more reliably:

- :func:`dedupe_stories`     — drop duplicate URLs and near-identical titles.
- :func:`is_excluded_by_keywords` — cheap pre-filter for the grim/political
  topics Graham explicitly wants kept off CraicGPT (death, war, elections …),
  so we don't spend tokens scoring stories we'd never run.
- :func:`select_diverse`     — pick the final N, spread across continents.
- :func:`validate_source_link` — confirm every published link actually resolves.

Per ``deciding-deterministic-vs-llm``: keep this layer out of the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Story model (internal; lightweight dataclass, not the LLM I/O schema)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Story:
    """A candidate story flowing through curation."""

    title: str
    summary: str
    source_url: str
    continent: Optional[str] = None
    score: float = 0.0
    tags: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Exclusion keywords — the "avoid the mundane reality of death and destruction"
# rule, plus politics. Tuned to be cheap, not exhaustive; the LLM is the real
# judge. Word-boundary matched to avoid e.g. "warm" matching "war".
# ─────────────────────────────────────────────────────────────────────────────
EXCLUSION_KEYWORDS: tuple[str, ...] = (
    # death / destruction
    "killed", "dead", "death", "dies", "died", "fatal", "massacre", "murder",
    "war", "bombing", "bomb", "shooting", "shooter", "terror", "terrorist",
    "earthquake", "flood", "wildfire", "famine", "genocide", "casualties",
    "crash", "disaster", "outbreak", "pandemic", "hostage", "kidnap",
    # politics
    "election", "senate", "parliament", "congress", "president", "minister",
    "tariff", "sanction", "impeach", "coup", "referendum", "ballot", "vote",
)

_EXCLUSION_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in EXCLUSION_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def is_excluded_by_keywords(story: Story) -> bool:
    """True if the story's title/summary hits a grim or political keyword."""
    haystack = f"{story.title} {story.summary}"
    return bool(_EXCLUSION_RE.search(haystack))


# ─────────────────────────────────────────────────────────────────────────────
# Dedupe
# ─────────────────────────────────────────────────────────────────────────────
def _normalise_title(title: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for comparison."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def dedupe_stories(stories: list[Story]) -> list[Story]:
    """Remove duplicate URLs and near-duplicate titles, keeping the best score.

    Two stories collide if they share a source URL OR normalise to the same
    title. Among colliding stories the highest ``score`` survives; original
    order is otherwise preserved.
    """
    best: dict[str, Story] = {}
    order: list[str] = []

    for story in stories:
        url_key = f"url:{story.source_url.strip().rstrip('/').lower()}"
        title_key = f"title:{_normalise_title(story.title)}"

        # Find an existing key this story collides with.
        collision = next((k for k in (url_key, title_key) if k in best), None)
        if collision is None:
            best[url_key] = story
            best[title_key] = story
            order.append(url_key)
        elif story.score > best[collision].score:
            # Replace the weaker survivor under both of its keys.
            prev = best[collision]
            for k, v in list(best.items()):
                if v is prev:
                    best[k] = story
            best[url_key] = story
            best[title_key] = story

    seen: set[int] = set()
    result: list[Story] = []
    for key in order:
        story = best[key]
        if id(story) not in seen:
            seen.add(id(story))
            result.append(story)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Diversity selection
# ─────────────────────────────────────────────────────────────────────────────
def select_diverse(stories: list[Story], n: int) -> list[Story]:
    """Pick ``n`` stories, highest-score-first but spread across continents.

    Round-robins one story per continent (each in descending score) before
    taking a second from any continent. When continents run out, the remaining
    slots are filled by pure score. Guarantees maximum continent spread while
    never preferring a low-scored story over a high one within a round.
    """
    by_continent: dict[str, list[Story]] = {}
    for story in sorted(stories, key=lambda s: s.score, reverse=True):
        by_continent.setdefault(story.continent or "", []).append(story)

    # Continents ordered by their best story's score (so the strongest leads).
    continents = sorted(
        by_continent,
        key=lambda c: by_continent[c][0].score,
        reverse=True,
    )

    picked: list[Story] = []
    while len(picked) < n and any(by_continent[c] for c in continents):
        for continent in continents:
            if not by_continent[continent]:
                continue
            picked.append(by_continent[continent].pop(0))
            if len(picked) == n:
                break
    return picked


# ─────────────────────────────────────────────────────────────────────────────
# Link validation
# ─────────────────────────────────────────────────────────────────────────────
def _default_fetch(url: str) -> int:
    """Return the HTTP status for ``url`` (HEAD, GET fallback). Stdlib only."""
    import urllib.request

    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "CraicGPT/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        # Some servers reject HEAD; retry once with GET before giving up.
        if exc.code in (403, 405):
            get = urllib.request.Request(url, headers={"User-Agent": "CraicGPT/1.0"})
            with urllib.request.urlopen(get, timeout=10) as resp:
                return resp.status
        return exc.code


def validate_source_link(url: str, *, fetch: Optional[Callable[[str], int]] = None) -> bool:
    """True if ``url`` resolves with a 2xx status.

    ``fetch`` is injectable for testing; it maps a URL to an HTTP status code
    and may raise on network failure (treated as invalid).
    """
    fetcher = fetch if fetch is not None else _default_fetch
    try:
        status = fetcher(url)
    except Exception:  # noqa: BLE001 — any fetch failure means "don't publish it"
        return False
    return 200 <= status < 300


# ─────────────────────────────────────────────────────────────────────────────
# The deterministic pipeline the harness runs over a researcher's candidates
# ─────────────────────────────────────────────────────────────────────────────
def curate_candidates(
    stories: list[Story],
    n: int,
    *,
    exclude: bool = True,
    fetch: Optional[Callable[[str], int]] = None,
) -> list[Story]:
    """Reduce raw candidate stories to the final ``n`` picks, deterministically.

    Order of operations (each step is its own tested function):
        1. drop grim/political stories (:func:`is_excluded_by_keywords`) — unless
           ``exclude`` is False;
        2. collapse duplicate URLs / near-identical titles
           (:func:`dedupe_stories`);
        3. if ``fetch`` is given, drop stories whose source link doesn't resolve
           (:func:`validate_source_link`);
        4. pick the final ``n`` spread across continents
           (:func:`select_diverse`).

    Args:
        stories: candidate stories collected by a researcher subagent.
        n: how many to keep.
        exclude: apply the grim/political keyword filter (default True).
        fetch: optional injectable HTTP-status fetcher for link validation; when
            None, links are NOT checked here (do it as a separate live step).
    """
    pool = [s for s in stories if not (exclude and is_excluded_by_keywords(s))]
    pool = dedupe_stories(pool)
    if fetch is not None:
        pool = [s for s in pool if validate_source_link(s.source_url, fetch=fetch)]
    return select_diverse(pool, n)
