"""Offline tests for the pipeline narration module.

The TTS call (`speak`) is injected, so these run with no network and no ffmpeg
dependency on the synth side — exactly like the image tests inject the OpenAI client.
"""
import io
import os
import wave

import pytest

from content_pipeline.generate import audio
from content_pipeline.content_config import content_cfg


def _wav(seconds=0.05, fr=24000):
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(fr)
    w.writeframes(b"\x00\x00" * int(fr * seconds))
    w.close()
    return buf.getvalue()


def _fake_speak(calls):
    def _s(text, ref_audio, ref_text):
        calls.append({"text": text, "ref_audio": ref_audio, "ref_text": ref_text})
        return _wav()
    return _s


def test_resolve_voice_graham_points_at_locked_reference():
    ref_audio, ref_text = audio.resolve_voice("graham")
    assert ref_audio == content_cfg.graham_ref_audio
    assert "Shane" in ref_text


def test_resolve_voice_tom_points_at_his_reference():
    ref_audio, ref_text = audio.resolve_voice("tom")
    assert ref_audio == content_cfg.tom_ref_audio
    assert "Afghanistan" in ref_text


def test_resolve_voice_unknown_raises():
    with pytest.raises(KeyError):
        audio.resolve_voice("nobody")


def test_narrate_text_synthesizes_each_chunk_in_the_named_voice():
    calls = []
    wavs = audio.narrate_text("Hello there.\n\nSecond bit.", "tom", speak=_fake_speak(calls))
    assert len(calls) == 2
    assert all(c["ref_audio"] == content_cfg.tom_ref_audio for c in calls)
    assert [c["text"] for c in calls] == ["Hello there.", "Second bit."]
    assert len(wavs) == 2


def test_narrate_article_writes_a_file_and_reports_the_model(tmp_path):
    calls = []
    item = {"title": "Big News", "body": "The robots learned to read.\n\nThen they read a whole book."}
    path, model = audio.narrate_article(
        item, voice="graham", out_dir=str(tmp_path), speak=_fake_speak(calls)
    )
    assert os.path.exists(path)
    assert model == content_cfg.audio_tts_model
    assert calls and all(c["ref_audio"] == content_cfg.graham_ref_audio for c in calls)
    spoken = " ".join(c["text"] for c in calls)
    assert "robots learned to read" in spoken
    assert "Big News" in spoken  # the headline is announced before the body


def test_render_podcast_uses_each_speakers_voice_and_writes_one_file(tmp_path):
    calls = []
    turns = [("graham", "Welcome to the show."), ("tom", "Howya!")]
    path, model = audio.render_podcast(turns, out_dir=str(tmp_path), speak=_fake_speak(calls))
    assert os.path.exists(path)
    assert model == content_cfg.audio_tts_model
    assert [c["ref_audio"] for c in calls] == [
        content_cfg.graham_ref_audio,
        content_cfg.tom_ref_audio,
    ]
