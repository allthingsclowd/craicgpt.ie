"""Integrity guardrails: fabrication and thin editions must be structurally
impossible. The 2026-06-04 incident published 12/18 fabricated source URLs.

These cover the deterministic defenses in editor_in_chief.run_edition:
  * _validate_ai_candidates drops grim/political, duplicate, unreachable, and
    recently-published candidates (the AI desk previously had NO curation);
  * run_edition HOLDs (EditionHeld) when too few real, fresh sources survive on
    either desk, naming the cause (incl. 'web search degraded' / 'fresh-only');
  * _search_failures surfaces the web_search SEARCH_FAILED sentinel so the HOLD
    can say WHY search failed.
All offline (link fetch + recency injected; writer/image stubbed).
"""

import json

import pytest

from content_pipeline.agent.editor_in_chief import (
    EditionHeld,
    _search_failures,
    _validate_ai_candidates,
    run_edition,
)
from content_pipeline.research.curation import story_key_set


class _ResearchAgent:
    def __init__(self, fun_candidates, ai_candidates, messages=None):
        self._files = {
            "/research/fun_candidates.json": {"content": json.dumps(fun_candidates)},
            "/research/ai_candidates.json": {"content": json.dumps(ai_candidates)},
        }
        self._messages = messages or []

    def invoke(self, _inputs, config=None):
        return {"messages": self._messages, "files": self._files}


def _ai(n):
    return [{"title": f"AI {i}", "summary": "s", "source_url": f"https://ai/{i}"}
            for i in range(n)]


def _fun(n):
    conts = ["Europe", "Asia", "Africa", "Americas", "Oceania"]
    return [{"title": f"Fun {i}", "summary": "lovely", "source_url": f"https://f/{i}",
             "continent": conts[i % 5]} for i in range(n)]


def _writer(prompt):
    if "AI editor" in prompt:  # the AI-section call
        return {
            "headliner": {"title": "H", "standfirst": "s", "body": "b", "source_url": "https://ai/0"},
            "subarticles": [{"title": f"sub{i}", "body": "b", "source_url": "https://ai/1"} for i in range(2)],
            "shorts": [{"title": f"sh{i}", "body": "b", "source_url": "https://ai/2"} for i in range(10)],
        }
    return {"title": "Fun!", "body": "...", "source_url": ""}


_IMG = lambda p: ("/tmp/i.png", "flux")  # noqa: E731 — terse offline image stub
_NOFEED = lambda url: None  # noqa: E731 — disable the live curated-feed harvest offline


# --- _validate_ai_candidates (the AI desk's missing curation) ----------------
def test_validate_ai_candidates_drops_grim_dupe_unreachable_recent():
    cands = [
        {"title": "Real one", "summary": "s", "source_url": "https://ok/1"},
        {"title": "War crimes tribunal opens", "summary": "grim", "source_url": "https://ok/2"},
        {"title": "Dupe of one", "summary": "s", "source_url": "https://ok/1"},
        {"title": "Dead link", "summary": "s", "source_url": "https://gone/3"},
        {"title": "Old news", "summary": "s", "source_url": "https://ok/4"},
        {"title": "Fresh two", "summary": "s", "source_url": "https://ok/5"},
    ]
    status = {"https://ok/1": 200, "https://gone/3": 404, "https://ok/5": 200}
    recent = story_key_set("Old news", "https://ok/4")
    survivors, dropped = _validate_ai_candidates(
        cands, fetch=lambda u: status[u], exclude_keys=recent)
    assert [c["title"] for c in survivors] == ["Real one", "Fresh two"]
    assert len(dropped) == 4  # grim, dupe, unreachable, recent


def test_validate_ai_candidates_preserves_rich_fields():
    cands = [{"title": "T", "summary": "s", "source_url": "https://ok/1",
              "why_it_matters": "w", "key_points": ["a", "b"], "conclusion": "c"}]
    survivors, _ = _validate_ai_candidates(cands, fetch=lambda u: 200)
    assert survivors[0]["key_points"] == ["a", "b"]
    assert survivors[0]["conclusion"] == "c"


# --- run_edition HOLD behaviour (never publish thin / fabricated) ------------
def test_run_edition_holds_when_ai_below_floor():
    agent = _ResearchAgent(_fun(6), _ai(5))  # 5 AI < min 11
    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                    link_fetch=lambda url: 200, recent_keys=set(), ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert "AI source" in str(exc.value)


def test_run_edition_holds_when_fun_below_floor():
    agent = _ResearchAgent(_fun(2), _ai(13))  # 2 fun < min 4
    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                    link_fetch=lambda url: 200, recent_keys=set(), ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert "fun source" in str(exc.value)


def test_run_edition_holds_when_links_unreachable():
    # 13 AI candidates but only 4 resolve (the rest are fabricated / dead) → HOLD.
    status = {f"https://ai/{i}": (200 if i < 4 else 404) for i in range(13)}
    agent = _ResearchAgent(_fun(6), _ai(13))
    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                    link_fetch=lambda url: status.get(url, 404), recent_keys=set(),
                    ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert "unreachable" in str(exc.value).lower()


def test_run_edition_holds_with_search_reason_when_degraded():
    msgs = [{"role": "tool", "content": "SEARCH_FAILED: 429 rate-limited (slow down / over quota)"}]
    agent = _ResearchAgent(_fun(2), _ai(3), messages=msgs)
    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                    link_fetch=lambda url: 200, recent_keys=set(), ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert "search degraded" in str(exc.value).lower() and "429" in str(exc.value)


def test_run_edition_recency_can_cause_hold_and_names_it():
    # 12 AI candidates, but the recency set excludes 2 → 10 < min 11 → HOLD.
    recent = story_key_set("AI 0", "https://ai/0") | story_key_set("AI 1", "https://ai/1")
    agent = _ResearchAgent(_fun(6), _ai(12))
    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                    link_fetch=lambda url: 200, recent_keys=recent, ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert "fresh-only" in str(exc.value).lower()


def test_run_edition_succeeds_when_enough_fresh_sources():
    # 15 AI (2 excluded as recent → 13 ≥ 11) + 8 fun → writes a full edition.
    recent = story_key_set("AI 0", "https://ai/0") | story_key_set("AI 1", "https://ai/1")
    agent = _ResearchAgent(_fun(8), _ai(15))
    paper = run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                        link_fetch=lambda url: 200, recent_keys=recent, ai_feed_fetch=_NOFEED, image_generate=_IMG)
    assert paper["ai"]["headliner"]["title"] == "H"
    assert len(paper["ai"]["shorts"]) == 10
    assert len(paper["fun"]) == 5


# --- _search_failures (so a HOLD can say WHY) --------------------------------
def test_search_failures_extracts_distinct_reasons():
    msgs = [
        {"role": "tool", "content": "blah\nSEARCH_FAILED: 429 rate-limited (slow down)\nmore"},
        {"role": "assistant", "content": "thinking"},
        {"role": "tool", "content": "SEARCH_FAILED: 401 unauthorized (bad key)"},
        {"role": "tool", "content": "SEARCH_FAILED: 429 rate-limited (slow down)"},  # dup
    ]
    fails = _search_failures(msgs)
    assert any("429" in f for f in fails)
    assert any("401" in f for f in fails)
    assert len(fails) == 2  # deduped


# --- curated-feed harvest rescues a thin agent yield -------------------------
def test_run_edition_harvest_rescues_thin_agent_yield():
    # The agent gathered only 3 AI candidates (would HOLD on its own), but the
    # curated-feed harvest supplies plenty of REAL items → the edition PUBLISHES,
    # and fabrication stays impossible (every feed URL is real + link-checked).
    import hashlib

    def _feed(url):  # each curated feed returns 4 DISTINCT recent items (real-world shape)
        tag = hashlib.md5(url.encode()).hexdigest()[:8]
        return ("<rss version='2.0'><channel>" + "".join(
            f"<item><title>Feed {tag} {i}</title><link>https://feed/{tag}/{i}</link>"
            f"<description>news</description></item>" for i in range(4)) + "</channel></rss>")

    agent = _ResearchAgent(_fun(6), _ai(3))  # the agent alone (3 < 11) would HOLD
    paper = run_edition("2026-06-02", generated_at="t", agent=agent, write_generate=_writer,
                        link_fetch=lambda url: 200, recent_keys=set(),
                        ai_feed_fetch=_feed, image_generate=_IMG)
    assert paper["ai"]["headliner"]["title"] == "H"  # published, not held
    assert len(paper["ai"]["shorts"]) == 10


# --- source-link fidelity: the writer can't slip an unreachable URL to the gate -
def test_snap_ai_sources_forces_validated_urls():
    from content_pipeline.agent.editor_in_chief import _snap_ai_sources
    cands = [
        {"title": "OpenAI ships GPT memory upgrade", "source_url": "https://real/openai-memory"},
        {"title": "DeepSeek raises seven billion in funding round", "source_url": "https://real/deepseek"},
        {"title": "Mistral opens a Paris research lab", "source_url": "https://real/mistral"},
    ]
    ai = {
        "headliner": {"title": "OpenAI Memory Upgrade Lands", "body": "b",
                      "source_url": "https://hallucinated/openai-dreaming"},           # invented → snap
        "subarticles": [{"title": "DeepSeek's Funding Round", "body": "b",
                         "source_url": "https://made-up/deepseek-x"}],                 # mangled → snap
        "shorts": [
            {"title": "Mistral Paris Lab Opens", "body": "b", "source_url": "https://real/mistral"},  # faithful → keep
            {"title": "Totally unrelated quantum widget", "body": "b",
             "source_url": "https://invented/xyz"},                                    # ungrounded → drop
        ],
    }
    out = _snap_ai_sources(ai, cands)
    assert out["headliner"]["source_url"] == "https://real/openai-memory"   # snapped by title match
    assert out["subarticles"][0]["source_url"] == "https://real/deepseek"   # snapped by title match
    assert [s["source_url"] for s in out["shorts"]] == ["https://real/mistral"]  # faithful kept, ungrounded dropped


def test_snap_ai_sources_headliner_never_keeps_writer_url():
    # Task #28: the headliner is never DROPPED, but it must never RETAIN the
    # writer's own (possibly invented / bot-blocked) URL either. With no title
    # match it falls back to a validated candidate — never the writer's guess.
    from content_pipeline.agent.editor_in_chief import _snap_ai_sources
    cands = [
        {"title": "DeepSeek raises a funding round", "source_url": "https://real/deepseek"},
        {"title": "Mistral opens a Paris lab", "source_url": "https://real/mistral"},
    ]
    ai = {
        "headliner": {"title": "Something nobody can verify", "body": "b",
                      "source_url": "https://openai.com/index/invented-slug"},  # no title match
        "subarticles": [], "shorts": [],
    }
    out = _snap_ai_sources(ai, cands)
    assert out["headliner"]["source_url"] in {"https://real/deepseek", "https://real/mistral"}
    assert out["headliner"]["source_url"] != "https://openai.com/index/invented-slug"


def test_snap_ai_sources_headliner_blanked_when_no_validated_candidates():
    # Defensive: with NO validated candidate to snap onto (an edition that will be
    # HELD anyway), the headliner's unverified URL is blanked rather than smuggled
    # through — a clean structural "missing source_url", not an unreachable link.
    from content_pipeline.agent.editor_in_chief import _snap_ai_sources
    ai = {"headliner": {"title": "T", "body": "b", "source_url": "https://openai.com/index/invented"},
          "subarticles": [], "shorts": []}
    out = _snap_ai_sources(ai, [])
    assert out["headliner"]["source_url"] == ""


def test_write_fun_forces_validated_source_url():
    # Even if the writer emits a hallucinated URL, the published fun story carries
    # the validated picked candidate's URL — never the writer's guess.
    from content_pipeline.agent.editor_in_chief import _write_fun
    from content_pipeline.research.curation import Story

    picked = [Story(title="Otters reunited", summary="lovely", source_url="https://validated/otters")]
    written = _write_fun(picked, "2026-06-04", {"https://validated/otters": "Foil Arms and Hog"},
                         generate=lambda p: {"title": "Otters!", "body": "x",
                                             "source_url": "https://hallucinated/nope"})
    assert written[0]["source_url"] == "https://validated/otters"  # validated URL, never the writer's guess
    assert written[0]["source"] == "Foil Arms and Hog"             # creator credit threaded through
