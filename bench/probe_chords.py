"""Can the notes channel render chord QUALITY?

The event-grammar idea hangs chords on steps and tool calls: a step opens a
chord, tension resolves back to home. That only works if a held pitch set
renders as an audibly distinct color -- major vs dom7 vs cluster -- instead of
smearing into generic texture. Consonance fusion (bad for counting agents) is
the hoped-for mechanism here: a chord SHOULD fuse into one percept.

Unlike probe_simple, this runs gapless with continuous state: the
cluster->home transition is itself under test (does resolution read as
release?), and an inserted silence would mask it.

Writes probe_chords.wav plus probe_chords.json (the schedule, consumed by
measure_timeline.py and spectro.py) so analyzers can never go stale against
this probe.
"""

import json

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

SR = 48_000
CFG_NOTES = 4.0      # default 1.0 is a loose suggestion; 4.0 is literal
CFG_MUSICCOCA = 2.0  # lowered so style doesn't fight the notes
UNUSED_PITCH = -1    # 0 starves the model; -1 means unconstrained
SECTION_S = 8        # 5s was not enough to establish character

STYLE = "loud sustained pipe organ, continuous held tone, bright, full"

# home twice on purpose: the last section asks "is home recognizable as home
# after tension?", not just "does a triad sound".
SECTIONS = [
    ("home",    [60, 64, 67]),
    ("dom7",    [60, 64, 67, 70]),
    ("cluster", [60, 61, 62]),
    ("home2",   [60, 64, 67]),
]


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    emb = np.asarray(mrt.embed_style(STYLE))

    out, state, prev = [], None, set()
    events, t = [], 0.0
    for label, pitches in SECTIONS:
        active = set(pitches)
        for _ in range(SECTION_S * 25):
            notes = [UNUSED_PITCH] * 128
            for p in active:
                notes[p] = 2 if p not in prev else 1
            wav, state = mrt.generate(
                style=emb, notes=notes, drums=[0], frames=1, state=state,
                cfg_notes=CFG_NOTES, cfg_musiccoca=CFG_MUSICCOCA,
            )
            out.append(np.asarray(wav.samples))
            prev = active
        events.append({"label": label, "start": t, "dur": SECTION_S,
                       "pitches": sorted(active)})
        t += SECTION_S

    audio = np.concatenate(out, axis=0)
    mono = audio.mean(axis=1)
    for e in events:
        seg = mono[int(e["start"] * SR):int((e["start"] + e["dur"]) * SR)]
        rms = float(np.sqrt((seg**2).mean()))
        print(f"  {e['dur']}s  {e['label']:<8} {e['pitches']}  rms {rms:.4f}")
        assert rms > 0.002, f"{e['label']!r} produced silence"

    sf.write("probe_chords.wav", audio, SR)
    with open("probe_chords.json", "w") as f:
        json.dump({"events": events}, f, indent=1)
    print(f"  wrote probe_chords.wav  {len(audio)/SR:.1f}s  + probe_chords.json")


if __name__ == "__main__":
    main()
