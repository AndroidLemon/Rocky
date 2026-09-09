"""Why don't held notes sustain?

The spectrogram shows note onsets firing then decaying to silence, which would
make a 30-second tool call sound identical to a 1-second one -- and that is the
entire value proposition of sustain-while-in-flight.

Two suspects, tested as a 2x2. Held pitch is C4 (60) for the whole run, never
changing, so any decay is the model's doing and not ours.

  unused pitches = 0   ("these 127 are OFF")  vs  -1 ("unconstrained")
  prompt         = minimal/sparse             vs  loud sustained instrument
"""

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

SR, SECS, GAP = 48_000, 6, 1.0
PITCH = 60

PROMPTS = {
    "minimal": "minimal sustained organ, dry, no drums, no melody",
    "loud": "loud sustained pipe organ, continuous held tone, bright, full",
}
UNUSED = {"off": 0, "masked": -1}


def run(mrt, emb, unused_val):
    state, out = None, []
    for i in range(SECS * 25):
        notes = [unused_val] * 128
        notes[PITCH] = 2 if i == 0 else 1
        wav, state = mrt.generate(
            style=emb, notes=notes, drums=[0], frames=1, state=state,
            cfg_notes=4.0, cfg_musiccoca=2.0,
        )
        out.append(np.asarray(wav.samples))
    return np.concatenate(out, axis=0)


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    pieces, labels = [], []

    for pname, prompt in PROMPTS.items():
        emb = np.asarray(mrt.embed_style(prompt))
        for uname, uval in UNUSED.items():
            seg = run(mrt, emb, uval)
            mono = seg.mean(axis=1)
            # Does it still sound at the END, or only at the onset?
            head = float(np.sqrt((mono[:SR] ** 2).mean()))
            tail = float(np.sqrt((mono[-2 * SR:] ** 2).mean()))
            ratio = tail / max(head, 1e-9)
            print(f"{pname:<8} unused={uname:<7} head {head:.4f}  "
                  f"tail {tail:.4f}  sustain {ratio:5.2f}x"
                  f"{'   <-- sustains' if ratio > 0.5 else ''}")
            pieces.append(seg)
            pieces.append(np.zeros((int(GAP * SR), 2), dtype=np.float32))
            labels.append(f"{pname}/{uname}")

    sf.write("exp_sustain.wav", np.concatenate(pieces, axis=0), SR)
    print("\nsections:", " | ".join(labels))
    print("wrote exp_sustain.wav")


if __name__ == "__main__":
    main()
