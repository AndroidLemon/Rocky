"""Can you hear HOW MANY agents are working?

Previous attempt used C4+E4+G4 -- a major triad on a dense organ. Consonant
intervals share partials, so three notes looked and sounded like one.

Tests two fixes against that failure:
  pitches - triad (60,64,67) vs inharmonic spread (38,61,82)
  timbre  - dense organ vs clean few-harmonic tone

Each renders a 1 -> 2 -> 3 -> 1 ladder. If the count is legible, the sections
differ; if not, they won't.
"""

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

SR, SECS, GAP = 48_000, 5, 1.0

TIMBRES = {
    "organ": "loud sustained pipe organ, continuous held tone, bright, full",
    "clean": "clean sustained synthesizer tone, simple, few harmonics, pure",
}
PITCHSETS = {
    "triad": [60, 64, 67],          # consonant, shares partials
    "spread": [38, 61, 82],         # D2 / C#4 / A#5 -- no octave relation
}


def ladder(mrt, emb, pitches):
    steps = [pitches[:1], pitches[:2], pitches[:3], pitches[:1]]
    out, state, prev = [], None, set()
    rms = []
    for held in steps:
        active = set(held)
        seg = []
        for _ in range(SECS * 25):
            notes = [-1] * 128
            for p in active:
                notes[p] = 2 if p not in prev else 1
            wav, state = mrt.generate(
                style=emb, notes=notes, drums=[0], frames=1, state=state,
                cfg_notes=4.0, cfg_musiccoca=2.0,
            )
            seg.append(np.asarray(wav.samples))
            prev = active
        seg = np.concatenate(seg, axis=0)
        out.append(seg)
        out.append(np.zeros((int(GAP * SR), 2), dtype=np.float32))
        rms.append(float(np.sqrt((seg**2).mean())))
    return np.concatenate(out, axis=0), rms


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    for tname, prompt in TIMBRES.items():
        emb = np.asarray(mrt.embed_style(prompt))
        for pname, pitches in PITCHSETS.items():
            audio, rms = ladder(mrt, emb, pitches)
            name = f"count_{tname}_{pname}.wav"
            sf.write(name, audio, SR)
            spread = max(rms) / max(min(rms), 1e-9)
            print(f"{tname:<6} {pname:<7} rms " +
                  "  ".join(f"{r:.3f}" for r in rms) +
                  f"   spread {spread:.2f}x -> {name}")


if __name__ == "__main__":
    main()
