"""
Tests for the content-enhancement agent (``shared.enrich``).

TUTORIAL: every test here is OFFLINE and deterministic. The LLM is the only
non-deterministic seam, and it is injected as a stub :class:`LLMClient` — so the
whole harness (prompt assembly, JSON extraction, the integrity gate, attribution)
runs with no network and no model. This mirrors the CraicGPT writer/gag tests,
where ``generate`` is injected as ``(prompt) -> dict``.

The two contract tests the ticket asks for:
  (a) a stub returning a valid cited hook -> a well-formed Enrichment;
  (b) a stub that declines / returns no verifiable hook -> None, no fabrication.
Everything else pins the integrity-over-output edges around those two.
"""

from __future__ import annotations

import json

import pytest

from shared.enrich import Enrichment, enrich_item
from shared.enrich.enrich import (
    DEFAULT_ENRICH_FALLBACK_MODEL,
    DEFAULT_ENRICH_MODEL,
    LLMResponse,
    _looks_like_citation,
    _model_routes,
    default_llm,
)


# ─────────────────────────────────────────────────────────────────────────────
# Stub LLM clients — the injectable boundary, five lines each
# ─────────────────────────────────────────────────────────────────────────────
class _Stub:
    """An :class:`LLMClient` that returns a fixed reply and records the prompt."""

    def __init__(self, text: str, model: str = "stub/model") -> None:
        self._text = text
        self._model = model
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text=self._text, model=self._model)


class _Boom:
    """An :class:`LLMClient` that raises — models a transport/engine failure."""

    def complete(self, prompt: str) -> LLMResponse:  # noqa: D401
        raise RuntimeError("engine unreachable")


_ITEM = {
    "title": "Password spraying",
    "body": "Trying a handful of common passwords across many accounts at once.",
}

_GOOD_JSON = json.dumps(
    {
        "found": True,
        "headline": "The 2024 Change Healthcare breach",
        "tie_in": "It started with one stolen login and no MFA — password spraying's"
                  " payday, and exactly the tactic this lesson teaches.",
        "source_url": "https://www.cisa.gov/news-events/analysis-reports/ar24-change",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# (a) THE HAPPY PATH — a valid cited hook becomes a well-formed Enrichment
# ─────────────────────────────────────────────────────────────────────────────
def test_valid_cited_hook_becomes_a_well_formed_enrichment():
    stub = _Stub(_GOOD_JSON, model="dgx/vllm/qwen3.8-27b-nvfp4")
    result = enrich_item(_ITEM, topic="Valid Accounts (T1078)", llm=stub)

    assert isinstance(result, Enrichment)
    assert result.headline == "The 2024 Change Healthcare breach"
    assert result.tie_in.startswith("It started with one stolen login")
    assert result.source_url.startswith("https://www.cisa.gov/")
    # Attribution is HONEST: it stamps the route the stub actually served.
    assert result.model_used == "dgx/vllm/qwen3.8-27b-nvfp4"
    # The blurb is JSON-friendly for stashing on the item.
    assert result.as_dict()["_model"] == "dgx/vllm/qwen3.8-27b-nvfp4"
    assert set(result.as_dict()) == {"headline", "tie_in", "source_url", "_model"}


def test_the_topic_and_item_are_put_in_front_of_the_model():
    """The model is TOLD the tactic and the item — it doesn't have to infer them."""
    stub = _Stub(_GOOD_JSON)
    enrich_item(_ITEM, topic="Valid Accounts (T1078)", llm=stub)
    prompt = stub.prompts[0]
    assert "Valid Accounts (T1078)" in prompt
    assert "Password spraying" in prompt


def test_reply_wrapped_in_a_code_fence_still_parses():
    """Local models love ```json fences and <think> preambles — plumbing strips them."""
    stub = _Stub("<think>let me recall...</think>\n```json\n" + _GOOD_JSON + "\n```")
    result = enrich_item(_ITEM, topic="Valid Accounts", llm=stub)
    assert isinstance(result, Enrichment)
    assert result.headline == "The 2024 Change Healthcare breach"


# ─────────────────────────────────────────────────────────────────────────────
# (b) INTEGRITY OVER OUTPUT — decline / no verifiable hook -> None, no fabrication
# ─────────────────────────────────────────────────────────────────────────────
def test_an_explicit_decline_returns_none():
    """found:false is the honourable answer — no hook rather than a fabricated one."""
    declined = json.dumps({"found": False, "headline": "", "tie_in": "", "source_url": ""})
    assert enrich_item(_ITEM, topic="a tactic with no recent example", llm=_Stub(declined)) is None


def test_a_placeholder_citation_is_rejected():
    """example.com is the classic fabrication smell — reject it, don't ship it."""
    faked = json.dumps(
        {
            "found": True,
            "headline": "A very convenient breach",
            "tie_in": "Suspiciously perfect for this lesson.",
            "source_url": "https://example.com/breach",
        }
    )
    assert enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub(faked)) is None


def test_a_missing_source_url_is_rejected():
    """A hook with no citation is a claim, not an enrichment — dropped."""
    uncited = json.dumps(
        {"found": True, "headline": "Something happened", "tie_in": "Trust me.", "source_url": ""}
    )
    assert enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub(uncited)) is None


def test_a_missing_tie_in_is_rejected():
    incomplete = json.dumps(
        {"found": True, "headline": "The 2024 X breach", "tie_in": "",
         "source_url": "https://www.cisa.gov/x"}
    )
    assert enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub(incomplete)) is None


def test_an_unparseable_reply_returns_none():
    assert enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub("sorry, I can't help")) is None


def test_a_failing_verifier_discards_the_hook():
    """A well-formed, well-cited hook whose live link is dead is still dropped."""
    stub = _Stub(_GOOD_JSON)
    result = enrich_item(_ITEM, topic="Valid Accounts", llm=stub, verify_url=lambda url: False)
    assert result is None


def test_a_passing_verifier_keeps_the_hook():
    calls: list[str] = []

    def verify(url: str) -> bool:
        calls.append(url)
        return True

    result = enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub(_GOOD_JSON), verify_url=verify)
    assert isinstance(result, Enrichment)
    assert calls == ["https://www.cisa.gov/news-events/analysis-reports/ar24-change"]


def test_a_verifier_that_raises_is_treated_as_a_failure_not_a_pass():
    def verify(url: str) -> bool:
        raise RuntimeError("DNS exploded")

    result = enrich_item(_ITEM, topic="Valid Accounts", llm=_Stub(_GOOD_JSON), verify_url=verify)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Fail-soft transport + empty input — never raise, never call the model needlessly
# ─────────────────────────────────────────────────────────────────────────────
def test_a_raising_client_returns_none_rather_than_propagating():
    """A flaky engine must never sink the caller — enrichment is fail-soft."""
    assert enrich_item(_ITEM, topic="Valid Accounts", llm=_Boom()) is None


def test_an_empty_item_is_skipped_without_calling_the_model():
    stub = _Stub(_GOOD_JSON)
    assert enrich_item({}, topic="Valid Accounts", llm=stub) is None
    assert stub.prompts == []  # not a single wasted token


# ─────────────────────────────────────────────────────────────────────────────
# Model routing is visible, env-overridable, and read via a factory (no singleton)
# ─────────────────────────────────────────────────────────────────────────────
def test_default_routes_match_the_grazlab_catalog():
    assert DEFAULT_ENRICH_MODEL == "dgx/vllm/qwen3.8-27b-nvfp4"
    assert DEFAULT_ENRICH_FALLBACK_MODEL == "m3/mlx/qwen3.8-27b-8bit"
    assert _model_routes() == (DEFAULT_ENRICH_MODEL, DEFAULT_ENRICH_FALLBACK_MODEL)


def test_routes_are_env_overridable(monkeypatch):
    monkeypatch.setenv("ENRICH_MODEL", "m3/mlx/some-other-model")
    monkeypatch.setenv("ENRICH_FALLBACK_MODEL", "dgx/vllm/backup")
    assert _model_routes() == ("m3/mlx/some-other-model", "dgx/vllm/backup")


def test_default_llm_builds_without_touching_the_network():
    """Constructing the real client does NO I/O and imports no heavy SDK — the
    langchain import is deferred to .complete(). So this is safe offline."""
    client = default_llm()
    assert hasattr(client, "complete")


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.cisa.gov/advisory/x", True),
        ("http://nvd.nist.gov/vuln/detail/CVE-2024-1234", True),
        ("https://example.com/x", False),
        ("https://example.org/y", False),
        ("http://localhost/z", False),
        ("ftp://files.example/x", False),
        ("not-a-url", False),
        ("", False),
        ("https://nodot", False),
    ],
)
def test_citation_smell_check(url, ok):
    assert _looks_like_citation(url) is ok
