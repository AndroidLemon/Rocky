"""Does mrt2_base sustain 25fps from Python under Rocky's control load?

Budget: one frame = 40ms of audio. A `generate(frames=F)` call must return in
under F*40ms or the ring buffer underruns. We care about p99, not the mean --
one slow call is one audible dropout.

Simulates Rocky's actual load: notes mutating as tool calls start/stop, and
style re-blended at 10Hz (the rate Magenta's own Collider example uses).
"""

import resource
import statistics
import time

import numpy as np

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

FRAME_MS = 40.0  # 25Hz
PHASES = [
    "sparse warm ambient drone",
    "pensive solo piano, thinking",
    "driving industrial percussion",
    "dissonant strings, alarm",
    "questioning motif, unresolved",
    "calm resolved major chord",
]


def rss_gb():
    # macOS reports maxrss in bytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**3


def pct(xs, p):
    return statistics.quantiles(xs, n=100)[p - 1] if len(xs) > 2 else max(xs)


def blend(embeddings, weights):
    """Exactly what mlx_engine.cpp reblend_musiccoca_tokens does."""
    w = np.asarray(weights, dtype=np.float64)
    w = w / w.sum()
    return np.tensordot(w, np.asarray(embeddings), axes=(0, 0)).astype(np.float32)


def notes_for(active, first_frame):
    """128-int note vector. 2=onset, 1=continuation, 0=off."""
    v = [0] * 128
    for pitch in active:
        v[pitch] = 2 if pitch in first_frame else 1
    return v


def main():
    t0 = time.perf_counter()
    mrt = MagentaRT2SystemMlxfn(size="mrt2_base")
    load_s = time.perf_counter() - t0
    print(f"load+warmup      {load_s:6.1f}s   rss {rss_gb():.1f}GB")

    t0 = time.perf_counter()
    embeddings = [np.asarray(mrt.embed_style(p)) for p in PHASES]
    embed_s = time.perf_counter() - t0
    print(f"embed {len(PHASES)} prompts {embed_s:6.1f}s   ({embed_s/len(PHASES)*1000:.0f}ms each, startup only)")
    print(f"embedding dim    {embeddings[0].shape}")

    # Cost of a phase change: weighted mean + quantize to RVQ tokens.
    ts = []
    for i in range(50):
        w = np.random.dirichlet(np.ones(len(PHASES)))
        t0 = time.perf_counter()
        style = blend(embeddings, w)
        mrt.tokenize_style(style)
        ts.append((time.perf_counter() - t0) * 1000)
    print(f"blend+tokenize   p50 {statistics.median(ts):5.1f}ms  p99 {pct(ts,99):5.1f}ms   (10Hz budget=100ms)")
    print()

    steady = blend(embeddings, [1, 0, 0, 0, 0, 0])
    results = {}

    for frames in (1, 5, 25):
        budget = frames * FRAME_MS
        calls = max(8, int(round(10_000 / budget)))  # ~10s of audio
        state = None
        active, first = set(), set()
        last_blend = 0.0
        style = steady
        lat = []

        for i in range(calls + 3):  # 3 discarded as warmup
            now = i * budget / 1000.0

            # Tool calls start and stop; notes churn like Rocky's would.
            first = set()
            if i % 7 == 0:
                p = 48 + (i % 12)
                if p not in active:
                    active.add(p)
                    first.add(p)
            if i % 11 == 0 and active:
                active.discard(min(active))

            # Re-blend at 10Hz, as Collider does.
            if now - last_blend >= 0.1:
                w = np.random.dirichlet(np.ones(len(PHASES)))
                style = blend(embeddings, w)
                last_blend = now

            t0 = time.perf_counter()
            wav, state = mrt.generate(
                style=style,
                notes=notes_for(active, first),
                frames=frames,
                state=state,
            )
            dt = (time.perf_counter() - t0) * 1000
            if i >= 3:
                lat.append(dt)

        p50, p99 = statistics.median(lat), pct(lat, 99)
        rtf = statistics.mean(lat) / budget
        results[frames] = (p50, p99, rtf, budget)
        verdict = "OK " if p99 < budget else "FAIL"
        print(
            f"frames={frames:<3} budget {budget:6.0f}ms | "
            f"p50 {p50:7.1f}  p99 {p99:7.1f}  max {max(lat):7.1f} | "
            f"rtf {rtf:.2f}x  {verdict}"
        )

    print(f"\npeak rss         {rss_gb():.1f}GB")

    # The claim under test: some frame size clears its budget with headroom.
    passing = [f for f, (_, p99, _, b) in results.items() if p99 < b]
    assert passing, f"mrt2_base cannot sustain 25fps from Python at any frame size: {results}"
    print(f"sustains realtime at frames={passing}")


if __name__ == "__main__":
    main()
