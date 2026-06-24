"""Offline tests for the pipeline narration module.

The TTS call (`speak`) is injected, so these run with no network and no ffmpeg
dependency on the synth side — exactly like the image tests inject the OpenAI client.
"""
import array
import io
import json
import math
import os
import time
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
    assert ref_text.strip()   # a real transcript resolves (content varies as the ref is retuned)


def test_resolve_voice_tom_points_at_his_reference():
    ref_audio, ref_text = audio.resolve_voice("tom")
    assert ref_audio == content_cfg.tom_ref_audio
    assert "Shropshire" in ref_text   # the retuned, upbeat Tom ref (was the sombre war story)


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


def test_narrate_text_runs_chunks_concurrently_when_configured(monkeypatch):
    # With concurrency, N slow chunks should overlap rather than sum up. Each chunk
    # sleeps 0.1s; serial = 0.6s, 6-wide ≈ 0.1s. A generous threshold avoids CI flakiness
    # while still failing hard if synthesis is sequential.
    monkeypatch.setattr(content_cfg, "narrate_tts_concurrency", 6)

    def _slow(text, ref_audio, ref_text):
        time.sleep(0.1)
        return ("WAV:" + text).encode()

    text = "\n\n".join(f"Chunk {i}." for i in range(6))
    t0 = time.time()
    wavs = audio.narrate_text(text, "graham", speak=_slow)
    elapsed = time.time() - t0
    assert len(wavs) == 6
    assert elapsed < 0.35, f"expected concurrent synthesis, took {elapsed:.2f}s (serial ~0.6s)"


def test_narrate_text_concurrency_preserves_chunk_order(monkeypatch):
    # The FIRST chunk synthesises slower than the second; an unordered gather would swap
    # them. ThreadPoolExecutor.map must keep the stitch order = input order.
    monkeypatch.setattr(content_cfg, "narrate_tts_concurrency", 2)
    delays = {"First chunk.": 0.15, "Second chunk.": 0.0}

    def _speak(text, ref_audio, ref_text):
        time.sleep(delays.get(text, 0.0))
        return ("WAV:" + text).encode()

    wavs = audio.narrate_text("First chunk.\n\nSecond chunk.", "graham", speak=_speak)
    assert [w.decode() for w in wavs] == ["WAV:First chunk.", "WAV:Second chunk."]


def test_render_podcast_renders_with_concurrency(tmp_path, monkeypatch):
    # Concurrency must not break the podcast stitch: every chunk is still synthesised and
    # one file is produced.
    monkeypatch.setattr(content_cfg, "narrate_tts_concurrency", 4)
    calls = []
    turns = [("graham", "One. Two. Three. Four."), ("tom", "Five. Six.")]
    path, _ = audio.render_podcast(turns, out_dir=str(tmp_path), speak=_fake_speak(calls))
    assert os.path.exists(path)
    assert len(calls) >= 2   # both turns' chunks were synthesised


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return _wav()


def _capture_post(monkeypatch, captured):
    def _fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp()
    monkeypatch.setattr(audio.urllib.request, "urlopen", _fake_urlopen)


def test_default_speak_sends_deterministic_generation_params(monkeypatch):
    # The server default temperature 0.7 makes TTS truncate/run away; we PIN generation so
    # the same chunk reproduces the same reading. Greedy 0.0 is the stable default.
    monkeypatch.setattr(content_cfg, "narrate_tts_temperature", 0.0)
    monkeypatch.setattr(content_cfg, "narrate_tts_repetition_penalty", 1.1)
    monkeypatch.setattr(content_cfg, "narrate_tts_max_tokens", 800)
    captured = {}
    _capture_post(monkeypatch, captured)
    spk = audio._default_speak(base_url="http://m3:8081/v1", model="qwen-tts")
    spk("Hello there.", "/ref.wav", "ref text")
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["repetition_penalty"] == 1.1
    assert captured["body"]["max_tokens"] == 800


def test_default_speak_omits_unset_generation_params(monkeypatch):
    # repetition_penalty / max_tokens of 0 mean "don't send — use the server default";
    # temperature is always sent (0.0 is a meaningful value, not "unset").
    monkeypatch.setattr(content_cfg, "narrate_tts_temperature", 0.0)
    monkeypatch.setattr(content_cfg, "narrate_tts_repetition_penalty", 0)
    monkeypatch.setattr(content_cfg, "narrate_tts_max_tokens", 0)
    captured = {}
    _capture_post(monkeypatch, captured)
    spk = audio._default_speak(base_url="http://m3:8081/v1", model="qwen-tts")
    spk("Hello.", "/ref.wav", "ref")
    assert captured["body"]["temperature"] == 0.0
    assert "repetition_penalty" not in captured["body"]
    assert "max_tokens" not in captured["body"]


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


def test_render_podcast_tops_and_tails_with_the_jingle(tmp_path):
    # The same speech rendered WITH the jingle is materially longer than without it
    # (the trad bookend adds ~10s of audio around the speech). Separate out_dirs so the
    # content-addressed filenames don't collide and overwrite each other.
    turns = [("graham", "Welcome to the show.")]
    with_jingle, _ = audio.render_podcast(turns, out_dir=str(tmp_path / "a"), speak=_fake_speak([]))
    without_jingle, _ = audio.render_podcast(
        turns, out_dir=str(tmp_path / "b"), speak=_fake_speak([]), add_jingle=False)
    assert os.path.exists(with_jingle)
    assert os.path.getsize(with_jingle) > os.path.getsize(without_jingle)


def test_craicgpt_ie_is_pronounced_as_a_spoken_url():
    spoken = audio._phonetic("Come back to craicgpt.ie tomorrow")
    assert "Crack Gee Pee Tee dot Eye Ee" in spoken
    assert "craicgpt.ie" not in spoken.lower()


def test_has_clone_gates_parody_on_availability(monkeypatch):
    assert audio.has_clone("graham") and audio.has_clone("tom")
    assert not audio.has_clone("nobody")
    monkeypatch.setattr(content_cfg, "available_parody_voices", "")
    assert not audio.has_clone("ronald_dump")            # ref not deployed -> not usable
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump, a_dell")
    assert audio.has_clone("ronald_dump") and audio.has_clone("a_dell")
    assert not audio.has_clone("bonio")


def test_resolve_voice_parody_uses_base_dir_and_repo_transcript():
    ref_audio, ref_text = audio.resolve_voice("ronald_dump")
    assert ref_audio == os.path.join(content_cfg.voice_ref_base, "ronald_dump", "ref.wav")
    assert ref_text and len(ref_text) > 10              # transcript ships in voice_refs/


# --------------------------------------------------------------------------- #
# Mastering chain: per-chunk leveling, seam crossfades, the ffmpeg master pass
# --------------------------------------------------------------------------- #
def _sine_wav(amp, seconds=0.3, fr=24000, freq=220.0):
    """A mono 16-bit tone — a non-silent fixture for level/peak assertions."""
    n = int(fr * seconds)
    data = array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / fr)) for i in range(n)))
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(fr)
    w.writeframes(data.tobytes())
    w.close()
    return buf.getvalue()


def _samples(wav_bytes):
    w = wave.open(io.BytesIO(wav_bytes), "rb")
    data = array.array("h")
    data.frombytes(w.readframes(w.getnframes()))
    w.close()
    return data


def _rms_of(wav_bytes):
    d = _samples(wav_bytes)
    return (sum(s * s for s in d) / len(d)) ** 0.5 if d else 0.0


def _peak_of(wav_bytes):
    return max((abs(s) for s in _samples(wav_bytes)), default=0)


def _frames(wav_bytes):
    w = wave.open(io.BytesIO(wav_bytes), "rb")
    n = w.getnframes()
    w.close()
    return n


def test_rms_normalize_balances_quiet_and_loud_to_a_common_level():
    # A quiet chunk and a loud chunk are pulled to the SAME band — this is what stops
    # one voice (or one boxy chunk) dominating the next when the clip is stitched.
    quiet = audio._rms_normalize(_sine_wav(2000))
    loud = audio._rms_normalize(_sine_wav(8000))
    rq, rl = _rms_of(quiet), _rms_of(loud)
    assert abs(rq - rl) / max(rq, rl) < 0.1
    ceiling = 32768 * 10 ** (-1.0 / 20)                 # the -1 dBFS peak ceiling
    assert _peak_of(quiet) <= ceiling + 1
    assert _peak_of(loud) <= ceiling + 1


def test_rms_normalize_leaves_silence_untouched():
    sil = _wav()                                        # all zeros -> no divide-by-zero, no gain
    assert audio._rms_normalize(sil) == sil


def test_crossfade_concat_overlaps_the_seam():
    a, b = _sine_wav(6000), _sine_wav(6000)
    out = audio._crossfade_concat([a, b], fade_ms=35)
    fade = int(24000 * 0.035)
    assert _frames(out) == _frames(a) + _frames(b) - fade   # the seam overlaps, not butt-joins


def test_crossfade_concat_butt_joins_when_chunks_too_short():
    a, b = _wav(seconds=0.01), _wav(seconds=0.01)       # shorter than the fade window
    out = audio._crossfade_concat([a, b], fade_ms=35)
    assert _frames(out) == _frames(a) + _frames(b)      # falls back to a plain concat


def test_crossfade_concat_single_chunk_is_identity():
    a = _sine_wav(6000)
    assert audio._crossfade_concat([a]) == a


@pytest.mark.skipif(not audio.find_ffmpeg(), reason="needs ffmpeg")
def test_overlap_mix_brings_the_voice_in_over_the_jingle_tail():
    # The voice enters overlap_sec before the (1.5s) jingle ends, mixed on top — so the
    # head is SHORTER than a sequential join by ~overlap_sec (no dead air, no gap).
    jingle = _sine_wav(8000, seconds=1.5)
    speech = _sine_wav(6000, seconds=1.0)
    head = audio._overlap_mix(jingle, speech, overlap_sec=0.5)
    assert head is not None
    seq = _frames(jingle) + _frames(speech)
    overlap_frames = int(0.5 * 24000)
    assert _frames(head) < seq                       # the seam overlaps, not butt-joins
    assert abs(_frames(head) - (seq - overlap_frames)) < int(0.1 * 24000)


def test_master_wav_is_a_noop_on_subsecond_clips():
    clip = _wav(seconds=0.05)                           # too short to master -> unchanged
    assert audio.master_wav(clip) == clip               # keeps unit tests offline & deterministic


def test_master_wav_disabled_returns_input(monkeypatch):
    monkeypatch.setattr(content_cfg, "audio_master", "none")
    clip = _sine_wav(6000, seconds=1.5)
    assert audio.master_wav(clip) == clip


@pytest.mark.skipif(not audio.find_ffmpeg(), reason="needs ffmpeg")
def test_master_wav_smoke_preserves_format(monkeypatch):
    monkeypatch.setattr(content_cfg, "audio_master", "ffmpeg")
    src = _sine_wav(8000, seconds=1.5)
    out = audio.master_wav(src)
    wi = wave.open(io.BytesIO(src), "rb")
    wo = wave.open(io.BytesIO(out), "rb")
    assert (wo.getframerate(), wo.getnchannels(), wo.getsampwidth()) == \
           (wi.getframerate(), wi.getnchannels(), wi.getsampwidth())
    assert wo.getnframes() > 0
    wi.close()
    wo.close()


def test_render_podcast_voices_a_deployed_parody_clone(tmp_path, monkeypatch):
    # A deployed parody guest must read in ITS OWN voice in the podcast, not Graham's.
    monkeypatch.setattr(content_cfg, "available_parody_voices", "ronald_dump")
    calls = []
    turns = [("graham", "Welcome."), ("ronald_dump", "The best, believe me."), ("tom", "Mad.")]
    audio.render_podcast(turns, out_dir=str(tmp_path), speak=_fake_speak(calls))
    refs = [c["ref_audio"] for c in calls]
    assert os.path.join(content_cfg.voice_ref_base, "ronald_dump", "ref.wav") in refs
    assert content_cfg.graham_ref_audio in refs and content_cfg.tom_ref_audio in refs


def test_render_podcast_unknown_or_undeployed_voice_falls_back_to_graham(tmp_path, monkeypatch):
    monkeypatch.setattr(content_cfg, "available_parody_voices", "")   # ronald NOT deployed
    calls = []
    audio.render_podcast([("ronald_dump", "Believe me.")], out_dir=str(tmp_path),
                         speak=_fake_speak(calls))
    assert calls[0]["ref_audio"] == content_cfg.graham_ref_audio      # safe fallback


# --------------------------------------------------------------------------- #
# Multi-lingual: language-aware phonetics + CJK chunking
# --------------------------------------------------------------------------- #
def test_phonetic_is_language_aware():
    # English: the Irish 'craic'→'crack' rule and the spelled-out site URL both apply.
    assert audio._phonetic("the craic was great") == "the crack was great"
    # German: the bare 'craic'→'crack' rule is NOT applied (it would corrupt other prose);
    # the brand URL still localises its connector ('dot'→'Punkt').
    de = audio._phonetic("besuche craicgpt.ie morgen", "de")
    assert "Punkt" in de and "craicgpt.ie" not in de.lower()
    assert audio._phonetic("der craic ist gut", "de") == "der craic ist gut"   # untouched


def test_phonetic_unknown_language_falls_back_to_english():
    assert audio._phonetic("the craic", "xx") == "the crack"


def test_chunk_text_splits_on_cjk_sentence_punctuation():
    # A long spaceless Japanese paragraph splits on 。 sentence breaks (not one giant chunk).
    para = "これはテストです。" * 100
    chunks = audio.chunk_text(para, max_chars=80)
    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)


def test_narrate_text_applies_language_phonetics_before_speak():
    calls = []
    audio.narrate_text("Visit craicgpt.ie", "graham", speak=_fake_speak(calls), language="de")
    assert "Punkt" in calls[0]["text"]               # German URL readout reaches the synth call
