# 06 — Narration & Audio: deterministic vs probabilistic, with LangChain

The newest build step turns the finished paper into **sound**: a per-article reading for
accessibility (every piece is listenable), and a daily **dad↔son podcast** where Graham
reads each article and Tom — his curious, cheeky 14-year-old — banters around it. It runs
**after validation**, on a long-running box (the Conductor host `.75` or the M3), never the
laptop.

It's also the cleanest worked example of this codebase's whole thesis:

> **Plain code does the deterministic work; a `deepagents` rubric governs the probabilistic
> work.** LangChain is the seam where the two meet.

## The three layers (two deterministic, one probabilistic)

A podcast episode is built from three layers — and only one of them is allowed near an LLM:

| Layer | Deterministic? | Who makes it |
|------|----------------|--------------|
| Signature jingle ("Goooood morning, CraicGPT!", date-stamped) | ✅ fixed text | `podcast_script.build_signature_intro` |
| Article **readings** | ✅ verbatim — the exact, already-rubric-approved article body | the harness |
| Dad↔son **banter** | ❌ LLM-written | `write_model` via `run_with_fallback`, then **gated** |

Reading the article *verbatim* matters: the edition rubric already passed that text, so the
podcast introduces **no new claims and no attribution drift**. The banter is the only new
probabilistic content — so it is the only thing the gate has to judge.

## The deterministic TTS harness — `content_pipeline/generate/audio.py`

Pure mechanics, no LLM. Mirrors `images.py` (injectable client → unit-testable offline):

```python
from content_pipeline.generate import audio

wavs = audio.narrate_text("Hello there.", "graham")     # chunk → synth → [WAV bytes]
path, model = audio.narrate_article(item, voice="graham")  # → ("/tmp/…mp3", tts_model)
path, model = audio.render_podcast([("graham", "…"), ("tom", "…")])  # multi-voice
```

- **Voice registry** — `resolve_voice("graham"|"tom")` returns the M3-side reference WAV
  (from `content_config`) + the matching transcript (shipped in `generate/voice_refs/`).
  The clone is **Qwen3-TTS-12Hz Base, Full-ICL**: a clean ~40–50s reference *plus its
  transcript* is the fidelity lever.
- **Custom transport, not the proxy** — the clone takes a non-OpenAI body
  (`ref_audio` + `ref_text`), so unlike chat/images we POST straight to the M3 mlx-audio
  server. `speak` is an injectable callable, so the chunk/stitch logic tests with no network.
- **Chunking + stitching** — split on paragraph/sentence boundaries (TTS token cap), stitch
  with stdlib `wave`, encode MP3 with `ffmpeg` (falls back to WAV if ffmpeg is absent).
- **Two quality fixes earned from real playback:**
  - `_phonetic` rewrites the **spoken** text only: `craic → "crack"`,
    `CraicGPT → "Crack Gee Pee Tee"`. The on-screen transcript keeps the real spelling, so
    "craic of dawn" / "put the AI back in craic" land as puns you can *see*.
  - `normalize_loudness` runs EBU R128 (`ffmpeg loudnorm`) per speaker turn, so Graham's
    and Tom's clones sit at the same level instead of one drowning the other.

## The probabilistic layer, governed — `podcast_script.py` + `rubric_review.py`

`build_podcast_script(paper)` assembles the turns: signature intro → for each article
*[banter before] → verbatim reading → [banter after]* → signature outro. The banter is one
`write_model` call (Tom's character stays consistent across the show); the readings are
spliced in by code.

The banter then passes the **same `deepagents` `RubricMiddleware`** the edition uses — a
separate judge model scores it against `PODCAST_RUBRIC` (harmless, kind, age-appropriate for
a 14-year-old, no defamation, on-brand) before a single word is voiced:

```python
from content_pipeline.agent.rubric_review import grade_podcast_script
verdict = grade_podcast_script(script["banter_text"])   # {"verdict": "APPROVE"|"HOLD", …}
```

`APPROVE` → render the podcast. `HOLD` → no podcast is attached and the reason is recorded
(`edition.podcast_hold`). Per-article readings need no gate — they read approved text.
This is the rule from `CLAUDE.md` made concrete: *probabilistic judgement never replaces the
deterministic guard, and never goes ungoverned either.*

## Orchestration & integration

- `content_pipeline/generate/narration.py` → `narrate_paper(paper)` ties it together
  (best-effort per-article audio like images; the gated podcast; trace events for the drawer).
- `cli.py narrate --date <d> [--prefix preview|content] [--publish] [--live] [--limit N]`
  loads a validated edition, enriches it, and (with `--publish`) uploads audio + the JSON.
- `publish.py` uploads local audio to `<prefix>/audio/…` and rewrites to CDN URLs — the same
  pattern as images (shorts have audio even though they have no image; the podcast too).
- `compile.py` carries a `podcast` key; `audio_url` is **additive and optional**, so editions
  without audio still validate.
- The frontend (`main.js`) shows a subtle 🔊 *Listen* on each article (one shared sticky
  player) and a masthead podcast bar with a screen-reader **transcript**; `?edition=preview`
  renders the un-published draft for review.

## Where LangChain sits in all this

LangChain isn't doing the audio — it's doing the **judgement and the routing** around it:
`run_with_fallback` keeps banter generation local-first with an honest fallback record, and
`deepagents.RubricMiddleware` is the governor that decides whether the probabilistic layer is
fit to ship. Everything else is deterministic Python you can read top-to-bottom. That is the
pattern to take away: **reach for the agent/rubric exactly where you need live judgement, and
nowhere else.**

## Verify it

```bash
python -m pytest -q tests/test_audio.py tests/test_podcast_script.py \
  tests/test_podcast_gate.py tests/test_narration.py        # offline, models stubbed
python -m content_pipeline.agent.cli narrate --date <today> --prefix content --limit 3 \
  --publish                                                  # render to preview/ + S3
# then open  …/?edition=preview  to hear it
```
