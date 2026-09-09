# Benchmark: can mrt2_base sustain realtime from Python?

The design assumes one `mrt2_base` instance generating at 25 Hz from Python
while a proxy feeds it control changes. This is the measurement that either
permits or kills that assumption.

**Machine**: Apple M5 Max, 128 GB, macOS 26.5.2 · Python 3.12 · `magenta-rt[mlx]`

## Result: it holds, at roughly half the frame budget

60 seconds of continuous generation at `frames=1` (one 40 ms frame per call),
driven by a scripted session — phases escalating idle → reasoning → tool →
awaiting-human → error, with tool-call notes sustained across frames.

| | |
|---|---|
| Frames generated | 1500 (60 s of audio) |
| Per-frame latency | p50 **20.9 ms** · p99 **23.1 ms** · max **31.4 ms** |
| Budget | 40 ms |
| Frames over budget | **0 / 1500** |
| Headroom | uses **0.53×** of realtime |

Frame size does not change the ratio — `frames=1/5/25` all land at ~0.51–0.53×,
so the finest control granularity costs nothing. Rocky should use `frames=1`.

## Supporting numbers

| | |
|---|---|
| Model load + warmup | 1.2 s |
| Resident memory | 2.9 GB after load, 3.7 GB peak |
| `embed_style` per prompt | ~126 ms — startup only, never on the audio path |
| Blend + quantize to RVQ | 5.8 ms first call, then p50 0.32 ms / max 0.69 ms over 290 calls |

An earlier 101 ms outlier in the blend step was traced to first-call lazy
initialisation, not a recurring stall. Steady state is sub-millisecond, so
re-blending on phase change is free.

## Consequences

**One instance, confirmed.** At 0.53× realtime, two concurrent instances need
1.06× and cannot both sustain. The "N instances mixed down" option is
arithmetically dead, not merely inadvisable.

**The margin is real but not generous.** Worst observed frame used 79% of its
budget, on an otherwise idle machine, from a runtime with no priority
scheduling. Underrun instrumentation ships in v1 — that number is what decides
whether the audio daemon ever needs porting to the C++ `RealtimeRunner`.

## Reproducing

`bench.py` (frame-size sweep), `probe_blend.py` (quantizer latency) and
`sustained.py` (60 s scripted session, writes a listenable WAV).
