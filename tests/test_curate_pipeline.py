"""Tests for the deterministic curation *pipeline* the harness runs.

A researcher subagent collects candidate stories (live web work — the LLM's
job). The harness then applies this deterministic pipeline to those candidates
BEFORE the editor writes them up: drop the grim/political, dedupe, validate
links, and pick the final N spread across continents. No LLM, no network
(link-check fetch is injected).
"""

from content_pipeline.research.curation import Story, curate_candidates


def _s(title, url, *, continent="Europe", score=1.0, summary="s"):
    return Story(title=title, summary=summary, source_url=url, continent=continent, score=score)


def test_pipeline_excludes_dedupes_and_selects_diverse():
    candidates = [
        _s("Otter learns to juggle", "https://a/1", continent="Europe", score=0.9),
        _s("Otter juggles!", "https://a/1", continent="Europe", score=0.5),       # dup URL
        _s("Election results spark fury", "https://a/2", continent="Europe", score=0.95),  # grim/political
        _s("Penguin wins marathon", "https://a/3", continent="Asia", score=0.8),
        _s("Cat mayor re-elected... as Best Boy", "https://a/4", continent="Africa", score=0.7),
    ]
    picked = curate_candidates(candidates, n=3)
    titles = [s.title for s in picked]
    # Political story removed; URL dup collapsed; 3 distinct continents represented.
    assert "Election results spark fury" not in titles
    assert len(picked) == 3
    assert len({s.continent for s in picked}) == 3


def test_pipeline_validates_links_when_fetch_provided():
    candidates = [
        _s("Good A", "https://ok/1", continent="Europe", score=0.9),
        _s("Dead B", "https://gone/2", continent="Asia", score=0.95),
    ]
    statuses = {"https://ok/1": 200, "https://gone/2": 404}
    picked = curate_candidates(candidates, n=5, fetch=lambda url: statuses[url])
    titles = [s.title for s in picked]
    assert "Good A" in titles
    assert "Dead B" not in titles  # unresolving link dropped


def test_pipeline_keeps_exclusion_optional():
    candidates = [_s("Election night recap", "https://a/1")]
    # With exclude disabled, the grim filter is skipped.
    assert len(curate_candidates(candidates, n=5, exclude=False)) == 1
    assert len(curate_candidates(candidates, n=5, exclude=True)) == 0
