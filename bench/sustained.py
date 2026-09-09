"""60s sustained at frames=1 under Rocky's control load, writing audio out.

Throughput alone proves nothing if the conditioning produces mush. This drives
a scripted Rocky session -- phases escalating, tool calls sustaining as notes --
and saves the result so it can actually be listened to.
"""

import statistics
import time

import numpy as np
import soundfile as sf

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

FRAME_MS = 40.0
SECONDS = 60
PHASES = {
    "idle":      "sparse warm ambient drone, still",
    "reasoning": "pensive solo piano, contemplative",
    "tool":      "driving rhythmic percussion, purposeful",
    "awaiting":  "questioning unresolved motif, suspended",
    "error":     "dissonant strings, alarm, harsh",
}

# A scripted session: (t_seconds, phase, tool calls held during it)
SCRIPT = [
    (0,  "idle",      []),
    (6,  "reasoning", []),
    (14, "tool",      [50]),
    (18, "tool",      [50, 55]),
    (26, "tool",      [55]),         # first tool returns
    (32, "reasoning", []),
    (40, "awaiting",  [62]),         # blocked on a human
    (50, "tool",      [50, 55, 60]),  # approved, three calls fire
    (56, "error",     []),
]


def main():
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    embs = {k: np.asarray(mrt.embed_style(v)) for k, v in PHASES.items()}
    print(f"loaded, {len(embs)} phases embedded\n")

    def phase_at(t):
        cur = SCRIPT[0]
        for entry in SCRIPT:
            if entry[0] <= t:
                cur = entry
        return cur[1], cur[2]

    state, lat, chunks = None, [], []
    prev_active, prev_phase = set(), None
    total = int(SECONDS * 1000 / FRAME_MS)

    for i in range(total):
        t = i * FRAME_MS / 1000.0
        phase, tools = phase_at(t)
        active = set(tools)

        # Sustain-while-in-flight: 2 on the frame a call starts, 1 while held.
        notes = [0] * 128
        for p in active:
            notes[p] = 2 if p not in prev_active else 1

        if phase != prev_phase:
            print(f"  t={t:5.1f}s  phase={phase:<10} notes={sorted(active)}")
            prev_phase = phase
        prev_active = active

        t0 = time.perf_counter()
        wav, state = mrt.generate(
            style=embs[phase], notes=notes, frames=1, state=state
        )
        lat.append((time.perf_counter() - t0) * 1000)
        chunks.append(np.asarray(wav.samples))

    over = sum(1 for x in lat if x > FRAME_MS)
    print(f"\nframes           {len(lat)}  ({SECONDS}s of audio)")
    print(f"per-frame ms     p50 {statistics.median(lat):5.1f}  "
          f"p99 {sorted(lat)[int(len(lat)*0.99)]:5.1f}  max {max(lat):5.1f}")
    print(f"budget 40ms      exceeded {over}/{len(lat)} frames "
          f"({over/len(lat)*100:.2f}%)")
    print(f"headroom         {statistics.mean(lat)/FRAME_MS:.2f}x realtime")

    audio = np.concatenate(chunks, axis=0)
    out = "rocky_session.wav"
    sf.write(out, audio, 48000)
    peak = float(np.abs(audio).max())
    print(f"\nwrote {out}  {audio.shape[0]/48000:.1f}s  peak {peak:.3f}")
    assert peak > 0.01, "output is silence -- conditioning produced nothing"
    assert over == 0, f"{over} frames blew the realtime budget"


if __name__ == "__main__":
    main()
