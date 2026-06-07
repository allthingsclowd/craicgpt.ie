# CraicGPT call-sign — renderer sources

The show's audio sting (the music that tops and tails every podcast) is an
**original 80s synth-pop hook** — *Am–F–C–G at 124 BPM*, pulsing octave synth
bass, gated-style drum groove, synth-brass stabs, a soaring saw lead and a
polysynth pad. **Our composition; nobody else's tune.**

It is voiced through **Apple's built-in sampled GM instruments** (the
`gs_instruments.dls` bank that ships with macOS and drives GarageBand's General
MIDI). Real sampled instruments + our own notes = recognisable, professional,
and **zero copyright/licence**. (The earlier pure-stdlib Karplus–Strong *Whiskey
in the Jar* synth is retained in `jingle.py` only as a graceful fallback if the
asset is ever missing — it must never be silence.)

## Why a committed asset and not pure code
You cannot reproduce Apple's DLS samples in stdlib Python, so — unlike the rest
of the pipeline — the sting is a **bounced WAV asset** (`../assets/jingle_80s_*.wav`,
24 kHz mono to match the TTS stitch format). To keep it *owned and reproducible*
we ship the full renderer here; anyone can regenerate the bytes from scratch.

## Regenerate (on any Mac — uses only system frameworks)
```bash
cd content_pipeline/generate/jingle_src
swiftc -O synth.swift -o synth          # multitrack 80s renderer (AVFoundation)
swiftc -O render.swift -o render        # single-line motif renderer (the trad call-sign, archived)
python3 gen80s.py                        # writes arr/{1..5}-synth-*.json variants
./synth arr/5-synth-full.json  master_intro_full.wav    # the chosen intro (full mix)
./synth arr/outro.json         master_outro.wav         # the stripped resolving sign-off

# conform to the runtime asset format (24 kHz mono 16-bit):
ffmpeg -y -i master_intro_full.wav -ar 24000 -ac 1 -c:a pcm_s16le ../assets/jingle_80s_intro.wav
ffmpeg -y -i master_outro.wav      -ar 24000 -ac 1 -c:a pcm_s16le ../assets/jingle_80s_outro.wav
```

## Files
| File | What |
|------|------|
| `synth.swift` | JSON-driven multitrack renderer → offline-rendered WAV via AVAudioEngine + DLS GM + plate reverb |
| `gen80s.py` | composes the Am–F–C–G hook and emits the 5 density variants + the bed |
| `arr/*.json` | the arrangements (`5-synth-full` = chosen intro; `outro` = sign-off) |
| `render.swift` | the archived single-line 5-note trad "call sign" motif renderer (option 6, superseded) |
| `master_*.wav` | 44.1 kHz stereo masters (reference / future re-voicing through Logic instruments) |
