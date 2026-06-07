"""
content_pipeline/generate/jingle.py
===================================
The show's **audio branding**: our **original 80s synth-pop call sign** — the
sting that tops and tails every podcast (the full mix fades out into Graham's
cold-open; a stripped, resolved tag returns under the "back to craicgpt.ie
tomorrow" sign-off).

TUTORIAL: owning your brand — composed, sampled, licence-free
-------------------------------------------------------------
There is no "music model" in the loop. The hook is **our own composition**
(*Am–F–C–G at 124 BPM* — pulsing octave synth bass, gated-style drums,
synth-brass stabs, a saw lead and a polysynth pad), voiced through **Apple's
built-in sampled GM instruments** (the `gs_instruments.dls` bank that ships with
macOS / drives GarageBand). Real sampled instruments + our own notes =
recognisable, professional, and **zero copyright/royalties**. The bounce is
deterministic too: same arrangement in → same bytes out.

Why a committed asset (not pure stdlib like the rest of the pipeline): you can't
reproduce Apple's DLS samples in Python, so the sting is a **bounced WAV**
(`assets/jingle_80s_{intro,outro}.wav`, 24 kHz mono to match the TTS stitch). We
keep it *owned and reproducible* by shipping the full renderer in `jingle_src/`
(Swift + AVFoundation + the arrangement JSON) — `jingle_src/README.md` regenerates
the bytes from scratch on any Mac.

**Fallback (still in this module):** the original pure-stdlib *Whiskey in the Jar*
Karplus–Strong synth below. If the asset is ever missing the show degrades to a
clean public-domain trad pluck — **never silence**. ffmpeg (already a soft
narration dependency) is used only for the MP3 + fade convenience wrapper; the
fallback synth is stdlib-only so it runs anywhere the tests do.
"""

from __future__ import annotations

import array
import hashlib
import io
import os
import random
import subprocess
import tempfile
import wave
from typing import Optional

from content_pipeline.content_config import content_cfg
from content_pipeline.generate.audio import find_ffmpeg

# ── The 80s call-sign assets (the live sting) ─────────────────────────────────
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
INTRO_ASSET = os.path.join(_ASSET_DIR, "jingle_80s_intro.wav")   # full mix → tops the show
OUTRO_ASSET = os.path.join(_ASSET_DIR, "jingle_80s_outro.wav")   # stripped resolve → signs off


def _load_asset(path: str) -> Optional[bytes]:
    """Read a committed sting WAV, or ``None`` if it's missing (→ synth fallback)."""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def intro_jingle() -> bytes:
    """The show-open sting bytes: the 80s full mix, else the trad-synth fallback."""
    return _load_asset(INTRO_ASSET) or synth_melody()


def outro_jingle() -> bytes:
    """The sign-off sting bytes: the stripped 80s tag, else the trad-synth fallback."""
    return _load_asset(OUTRO_ASSET) or synth_melody()


DEF_SAMPLE_RATE = 24000  # matches the M3 mlx-audio TTS output, so clips stitch directly
DEF_BPM = 126            # a sprightly trad-session lilt (fallback synth)
_AMP = 0.72              # headroom so plucks never clip int16

Note = tuple  # (name, beats); name "R" is a rest

# ── The tune ──────────────────────────────────────────────────────────────────
# *Whiskey in the Jar* — the chorus hook ("musha ring dum-a-doo … whack for my
# daddy-o … there's whiskey in the jar"), trad / public domain; OUR arrangement
# in G major, ~5 bars of 4/4. (note, beats); "R" = rest.
WHISKEY_IN_THE_JAR: list[Note] = [
    # Bar 1 — "Mu-sha ring dum-a-doo, dum-a-da"
    ("D5", 0.5), ("D5", 0.5), ("D5", 0.5), ("D5", 0.5), ("B4", 0.5), ("A4", 0.5), ("G4", 1.0),
    # Bar 2 — "Whack for my dad-dy-o"
    ("D5", 0.5), ("D5", 0.5), ("B4", 0.5), ("A4", 0.5), ("G4", 1.0), ("R", 1.0),
    # Bar 3 — "Whack for my dad-dy-o"
    ("D5", 0.5), ("D5", 0.5), ("B4", 0.5), ("A4", 0.5), ("G4", 1.0), ("R", 1.0),
    # Bar 4 — "There's whis-key in the jar-o"
    ("E5", 0.5), ("D5", 0.5), ("B4", 0.5), ("A4", 0.5), ("G4", 0.5), ("A4", 0.5), ("B4", 1.0),
    # Bar 5 — resolve and ring out
    ("A4", 1.0), ("G4", 2.0), ("R", 1.0),
]

_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


# ── Pitch helpers (equal temperament; A4 = 440 Hz = MIDI 69) ──────────────────
def note_to_midi(note: str) -> int:
    """``"A4" → 69``, ``"C#5" → 73``, ``"Bb4" → 70``. Raises on a rest/garbage."""
    s = (note or "").strip()
    if not s or s[0].upper() not in _SEMITONE:
        raise ValueError(f"not a pitch: {note!r}")
    semi = _SEMITONE[s[0].upper()]
    i = 1
    while i < len(s) and s[i] in "#b♯♭":
        semi += 1 if s[i] in "#♯" else -1
        i += 1
    octave = int(s[i:])
    return (octave + 1) * 12 + semi


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def note_to_freq(note: str) -> float:
    return midi_to_freq(note_to_midi(note))


# ── Synthesis ─────────────────────────────────────────────────────────────────
def karplus_strong(freq: float, dur_sec: float, sample_rate: int = DEF_SAMPLE_RATE,
                   *, seed: int = 0, decay: float = 0.996) -> list[int]:
    """One plucked-string note → int16 samples. Deterministic for a fixed ``seed``.

    A seeded noise burst of period ``sample_rate/freq`` is fed through a 2-tap
    averaging filter; the running average bleeds off the high harmonics so the
    string "rings down" like a pluck. The seed makes the excitation reproducible.
    """
    n = max(2, int(round(sample_rate / float(freq))))
    rng = random.Random(seed)
    buf = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    total = int(sample_rate * dur_sec)
    out: list[int] = []
    idx = 0
    for _ in range(total):
        cur = buf[idx]
        buf[idx] = decay * 0.5 * (cur + buf[(idx + 1) % n])
        out.append(int(max(-1.0, min(1.0, cur)) * 32767 * _AMP))
        idx = (idx + 1) % n
    _apply_envelope(out, sample_rate)
    return out


def _apply_envelope(samples: list[int], sample_rate: int,
                    attack_sec: float = 0.005, release_sec: float = 0.02) -> None:
    """In-place click-guard: short linear attack in, linear release out to zero."""
    a = min(len(samples), int(sample_rate * attack_sec))
    r = min(len(samples), int(sample_rate * release_sec))
    for k in range(a):
        samples[k] = int(samples[k] * (k / a))
    for k in range(r):
        samples[-1 - k] = int(samples[-1 - k] * (k / r))


def _wav_bytes(int_samples: list[int], sample_rate: int) -> bytes:
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sample_rate)
    w.writeframes(array.array("h", int_samples).tobytes())
    w.close()
    return buf.getvalue()


def synth_melody(melody: Optional[list[Note]] = None, *, bpm: int = DEF_BPM,
                 sample_rate: int = DEF_SAMPLE_RATE) -> bytes:
    """Render ``melody`` (defaults to *Whiskey in the Jar*) to mono 16-bit WAV bytes.

    Deterministic: rests are exact silence, and each note's pluck is seeded by its
    position, so the same melody always yields byte-identical audio.
    """
    melody = melody if melody is not None else WHISKEY_IN_THE_JAR
    spb = 60.0 / float(bpm)  # seconds per beat
    samples: list[int] = []
    for i, (note, beats) in enumerate(melody):
        dur = beats * spb
        if str(note).strip().upper() == "R":
            samples.extend([0] * int(sample_rate * dur))
        else:
            samples.extend(karplus_strong(note_to_freq(note), dur, sample_rate, seed=i + 1))
    return _wav_bytes(samples, sample_rate)


# ── Convenience: a standalone, faded jingle file (MP3 via ffmpeg, else WAV) ────
def render_jingle(out_dir: Optional[str] = None, *, melody: Optional[list[Note]] = None,
                  bpm: int = DEF_BPM, sample_rate: int = DEF_SAMPLE_RATE,
                  fade_in_sec: float = 0.0, fade_out_sec: float = 1.2,
                  basename: str = "whiskey-in-the-jar") -> tuple[str, str]:
    """Write a content-addressed jingle clip and return ``(path, tune_name)``.

    With ffmpeg: an MP3 with the requested fade(s). Without ffmpeg: a plain WAV
    (no fade) — callers degrade gracefully, exactly like the narration path.
    """
    melody = melody if melody is not None else WHISKEY_IN_THE_JAR
    wav = synth_melody(melody, bpm=bpm, sample_rate=sample_rate)
    out_dir = out_dir or content_cfg.audio_dir
    os.makedirs(out_dir, exist_ok=True)
    key = hashlib.sha256(
        f"{basename}|{bpm}|{sample_rate}|{fade_in_sec}|{fade_out_sec}|{melody}".encode()
    ).hexdigest()[:16]

    ff = find_ffmpeg()
    if ff:
        dur = sum(float(b) for _, b in melody) * 60.0 / float(bpm)
        af = _fade_filter(dur, fade_in_sec, fade_out_sec)
        in_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
                fin.write(wav)
                in_path = fin.name
            out_path = os.path.join(out_dir, f"{basename}-{key}.mp3")
            subprocess.run([ff, "-y", "-i", in_path, "-af", af,
                            "-c:a", "libmp3lame", "-b:a", "96k", out_path],
                           check=True, capture_output=True)
            return out_path, basename
        except subprocess.CalledProcessError:
            pass  # fall through to plain WAV
        finally:
            if in_path and os.path.exists(in_path):
                os.remove(in_path)

    out_path = os.path.join(out_dir, f"{basename}-{key}.wav")
    with open(out_path, "wb") as fh:
        fh.write(wav)
    return out_path, basename


def _fade_filter(dur: float, fade_in_sec: float, fade_out_sec: float) -> str:
    parts = []
    if fade_in_sec > 0:
        parts.append(f"afade=t=in:st=0:d={fade_in_sec}")
    if fade_out_sec > 0:
        parts.append(f"afade=t=out:st={max(0.0, dur - fade_out_sec):.3f}:d={fade_out_sec}")
    return ",".join(parts) or "anull"
