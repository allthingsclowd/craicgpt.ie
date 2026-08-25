"""The Craic & Throttle desk must never call a Honda a car.

Regression coverage for the 2026-08-24 live edition, which shipped
"I was sitting on my Civic" on a motorcycle story (issue #104).

The fix has FOUR independent layers and each is tested here, because any one of
them alone leaves a hole:
  1. harvest      — a car story from a moto feed never enters the pool
  2. routing      — the vertical is derived in CODE from the creator credit
  3. prose        — the writer is told, and the result is checked + re-written
  4. illustration — the image prompt is told too, or we ship a drawing of a car
"""

import pytest

from content_pipeline.generate.image_styles import STYLE_PRESETS, build_image_prompt
from content_pipeline.generate.writer import car_words_in, write_fun_story
from content_pipeline.research.fun_sources import (
    MOTO_SOURCES,
    is_comedy_source,
    is_moto_source,
)


# ── 2. routing ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["MCN", "Visordown", "MoreBikes", "RideApart",
                                  "Honda UK", "Honda Racing HRC"])
def test_bike_outlets_are_moto_sources(name):
    assert is_moto_source(name)
    assert not is_comedy_source(name)


@pytest.mark.parametrize("name", ["Sarah Millican", "Graham Norton", "Romesh Ranganathan"])
def test_comedians_are_not_moto_sources(name):
    assert not is_moto_source(name)
    assert is_comedy_source(name)


def test_moto_and_comedy_are_exact_complements():
    """The two predicates must partition every credit — no name is both or neither."""
    for name in list(MOTO_SOURCES) + ["Sarah Millican", "some new comedian"]:
        assert is_moto_source(name) != is_comedy_source(name)


def test_blank_credit_is_neither():
    for blank in (None, ""):
        assert not is_moto_source(blank)
        assert not is_comedy_source(blank)


# ── 3a. the deterministic detector ────────────────────────────────────────────
def test_detector_catches_the_live_bug():
    """The exact sentence the 2026-08-24 edition published."""
    assert car_words_in("I was sitting on my Civic, thinking I'm quite sophisticated") == ["civic"]


@pytest.mark.parametrize("text,expected", [
    ("a car with a steering wheel", ["car", "steering wheel"]),
    ("the new CR-V is roomy", ["cr-v"]),
    ("a four-wheel Honda Prologue SUV", ["four-wheel", "prologue", "suv"]),
])
def test_detector_finds_car_nouns(text, expected):
    assert car_words_in(text) == sorted(expected)


@pytest.mark.parametrize("text", [
    "He pulled on his boots and opened the throttle",       # riders wear boots
    "The CB1000GT is a big tall rounder",                   # the bike we bias toward
    "the Integra scooter sounded great",                    # Honda sells an Integra SCOOTER
    "a jazz soundtrack over the pillion footage",           # Jazz is also music
    "she opened the door to the green room",                # doors are usually metaphorical
])
def test_detector_does_not_false_positive(text):
    """Deliberately conservative — a false positive costs a wasted LLM call and,
    worse, teaches the writer to avoid legitimate motorcycling words."""
    assert car_words_in(text) == []


def test_detector_handles_none_and_empty():
    assert car_words_in("") == []
    assert car_words_in(None) == []


# ── 3b. the writer: prompt + re-write ─────────────────────────────────────────
def _fake_gen(bodies):
    """Generator returning each body in turn; records the prompts it was given."""
    seen = []
    it = iter(bodies)

    def gen(prompt):
        seen.append(prompt)
        return {"title": "T", "body": next(it), "source_url": "https://x"}

    return gen, seen


def test_moto_story_gets_the_constraint_and_comedy_does_not():
    gen, seen = _fake_gen(["a clean bike story"])
    write_fun_story({"title": "t", "source_url": "https://x"}, "MCN",
                    persona="Roy Mean", moto=True, generate=gen)
    assert "MOTORCYCLE STORY" in seen[0]
    assert "never a car" in seen[0]

    gen, seen = _fake_gen(["a clean comedy story"])
    write_fun_story({"title": "t", "source_url": "https://x"}, "Sarah Millican",
                    persona="Roy Mean", moto=False, generate=gen)
    assert "MOTORCYCLE STORY" not in seen[0]


def test_a_car_word_triggers_one_rewrite_and_the_clean_draft_wins():
    gen, seen = _fake_gen(["I sat on my Civic", "I sat on the CB1000GT"])
    out = write_fun_story({"title": "t", "source_url": "https://x"}, "MCN",
                          moto=True, generate=gen)
    assert len(seen) == 2, "exactly one retry — not a loop"
    assert "civic" in seen[1].lower(), "the retry must quote the offending word back"
    assert out["body"] == "I sat on the CB1000GT"


def test_a_clean_first_draft_costs_no_retry():
    gen, seen = _fake_gen(["straight onto the CB1000GT and away"])
    write_fun_story({"title": "t", "source_url": "https://x"}, "MCN",
                    moto=True, generate=gen)
    assert len(seen) == 1


def test_a_still_dirty_rewrite_keeps_the_cleaner_draft_rather_than_holding():
    """A slightly-wrong piece beats a hole in the desk — the per-article gate is
    advisory by design (2026-06-19), so this layer must never hard-fail either."""
    gen, _ = _fake_gen(["my Civic and my car and the steering wheel", "just my Civic"])
    out = write_fun_story({"title": "t", "source_url": "https://x"}, "MCN",
                          moto=True, generate=gen)
    assert out["body"] == "just my Civic"


def test_a_failing_rewrite_falls_back_to_the_first_draft():
    calls = {"n": 0}

    def gen(prompt):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("engine dropped")
        return {"title": "T", "body": "my Civic", "source_url": "https://x"}

    out = write_fun_story({"title": "t", "source_url": "https://x"}, "MCN",
                          moto=True, generate=gen)
    assert out["body"] == "my Civic", "a failed retry must not sink the story"


# ── 4. illustration ───────────────────────────────────────────────────────────
def test_image_prompt_tells_the_illustrator_it_is_a_bike():
    p = build_image_prompt({"title": "Honda CB1000GT", "body": "b", "_vertical": "moto"},
                           STYLE_PRESETS[0])
    assert "MOTORCYCLE" in p and "NOT a car" in p


@pytest.mark.parametrize("item", [
    {"title": "t", "body": "b", "_vertical": "comedy"},
    {"title": "t", "body": "b"},                       # AI desk items carry no vertical
])
def test_image_prompt_stays_clean_for_everything_else(item):
    assert "MOTORCYCLE" not in build_image_prompt(item, STYLE_PRESETS[0])


# ── 1. harvest: a car story never enters a motorcycle desk ────────────────────
# The bike press is filtered on "honda" alone, and several of these outlets also
# cover Honda's cars and EVs — so a Civic review passes the keyword filter cleanly.
# Dropping it is mechanical, so it belongs in code, not in the writer's lap.
from datetime import datetime, timedelta, timezone  # noqa: E402

from content_pipeline.research import feeds  # noqa: E402

_FRESH = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _rss(*items: tuple[str, str]) -> str:
    entries = "".join(
        f"<item><title>{t}</title><link>https://example.test/{i}</link>"
        f"<description>{d}</description><pubDate>{_FRESH}</pubDate></item>"
        for i, (t, d) in enumerate(items)
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{entries}</channel></rss>"


def _harvest_from_mcn(xml: str) -> list[dict]:
    """Harvest with ONLY the MCN feed wired up, so the assertion is unambiguous."""
    mcn = [(n, u) for n, u in feeds.FUN_FEEDS if n == "MCN"]
    assert mcn, "MCN must still be a configured fun feed"
    return feeds.harvest_fun_candidates(feeds_list=mcn, max_per_feed=10,
                                        fetch=lambda url: xml)


def test_a_honda_car_story_is_dropped_from_a_moto_feed():
    got = _harvest_from_mcn(_rss(
        ("Honda Civic Type R review", "The new Honda hot hatchback driven"),
        ("Honda CB1000GT first ride", "Honda's new sports tourer ridden"),
    ))
    titles = [c["title"] for c in got]
    assert "Honda CB1000GT first ride" in titles
    assert not any("Civic" in t for t in titles), f"a car story reached the moto desk: {titles}"


def test_a_non_honda_story_is_still_filtered_out_by_the_keyword():
    """The exclusion must not accidentally loosen the existing 'honda' filter."""
    got = _harvest_from_mcn(_rss(("Yamaha R1 review", "A different marque entirely")))
    assert got == []
