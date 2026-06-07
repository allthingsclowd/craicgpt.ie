"""Tests for the deterministic curation core.

The *judgment* of whether a story is fun/positive is the LLM's job (and lives
in the curating-positive-news skill). But the mechanics around it — dropping
duplicates, spreading the final picks across continents, cheaply excluding the
obviously-grim/political before we spend tokens, and validating that every
source link actually resolves — are deterministic and belong here, fully
unit-tested. Per deciding-deterministic-vs-llm: don't pay an LLM to do what a
function can.
"""

from content_pipeline.research.curation import (
    Story,
    dedupe_stories,
    is_excluded_by_keywords,
    select_diverse,
    validate_source_link,
)


def _story(title, url, *, continent="Europe", score=1.0, summary="s"):
    return Story(title=title, summary=summary, source_url=url,
                 continent=continent, score=score)


def test_dedupe_removes_duplicate_urls_keeping_higher_score():
    stories = [
        _story("Otter learns to juggle", "https://x.com/otter", score=0.4),
        _story("Otter juggles!", "https://x.com/otter", score=0.9),  # same URL
    ]
    out = dedupe_stories(stories)
    assert len(out) == 1
    assert out[0].score == 0.9  # higher-scored survivor


def test_dedupe_removes_near_duplicate_titles():
    stories = [
        _story("Penguin Wins Local Marathon", "https://a.com/1"),
        _story("penguin wins local marathon!!", "https://b.com/2"),  # same title
        _story("Cat Mayor Re-elected", "https://c.com/3"),
    ]
    out = dedupe_stories(stories)
    titles = {s.title for s in out}
    assert len(out) == 2
    assert "Cat Mayor Re-elected" in titles


def test_select_diverse_spreads_across_continents():
    stories = [
        _story("A", "https://a", continent="Europe", score=0.9),
        _story("B", "https://b", continent="Europe", score=0.85),
        _story("C", "https://c", continent="Asia", score=0.8),
        _story("D", "https://d", continent="Africa", score=0.7),
        _story("E", "https://e", continent="Europe", score=0.6),
    ]
    picked = select_diverse(stories, n=3)
    continents = [s.continent for s in picked]
    # Top 3 by score alone would be Europe/Europe/Asia; diversity must include
    # at least 3 distinct continents when they're available.
    assert len(set(continents)) == 3


def test_select_diverse_falls_back_to_score_when_diversity_exhausted():
    stories = [
        _story("A", "https://a", continent="Europe", score=0.9),
        _story("B", "https://b", continent="Europe", score=0.8),
        _story("C", "https://c", continent="Europe", score=0.7),
    ]
    picked = select_diverse(stories, n=2)
    assert len(picked) == 2
    assert [s.title for s in picked] == ["A", "B"]  # highest scores


def test_select_diverse_by_creator_picks_distinct_creators():
    # The fun desk keys diversity on CREATOR (not continent): five candidates but
    # only three creators (two with two uploads each). Picking the top 3 by score
    # alone would take both Foil Arms and Hog + a 2 Johnnies and starve the third;
    # the per-creator key must spread to three distinct creators instead. This is
    # the fix for the "5 articles, only 3 distinct sources" complaint.
    stories = [
        Story("Sketch A", "s", "https://yt/a1", score=0.95, creator="Foil Arms and Hog"),
        Story("Sketch B", "s", "https://yt/a2", score=0.90, creator="Foil Arms and Hog"),
        Story("Bit C",    "s", "https://yt/b1", score=0.85, creator="The 2 Johnnies"),
        Story("Bit D",    "s", "https://yt/b2", score=0.80, creator="The 2 Johnnies"),
        Story("Clip E",   "s", "https://yt/c1", score=0.50, creator="Graham Norton"),
    ]
    picked = select_diverse(stories, n=3, key=lambda s: s.creator or "")
    creators = [s.creator for s in picked]
    assert len(set(creators)) == 3                 # one per creator, never 2+1
    assert "Graham Norton" in creators             # the lower-scored third creator still lands


def test_keyword_exclusion_flags_grim_and_political():
    assert is_excluded_by_keywords(_story("Election poll shows tight race", "https://p"))
    assert is_excluded_by_keywords(_story("Dozens killed in earthquake", "https://q"))
    assert not is_excluded_by_keywords(_story("Dog reunited with owner after 5 years", "https://r"))


def test_validate_source_link_accepts_2xx_rejects_others():
    assert validate_source_link("https://ok", fetch=lambda url: 200) is True
    assert validate_source_link("https://gone", fetch=lambda url: 404) is False

    def boom(url):
        raise OSError("dns failure")

    assert validate_source_link("https://broken", fetch=boom) is False


def test_validate_source_link_treats_bot_block_and_ratelimit_as_reachable():
    # 401/403/405/429 = the host EXISTS but blocks/limits the bot — NOT a fabrication.
    # (cybersecuritydive 429'd under the gate's 18-link burst → was falsely HELD.)
    for code in (401, 403, 405, 429):
        assert validate_source_link("https://blocked", fetch=lambda url, c=code: c) is True


def test_validate_source_link_rejects_404_and_410_as_invented_or_gone():
    # The fabrication signal we MUST keep: an invented/removed URL 404s/410s.
    assert validate_source_link("https://gone", fetch=lambda url: 404) is False
    assert validate_source_link("https://gone", fetch=lambda url: 410) is False


def test_validate_source_link_retries_a_transient_error_then_succeeds():
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("burst timeout")
        return 200

    assert validate_source_link("https://slow", fetch=flaky) is True
    assert calls["n"] == 2


def test_validate_source_link_persistent_network_failure_is_unreachable():
    def boom(url):
        raise OSError("dns failure")

    assert validate_source_link("https://nope", fetch=boom) is False
