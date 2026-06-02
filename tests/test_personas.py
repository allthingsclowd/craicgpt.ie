"""Tests for the Marvel-persona assignment used by the fun-news rewriter.

Decision from grilling: real Marvel character names + a visible satire
disclaimer, one distinct character per article. The voice prompt itself is the
LLM's to perform; this module just owns the roster, the deterministic
day-stable assignment, the byline, and the disclaimer text.
"""

from content_pipeline.generate.personas import (
    SATIRE_DISCLAIMER,
    ROSTER,
    assign_personas,
    persona_byline,
    voice_brief,
)


def test_assign_returns_n_distinct_personas():
    picks = assign_personas(5, seed="2026-06-02")
    assert len(picks) == 5
    assert len(set(picks)) == 5  # all distinct characters
    assert all(p in ROSTER for p in picks)


def test_assign_is_stable_for_a_given_day():
    a = assign_personas(5, seed="2026-06-02")
    b = assign_personas(5, seed="2026-06-02")
    assert a == b  # same day → same lineup (reproducible runs)


def test_assign_rotates_across_days():
    a = assign_personas(5, seed="2026-06-02")
    c = assign_personas(5, seed="2026-06-03")
    assert a != c  # different day → different lineup


def test_assign_caps_at_roster_size():
    picks = assign_personas(len(ROSTER) + 10, seed="x")
    assert len(picks) == len(ROSTER)  # never repeats a character


def test_byline_names_the_character():
    line = persona_byline("Spider-Man")
    assert "Spider-Man" in line


def test_voice_brief_is_nonempty_for_roster_members():
    for character in ROSTER:
        assert voice_brief(character).strip()


def test_satire_disclaimer_is_present_and_marks_parody():
    assert SATIRE_DISCLAIMER.strip()
    assert "parody" in SATIRE_DISCLAIMER.lower() or "satire" in SATIRE_DISCLAIMER.lower()
