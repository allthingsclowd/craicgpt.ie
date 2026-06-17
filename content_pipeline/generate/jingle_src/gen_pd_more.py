#!/usr/bin/env python3
"""More PUBLIC-DOMAIN tune options as full-fat arena-synth stings (compositions are PD;
we synthesise our own performance via the DLS GM bank → zero copyright).

- Wagner — "Ride of the Valkyries" (1856): the epic rising brass call + galloping
  rhythm. Bombastic/cinematic, not churchy.
- Vivaldi — "Summer" (L'estate, Presto / 'the storm', 1725): driving agitated
  descending runs in G minor. High-energy, not churchy.
"""

import json
import os

ARR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arr")
os.makedirs(ARR, exist_ok=True)


# ---------------------------------------------------------------- Ride of the Valkyries
def valkyries():
    bpm = 138
    # The rising triadic "ho-jo-to-ho" call (B minor), dotted, sequenced upward.
    call = [
        [0.0, 0.5, 59, 104], [0.5, 0.25, 62, 96], [0.75, 0.75, 66, 114],   # B  D  F#
        [1.5, 0.5, 62, 102], [2.0, 0.25, 66, 96], [2.25, 0.75, 69, 116],   # D  F# A
        [3.0, 0.5, 66, 102], [3.5, 0.25, 69, 96], [3.75, 0.75, 71, 118],   # F# A  B
        [4.5, 1.8, 71, 116],                                               # B (held peak)
    ]
    brass = {"name": "orchbrass", "program": 61, "wet": True, "gain": 0.7, "notes": call}
    lead = {"name": "lead", "program": 81, "wet": True, "gain": 0.55,
            "notes": [[a, b, c + 12, d - 8] for a, b, c, d in call]}  # octave shimmer on top
    # galloping bass on B (dotted 6/8 feel)
    bnotes = []
    t = 0.0
    while t < 6.0:
        bnotes.append([round(t, 3), 0.3, 35, 106])        # B1 strong
        bnotes.append([round(t + 0.5, 3), 0.18, 47, 86])  # B2 off
        t += 1.0
    bass = {"name": "bass", "program": 38, "gain": 1.0, "notes": bnotes}
    dn = []
    t = 0.0
    while t < 6.0:
        dn.append([round(t, 3), 0.2, 36, 112])             # kick (timpani-ish) on the beat
        dn.append([round(t + 0.66, 3), 0.15, 36, 92])      # gallop
        t += 1.0
    for b in [1, 3, 5]:
        dn.append([b, 0.2, 38, 104])
    dn.append([0.0, 0.5, 49, 110])
    dn.append([6.3, 0.8, 49, 118])                          # crash reveal
    drums = {"name": "drums", "program": 0, "drum": True, "gain": 0.95, "notes": dn}
    strings = {"name": "strings", "program": 48, "wet": True, "gain": 0.45,
               "notes": [[0.0, 6.3, p, 70] for p in (47, 59, 62, 66)]}  # B-minor pad bed
    reveal = {"name": "orchhit", "program": 55, "gain": 0.6,
              "notes": [[6.3, 0.6, p, 116] for p in (47, 59, 62, 66, 71)]}
    return {"bpm": bpm, "reverb": 24, "tracks": [bass, drums, strings, brass, lead, reveal]}


# ----------------------------------------------------------------------- Vivaldi Summer
def vivaldi_summer():
    bpm = 160
    # Agitated descending G-minor storm runs (16ths), repeated + answered, driving bed.
    scale = [67, 65, 63, 62, 60, 58, 57, 55]  # G F Eb D C Bb A G  (G minor, descending)
    run = []
    t = 0.0
    for _ in range(2):  # two storm sweeps
        for p in scale:
            run.append([round(t, 3), 0.22, p, 100])
            t += 0.25
    lead = {"name": "lead", "program": 81, "wet": True, "gain": 0.8, "notes": run}
    strings = {"name": "strings", "program": 48, "wet": True, "gain": 0.55,
               "notes": [[round(i * 0.25, 3), 0.22, p, 86] for i, p in enumerate(scale * 2)]}
    bn = []
    t = 0.0
    while t < 4.0:
        bn.append([round(t, 3), 0.22, 31, 108])  # G1 pounding pedal, 8ths
        t += 0.5
    bass = {"name": "bass", "program": 38, "gain": 1.0, "notes": bn}
    dn = []
    for b in [x * 0.5 for x in range(8)]:
        dn.append([round(b, 3), 0.18, 36, 110])
    for b in [0.5, 1.5, 2.5, 3.5]:
        dn.append([b, 0.2, 38, 104])
    t = 0.0
    while t < 4.0:
        dn.append([round(t, 3), 0.1, 42, 76])
        t += 0.25
    dn.append([0.0, 0.5, 49, 108])
    dn.append([4.0, 0.7, 49, 116])
    drums = {"name": "drums", "program": 0, "drum": True, "gain": 0.95, "notes": dn}
    reveal = {"name": "orchhit", "program": 55, "gain": 0.6,
              "notes": [[4.0, 0.6, p, 114] for p in (43, 55, 58, 62)]}  # Gm hit
    return {"bpm": bpm, "reverb": 18, "tracks": [bass, drums, strings, lead, reveal]}


def valkyries_outro():
    """Stripped, resolving sign-off — a single triumphant B-minor chord ringing out,
    strings + brass + orchestra-hit + a final timpani/crash."""
    bpm = 138
    chord = (47, 59, 62, 66, 71)  # B minor, doubled (B1 B2 D3 F#3 B3)
    strings = {"name": "strings", "program": 48, "wet": True, "gain": 0.6,
               "notes": [[0.0, 2.4, p, 78] for p in chord]}
    orchbrass = {"name": "orchbrass", "program": 61, "wet": True, "gain": 0.55,
                 "notes": [[0.0, 2.0, p, 86] for p in chord]}
    hit = {"name": "orchhit", "program": 55, "gain": 0.62,
           "notes": [[0.0, 0.6, p, 118] for p in chord]}
    bass = {"name": "bass", "program": 38, "gain": 0.9, "notes": [[0.0, 1.8, 35, 106]]}
    crash = {"name": "drums", "program": 0, "drum": True, "gain": 0.9,
             "notes": [[0.0, 1.2, 49, 110], [0.0, 0.3, 36, 116]]}
    return {"bpm": bpm, "reverb": 28, "tracks": [bass, crash, strings, orchbrass, hit]}


if __name__ == "__main__":
    with open(os.path.join(ARR, "pd-valkyries.json"), "w") as f:
        json.dump(valkyries(), f)
    with open(os.path.join(ARR, "pd-valkyries-outro.json"), "w") as f:
        json.dump(valkyries_outro(), f)
    with open(os.path.join(ARR, "pd-vivaldi-summer.json"), "w") as f:
        json.dump(vivaldi_summer(), f)
    print("wrote arr/pd-valkyries.json + arr/pd-valkyries-outro.json + arr/pd-vivaldi-summer.json")
