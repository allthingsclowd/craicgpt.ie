"""Offline tests for the deterministic jingle synth (generate/jingle.py).

The jingle is the show's audio branding: a few bars of *Whiskey in the Jar*
(trad, public domain; our own arrangement), rendered in pure stdlib so the same
notes always produce the same bytes — no network, no music model, no licence.
ffmpeg is only needed for the MP3/fade convenience wrapper; the core synth is
stdlib-only so these tests run anywhere.
"""
import io
import wave

import pytest

from content_pipeline.generate import jingle


def _read_wav(b: bytes):
    w = wave.open(io.BytesIO(b), "rb")
    try:
        return {
            "nchannels": w.getnchannels(),
            "sampwidth": w.getsampwidth(),
            "framerate": w.getframerate(),
            "nframes": w.getnframes(),
            "frames": w.readframes(w.getnframes()),
        }
    finally:
        w.close()


def test_note_to_freq_equal_temperament():
    assert abs(jingle.note_to_freq("A4") - 440.0) < 0.01
    assert abs(jingle.note_to_freq("A5") - 880.0) < 0.01
    assert abs(jingle.note_to_freq("G4") - 392.0) < 0.5


def test_note_to_midi_parses_accidentals_and_octaves():
    assert jingle.note_to_midi("A4") == 69
    assert jingle.note_to_midi("C#5") == 73
    assert jingle.note_to_midi("Bb4") == 70
    assert jingle.note_to_midi("G4") == 67


def test_synth_melody_is_valid_mono_24k_wav():
    info = _read_wav(jingle.synth_melody())
    assert info["nchannels"] == 1
    assert info["sampwidth"] == 2
    assert info["framerate"] == jingle.DEF_SAMPLE_RATE == 24000
    assert info["nframes"] > 0


def test_synth_melody_duration_tracks_tempo():
    melody = [("G4", 1.0), ("A4", 1.0), ("B4", 2.0)]  # 4 beats
    bpm = 120  # 2 beats/sec -> 2.0 seconds
    info = _read_wav(jingle.synth_melody(melody, bpm=bpm))
    seconds = info["nframes"] / info["framerate"]
    assert abs(seconds - 2.0) < 0.2


def test_synth_melody_is_deterministic():
    assert jingle.synth_melody() == jingle.synth_melody()


def test_rest_is_silence():
    info = _read_wav(jingle.synth_melody([("R", 0.5)], bpm=120))
    # 0.5 beats at 120bpm = 0.25s of pure silence
    assert info["nframes"] == pytest.approx(0.25 * 24000, abs=2)
    assert set(info["frames"]) == {0}


def test_default_tune_is_about_five_bars_long():
    # ~5 bars of 4/4 at the default tempo -> a short jingle, not a full song.
    info = _read_wav(jingle.synth_melody())
    seconds = info["nframes"] / info["framerate"]
    assert 7.0 < seconds < 14.0


def test_render_jingle_writes_a_file(tmp_path):
    path, name = jingle.render_jingle(out_dir=str(tmp_path))
    import os

    assert os.path.exists(path)
    assert name == "whiskey-in-the-jar"
    assert path.lower().endswith((".mp3", ".wav"))
