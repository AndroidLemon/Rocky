"""Does a sequenced melody land on schedule at streaming-text speed?

The event-grammar idea plays a melody while text/reasoning streams, possibly
over a drone. That requires the notes channel to follow SCHEDULED onsets, not
just held pitches. Three rates (1, 2, 4 notes/s) find the fastest legible one
-- 4/s is the stress case and is allowed to fail; whatever fails becomes the
minimum gesture duration in the grammar. The last section holds a pedal tone
under the melody to see whether the drone survives the engine's known
redistribute-don't-stack behavior.

Same organ prompt as probe_chords: we measure pitch-band adherence, not attack
character, and it's the vocabulary already proven not to render silence.

Writes probe_melody.wav plus probe_melody.json (one event per note, consumed
by measure_timeline.py and spectro.py).
"""

import json

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

SR = 48_000
CFG_NOTES = 4.0
CFG_MUSICCOCA = 2.0
UNUSED_PITCH = -1
SECTION_S = 8
GAP = 1.0  # silence between sections; state persists across it

STYLE = "loud sustained pipe organ, continuous held tone, bright, full"

# Diminished arpeggio: all minor thirds, so no pitch's harmonic lands in
# another's measurement band (a first draft used a Cm7 arpeggio and C4's 3rd
# harmonic sat exactly on G4's band, faking a failure). Drone Bb2 chosen the
# same way: harmonics 233/350/466Hz all clear the pattern bands by >2.5%.
PATTERN = [60, 63, 66, 69]
DRONE = 46

# (label, notes_per_second, drone_pitch_or_None)
SECTIONS = [
    ("mel_1ps", 1, None),
    ("mel_2ps", 2, None),
    ("mel_4ps", 4, None),
    ("drone_2ps", 2, DRONE),
]


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    emb = np.asarray(mrt.embed_style(STYLE))

    out, state, prev = [], None, set()
    events, t = [], 0.0
    for label, rate, drone in SECTIONS:
        frames = SECTION_S * 25
        for i in range(frames):
            step = int(i * rate / 25)  # which note of the sequence
            active = {PATTERN[step % len(PATTERN)]}
            if drone is not None:
                active.add(drone)
            notes = [UNUSED_PITCH] * 128
            for p in active:
                notes[p] = 2 if p not in prev else 1
            wav, state = mrt.generate(
                style=emb, notes=notes, drums=[0], frames=1, state=state,
                cfg_notes=CFG_NOTES, cfg_musiccoca=CFG_MUSICCOCA,
            )
            out.append(np.asarray(wav.samples))
            prev = active
        note_dur = 1.0 / rate
        for k in range(SECTION_S * rate):
            p = PATTERN[k % len(PATTERN)]
            events.append({"label": f"{label}:{p}", "start": t + k * note_dur,
                           "dur": note_dur, "pitches": [p]})
        if drone is not None:
            events.append({"label": f"{label}:drone", "start": t,
                           "dur": float(SECTION_S), "pitches": [drone]})
        out.append(np.zeros((int(GAP * SR), 2), dtype=np.float32))
        t += SECTION_S + GAP

    audio = np.concatenate(out, axis=0)
    mono = audio.mean(axis=1)
    for label, rate, drone in SECTIONS:
        start = SECTIONS.index((label, rate, drone)) * (SECTION_S + GAP)
        seg = mono[int(start * SR):int((start + SECTION_S) * SR)]
        rms = float(np.sqrt((seg**2).mean()))
        print(f"  {SECTION_S}s  {label:<10} {rate}/s"
              f"{'  +drone' if drone else ''}  rms {rms:.4f}")
        assert rms > 0.002, f"{label!r} produced silence"

    sf.write("probe_melody.wav", audio, SR)
    with open("probe_melody.json", "w") as f:
        json.dump({"events": events}, f, indent=1)
    print(f"  wrote probe_melody.wav  {len(audio)/SR:.1f}s  + probe_melody.json")


if __name__ == "__main__":
    main()
