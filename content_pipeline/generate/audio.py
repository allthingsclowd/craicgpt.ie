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

import array
import hashlib
import io
import json
import logging
import math
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

# Core voices: key → (content_cfg attribute for the M3-side ref WAV, transcript file).
_VOICES = {
    "graham": ("graham_ref_audio", "graham.txt"),
    "tom": ("tom_ref_audio", "tom.txt"),
}

# Parody-persona voice clones: ref WAV at <voice_ref_base>/<key>/ref.wav (M3-side),
# transcript at voice_refs/<key>.txt. They render in their cloned voice ONLY when the ref
# is actually deployed (content_cfg.available_parody_voices); otherwise the pipeline falls
# back to a graham/tom read with the text "character" framing (personas.character_read_intro).
_PARODY_VOICES = {
    "jack_blarney", "roy_mean", "ronald_dump", "saoirse_ronaround", "jessie_buckled",
    "rogue_williams", "sharon_horrigan", "bonio", "jeremy_clarkscone", "keira_knightleigh",
    "a_dell",
}


def _available_parody() -> set[str]:
    return {v.strip() for v in (content_cfg.available_parody_voices or "").split(",") if v.strip()}


def has_clone(name: str) -> bool:
    """True if ``name`` is a usable clone NOW: a core voice, or a parody voice whose ref is
    deployed on the M3 (per ``content_cfg.available_parody_voices``)."""
    key = (name or "").strip().lower()
    return key in _VOICES or (key in _PARODY_VOICES and key in _available_parody())

DEF_MAX_CHARS = 600
DEF_GAP_SEC = 0.4

Speak = Callable[[str, str, str], bytes]  # (text, ref_audio, ref_text) -> WAV bytes


# --------------------------------------------------------------------------- #
# Voice registry
# --------------------------------------------------------------------------- #
def resolve_voice(name: str) -> tuple[str, str]:
    """Return ``(ref_audio_path, ref_text)`` for a voice. Raises KeyError if unknown.

    Core voices read their ref path from ``content_cfg``; parody clones live at
    ``<voice_ref_base>/<key>/ref.wav`` with the transcript in ``voice_refs/<key>.txt``."""
    key = (name or "").strip().lower()
    if key in _VOICES:
        attr, fname = _VOICES[key]
        ref_audio = getattr(content_cfg, attr)
    elif key in _PARODY_VOICES:
        ref_audio = os.path.join(content_cfg.voice_ref_base, key, "ref.wav")
        fname = f"{key}.txt"
    else:
        known = sorted(set(_VOICES) | _PARODY_VOICES)
        raise KeyError(f"unknown voice {name!r}; known: {', '.join(known)}")
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
        # Sentence-split on Latin (.!? + space) AND CJK (。！？, which carry no trailing
        # space) punctuation, so Japanese/Chinese readings chunk on real sentence breaks.
        for s in re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*", p):
            if cur and len(cur) + len(s) + 1 > max_chars:
                chunks.append(cur.strip())
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur.strip():
            chunks.append(cur.strip())
    return chunks


# Phonetic fixes applied to the SPOKEN text only (the on-screen transcript keeps the real
# spelling), and they are PER-LANGUAGE: the English-only "craic"→"crack" rule must NOT be
# applied to other languages' prose, and the spoken site URL localises its connector
# ("dot"→"Punkt"/"point"/"punto"/"ドット"). English is the default/fallback map. CraicGPT
# MUST come before craic (longer match first). Non-English maps are frozen, review-pending
# (decision: reuse the voice clones cross-lingually, review accent/readout post-deploy).
PRONUNCIATIONS_BY_LANG: dict[str, dict[str, str]] = {
    "en": {
        r"\bcraicgpt\.ie\b": "Crack Gee Pee Tee dot Eye Ee",
        r"\bcraicgpt\b": "Crack Gee Pee Tee",
        r"\bcraic\b": "crack",
    },
    "de": {
        r"\bcraicgpt\.ie\b": "Crack Gee Pee Tee Punkt Eye Ee",
        r"\bcraicgpt\b": "Crack Gee Pee Tee",
    },
    "fr": {
        r"\bcraicgpt\.ie\b": "Crack Gee Pee Tee point Eye Ee",
        r"\bcraicgpt\b": "Crack Gee Pee Tee",
    },
    "es": {
        r"\bcraicgpt\.ie\b": "Crack Ge Pe Te punto Eye Ee",
        r"\bcraicgpt\b": "Crack Ge Pe Te",
    },
    "it": {
        r"\bcraicgpt\.ie\b": "Crack Gi Pi Ti punto Eye Ee",
        r"\bcraicgpt\b": "Crack Gi Pi Ti",
    },
    "ja": {
        r"\bcraicgpt\.ie\b": "クラックジーピーティー ドット アイイー",
        r"\bcraicgpt\b": "クラックジーピーティー",
    },
}

# Back-compat alias: the bare English map under its original name.
PRONUNCIATIONS = PRONUNCIATIONS_BY_LANG["en"]


def _phonetic(text: str, language: str = "en") -> str:
    """Apply the language's spoken-form fixes to ``text`` (falls back to the English map)."""
    table = PRONUNCIATIONS_BY_LANG.get(language, PRONUNCIATIONS_BY_LANG["en"])
    for pat, repl in table.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def _post_speech(base: str, model: str, ref_audio: str, ref_text: str, text: str,
                 timeout: float = 400) -> bytes:
    """POST one chunk to the M3 mlx-audio server and return raw WAV bytes.

    Phonetic fixes are applied by the callers (``narrate_text``/``render_podcast``), which
    know the language — so they run identically whether the backend is the real M3 or an
    injected test double."""
    body = {"model": model, "input": text, "ref_audio": ref_audio,
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
# Mastering chain: per-chunk leveling (stdlib) → seam crossfade (stdlib) →
# ffmpeg master (de-box EQ + two-pass loudness + limiter). The stdlib halves run
# offline (and in CI); only the final polish needs ffmpeg, and it's best-effort.
# --------------------------------------------------------------------------- #
def _rms_normalize(wav_bytes: bytes, *, target_dbfs: float = -20.0,
                   peak_ceiling_dbfs: float = -1.0, max_gain_db: float = 12.0) -> bytes:
    """Scale one mono/16-bit chunk toward a common RMS level — stdlib, no ffmpeg.

    This is the per-chunk leveler: every chunk aims at the SAME loudness, so a quiet or
    boxy chunk no longer jumps against the next, and Graham/Tom end up at one level
    before they're even stitched. Silence is returned untouched (no divide-by-zero); the
    boost is capped (so a mostly-pause chunk isn't blown up) and a true-peak ceiling
    always wins over the target so the output never clips. Non-mono / non-16-bit input
    is returned unchanged (safe — the TTS clone is mono 16-bit).
    """
    try:
        w = wave.open(io.BytesIO(wav_bytes), "rb")
        params = w.getparams()
        if params.sampwidth != 2 or params.nchannels != 1:
            w.close()
            return wav_bytes
        data = array.array("h")
        data.frombytes(w.readframes(params.nframes))
        w.close()
    except Exception:
        return wav_bytes
    if not data:
        return wav_bytes
    rms = (sum(s * s for s in data) / len(data)) ** 0.5
    peak = max((abs(s) for s in data), default=0)
    if rms <= 1.0 or peak == 0:                      # silence / near-silence → leave it
        return wav_bytes
    full = 32768.0
    gain = (full * 10 ** (target_dbfs / 20.0)) / rms
    gain = min(gain, 10 ** (max_gain_db / 20.0))     # don't over-amplify pausey chunks
    peak_limit = full * 10 ** (peak_ceiling_dbfs / 20.0)
    if peak * gain > peak_limit:                     # the ceiling always wins (no clipping)
        gain = peak_limit / peak
    if abs(gain - 1.0) < 1e-3:
        return wav_bytes
    out = array.array("h", (max(-32768, min(32767, int(round(s * gain)))) for s in data))
    buf = io.BytesIO()
    o = wave.open(buf, "wb")
    o.setparams(params)
    o.writeframes(out.tobytes())
    o.close()
    return buf.getvalue()


def _crossfade_concat(wavs: list[bytes], *, fade_ms: float = 35.0) -> bytes:
    """Stitch mono/16-bit chunks with a short equal-power crossfade at each seam.

    Adjacent TTS chunks are independent inferences, so a hard butt-join exposes the
    room-tone/timbre step (the 'boxy then fine' you hear). A ~35 ms equal-power overlap
    hides the seam without smearing the speech. Chunks too short for the fade — or any
    format mismatch — fall back to a plain concat, so it always degrades safely.
    """
    wavs = [w for w in wavs if w]
    if not wavs:
        return b""
    if len(wavs) == 1:
        return wavs[0]
    try:
        with wave.open(io.BytesIO(wavs[0]), "rb") as first:
            rate, ch, width = first.getframerate(), first.getnchannels(), first.getsampwidth()
        if width != 2 or ch != 1:
            return _concat_to_bytes(wavs)
        segs: list[array.array] = []
        for wb in wavs:
            w = wave.open(io.BytesIO(wb), "rb")
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (rate, 1, 2):
                w.close()
                return _concat_to_bytes(wavs)        # mixed formats → safe butt-join
            d = array.array("h")
            d.frombytes(w.readframes(w.getnframes()))
            w.close()
            segs.append(d)
    except Exception:
        return _concat_to_bytes(wavs)

    fade = max(1, int(rate * fade_ms / 1000.0))
    out = array.array("h", segs[0])
    for nxt in segs[1:]:
        ov = min(fade, len(out), len(nxt))
        if ov < fade or len(out) < 2 * ov:           # too short to fade → butt-join
            out.extend(nxt)
            continue
        base = len(out) - ov
        for i in range(ov):                          # equal-power (cos/sin) overlap
            t = (i + 1) / (ov + 1)
            mixed = int(out[base + i] * math.cos(t * math.pi / 2)
                        + nxt[i] * math.sin(t * math.pi / 2))
            out[base + i] = max(-32768, min(32767, mixed))
        out.extend(nxt[ov:])
    buf = io.BytesIO()
    o = wave.open(buf, "wb")
    o.setnchannels(1)
    o.setsampwidth(2)
    o.setframerate(rate)
    o.writeframes(out.tobytes())
    o.close()
    return buf.getvalue()


def _measure_loudness(ff: str, in_path: str, pre: str, target_i: float,
                      target_tp: float, target_lra: float) -> Optional[dict]:
    """First loudnorm pass: measure the (filtered) signal; return the JSON stats, or None.

    Two-pass loudnorm (measure → apply) is what makes the final level land accurately and
    match between voices — single-pass only estimates and audibly drifts. The stats print
    to stderr as a trailing JSON block; we parse the last ``{…}``.
    """
    try:
        proc = subprocess.run(
            [ff, "-hide_banner", "-i", in_path, "-af",
             f"{pre},loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
             "-f", "null", "-"], check=True, capture_output=True)
        err = proc.stderr.decode("utf-8", "replace")
        start, end = err.rfind("{"), err.rfind("}")
        if start == -1 or end <= start:
            return None
        stats = json.loads(err[start:end + 1])
        if not all(k in stats for k in
                   ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")):
            return None
        return stats
    except Exception:
        return None


def master_wav(wav_bytes: bytes, *, target_i: float = -16.0, target_tp: float = -1.5,
               target_lra: float = 11.0, min_seconds: float = 1.0,
               mode: Optional[str] = None) -> bytes:
    """The final polish over the WHOLE stitched clip: high-pass + de-box EQ + a touch of
    air + gentle compression + two-pass EBU-R128 loudness + a true-peak limiter — so every
    voice sits at one level and tone.

    Best-effort and offline-safe: a no-op when mastering is disabled (``audio_master`` =
    ``none``), ffmpeg is absent, or the clip is shorter than ``min_seconds`` (which keeps
    the unit tests deterministic). Any ffmpeg/parse error falls back to the input, never
    corrupting the show. Format (rate/channels/width) is preserved so the mastered audio
    still stitches with the jingle.

    TUTORIAL: the seam for the Apple suite. ``mode='apple'`` is reserved for an M3-side
    Match-EQ pass — spectral-matching every chunk to one reference, the one thing this
    static ffmpeg curve can't do. It slots in here without touching a single caller.
    """
    mode = (mode or content_cfg.audio_master or "ffmpeg").strip().lower()
    if mode in ("none", "off", ""):
        return wav_bytes
    try:
        w = wave.open(io.BytesIO(wav_bytes), "rb")
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        dur = w.getnframes() / float(rate or 1)
        w.close()
    except Exception:
        return wav_bytes
    ff = find_ffmpeg()
    if not ff or dur < min_seconds:
        return wav_bytes
    # The corrective voice chain (BEFORE loudness): trim sub-bass rumble, dip the "boxy"
    # low-mid, add a little air, then gently even the dynamics so quiet/boxy and loud/clear
    # chunks sit closer together.
    pre = ("highpass=f=80,"
           "equalizer=f=350:t=q:w=1.1:g=-3,"        # de-box: cut the hollow low-mid
           "highshelf=f=7000:g=2,"                  # a touch of air/presence
           "acompressor=threshold=-18dB:ratio=2.5:attack=15:release=220:makeup=2")
    limiter = f"alimiter=limit={10 ** (target_tp / 20.0):.4f}"   # true-peak ceiling
    codec = _PCM.get(width, "pcm_s16le")
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(wav_bytes)
            in_path = fin.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
            out_path = fout.name
        m = _measure_loudness(ff, in_path, pre, target_i, target_tp, target_lra)
        if m:
            norm = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                    f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                    f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                    f"offset={m['target_offset']}:linear=true")
        else:                                        # parse failed → single-pass fallback
            norm = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        subprocess.run([ff, "-y", "-i", in_path, "-af", f"{pre},{norm},{limiter}",
                        "-ar", str(rate), "-ac", str(ch), "-c:a", codec, out_path],
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
                 max_chars: int = DEF_MAX_CHARS, language: str = "en") -> list[bytes]:
    """Synthesise ``text`` in ``voice`` → list of WAV byte-chunks.

    Phonetic fixes are applied here (language-aware) before synthesis, so the same fix runs
    whether ``speak`` is the real M3 backend or an injected test double."""
    ref_audio, ref_text = resolve_voice(voice)
    spk = speak or _default_speak(base_url, model)
    return [spk(_phonetic(c, language), ref_audio, ref_text)
            for c in chunk_text(strip_markdown(text), max_chars)]


def article_text(item: dict[str, Any]) -> str:
    """Compose the spoken form of an article: headline, then standfirst, then body."""
    parts = [item.get("title", ""), item.get("standfirst", ""), item.get("body", "")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def narrate_article(item: dict[str, Any], *, voice: str = "graham",
                    out_dir: Optional[str] = None, speak: Optional[Speak] = None,
                    base_url: Optional[str] = None, model: Optional[str] = None,
                    language: str = "en") -> tuple[str, str]:
    """Narrate one article (title + standfirst + body) in ``voice``.

    Writes a content-addressed MP3 (or WAV without ffmpeg) to the scratch dir and
    returns ``(local_path, model_used)`` — the same shape as ``images.save_image``.
    ``language`` selects the spoken-form fixes (the translated body already differs, so the
    content-addressed filename is distinct per language).
    """
    text = article_text(item)
    wavs = narrate_text(text, voice, speak=speak, base_url=base_url, model=model,
                        language=language)
    if not wavs:
        raise ValueError("no audio produced for article")
    leveled = [_rms_normalize(w) for w in wavs]        # even out chunk-to-chunk level
    clip = master_wav(_crossfade_concat(leveled))      # seam crossfade + final polish
    out_dir = out_dir or content_cfg.audio_dir
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha256((voice + "|" + text).encode("utf-8")).hexdigest()[:16]
    path = to_mp3_or_wav([clip], os.path.join(out_dir, f"{voice}-{digest}.mp3"))
    return path, (model or content_cfg.audio_tts_model)


# --------------------------------------------------------------------------- #
# Jingle bookending — the trad audio branding tops & tails the show
# --------------------------------------------------------------------------- #
_PCM = {1: "pcm_u8", 2: "pcm_s16le", 3: "pcm_s24le", 4: "pcm_s32le"}


def _default_jingle() -> bytes:
    """The show-open sting WAV (80s full mix). Lazy import dodges an audio↔jingle cycle."""
    from content_pipeline.generate import jingle
    return jingle.intro_jingle()


def _default_outro_jingle() -> bytes:
    """The sign-off sting WAV (stripped 80s tag). Lazy import dodges the import cycle."""
    from content_pipeline.generate import jingle
    return jingle.outro_jingle()


def _conform_and_fade(wav_bytes: bytes, target: bytes, *, fade_in: float = 0.0,
                      fade_out: float = 0.0) -> Optional[bytes]:
    """Conform ``wav_bytes`` to ``target``'s rate/channels/width (+ optional fades).

    The jingle is synthesised at the TTS sample rate, but the live voice clone may
    differ — so when ffmpeg is present we resample/refmt (and fade) the jingle to match
    the speech exactly. Without ffmpeg we return it unchanged IFF it already matches,
    else ``None`` so the caller simply drops the jingle rather than corrupt the mix.
    """
    try:
        with wave.open(io.BytesIO(target), "rb") as t:
            tr, tc, tw = t.getframerate(), t.getnchannels(), t.getsampwidth()
        with wave.open(io.BytesIO(wav_bytes), "rb") as j:
            jr, jc, jw, jn = j.getframerate(), j.getnchannels(), j.getsampwidth(), j.getnframes()
    except Exception:
        return None
    ff = find_ffmpeg()
    if not ff:
        return wav_bytes if (jr, jc, jw) == (tr, tc, tw) else None
    af = []
    if fade_in > 0:
        af.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        af.append(f"afade=t=out:st={max(0.0, jn / float(jr) - fade_out):.3f}:d={fade_out}")
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(wav_bytes)
            in_path = fin.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
            out_path = fout.name
        cmd = [ff, "-y", "-i", in_path]
        if af:
            cmd += ["-af", ",".join(af)]
        cmd += ["-ar", str(tr), "-ac", str(tc), "-c:a", _PCM.get(tw, "pcm_s16le"), out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        with open(out_path, "rb") as fh:
            return fh.read()
    except Exception:
        return wav_bytes if (jr, jc, jw) == (tr, tc, tw) else None
    finally:
        for p in (in_path, out_path):
            if p and os.path.exists(p):
                os.remove(p)


def _overlap_mix(intro: bytes, speech: bytes, *, overlap_sec: float = 1.6) -> Optional[bytes]:
    """Mix the speech ONSET on top of the jingle's fading tail (no dead air): the voice
    enters ``overlap_sec`` before the (faded-out) intro ends and plays at full level over
    it. ffmpeg ``amix`` with ``normalize=0`` keeps the voice from being ducked; the
    intro's own ``fade_out`` makes its last notes recede under the voice. Returns the
    mixed head, or ``None`` (caller falls back to a plain sequential join)."""
    ff = find_ffmpeg()
    if not ff:
        return None
    try:
        with wave.open(io.BytesIO(intro), "rb") as j:
            jr, jc, jn = j.getframerate(), j.getnchannels(), j.getnframes()
        intro_len = jn / float(jr)
        delay_ms = int(max(0.0, intro_len - overlap_sec) * 1000)
        delay = "|".join([str(delay_ms)] * max(1, jc))
        in_i = in_s = out_p = None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fi:
            fi.write(intro)
            in_i = fi.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fs:
            fs.write(speech)
            in_s = fs.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fo:
            out_p = fo.name
        fc = (f"[1:a]adelay={delay}[s];"
              f"[0:a][s]amix=inputs=2:duration=longest:normalize=0[a]")
        cmd = [ff, "-y", "-i", in_i, "-i", in_s, "-filter_complex", fc, "-map", "[a]", out_p]
        subprocess.run(cmd, check=True, capture_output=True)
        with open(out_p, "rb") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001 — best-effort; fall back to a sequential join
        return None
    finally:
        for p in (locals().get("in_i"), locals().get("in_s"), locals().get("out_p")):
            if p and os.path.exists(p):
                os.remove(p)


def render_podcast(turns: list[tuple[str, str]], *, out_dir: Optional[str] = None,
                   speak: Optional[Speak] = None, base_url: Optional[str] = None,
                   model: Optional[str] = None, gap_sec: float = DEF_GAP_SEC,
                   max_chars: int = DEF_MAX_CHARS, add_jingle: bool = True,
                   jingle_wav: Optional[bytes] = None,
                   outro_wav: Optional[bytes] = None,
                   language: str = "en") -> tuple[str, str]:
    """Render speaker turns ``[(voice, text), …]`` → one stitched MP3.

    Each turn is synthesised in its speaker's voice (unknown speaker → graham), with a
    short silence gap between turns. When ``add_jingle`` (the default) the 80s call-sign
    sting tops and tails the show — the full mix fades out into the cold-open, and a
    stripped, resolved tag fades back in under the sign-off. ``jingle_wav``/``outro_wav``
    override the intro/outro stings (a single ``jingle_wav`` is used for both if
    ``outro_wav`` is omitted). Returns ``(local_path, model_used)``.
    """
    spk = speak or _default_speak(base_url, model)
    segments: list[bytes] = []
    last: Optional[bytes] = None
    for who, text in turns:
        # Voice any USABLE clone — graham/tom OR a deployed parody guest — in its own
        # voice; only an unknown/undeployed speaker falls back to graham. (Without this a
        # parody key was silently read in Graham's voice within the podcast.)
        voice = who if has_clone(who) else "graham"
        ref_audio, ref_text = resolve_voice(voice)
        wavs = [spk(_phonetic(c, language), ref_audio, ref_text)
                for c in chunk_text(strip_markdown(text), max_chars)]
        if not wavs:
            continue
        # Level each chunk to a common target, then crossfade the seams within the turn —
        # the per-chunk RMS pass is what balances Graham vs Tom (and tames boxy chunks).
        turn_wav = _crossfade_concat([_rms_normalize(w) for w in wavs])
        if segments and gap_sec > 0:
            segments.append(silence_like(last or turn_wav, gap_sec))
        segments.append(turn_wav)
        last = turn_wav
    if not segments:
        raise ValueError("no podcast turns produced audio")

    # Master the WHOLE spoken track in one pass — the de-box EQ, two-pass loudness and
    # limiter applied across every turn at once, so the show holds one level and tone.
    speech = master_wav(_concat_to_bytes(segments))

    final = [speech]
    if add_jingle:  # best-effort: a format mismatch / missing ffmpeg just drops it
        jw_in = jingle_wav if jingle_wav is not None else _default_jingle()
        jw_out = outro_wav if outro_wav is not None else (
            jingle_wav if jingle_wav is not None else _default_outro_jingle())
        # Intro: fade the jingle's tail and CROSSFADE the voice in over it (no gap) —
        # the voice rides on top of the last fading notes. Falls back to a sequential
        # join if the overlap-mix is unavailable (no ffmpeg / mix error).
        intro = _conform_and_fade(jw_in, speech, fade_out=1.8)
        outro = _conform_and_fade(jw_out, speech, fade_in=0.6, fade_out=1.3)
        head = _overlap_mix(intro, speech, overlap_sec=1.6) if intro else None
        if head is not None:
            final = [head] + ([outro] if outro else [])
        else:
            final = ([intro] if intro else []) + [speech] + ([outro] if outro else [])

    out_dir = out_dir or content_cfg.audio_dir
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha256(
        "|".join(f"{w}:{t}" for w, t in turns).encode("utf-8")).hexdigest()[:16]
    path = to_mp3_or_wav(final, os.path.join(out_dir, f"podcast-{digest}.mp3"))
    return path, (model or content_cfg.audio_tts_model)
