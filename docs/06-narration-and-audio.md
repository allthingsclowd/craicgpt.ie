# 06 — Narration & Audio: deterministic vs probabilistic, with LangChain

The newest build step turns the finished paper into **sound**: a per-article reading for
accessibility (every piece is listenable), a daily **dad↔son podcast** where Graham and Tom —
his curious, cheeky 14-year-old — **take turns** reading the articles and banter around them
as a flowing discussion, and a fast **under-180-second TL;DR** headline bulletin. Both shows
are topped and tailed by our own **80s call-sign jingle** (Apple sampled instruments,
bounced offline). It runs **after validation**, on a long-running box (the Conductor host
`.75` or the M3), never the laptop.

It's also the cleanest worked example of this codebase's whole thesis:

> **Plain code does the deterministic work; a `deepagents` rubric governs the probabilistic
> work.** LangChain is the seam where the two meet.

## The three layers (two deterministic, one probabilistic)

A podcast episode is built from three layers — and only one of them is allowed near an LLM:

| Layer | Deterministic? | Who makes it |
|------|----------------|--------------|
| **80s call-sign jingle** bookend + a clean date-stamped cold-open (Graham + date, Tom breaks in) + the **fixed guest welcome / thanks / sign-off** templates | ✅ bounced Apple-instrument asset / fixed text | `generate/jingle.py` + `build_signature_intro` + `GUEST_*` |
| Article **readings** — Graham & Tom **alternating** (a deployed parody guest reads its own) | ✅ verbatim — the exact, already-rubric-approved article body | the harness |
| Host **links** — ONE short *pre* (react to the previous bit) + *post* (wrap + hand to the next BY NAME), **woven into each host reader's single clip**; Tom's minimal, timeless slang | ❌ LLM-written | `write_model` via `run_with_fallback` (+ length guard) |

**One clip per article.** Every short back-and-forth turn used to be its own TTS clip, and
the *seams between clips* were where the clone degraded. So each article is now recorded as
**ONE clip** — the reader's `pre` link + the verbatim reading + their `post` hand-off, in one
voice — and a parody guest reads in their **own** voice between a fixed welcome and sign-off.
Far fewer seams; only the host links are LLM-written — everything else is fixed text or verbatim.

Reading the article *verbatim* matters: the edition rubric already passed that text, so the
podcast introduces **no new claims and no attribution drift**.

## The jingle is ours, not a licence — `generate/jingle.py`

There is no "music model" in the loop. The hook is **our own composition** — an 80s
synth-pop call sign (*Am–F–C–G* at 124 BPM: pulsing octave synth bass, gated-style drums,
synth-brass stabs, a saw lead and a polysynth pad) — voiced through **Apple's built-in
sampled GM instruments** (the `gs_instruments.dls` bank that ships with macOS / drives
GarageBand) and **bounced offline** via AVFoundation. Our notes + real sampled instruments =
recognisable, professional, **zero copyright/royalties**. `render_podcast` tops & tails the
show with it — the full mix fades into the cold-open, a stripped, resolved tag fades back
under the sign-off (best-effort — it drops gracefully without `ffmpeg`).

Unlike the rest of the pipeline you can't reproduce Apple's DLS samples in stdlib Python, so
the sting is a **committed WAV asset** (`assets/jingle_80s_{intro,outro}.wav`, 24 kHz mono to
match the TTS stitch). It stays *owned and reproducible* because the full renderer ships in
`generate/jingle_src/` (Swift + AVFoundation + the arrangement JSON) — regenerate the bytes
from scratch on any Mac. The pure-stdlib *Whiskey in the Jar* Karplus–Strong synth is retained
in `jingle.py` only as a **graceful fallback** if the asset ever goes missing (never silence).
Same deterministic-vs-probabilistic split as everything else: a jingle needs no judgement, so
no LLM goes near it.

> **On copyright:** this is deliberately *not* a sound-alike of a specific hit — we ruled out
> both Stairway *and* the Close Encounters five-note motif (still in copyright). An **original**
> melody on licence-clean Apple instruments is on-brand, recognisable, and can't be confused
> with anyone's song.

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
- **Chunking + stitching** — split on paragraph/sentence boundaries (TTS token cap), then
  stitch through a small **mastering chain**, encode MP3 with `ffmpeg` (falls back to WAV if
  ffmpeg is absent).
- **Two quality fixes earned from real playback:**
  - `_phonetic` rewrites the **spoken** text only: `craic → "crack"`,
    `CraicGPT → "Crack Gee Pee Tee"`. The on-screen transcript keeps the real spelling, so
    "craic of dawn" / "put the AI back in craic" land as puns you can *see*.
  - **The mastering chain** (`_rms_normalize` → `_crossfade_concat` → `master_wav`) replaces
    the old single bare per-turn `loudnorm`. Each chunk is RMS-levelled to a common target
    (so a quiet or *boxy* chunk no longer jumps against the next, and Graham/Tom land at one
    level **before** they're stitched); seams get a ~35 ms **equal-power crossfade** (hiding
    the room-tone step between independent inferences); then the **whole** show gets one
    `ffmpeg` master — high-pass + a de-box EQ dip (~350 Hz) + a touch of air + gentle
    compression + **two-pass** EBU-R128 loudness + a true-peak limiter. The stdlib halves run
    in CI; the ffmpeg pass is best-effort (no-op without ffmpeg / on sub-second clips).
    > **The Apple seam.** `master_wav(mode='apple')` is reserved for an M3-side **Match-EQ**
    > pass — spectral-matching every chunk to one reference, the one thing a static ffmpeg
    > curve can't do — which drops in without touching a caller. The portable ffmpeg chain is
    > the deterministic baseline that runs on `.75` today.

## The probabilistic layer — `podcast_script.py`

`build_podcast_script(paper)` assembles the turns as **one clip per article**: signature
intro → for each article a single reader clip *[pre link → verbatim reading → post hand-off]*
→ signature outro. One `write_model` call drafts just the host **links** (a one-line `pre`
that reacts to the bit before + a one-line `post` that wraps and hands to the next reader BY
NAME); the harness then concatenates `pre + reading + post` into one clip in the reader's
voice. Recording each reader's whole segment as ONE piece (rather than read-banter-read as
three) is what removes the transition seams the clone struggled with. A deployed parody guest
is framed by **fixed templates** (`GUEST_WELCOME` by the seniority host, then `GUEST_ACK` +
verbatim reading + `GUEST_SIGNOFF` in the guest's own voice) — no LLM, nothing to gate there.

The host links ship **ungated**. There *was* a per-banter rubric gate (the same
`deepagents` `RubricMiddleware` the edition uses, over a `PODCAST_RUBRIC`) — it was
**removed on 2026-06-10 as too strict**: in practice its false holds (sanctioned parody
bylines read as mockery, non-English banter read as off-rubric, borderline tone calls)
cost far more banter than they ever caught real harm. What still governs the banter:

- the **banter prompt** itself bakes in the register (warm, PG, cheeky-never-cruel,
  Tom's minimal slang);
- a **deterministic guard** (`_valid_link`) drops any link over 300 chars — one sentence
  was asked for; rambling is the failure mode — before it is ever voiced;
- the **finished edition** (every word the readings speak) is still rubric-judged
  upstream by `grade_edition`.

A history lesson worth keeping: the gate's last design iteration (PR #66) stripped a held
banter instead of dropping the podcast — the right shape *if* you keep a gate. Graham's
call was simpler: the judge had no business holding the show's own furniture.

## The TL;DR bulletin — `build_tldr_script` (deterministic)

A second, faster show for skimmers: Graham and Tom **alternate reading the day's headlines**
(each item's already-approved title + a one-line gloss) like a news bulletin, topped & tailed
by the same jingle. It is **fully deterministic** — no LLM, nothing to gate — and
**word-budgeted** to the speaking time left after the jingle, so it reliably lands **under
180 seconds** even if the clone reads slowly. It attaches as `paper["podcast_tldr"]` (additive
/ optional, mirroring `podcast`) and gets its own masthead player.

## Parody voice clones — each persona reads in character

Each parody persona now has its **own Qwen3-TTS clone**, trained from a willing
impressionist's reference (a recording *of the impression*, never the real public figure — so
the clone is a parody performance, not an identity). When a persona's clone is deployed
(listed in `CRAICGPT_PARODY_VOICES`), `narrate_paper` reads that item — and its podcast turn —
**in the cloned voice** (`render_podcast` voices any *usable* clone via `has_clone`, not just
graham/tom; `resolve_voice` finds the reference at `<VOICE_REF_BASE>/<key>/ref.wav` plus its
transcript in `generate/voice_refs/`). A persona with no deployed clone falls back to a short
theatrical **spoken intro** announcing the character, carried by the *script* — the honest
maximum without reference audio. The body always stays verbatim, and the satire disclaimer
always stands.

**Conversational hand-offs.** On the podcast each guest is *introduced* before they read,
generationally: `personas.introducer_for` sends the **younger** figures to **Tom** and the
**older** ones to **Graham** (`PERSONA_SENIORITY`), and `personas.real_name` decodes the punny
byline so the host can say who they really are. When the banter introduces a guest we skip the
deterministic "in the style of X" framing (no double-announce); and a guest **whose clone is
deployed** may speak **one** in-character banter line in their own voice — ungated, like
all banter, and dropped by the same length guard if it rambles.

## Narration runs for every language

Since the paper went **multi-lingual** (write-once, translate-many — see
[`docs/07`](07-multilingual.md)), the narration pass runs **once per language**, not just for
English. `narrate_paper(paper, language=…)` takes the edition's language (explicit override,
else `edition.language`) and threads it through everything:

- **The voice clones are reused cross-lingually** — Graham, Tom and each parody persona read
  the *target-language* text from their **same English reference WAVs** (accept some accent
  drift; review post-deploy). No new clones per language.
- **The spoken-form fixes are localised.** `audio._phonetic` is per-language — the English
  `craic → "crack"` / spoken-URL rules must *not* touch German or Japanese prose, so each
  language has its own (English-fallback) map. `chunk_text` also splits on **CJK** sentence
  punctuation (`。！？`), which carries no trailing space.
- **A translated edition is honest in audio too.** Its podcast and TL;DR open with a short
  spoken *"this was machine-translated from English by `<model>`"* note
  (`podcast_script.translation_preamble`, naming the real `edition.translated_by`) — empty for
  English, so it only ever rides a genuinely translated edition. The fixed podcast/TL;DR
  framing (`_L10N`) and the date phrase are translated per language.
- **The <180s TL;DR budget counts the right unit.** For spaceless CJK (`_CJK_LANGS`) the
  word-budget becomes a **character** budget (`_speaking_units`), so the bulletin still lands
  under 180 seconds in Japanese as reliably as in English.
- **The banter ships ungated in every language** (gate removed 2026-06-10) — written
  in-language by the same prompt, length-guarded the same way; the edition each language
  translates was rubric-judged once, in English.

## The publish gate is autonomous — with a human window

Once narrated, the edition flows to the **idempotent publish gate** (`review.gate`, polled by
the `craicgpt_publish_gate` workflow). On the rubric's APPROVE + host structural validation +
a browser-UA link-check it **auto-publishes live** — no human in the loop. A *judgement* HOLD
(the rubric held, but the page is structurally valid) is **escalated to Graham on Telegram**;
if no human directive lands within `CRAICGPT_HITL_PASSIVE_MINUTES` (default 60) the gate
**passively approves** it (`passive-publish`). `cli override` publishes now; `cli hold` pins
it and suppresses the timer. The fail-open is **fenced by structural validity** — a broken
page or dead links never auto-publish.

## Orchestration & integration

- `content_pipeline/generate/narration.py` → `narrate_paper(paper, language=…)` ties it together
  (best-effort per-article audio like images; the podcast; trace events for the drawer).
- `cli.py narrate --date <d> [--language <l>] [--prefix preview|content] [--publish] [--live] [--limit N]`
  loads a validated edition (a translation language loads from its `<lang>/<prefix>/…` tree),
  enriches it, and (with `--publish`) uploads audio + the JSON.
- `publish.py` uploads local audio to `<prefix>/audio/…` and rewrites to CDN URLs — the same
  pattern as images (shorts have audio even though they have no image; the podcast too).
  Translations publish under a per-language prefix; **audio is per-language, images are shared**
  (a translation carries the absolute English image URLs, so `_is_local_path` skips re-upload).
- `compile.py` carries `podcast` + `podcast_tldr` keys; `audio_url` is **additive and
  optional**, so editions without audio still validate.
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
python -m pytest -q tests/test_jingle.py tests/test_audio.py tests/test_podcast_script.py \
  tests/test_podcast_gate.py tests/test_narration.py tests/test_gate_passive.py   # offline
python -m content_pipeline.agent.cli narrate --date <today> --prefix content --limit 3 \
  --publish                                                  # render to preview/ + S3
# then open  …/?edition=preview  to hear it
```
