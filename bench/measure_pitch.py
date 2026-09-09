"""Does the notes vector actually control pitch?

Decisive test for Registers. For each ladder step, measure energy in a narrow
band at each requested pitch's fundamental. If note conditioning works, a
pitch's band should light up exactly when that pitch is held and go dark when
it isn't. If the bands don't track, the note channel cannot carry agent
identity and Registers are not a real mechanism.
"""

import sys

import numpy as np
import soundfile as sf

SECS, GAP = 5, 1.0
PITCHES = [38, 61, 82]
STEPS = [[38], [38, 61], [38, 61, 82], [38]]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def band_energy(seg, sr, f0, width=0.04):
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    m = (freqs > f0 * (1 - width)) & (freqs < f0 * (1 + width))
    total = spec.sum()
    return float(spec[m].sum() / max(total, 1e-9))


def main():
    path = sys.argv[1]
    audio, sr = sf.read(path)
    mono = audio.mean(axis=1)
    print(f"{path}\n")
    print("            " + "".join(f"{p:>4}({hz(p):5.0f}Hz) " for p in PITCHES))

    rows = []
    for i, held in enumerate(STEPS):
        start = int(i * (SECS + GAP) * sr) + sr  # skip 1s of attack
        seg = mono[start:start + int((SECS - 1) * sr)]
        vals = [band_energy(seg, sr, hz(p)) for p in PITCHES]
        rows.append(vals)
        marks = "".join(" HELD      " if p in held else " --        " for p in PITCHES)
        print(f"step {i+1}    " + "".join(f"{v:>10.4f} " for v in vals))
        print(f"           {marks}")

    print("\nverdict per pitch (does its band track being held?):")
    for j, p in enumerate(PITCHES):
        held_steps = [i for i, s in enumerate(STEPS) if p in s]
        off_steps = [i for i, s in enumerate(STEPS) if p not in s]
        if not off_steps:
            print(f"  {p}: held throughout, no contrast available")
            continue
        on = np.mean([rows[i][j] for i in held_steps])
        off = np.mean([rows[i][j] for i in off_steps])
        ratio = on / max(off, 1e-9)
        verdict = "tracks" if ratio > 1.5 else "DOES NOT TRACK"
        print(f"  {p} ({hz(p):.0f}Hz): held {on:.4f} vs unheld {off:.4f}"
              f"  = {ratio:.2f}x  {verdict}")


if __name__ == "__main__":
    main()
