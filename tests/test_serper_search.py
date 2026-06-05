"""Tests for the Serper.dev web_search tool + its failure reporting.

The 2026-06-04 hallucination traced back to ddgs scraping getting 429'd from the
datacenter IP and the researcher fabricating to fill the gap. web_search now uses
the keyed Serper.dev (Google SERP) API and returns an explicit ``SEARCH_FAILED:
<reason>`` sentinel (never silent emptiness) so the newsroom can HOLD and say WHY.
All offline (httpx stubbed). (Serper replaced Brave in 2026-06 after Brave withdrew
its free API tier.)
"""

import httpx
import pytest

from content_pipeline.agent import tools as T
from content_pipeline.content_config import content_cfg


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _set_key(monkeypatch, key):
    monkeypatch.setattr(content_cfg, "serper_api_key", key)


def test_web_search_no_key_reports_failure(monkeypatch):
    _set_key(monkeypatch, "")
    out = T.web_search.invoke({"query": "irish ai news"})
    assert out.startswith("SEARCH_FAILED:")
    assert "key" in out.lower()


def test_web_search_parses_results(monkeypatch):
    _set_key(monkeypatch, "test-key")
    # Serper returns matches under `organic` with title / snippet / link.
    payload = {"organic": [
        {"title": "Qwen3.6 drops", "snippet": "A new open model", "link": "https://ex/1"},
        {"title": "FLUX update", "snippet": "image gen", "link": "https://ex/2"},
    ]}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(200, payload))
    out = T.web_search.invoke({"query": "ai"})
    assert "Qwen3.6 drops" in out
    assert "A new open model" in out
    assert "https://ex/1" in out and "https://ex/2" in out
    assert not out.startswith("SEARCH_FAILED:")


def test_web_search_429_reports_rate_limit(monkeypatch):
    _set_key(monkeypatch, "test-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(429))
    out = T.web_search.invoke({"query": "ai"})
    assert out.startswith("SEARCH_FAILED:") and "429" in out


def test_web_search_401_reports_bad_key(monkeypatch):
    _set_key(monkeypatch, "bad-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(401))
    out = T.web_search.invoke({"query": "ai"})
    assert out.startswith("SEARCH_FAILED:") and "401" in out


def test_web_search_network_error_reports_failure(monkeypatch):
    _set_key(monkeypatch, "test-key")

    def _boom(*a, **k):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", _boom)
    out = T.web_search.invoke({"query": "ai"})
    assert out.startswith("SEARCH_FAILED:") and "network" in out.lower()


def test_web_search_empty_results_is_not_a_failure(monkeypatch):
    _set_key(monkeypatch, "test-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(200, {"organic": []}))
    out = T.web_search.invoke({"query": "ai"})
    assert out == "no results found"
    assert not out.startswith("SEARCH_FAILED:")
