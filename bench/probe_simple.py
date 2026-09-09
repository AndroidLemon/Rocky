"""Minimal probes. Each varies ONE thing, everything else nailed down.

probe_notes.wav  - one fixed sparse style, notes added then removed. Tests
                   whether Registers are separable. No phase changes at all.
probe_phases.wav - no notes ever, each phase generated from a fresh state so
                   you hear its character without the previous one bleeding in.

Deliberately un-musical: drums off, strong note adherence, sparse prompts,
silence between sections so edges are obvious.
"""

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

SR = 48_000
CFG_NOTES = 4.0      # default 1.0 is a loose suggestion; 4.0 is literal
CFG_MUSICCOCA = 2.0  # default 3.0; lowered so style doesn't fight the notes
GAP = 1.0            # seconds of true silence between sections

# Measured: a "minimal / sparse / no melody" prompt makes held notes decay to
# silence within ~3s regardless of masking. A loud sustained instrument holds.
NOTE_STYLE = "loud sustained pipe organ, continuous held tone, bright, full"

# Measured: unused pitches must be -1 (unconstrained), not 0 ("explicitly off").
# 0 starves the model -- sustain drops from 0.57x to 0.15x and onsets halve.
UNUSED_PITCH = -1

# (seconds, held pitches) - an additive then subtractive ladder, no empty
# sections: with UNUSED_PITCH=-1 an empty vector means "play freely", not
# silence. Silence when nothing is held is the gate's job, not conditioning's.
NOTE_LADDER = [
    (5, [60]),
    (5, [60, 64]),
    (5, [60, 64, 67]),
    (5, [60]),
]

# idle is deliberately absent: idle is the gate closing, not a prompt. Every
# phase below must describe something PLAYING -- "sparse", "minimal" and
# "almost silence" are literal instructions to this model, and two of them
# produced pure digital silence on the first attempt.
# Contrast is carried by register, brightness and density, never by "how little".
PHASES = [
    ("reasoning", "slow warm cello, low register, smooth sustained bowing"),
    ("tool",      "bright fast marimba, mid register, busy repeating pattern"),
    ("needs-you", "loud ringing high bell, insistent, repeating chime"),
    ("error",     "harsh distorted low buzz, grinding, unstable"),
]
CFG_PHASES = 5.0   # style adherence is the ONLY thing this probe tests
SECTION_S = 8      # 5s from a fresh state was not enough to establish character


def render(mrt, style_emb, sections, reset_each=False, cfg_mc=CFG_MUSICCOCA):
    """sections: list of (seconds, held_pitches). Returns float array."""
    out, state, prev = [], None, set()
    for secs, pitches in sections:
        if reset_each:
            state, prev = None, set()
        active = set(pitches)
        for _ in range(int(secs * 25)):
            notes = [UNUSED_PITCH] * 128
            for p in active:
                notes[p] = 2 if p not in prev else 1
            wav, state = mrt.generate(
                # drums is documented as "1 int" but is concatenated as a list
                style=style_emb, notes=notes, drums=[0], frames=1, state=state,
                cfg_notes=CFG_NOTES, cfg_musiccoca=cfg_mc,
            )
            out.append(np.asarray(wav.samples))
            prev = active
        out.append(np.zeros((int(GAP * SR), 2), dtype=np.float32))
    return np.concatenate(out, axis=0)


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")

    print("probe_notes: one style, notes added then removed")
    emb = np.asarray(mrt.embed_style(NOTE_STYLE))
    audio = render(mrt, emb, NOTE_LADDER)
    sf.write("probe_notes.wav", audio, SR)
    for secs, pitches in NOTE_LADDER:
        print(f"  {secs}s  notes={sorted(pitches) or '-'}")
    print(f"  wrote probe_notes.wav  {len(audio)/SR:.1f}s\n")

    print("probe_phases: no notes, fresh state per phase")
    out = []
    for name, prompt in PHASES:
        emb = np.asarray(mrt.embed_style(prompt))
        seg = render(mrt, emb, [(SECTION_S, [])], reset_each=True, cfg_mc=CFG_PHASES)
        out.append(seg)
        rms = float(np.sqrt((seg**2).mean()))
        print(f"  {SECTION_S}s  {name:<10} rms {rms:.4f}  {prompt!r}")
        assert rms > 0.002, f"{name!r} produced silence -- prompt asked for too little"
    audio = np.concatenate(out, axis=0)
    sf.write("probe_phases.wav", audio, SR)
    print(f"  wrote probe_phases.wav  {len(audio)/SR:.1f}s")


if __name__ == "__main__":
    main()
