"""Is the 101ms blend p99 a one-off warmup, or a recurring spike?

Matters because generate() re-tokenizes the style embedding on EVERY call. If
the quantizer can stall for 100ms, it stalls inside the 40ms frame budget.
"""

import statistics
import time

import numpy as np

from magenta_rt.mlx.system import MagentaRT2SystemMlxfn

mrt = MagentaRT2SystemMlxfn(size="mrt2_base", warmup_steps=1)
embs = [np.asarray(mrt.embed_style(p)) for p in
        ["warm drone", "solo piano", "industrial percussion"]]


def blend(w):
    w = np.asarray(w, dtype=np.float64)
    return np.tensordot(w / w.sum(), np.asarray(embs), axes=(0, 0)).astype(np.float32)


ts = []
for i in range(300):
    style = blend(np.random.dirichlet(np.ones(len(embs))))
    t0 = time.perf_counter()
    mrt.tokenize_style(style)
    ts.append((time.perf_counter() - t0) * 1000)

print(f"first call        {ts[0]:7.2f}ms")
print(f"calls 2-10        {max(ts[1:10]):7.2f}ms max")
rest = ts[10:]
print(f"calls 11-300      p50 {statistics.median(rest):5.2f}  "
      f"p99 {sorted(rest)[int(len(rest)*0.99)]:5.2f}  max {max(rest):5.2f}ms")
print(f"over 5ms          {sum(1 for t in rest if t > 5)}/{len(rest)}")
print(f"over 40ms         {sum(1 for t in rest if t > 40)}/{len(rest)}")
