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


def _ai_pool(n):
    """n validated AI candidates with real source links, in significance order."""
    return [
        {"title": f"Story {i}", "summary": f"s{i}", "source_url": f"https://e.com/{i}",
         "key_points": ["a", "b"], "conclusion": f"c{i}"}
        for i in range(n)
    ]


def test_write_ai_section_fills_exactly_the_target_counts_from_the_full_pool():
    # THE RCA regression: 1 headliner + 2 subs + 10 shorts = 13 needed; a pool of
    # 33 must yield exactly 10 shorts, ONE write call per item (no single-shot clip).
    calls = {"n": 0}

    def gen(prompt):
        calls["n"] += 1
        return {"title": "T", "standfirst": "sf", "body": "B"}

    out = write_ai_section(_ai_pool(33), num_subarticles=2, num_shorts=10, generate=gen)
    assert out["headliner"]["title"] == "T"
    assert out["headliner"]["standfirst"] == "sf"
    assert len(out["subarticles"]) == 2
    assert len(out["shorts"]) == 10  # never under-fills below the target
    assert calls["n"] == 13  # one call per produced item, nothing wasted


def test_write_ai_section_re_stamps_the_candidate_source_url():
    def gen(prompt):
        # model omits the link (and could even invent one) — the writer puts the real back
        return {"title": "T", "body": "B", "source_url": "https://hallucinated.example/x"}

    out = write_ai_section(_ai_pool(13), num_subarticles=2, num_shorts=10, generate=gen)
    assert out["headliner"]["source_url"] == "https://e.com/0"
    assert all(s["source_url"].startswith("https://e.com/") for s in out["shorts"])


def test_write_ai_section_draws_deeper_when_an_item_write_fails():
    # A flaky item must not leave the section short — the loop draws the next candidate.
    calls = {"n": 0}

    def gen(prompt):
        calls["n"] += 1
        if calls["n"] == 2:  # second item write blows up
            raise RuntimeError("model hiccup")
        return {"title": "T", "body": "B", "standfirst": "sf"}

    out = write_ai_section(_ai_pool(20), num_subarticles=2, num_shorts=10, generate=gen)
    assert len(out["shorts"]) == 10  # still full despite the one failure


def test_write_ai_section_passes_one_candidate_into_each_prompt():
    seen = []

    def gen(prompt):
        seen.append(prompt)
        return {"title": "H", "body": "b", "standfirst": "s"}

    write_ai_section(
        [{"title": "DeepSeek V4 drops", "source_url": "https://e.com/x"}],
        num_subarticles=0, num_shorts=0, generate=gen,
    )
    assert "DeepSeek V4 drops" in seen[0]  # the one candidate reached its own prompt


def test_write_fun_story_credits_creator_and_keeps_source_url():
    captured = {}

    def gen(prompt):
        captured["prompt"] = prompt
        return {"title": "Foil Arms and Hog Nail the Phone Call", "body": "...", "source_url": ""}

    cand = {"title": "Every Irish Mammy on the Phone", "summary": "",
            "source_url": "https://www.youtube.com/watch?v=VID1"}
    out = write_fun_story(cand, "Foil Arms and Hog", generate=gen)
    # The creator is name-checked in the prompt and we write in GRAHAM'S voice,
    # explicitly NOT impersonating the creator.
    assert "Foil Arms and Hog" in captured["prompt"]
    assert "scripting paddy" in captured["prompt"].lower()
    assert "not impersonating" in captured["prompt"].lower()
    # URL fidelity: falls back to the creator's real URL when the model omits it.
    assert out["source_url"] == "https://www.youtube.com/watch?v=VID1"
    # The creator's name is carried onto the piece as the credit.
    assert out["source"] == "Foil Arms and Hog"
    # No persona requested → no persona field (the legacy/fallback house-voice path).
    assert "persona" not in out


def test_write_fun_story_persona_voices_celebrity_while_crediting_creator():
    captured = {}

    def gen(prompt):
        captured["prompt"] = prompt
        return {"title": "BEHOLD, THE MIGHTY PHONE CALL", "body": "...", "source_url": ""}

    cand = {"title": "Every Irish Mammy on the Phone", "summary": "",
            "source_url": "https://www.youtube.com/watch?v=VID1"}
    out = write_fun_story(cand, "Foil Arms and Hog", persona="Jack Blarney", generate=gen)
    # Written in the assigned celebrity's comic VOICE (its brief is injected)...
    assert "Jack Blarney" in captured["prompt"]
    assert "comic voice" in captured["prompt"].lower()
    assert "rock-and-roll" in captured["prompt"].lower()   # from Jack Black's voice_brief
    # ...while STILL crediting the real creator and keeping their real URL.
    assert "Foil Arms and Hog" in captured["prompt"]
    assert out["source"] == "Foil Arms and Hog"            # creator credit kept
    assert out["persona"] == "Jack Blarney"                # voice carried for byline + disclaimer
    assert out["source_url"] == "https://www.youtube.com/watch?v=VID1"


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
    # 2 re-samples on the primary, THEN 2 on the cross-box fallback, before giving up.
    assert calls["n"] == 4


def test_default_generate_falls_back_to_other_box_on_connection_error(monkeypatch):
    # A DGX connection drop must NOT crash the run — it falls back to FALLBACK_TEXT_MODEL
    # on the M3 (run_with_fallback). The primary raises like a real litellm 500; the
    # fallback box returns valid JSON.
    from content_pipeline.generate import writer
    from content_pipeline.providers import litellm as litellm_mod

    seen = []

    class _LLM:
        def __init__(self, model):
            self.model = model

        def invoke(self, prompt):
            seen.append(self.model)
            if self.model == writer.content_cfg.write_model:
                raise RuntimeError("Cannot connect to host 192.168.50.13:8003")
            return _Resp('{"headliner": {"title": "H"}}')

    monkeypatch.setattr(litellm_mod, "get_litellm_llm", lambda model, **k: _LLM(model))
    out = writer._default_generate("prompt")
    assert out == {"headliner": {"title": "H"}}
    assert seen[0] == writer.content_cfg.write_model               # tried the DGX first
    assert seen[-1] == writer.content_cfg.fallback_text_model      # then the M3 fallback
