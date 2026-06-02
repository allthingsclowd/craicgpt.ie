"""Tests for the local-first → frontier-fallback wrapper.

This is the safety net that lets the daily pipeline default to open-source
local models (Qwen3.6 for writing, Qwen3-Coder for the research brain) while
guaranteeing a usable result: if the local call raises or fails validation,
we transparently retry on a frontier model and record *which* model actually
produced the output (for the published attribution note) plus the local
failure (for the eval feedback loop).

No network here — ``run_with_fallback`` takes a callable, so we drive it with
fakes.
"""

import pytest

from content_pipeline.providers.litellm import (
    GenerationResult,
    run_with_fallback,
)


def test_local_success_no_fallback():
    """Local model succeeds → its output is returned, no fallback recorded."""
    result = run_with_fallback(
        lambda model: f"written by {model}",
        local_model="local/qwen3.6",
        fallback_model="frontier/claude",
    )
    assert isinstance(result, GenerationResult)
    assert result.output == "written by local/qwen3.6"
    assert result.model_used == "local/qwen3.6"
    assert result.fell_back is False
    assert result.error is None


def test_local_raises_falls_back_to_frontier():
    """Local model raises → frontier runs, fall-back flagged, error captured."""
    def fn(model):
        if model == "local/qwen3.6":
            raise RuntimeError("local server timed out")
        return f"written by {model}"

    result = run_with_fallback(
        fn,
        local_model="local/qwen3.6",
        fallback_model="frontier/claude",
    )
    assert result.output == "written by frontier/claude"
    assert result.model_used == "frontier/claude"
    assert result.fell_back is True
    assert "timed out" in result.error


def test_local_fails_validation_falls_back():
    """Local output that fails validate() is treated as a failure → fallback."""
    def fn(model):
        # Local returns unusable empty content; frontier returns good content.
        return "" if model == "local/qwen3.6" else "proper article"

    result = run_with_fallback(
        fn,
        local_model="local/qwen3.6",
        fallback_model="frontier/claude",
        validate=lambda out: bool(out and out.strip()),
    )
    assert result.output == "proper article"
    assert result.model_used == "frontier/claude"
    assert result.fell_back is True
    assert result.error  # a non-empty reason recorded for the feedback loop


def test_both_fail_raises():
    """If local AND frontier both fail, the wrapper raises — no silent dud."""
    def fn(model):
        raise RuntimeError(f"{model} is down")

    with pytest.raises(RuntimeError):
        run_with_fallback(
            fn,
            local_model="local/qwen3.6",
            fallback_model="frontier/claude",
        )


def test_default_validation_rejects_falsy_output():
    """With no explicit validate, a falsy local result triggers fallback."""
    def fn(model):
        return None if model == "local/qwen3.6" else "ok"

    result = run_with_fallback(
        fn,
        local_model="local/qwen3.6",
        fallback_model="frontier/claude",
    )
    assert result.fell_back is True
    assert result.model_used == "frontier/claude"


def test_get_litellm_llm_binds_model_and_proxy():
    """The factory builds a ChatOpenAI for the given route with no network I/O."""
    from langchain_openai import ChatOpenAI

    from content_pipeline.content_config import content_cfg
    from content_pipeline.providers.litellm import get_litellm_llm

    llm = get_litellm_llm("m3/mlx/qwen3.6-35b-a3b-unsloth-8bit")
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit"
    # Bound to the LiteLLM proxy, not OpenAI cloud.
    assert content_cfg.litellm_base_url in str(llm.openai_api_base)
