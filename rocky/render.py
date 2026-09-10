"""Render a Capture to WAV + schedule JSON, offline, through MRT2.

Runs in the Prosody venv (the only env with magenta_rt; no ag_ui needed):

  PYTHONPATH=. ~/Desktop/Projects/Prosody/.venv/bin/python -m rocky.render \
      captures/<id>.jsonl renders/<name>.wav [--max-gap 6]

Writes <name>.wav and <name>.json ({"events": [{label, start, dur, pitches}]},
the shape bench/measure_timeline.py and bench/spectro.py read).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from rocky.harmony import Harmony

SR = 48_000
FRAME_MS = 40
# same settings as bench/probe_chords.py, the probe the chord finding came from
STYLE = "loud sustained pipe organ, continuous held tone, bright, full"
CFG_NOTES, CFG_MUSICCOCA, UNUSED = 4.0, 2.0, -1
FADE_FRAMES = 25  # 1 s gate fade-out; fade-in is instant so onsets stay sharp


def rebase(events, max_gap_ms):
    """t=0 at the first event; idle gaps longer than max_gap are clamped."""
    out, t, prev = [], 0, None
    for e in events:
        if prev is not None:
            t += min(max(e["timestamp"] - prev, 0), max_gap_ms)
        prev = e["timestamp"]
        out.append({**e, "timestamp": t})
    return out


def main():
    args = sys.argv[1:]
    max_gap = float(args[args.index("--max-gap") + 1]) if "--max-gap" in args else 6.0
    src, out = args[0], Path(args[1])
    events = rebase([json.loads(l) for l in open(src) if l.strip()], int(max_gap * 1000))
    end_ms = events[-1]["timestamp"] + 3000

    from magenta_rt.mlx.system import MagentaRT2SystemMlxfn
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    emb = np.asarray(mrt.embed_style(STYLE))

    h, chunks, lat, state, gain, i = Harmony(), [], [], None, 0.0, 0
    for now in range(0, end_ms, FRAME_MS):
        while i < len(events) and events[i]["timestamp"] <= now:
            h.apply(events[i])
            i += 1
        active, onsets = h.notes(now, FRAME_MS)
        notes = [UNUSED] * 128
        for p in active:
            notes[p] = 2 if p in onsets else 1
        t0 = time.perf_counter()
        wav, state = mrt.generate(style=emb, notes=notes, drums=[0], frames=1, state=state,
                                  cfg_notes=CFG_NOTES, cfg_musiccoca=CFG_MUSICCOCA)
        lat.append(time.perf_counter() - t0)
        # gate: masked pitches let the model play freely, so no Run open must mean silence
        gain = 1.0 if active else max(0.0, gain - 1 / FADE_FRAMES)
        chunks.append(np.asarray(wav.samples) * gain)

    audio = np.concatenate(chunks, axis=0)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, audio, SR)
    sched = [{"label": g["label"], "start": g["start"] / 1000,
              "dur": ((g["end"] if g["end"] is not None else end_ms) - g["start"]) / 1000,
              "pitches": sorted(g["pitches"])} for g in h.log]
    out.with_suffix(".json").write_text(json.dumps({"events": sched}, indent=1))

    counts = {}
    for g in h.log:
        k = g["label"].split(":")[0]
        counts[k] = counts.get(k, 0) + 1
    lat_ms = np.percentile(lat, [50, 99]) * 1000
    print(f"{out}  {len(audio) / SR:.1f}s  frame p50 {lat_ms[0]:.1f}ms p99 {lat_ms[1]:.1f}ms  "
          + "  ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
