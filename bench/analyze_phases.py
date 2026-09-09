"""Did the phase prompts actually change the audio, or only the label?

If the sections are numerically close, the problem is conditioning strength,
not prompt wording -- and rewriting adjectives would be wasted effort.
"""

import itertools

import numpy as np
import soundfile as sf

NAMES = ["idle", "working", "needs-you", "error"]
SECTION = 5.0
GAP = 1.0

audio, sr = sf.read("probe_phases.wav")
mono = audio.mean(axis=1)

feats = {}
for i, name in enumerate(NAMES):
    start = int(i * (SECTION + GAP) * sr)
    seg = mono[start:start + int(SECTION * sr)]
    seg = seg[int(0.5 * sr):]  # drop ramp-in

    rms = float(np.sqrt((seg**2).mean()))
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    centroid = float((spec * freqs).sum() / spec.sum())
    # rolloff: frequency below which 85% of energy sits
    cum = np.cumsum(spec)
    rolloff = float(freqs[np.searchsorted(cum, 0.85 * cum[-1])])
    # crude density: zero crossings per second
    zcr = float(((seg[:-1] * seg[1:]) < 0).sum() / (len(seg) / sr))

    feats[name] = dict(rms=rms, centroid=centroid, rolloff=rolloff, zcr=zcr)
    print(f"{name:<10} rms {rms:.4f}  centroid {centroid:7.0f}Hz  "
          f"rolloff {rolloff:7.0f}Hz  zcr {zcr:7.0f}/s")

print("\npairwise separation (ratio of larger to smaller; 1.00 = identical)")
worst = None
for a, b in itertools.combinations(NAMES, 2):
    ratios = []
    for k in ("rms", "centroid", "rolloff", "zcr"):
        x, y = feats[a][k], feats[b][k]
        ratios.append(max(x, y) / max(min(x, y), 1e-9))
    spread = max(ratios)
    flag = "  <-- indistinguishable" if spread < 1.3 else ""
    print(f"  {a:<10} vs {b:<10} max ratio {spread:.2f}{flag}")
    if worst is None or spread < worst[1]:
        worst = ((a, b), spread)

print(f"\nclosest pair: {worst[0][0]} / {worst[0][1]} at {worst[1]:.2f}x")
