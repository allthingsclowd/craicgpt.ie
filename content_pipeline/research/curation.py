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
    category: Optional[str] = None
    # The creator/source NAME (e.g. an Irish YouTuber for the fun desk). Carried
    # so :func:`select_diverse` can spread the picks one-per-creator — without it
    # two uploads from the same creator can both win and the desk reads thin.
    creator: Optional[str] = None


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


def story_key_set(title: str, source_url: str) -> set[str]:
    """The dedupe/recency keys for a story: its normalised URL and normalised title.

    Mirrors the keying :func:`dedupe_stories` uses internally, exposed so the
    recency check (see :mod:`content_pipeline.research.recency`) can build the set
    of already-published keys and curation can drop any candidate that collides.
    """
    keys: set[str] = set()
    url = (source_url or "").strip().rstrip("/").lower()
    if url:
        keys.add(f"url:{url}")
    title_norm = _normalise_title(title or "")
    if title_norm:
        keys.add(f"title:{title_norm}")
    return keys


# ─────────────────────────────────────────────────────────────────────────────
# Diversity selection
# ─────────────────────────────────────────────────────────────────────────────
def select_diverse(
    stories: list[Story],
    n: int,
    *,
    key: Optional[Callable[[Story], str]] = None,
) -> list[Story]:
    """Pick ``n`` stories, highest-score-first but spread across a diversity axis.

    Round-robins one story per bucket (each in descending score) before taking a
    second from any bucket. When buckets run out, the remaining slots are filled
    by pure score. Guarantees maximum spread while never preferring a low-scored
    story over a high one within a round.

    ``key`` chooses the diversity axis. Defaults to **continent** (the AI desk's
    geographic spread); the fun desk passes a per-**creator** key so a single
    Irish creator's two uploads never both land in one edition.
    """
    bucket_of = key or (lambda s: s.continent or "")
    by_bucket: dict[str, list[Story]] = {}
    for story in sorted(stories, key=lambda s: s.score, reverse=True):
        by_bucket.setdefault(bucket_of(story) or "", []).append(story)

    # Buckets ordered by their best story's score (so the strongest leads).
    buckets = sorted(
        by_bucket,
        key=lambda b: by_bucket[b][0].score,
        reverse=True,
    )

    picked: list[Story] = []
    while len(picked) < n and any(by_bucket[b] for b in buckets):
        for bucket in buckets:
            if not by_bucket[bucket]:
                continue
            picked.append(by_bucket[bucket].pop(0))
            if len(picked) == n:
                break
    return picked


# ─────────────────────────────────────────────────────────────────────────────
# Link validation
# ─────────────────────────────────────────────────────────────────────────────
def _default_fetch(url: str) -> int:
    """Return the HTTP status for ``url`` (HEAD, GET fallback). Stdlib only.

    Returns the status CODE for HTTP errors (403/404/429/…) instead of raising, so the
    caller can apply a status policy. Only true network failures (DNS / refused /
    timeout) raise.
    """
    import urllib.request

    from content_pipeline.content_config import WEB_USER_AGENT

    def _status(method: str) -> int:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": WEB_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    status = _status("HEAD")
    # Some servers reject HEAD with 403/405 but serve GET — retry once with GET.
    if status in (403, 405):
        status = _status("GET")
    return status


# A host that EXISTS but blocks/limits the bot (auth, bot-detection, method, rate-limit)
# answers with these — they do NOT mean "the URL doesn't exist", so they count as reachable.
# Only 404/410 (invented / removed) are the fabrication signal we must keep failing.
_UNREACHABLE_STATUS = frozenset({404, 410})


def validate_source_link(url: str, *, fetch: Optional[Callable[[str], int]] = None,
                         attempts: int = 2) -> bool:
    """True if ``url`` is REACHABLE — i.e. the source genuinely exists.

    Reachable = the host answered with anything other than 404/410 (a 2xx/3xx, or a
    bot-block / rate-limit / auth / server-error — the host is real, just hostile to a
    bot). Unreachable = 404/410 (invented or removed), or a persistent network failure
    (DNS / refused / timeout) across ``attempts``. A one-off transient error is retried,
    so the gate's ~18-link burst can't falsely HOLD a valid edition on a single 429/timeout
    (the 2026-06-07 cybersecuritydive false-hold). NOT an allowlist: an invented URL still
    404s and fails. The SAME function backs generation and the publish gate, so they agree.

    ``fetch`` is injectable for tests (maps a URL → status code, may raise to simulate a
    network failure).
    """
    fetcher = fetch if fetch is not None else _default_fetch
    for _ in range(max(1, attempts)):
        try:
            status = fetcher(url)
        except Exception:  # noqa: BLE001 — network failure: retry, then treat as unreachable
            continue
        return status not in _UNREACHABLE_STATUS
    return False  # every attempt hit a network error → genuinely unreachable


# ─────────────────────────────────────────────────────────────────────────────
# The deterministic pipeline the harness runs over a researcher's candidates
# ─────────────────────────────────────────────────────────────────────────────
def curate_candidates(
    stories: list[Story],
    n: int,
    *,
    exclude: bool = True,
    fetch: Optional[Callable[[str], int]] = None,
    exclude_keys: Optional[set[str]] = None,
    diversity_key: Optional[Callable[[Story], str]] = None,
) -> list[Story]:
    """Reduce raw candidate stories to the final ``n`` picks, deterministically.

    Order of operations (each step is its own tested function):
        1. drop grim/political stories (:func:`is_excluded_by_keywords`) — unless
           ``exclude`` is False;
        2. drop stories already published recently, if ``exclude_keys`` is given —
           any story whose URL/title key (:func:`story_key_set`) is in the set;
        3. collapse duplicate URLs / near-identical titles
           (:func:`dedupe_stories`);
        4. if ``fetch`` is given, drop stories whose source link doesn't resolve
           (:func:`validate_source_link`);
        5. pick the final ``n`` spread across continents
           (:func:`select_diverse`).

    Args:
        stories: candidate stories collected by a researcher subagent.
        n: how many to keep.
        exclude: apply the grim/political keyword filter (default True).
        fetch: optional injectable HTTP-status fetcher for link validation; when
            None, links are NOT checked here (do it as a separate live step).
        exclude_keys: optional set of story-keys (from :func:`story_key_set`) to
            drop — used to avoid republishing the last few days' stories.
        diversity_key: optional diversity axis for :func:`select_diverse` (e.g. a
            per-creator key for the fun desk). Defaults to continent spread.
    """
    pool = [s for s in stories if not (exclude and is_excluded_by_keywords(s))]
    if exclude_keys:
        pool = [s for s in pool if not (story_key_set(s.title, s.source_url) & exclude_keys)]
    pool = dedupe_stories(pool)
    if fetch is not None:
        pool = [s for s in pool if validate_source_link(s.source_url, fetch=fetch)]
    return select_diverse(pool, n, key=diversity_key)
