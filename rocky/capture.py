"""Captures: one AG-UI event per JSONL line, replayable at original timing.

  python -m rocky.capture replay captures/<id>.jsonl [--speed 1.0]
  python -m rocky.capture check  captures/<id>.jsonl
"""

import json
import sys
import time
from pathlib import Path

from pydantic import TypeAdapter
from ag_ui.core import Event

DIR = Path("captures")
_parse = TypeAdapter(Event).validate_python


def append(event, thread: str) -> None:
    DIR.mkdir(exist_ok=True)
    with open(DIR / f"{thread}.jsonl", "a") as f:
        f.write(json.dumps(event.model_dump(by_alias=True, exclude_none=True)) + "\n")


def load(path):
    return [_parse(json.loads(line)) for line in Path(path).read_text().splitlines() if line.strip()]


def replay(path, speed: float = 1.0):
    """Yield events, sleeping the original gap between them (speed=0: no sleep)."""
    prev = None
    for e in load(path):
        if prev is not None and speed and e.timestamp and prev:
            time.sleep(max(0, (e.timestamp - prev) / 1000 / speed))
        prev = e.timestamp
        yield e


def check(path) -> list[str]:
    """Ordering problems in a capture. Empty list means clean."""
    problems, started, last_ts, open_run = [], set(), 0, None
    for i, e in enumerate(load(path)):
        t = e.type.value
        if e.timestamp and e.timestamp < last_ts:
            problems.append(f"line {i}: {t} timestamp goes backwards")
        last_ts = e.timestamp or last_ts
        if t == "TOOL_CALL_START":
            started.add(e.tool_call_id)
        elif t == "TOOL_CALL_RESULT" and e.tool_call_id not in started:
            problems.append(f"line {i}: TOOL_CALL_RESULT {e.tool_call_id} before its TOOL_CALL_START")
        elif t == "RUN_STARTED":
            if open_run:
                problems.append(f"line {i}: RUN_STARTED while run {open_run} still open")
            open_run = e.run_id
        elif t in ("RUN_FINISHED", "RUN_ERROR"):
            open_run = None
    return problems


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "replay":
        speed = float(sys.argv[sys.argv.index("--speed") + 1]) if "--speed" in sys.argv else 1.0
        t0 = time.time()
        for e in replay(path, speed):
            d = e.model_dump(by_alias=True, exclude_none=True)
            d.pop("timestamp", None)
            print(f"{time.time() - t0:7.2f}s  {json.dumps(d)[:140]}")
    elif cmd == "check":
        problems = check(path)
        print("\n".join(problems) or "clean")
        sys.exit(1 if problems else 0)
