#!/usr/bin/env python3
"""Compose the 80s synth-pop call sign and emit 5 arrangement variants.

One 2-bar hook in A minor (i-bVI-bIII-bVII = Am-F-C-G, the most 80s loop there is),
at 124 BPM. Pulsing octave synth bass + a gated-style drum groove are the bed;
synth-brass stabs, a soaring saw lead and a polysynth pad layer on top. Each
variant is a SUBSET so Graham can pick the density.  Apple's GM synths, our notes.
"""
import json, os

OUT = "/tmp/callsign/arr"
os.makedirs(OUT, exist_ok=True)

# --- chord plan: 2 beats each over an 8-beat (2-bar) phrase --------------------
# region start beat -> (bass root midi, stab/pad chord midis)
REGIONS = [
    (0.0, 45, [57, 60, 64]),   # Am  (A2 bass; A3 C4 E4)
    (2.0, 41, [53, 57, 60]),   # F   (F2;     F3 A3 C4)
    (4.0, 48, [60, 64, 67]),   # C   (C3;     C4 E4 G4)
    (6.0, 43, [55, 59, 62]),   # G   (G2;     G3 B3 D4)
]

def bass():
    notes = []
    for start, root, _ in REGIONS:
        # eighths: root, root, octave-pop-down, root  (staccato, punchy)
        for i, (pitch, vel) in enumerate([(root,102),(root,86),(root-12,106),(root,90)]):
            notes.append([round(start + i*0.5, 3), 0.45, pitch, vel])
    return {"name": "bass", "program": 38, "gain": 1.0, "notes": notes}   # Synth Bass 1

def drums():
    n = []
    for b in [0,2,3.5,4,6,7.5]: n.append([b, 0.2, 36, 112])   # kick
    for b in [1,3,5,7]:         n.append([b, 0.2, 38, 106])   # snare
    t = 0.0
    while t < 8.0:                                            # closed hats, every 8th
        n.append([round(t,3), 0.15, 42, 80 if (t*2)%2==0 else 62]); t += 0.5
    for b in [1.5,5.5]: n.append([b, 0.2, 46, 72])           # open-hat sizzle
    n.append([0.0, 0.4, 49, 96])                              # crash on the one
    return {"name": "drums", "program": 0, "drum": True, "gain": 0.9, "notes": n}

def brass():
    n = []
    for start, _, chord in REGIONS:
        for off in (0.5, 1.5):                                # offbeat stabs
            for p in chord: n.append([round(start+off,3), 0.22, p, 96])
    return {"name": "brass", "program": 62, "gain": 0.7, "notes": n}   # Synth Brass 1

def lead():
    seq = [
        [0.0,1.0,69,104],[1.0,0.5,72,98],[1.5,0.5,74,98],[2.0,1.0,76,108],
        [3.0,1.0,74,100],[4.0,0.75,76,104],[4.75,0.25,79,100],[5.0,1.0,81,112],
        [6.0,0.5,79,102],[6.5,0.5,76,98],[7.0,0.5,74,96],[7.5,0.5,76,98],
    ]
    return {"name": "lead", "program": 81, "wet": True, "gain": 0.85, "notes": seq}  # saw Lead 2

def pad():
    n = []
    for start, _, chord in REGIONS:
        for p in chord: n.append([start, 2.0, p, 66])
    return {"name": "pad", "program": 90, "wet": True, "gain": 0.5, "notes": n}  # Polysynth

VARIANTS = {
    "1-synth-groove":  (12, [bass(), drums()]),                          # rhythm bed
    "2-synth-stabs":   (14, [bass(), drums(), brass()]),                 # Notorious
    "3-synth-lead":    (16, [bass(), drums(), lead()]),                  # Rio
    "4-synth-lush":    (22, [bass(), drums(), pad(), lead()]),           # Save a Prayer
    "5-synth-full":    (18, [bass(), drums(), brass(), pad(), lead()]),  # the big one
}

for name, (reverb, tracks) in VARIANTS.items():
    arr = {"bpm": 124, "reverb": reverb, "tracks": tracks}
    with open(f"{OUT}/{name}.json", "w") as f:
        json.dump(arr, f)
    print("wrote", name)
