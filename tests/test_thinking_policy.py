"""Per-route thinking policy (2026-11-03).

Flash-Next (dgx/vllm/qwen3.8-flash-next-fp4) dropped digits from identifiers with
thinking OFF ("CVE-2026-20002" → "CVE-20002", 3/3) and was right 3/3 at low-effort
thinking. These pin that the policy turns thinking on ONLY for that route, and that
every writer / translate / judge / brain call site routes through it.
"""

import pytest

from content_pipeline.providers import litellm as litellm_mod
from content_pipeline.providers.litellm import (
    THINKING_MIN_TIMEOUT_S,
    THINKING_REASONING_TOKENS,
    agentic_thinking_kwargs,
    request_timeout_for,
    thinking_policy,
)

FLASH = "dgx/vllm/qwen3.8-flash-next-fp4"
OTHER = "m3/mlx/qwen3.8-27b-8bit"
ON = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_effort": "low"}
OFF = {"chat_template_kwargs": {"enable_thinking": False}}


@pytest.fixture(autouse=True)
def _default_policy(monkeypatch):
    monkeypatch.delenv("LLM_THINKING_MODELS", raising=False)


class _Resp:
    def __init__(self, content):
        self.content = content


def _capture(monkeypatch, reply):
    calls = []

    class _LLM:
        def invoke(self, prompt):
            return _Resp(reply)

    def _factory(model, **kwargs):
        calls.append((model, kwargs))
        return _LLM()

    monkeypatch.setattr(litellm_mod, "get_litellm_llm", _factory)
    return calls


def test_flash_next_thinks_low_with_room_for_the_reasoning():
    body, tokens = thinking_policy(FLASH, 6000)
    assert body == ON
    assert tokens == 6000 + THINKING_REASONING_TOKENS
    assert thinking_policy(FLASH + "-long", 10)[0] == ON


def test_other_routes_keep_thinking_off():
    body, tokens = thinking_policy(OTHER, 6000)
    assert body == OFF
    assert tokens == 6000


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_THINKING_MODELS", "")
    assert thinking_policy(FLASH, 100) == (OFF, 100)
    monkeypatch.setenv("LLM_THINKING_MODELS", f" {OTHER} ,")
    assert thinking_policy(OTHER, 100)[0] == ON
    assert thinking_policy(FLASH, 100)[0] == OFF


def test_agent_loops_untouched_on_other_routes_low_effort_on_flash():
    # Brain + rubric judge never sent a thinking flag: a non-thinking route keeps that.
    assert agentic_thinking_kwargs(OTHER) == {}
    kw = agentic_thinking_kwargs(FLASH)
    assert kw["extra_body"] == ON
    assert kw["max_tokens"] > THINKING_REASONING_TOKENS


def test_thinking_route_gets_a_longer_client_timeout():
    from content_pipeline.content_config import content_cfg

    assert request_timeout_for(OTHER) == content_cfg.request_timeout
    assert request_timeout_for(FLASH) >= THINKING_MIN_TIMEOUT_S
    llm = litellm_mod.get_litellm_llm(FLASH)  # construction only — no network I/O
    assert llm.request_timeout >= THINKING_MIN_TIMEOUT_S


def test_writer_json_call_uses_the_policy_and_keeps_json_schema(monkeypatch):
    from content_pipeline.generate import writer

    monkeypatch.setattr(writer.content_cfg, "write_model", FLASH)
    calls = _capture(monkeypatch, '{"title": "T", "body": "B"}')
    writer._default_generate("p", schema=writer.SCHEMA_ARTICLE, max_tokens=8000)
    model, kw = calls[0]
    assert model == FLASH
    assert kw["extra_body"]["chat_template_kwargs"] == ON["chat_template_kwargs"]
    assert kw["extra_body"]["reasoning_effort"] == "low"
    assert kw["extra_body"]["response_format"]["type"] == "json_schema"
    assert kw["max_tokens"] == 8000 + THINKING_REASONING_TOKENS


def test_writer_off_route_unchanged(monkeypatch):
    from content_pipeline.generate import writer

    monkeypatch.setattr(writer.content_cfg, "write_model", OTHER)
    calls = _capture(monkeypatch, '{"title": "T", "body": "B"}')
    writer._default_generate("p", max_tokens=8000)
    _, kw = calls[0]
    assert kw["extra_body"] == OFF
    assert kw["max_tokens"] == 8000


def test_translate_text_call_uses_the_policy(monkeypatch):
    from content_pipeline.generate import translate, writer

    monkeypatch.setattr(writer.content_cfg, "write_model", FLASH)
    calls = _capture(monkeypatch, "hallo")
    assert translate._default_translate("p") == "hallo"
    model, kw = calls[0]
    assert model == FLASH
    assert kw["extra_body"] == ON
    assert kw["max_tokens"] == translate._TRANSLATE_MAX_TOKENS + THINKING_REASONING_TOKENS


def test_article_judge_uses_the_policy(monkeypatch):
    from content_pipeline.agent import article_review

    calls = []

    class _LLM:
        def invoke(self, prompt):
            return _Resp('{"fabricated": []}')

    def _factory(model, **kwargs):
        calls.append((model, kwargs))
        return _LLM()

    monkeypatch.setattr(article_review, "get_litellm_llm", _factory)
    article_review._grade_articles_once(FLASH, "view")
    article_review._grade_articles_once(OTHER, "view")
    assert calls[0][1]["extra_body"] == ON
    assert calls[1][1]["extra_body"] == OFF


def test_brain_on_flash_thinks_low(monkeypatch):
    from content_pipeline.agent import editor_in_chief

    calls = []
    monkeypatch.setattr(editor_in_chief, "get_litellm_llm",
                        lambda model, **kw: calls.append((model, kw)))
    editor_in_chief.build_brain(FLASH)
    editor_in_chief.build_brain(OTHER)
    assert calls[0][1]["extra_body"] == ON
    assert calls[1][1] == {}
