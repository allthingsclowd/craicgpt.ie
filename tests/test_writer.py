"""Tests for the deterministic article writer.

Editing moved out of the deep agent (whose single giant write_file call kept
getting mangled by the vLLM tool-call parser) into the harness: small plain-chat
→ JSON calls, one for the AI section and one per fun story. The LLM call is
injected here as `generate(prompt) -> dict`, so this runs offline.
"""

from content_pipeline.generate.writer import loads_lenient, write_ai_section, write_fun_story


def test_loads_lenient_strips_fences_and_thinking():
    assert loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}
    assert loads_lenient('<think>hmm</think>{"b": 2}') == {"b": 2}
    assert loads_lenient('prose then {"c": 3}') == {"c": 3}
    # Unclosed <think> preamble (thinking truncated) followed by JSON.
    assert loads_lenient('<think>let me reason a lot...\n{"d": 4}') == {"d": 4}


def test_write_ai_section_normalises_counts():
    def gen(prompt):
        return {
            "headliner": {"title": "H", "standfirst": "s", "body": "b", "source_url": "u"},
            "subarticles": [{"title": f"sub{i}", "body": "b", "source_url": "u"} for i in range(5)],
            "shorts": [{"title": f"sh{i}", "body": "b", "source_url": "u"} for i in range(20)],
        }

    out = write_ai_section([{"title": "cand"}], num_subarticles=2, num_shorts=10, generate=gen)
    assert out["headliner"]["title"] == "H"
    assert len(out["subarticles"]) == 2
    assert len(out["shorts"]) == 10


def test_write_ai_section_passes_candidates_into_prompt():
    seen = {}

    def gen(prompt):
        seen["prompt"] = prompt
        return {"headliner": {"title": "H"}, "subarticles": [], "shorts": []}

    write_ai_section([{"title": "DeepSeek V4 drops"}], num_subarticles=2, num_shorts=10, generate=gen)
    assert "DeepSeek V4 drops" in seen["prompt"]


def test_write_fun_story_keeps_source_url_and_persona_voice():
    captured = {}

    def gen(prompt):
        captured["prompt"] = prompt
        return {"title": "Tremendous Whale, Believe Me", "body": "...", "source_url": ""}

    cand = {"title": "Whale freed", "summary": "net cut", "source_url": "https://x/whale"}
    out = write_fun_story(cand, "Ronald Dump", "Trump style: 'believe me', 'tremendous'", generate=gen)
    # The persona + its voice brief reach the prompt.
    assert "Ronald Dump" in captured["prompt"]
    assert "tremendous" in captured["prompt"].lower()
    # Source URL falls back to the candidate's when the model omits it.
    assert out["source_url"] == "https://x/whale"


# --- _default_generate re-samples on unparseable JSON (the run-1 flake) ---------
class _Resp:
    def __init__(self, content):
        self.content = content


def test_default_generate_resamples_on_unparseable_json(monkeypatch):
    # The local model sometimes returns JSON the lenient parser can't recover; rather
    # than HOLD the edition, _default_generate re-samples. First sample is broken,
    # second is valid → it returns the parsed dict, having retried exactly once.
    from content_pipeline.generate import writer
    from content_pipeline.providers import litellm as litellm_mod

    calls = {"n": 0}

    class _LLM:
        def invoke(self, prompt):
            calls["n"] += 1
            return _Resp('{"headliner": broken' if calls["n"] == 1
                         else '{"headliner": {"title": "H"}}')

    monkeypatch.setattr(litellm_mod, "get_litellm_llm", lambda *a, **k: _LLM())
    out = writer._default_generate("prompt")
    assert out == {"headliner": {"title": "H"}}
    assert calls["n"] == 2  # one bad sample, then a successful re-sample


def test_default_generate_raises_after_exhausting_attempts(monkeypatch):
    import pytest

    from content_pipeline.generate import writer
    from content_pipeline.providers import litellm as litellm_mod

    calls = {"n": 0}

    class _LLM:
        def invoke(self, prompt):
            calls["n"] += 1
            return _Resp("not json at all {")

    monkeypatch.setattr(litellm_mod, "get_litellm_llm", lambda *a, **k: _LLM())
    with pytest.raises(ValueError):
        writer._default_generate("prompt", attempts=2)
    assert calls["n"] == 2  # tried the configured number of times, then gave up
