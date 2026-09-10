"""Scripted timeline through the event grammar, plus invariants over captures/.

Run: .venv/bin/python test_harmony.py
"""

import json
from pathlib import Path

from rocky.harmony import DRONE, ERROR, HOME, INTERRUPT, Harmony

T = "t1"


def ev(type, t, **f):
    return {"type": type, "timestamp": t, "threadId": T, **f}


SCRIPT = [
    ev("RUN_STARTED", 0, runId="r1"),
    ev("TOOL_CALL_START", 2000, toolCallId="tc1", toolCallName="Bash"),
    ev("TOOL_CALL_RESULT", 2120, toolCallId="tc1", content="ok"),
    ev("TOOL_CALL_START", 3000, toolCallId="tc2", toolCallName="Edit"),
    ev("RUN_FINISHED", 8000, runId="r1", outcome={"type": "interrupt", "interrupts": []}),
    ev("RUN_STARTED", 20000, runId="r2", parentRunId="r1"),
    ev("TOOL_CALL_RESULT", 21000, toolCallId="tc2", content="late"),   # released by the interrupt already
    ev("TEXT_MESSAGE_START", 21500, messageId="m1", role="assistant"),
    ev("TOOL_CALL_START", 23000, toolCallId="tc3", toolCallName="Read"),
    ev("TOOL_CALL_RESULT", 23050, toolCallId="tc3", content="nope", metadata={"error": True}),
    ev("RUN_ERROR", 25000, message="boom"),
    ev("RUN_STARTED", 28000, runId="r3"),
    ev("RUN_FINISHED", 29000, runId="r3", outcome={"type": "success"}),
]

# (instant, expected active, pitches that must be onsets, pitches that must not be onsets)
EXPECT = [
    (40, set(HOME), set(HOME), set()),
    (1500, {DRONE}, {DRONE}, set()),                 # arrival over, drone only
    (2040, {60, 65, 67}, {60, 65, 67}, set()),       # shell chord (sus4)
    (2220, {60, 65, 67}, set(), {60, 65, 67}),       # 100 ms after a 120 ms call: minimum hold
    (2700, {DRONE}, set(), set()),
    (3040, {60, 63, 67}, {60, 63, 67}, set()),       # mutate chord (minor)
    (6960, {60, 63, 67}, set(), {60, 63, 67}),
    (7000, {60, 63, 67}, {60, 63, 67}, set()),       # re-onset at 4 s
    (8040, set(INTERRUPT), set(INTERRUPT), set()),   # G7 replaces the chord
    (12000, set(INTERRUPT), set(INTERRUPT), set()),  # re-onset while waiting
    (19960, set(INTERRUPT), set(), set(INTERRUPT)),
    (20040, set(HOME), set(HOME), set()),            # resolution
    (21520, {72}, {72}, set()),                      # arpeggio over home, +12
    (21800, {76}, {76}, set()),
    (22040, {79}, {79}, set()),
    (22300, {DRONE}, set(), set()),
    (23100, {60, 61, 64, 67, 74}, {61}, set()),      # add9 chord + failure semitone
    (23600, {DRONE}, set(), set()),
    (25040, set(ERROR), set(ERROR), set()),
    (27100, set(), set(), set()),                    # error over, nothing until the next Run
    (28040, set(HOME), set(HOME), set()),
    (29040, set(), set(), set()),
    (40000, set(), set(), set()),
]


def main():
    h = Harmony()
    i = 0
    for now, want_active, want_on, want_off in EXPECT:
        while i < len(SCRIPT) and SCRIPT[i]["timestamp"] <= now:
            h.apply(SCRIPT[i])
            i += 1
        active, onsets = h.notes(now)
        assert active == want_active, f"t={now}: active {sorted(active)} != {sorted(want_active)}"
        assert want_on <= onsets, f"t={now}: onsets {sorted(onsets)} missing {sorted(want_on - onsets)}"
        assert not (want_off & onsets), f"t={now}: unexpected onsets {sorted(want_off & onsets)}"
        assert onsets <= active

    labels = [g["label"] for g in h.log]
    assert labels.count("interrupt") == 1 and labels.count("error") == 1 and labels.count("arpeggio") == 3
    assert all(g["end"] is not None for g in h.log), "every gesture is closed by the end"

    # Invariants over every real capture.
    n = 0
    for path in sorted(Path("captures").glob("*.jsonl")):
        if "hooks" in path.name or path.name.startswith("unknown"):
            continue
        events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        if not events:
            continue
        h = Harmony()
        t0, t1 = events[0]["timestamp"], events[-1]["timestamp"] + 3000
        j = 0
        for now in range(t0, t1, 40):
            while j < len(events) and events[j]["timestamp"] <= now:
                h.apply(events[j])
                j += 1
            active, onsets = h.notes(now)
            assert len(active) <= 8, f"{path.name} t={now - t0}: {len(active)} active pitches"
            assert onsets <= active, path.name
        ended = events[-1]["type"] in ("RUN_FINISHED", "RUN_ERROR") and \
            (events[-1].get("outcome") or {}).get("type") != "interrupt"
        if ended:
            assert not active, f"{path.name}: {sorted(active)} still active after the final run ended"
        n += 1
    print(f"ok: timeline, {n} captures")


if __name__ == "__main__":
    main()
