"""
content_pipeline/generate/audio.py
==================================
Narration via the grazlab **M3 mlx-audio** server (Qwen3-TTS-12Hz Base, a Full-ICL
voice clone). Produces (a) a per-article reading in Graham's voice — an accessibility
feature so blind / low-vision readers can *listen* to every piece — and (b) the
multi-voice daily **dad↔son podcast** (Graham reading, Tom and Graham bantering).

TUTORIAL: deterministic vs probabilistic
----------------------------------------
This whole module is the DETERMINISTIC half of narration: chunk → synth → stitch →
upload. Same text in, same audio request out — no LLM in the loop. The PROBABILISTIC
half (writing the dad↔son banter) lives in ``podcast_script.py`` and is judged by the
deepagents rubric before a single word is voiced. Keeping the mechanical work in code
and the judgement behind a rubric is the core CraicGPT pattern (see CLAUDE.md).

Why a direct POST and not the LiteLLM proxy: the mlx-audio clone takes a CUSTOM body
(``ref_audio`` + ``ref_text``, the Full-ICL pair), which is not the OpenAI
``/audio/speech`` shape — so, unlike chat/images, we talk to the M3 directly. The
reference WAVs live on the M3 (read by path); their transcripts ship in ``voice_refs/``.
The ``speak`` callable is injectable, so the chunk/stitch logic is unit-testable offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import wave
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

_VOICE_REFS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_refs")

# Voice key → (content_cfg attribute holding the M3-side ref WAV path, transcript file).
_VOICES = {
    "graham": ("graham_ref_audio", "graham.txt"),
    "tom": ("tom_ref_audio", "tom.txt"),
}

DEF_MAX_CHARS = 600
DEF_GAP_SEC = 0.4

Speak = Callable[[str, str, str], bytes]  # (text, ref_audio, ref_text) -> WAV bytes


# --------------------------------------------------------------------------- #
# Voice registry
# --------------------------------------------------------------------------- #
def resolve_voice(name: str) -> tuple[str, str]:
    """Return ``(ref_audio_path, ref_text)`` for a voice. Raises KeyError if unknown."""
    key = (name or "").strip().lower()
    if key not in _VOICES:
        raise KeyError(f"unknown voice {name!r}; known: {', '.join(sorted(_VOICES))}")
    attr, fname = _VOICES[key]
    ref_audio = getattr(content_cfg, attr)
    with open(os.path.join(_VOICE_REFS_DIR, fname)) as fh:
        ref_text = fh.read().strip()
    return ref_audio, ref_text


# --------------------------------------------------------------------------- #
# Text prep + synthesis (the mlx-audio contract, mirrored from the narrate skill)
# --------------------------------------------------------------------------- #
def strip_markdown(t: str) -> str:
    t = re.sub(r"```.*?```", "", t, flags=re.DOTALL)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"[*_`>]", "", t)
    return t


def chunk_text(text: str, max_chars: int = DEF_MAX_CHARS) -> list[str]:
    """Split on paragraph then sentence boundaries to stay under the TTS token cap."""
    chunks: list[str] = []
    for p in (x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()):
        p = " ".join(p.split())
        if len(p) <= max_chars:
            chunks.append(p)
            continue
        cur = ""
        for s in re.split(r"(?<=[.!?])\s+", p):
            if cur and len(cur) + len(s) + 1 > max_chars:
                chunks.append(cur.strip())
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur.strip():
            chunks.append(cur.strip())
    return chunks


# Phonetic fixes applied to the SPOKEN text only (the on-screen transcript keeps the real
# spelling). Irish "craic" is pronounced "crack"; the brand "CraicGPT" → "Crack Gee Pee
# Tee". Word-boundary, case-insensitive. CraicGPT MUST come before craic (longer match).
PRONUNCIATIONS = {
    r"\bcraicgpt\b": "Crack Gee Pee Tee",
    r"\bcraic\b": "crack",
}


def _phonetic(text: str) -> str:
    for pat, repl in PRONUNCIATIONS.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def _post_speech(base: str, model: str, ref_audio: str, ref_text: str, text: str,
                 timeout: float = 400) -> bytes:
    """POST one chunk to the M3 mlx-audio server and return raw WAV bytes."""
    body = {"model": model, "input": _phonetic(text), "ref_audio": ref_audio,
            "ref_text": ref_text, "response_format": "wav"}
    req = urllib.request.Request(base.rstrip("/") + "/audio/speech",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _default_speak(base_url: Optional[str] = None, model: Optional[str] = None) -> Speak:
    base = base_url or content_cfg.audio_tts_base_url
    model = model or content_cfg.audio_tts_model

    def _s(text: str, ref_audio: str, ref_text: str) -> bytes:
        return _post_speech(base, model, ref_audio, ref_text, text)

    return _s


# --------------------------------------------------------------------------- #
# WAV stitching (stdlib; MP3 via ffmpeg when present, else WAV)
# --------------------------------------------------------------------------- #
def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg") or next(
        (p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg")
         if os.path.exists(p)), None)


def concat_wavs(wavs: list[bytes], out_path: str) -> None:
    out = None
    for wb in wavs:
        w = wave.open(io.BytesIO(wb), "rb")
        if out is None:
            out = wave.open(out_path, "wb")
            out.setparams(w.getparams())
        out.writeframes(w.readframes(w.getnframes()))
        w.close()
    if out:
        out.close()


def silence_like(wav_bytes: bytes, seconds: float) -> bytes:
    w = wave.open(io.BytesIO(wav_bytes), "rb")
    p = w.getparams()
    n = int(p.framerate * seconds)
    buf = io.BytesIO()
    out = wave.open(buf, "wb")
    out.setparams(p)
    out.writeframes(b"\x00" * (n * p.sampwidth * p.nchannels))
    out.close()
    w.close()
    return buf.getvalue()


def to_mp3_or_wav(wavs: list[bytes], out_path: str) -> str:
    """Concat WAV chunks → out_path (.mp3 via ffmpeg, else .wav). Returns the real path."""
    ff = find_ffmpeg()
    if out_path.lower().endswith(".mp3") and ff:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp = tf.name
        concat_wavs(wavs, tmp)
        try:
            subprocess.run([ff, "-y", "-i", tmp, "-c:a", "libmp3lame", "-b:a", "96k", out_path],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError:
            wav_out = out_path[:-4] + ".wav"
            os.replace(tmp, wav_out)
            return wav_out
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return out_path
    if out_path.lower().endswith(".mp3"):
        out_path = out_path[:-4] + ".wav"
    concat_wavs(wavs, out_path)
    return out_path


def _concat_to_bytes(wavs: list[bytes]) -> bytes:
    """Concatenate WAV byte-chunks into one in-memory WAV (same params)."""
    if len(wavs) == 1:
        return wavs[0]
    buf = io.BytesIO()
    out = None
    for wb in wavs:
        w = wave.open(io.BytesIO(wb), "rb")
        if out is None:
            out = wave.open(buf, "wb")
            out.setparams(w.getparams())
        out.writeframes(w.readframes(w.getnframes()))
        w.close()
    out.close()
    return buf.getvalue()


def normalize_loudness(wav_bytes: bytes, *, target_i: float = -16.0, target_tp: float = -1.5,
                       target_lra: float = 11.0, min_seconds: float = 1.0) -> bytes:
    """Loudness-normalise a WAV to EBU R128 so every voice sits at the same level.

    No-op without ffmpeg, on clips shorter than ``min_seconds`` (also keeps unit tests
    offline), or on any ffmpeg error. Keeps the input's rate/channels/width so segments
    still concatenate. This is what balances Graham's and Tom's voices in the podcast.
    """
    try:
        w = wave.open(io.BytesIO(wav_bytes), "rb")
        rate, ch = w.getframerate(), w.getnchannels()
        dur = w.getnframes() / float(rate or 1)
        w.close()
    except Exception:
        return wav_bytes
    ff = find_ffmpeg()
    if not ff or dur < min_seconds:
        return wav_bytes
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(wav_bytes)
            in_path = fin.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
            out_path = fout.name
        subprocess.run(
            [ff, "-y", "-i", in_path, "-af",
             f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}",
             "-ar", str(rate), "-ac", str(ch), "-c:a", "pcm_s16le", out_path],
            check=True, capture_output=True)
        with open(out_path, "rb") as fh:
            return fh.read()
    except Exception:
        return wav_bytes
    finally:
        for p in (in_path, out_path):
            if p and os.path.exists(p):
                os.remove(p)


# --------------------------------------------------------------------------- #
# Public API: narrate text, an article, or a multi-voice podcast
# --------------------------------------------------------------------------- #
def narrate_text(text: str, voice: str, *, speak: Optional[Speak] = None,
                 base_url: Optional[str] = None, model: Optional[str] = None,
                 max_chars: int = DEF_MAX_CHARS) -> list[bytes]:
    """Synthesise ``text`` in ``voice`` → list of WAV byte-chunks."""
    ref_audio, ref_text = resolve_voice(voice)
    spk = speak or _default_speak(base_url, model)
    return [spk(c, ref_audio, ref_text) for c in chunk_text(strip_markdown(text), max_chars)]


def article_text(item: dict[str, Any]) -> str:
    """Compose the spoken form of an article: headline, then standfirst, then body."""
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def narrate_article(item: dict[str, Any], *, voice: str = "graham",
                    out_dir: Optional[str] = None, speak: Optional[Speak] = None,
                    base_url: Optional[str] = None, model: Optional[str] = None
                    ) -> tuple[str, str]:
    """Narrate one article (title + standfirst + body) in ``voice``.

    Writes a content-addressed MP3 (or WAV without ffmpeg) to the scratch dir and
    returns ``(local_path, model_used)`` — the same shape as ``images.save_image``.
    """
    text = article_text(item)
    wavs = narrate_text(text, voice, speak=speak, base_url=base_url, model=model)
    if not wavs:
        raise ValueError("no audio produced for article")
    clip = normalize_loudness(_concat_to_bytes(wavs))  # consistent level across articles
    out_dir = out_dir or content_cfg.audio_dir
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha256((voice + "|" + text).encode("utf-8")).hexdigest()[:16]
    path = to_mp3_or_wav([clip], os.path.join(out_dir, f"{voice}-{digest}.mp3"))
    return path, (model or content_cfg.audio_tts_model)


def render_podcast(turns: list[tuple[str, str]], *, out_dir: Optional[str] = None,
                   speak: Optional[Speak] = None, base_url: Optional[str] = None,
                   model: Optional[str] = None, gap_sec: float = DEF_GAP_SEC,
                   max_chars: int = DEF_MAX_CHARS) -> tuple[str, str]:
    """Render speaker turns ``[(voice, text), …]`` → one stitched MP3.

    Each turn is synthesised in its speaker's voice (unknown speaker → graham), with a
    short silence gap between turns. Returns ``(local_path, model_used)``.
    """
    spk = speak or _default_speak(base_url, model)
    segments: list[bytes] = []
    last: Optional[bytes] = None
    for who, text in turns:
        voice = who if (who or "").strip().lower() in _VOICES else "graham"
        ref_audio, ref_text = resolve_voice(voice)
        wavs = [spk(c, ref_audio, ref_text) for c in chunk_text(strip_markdown(text), max_chars)]
        if not wavs:
            continue
        turn_wav = normalize_loudness(_concat_to_bytes(wavs))  # balance Graham vs Tom
        if segments and gap_sec > 0:
            segments.append(silence_like(last or turn_wav, gap_sec))
        segments.append(turn_wav)
        last = turn_wav
    if not segments:
        raise ValueError("no podcast turns produced audio")
    out_dir = out_dir or content_cfg.audio_dir
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha256(
        "|".join(f"{w}:{t}" for w, t in turns).encode("utf-8")).hexdigest()[:16]
    path = to_mp3_or_wav(segments, os.path.join(out_dir, f"podcast-{digest}.mp3"))
    return path, (model or content_cfg.audio_tts_model)
