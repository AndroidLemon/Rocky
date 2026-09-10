"""Event grammar: AG-UI events -> MRT2 note conditioning (milestone 2).

Pure and dependency-free: consumes wire-format dicts (`type`, `toolCallId`,
`toolCallName`, `outcome`, `timestamp`), so it runs in any env. Home key is C
(single agent, v1). Every Run arrives at home, every Interrupt leaves it.

    h = Harmony()
    h.apply(event)                 # event["timestamp"] is the clock, ms
    active, onsets = h.notes(now)  # pitch sets for the frame ending at now
    h.log                          # gesture records for schedule JSON
"""

DRONE = 36
HOME = (60, 64, 67)
INTERRUPT = (55, 59, 62, 65)  # G7: leaves home, resolves on the chained RUN_STARTED
ERROR = (60, 61, 62)          # cluster
FAILURE = (61,)               # added to the chord

REONSET_MS = 4000   # measured sustain decay: re-articulate held pitches
MIN_HOLD_MS = 500   # a sub-second tool call still gets an audible chord
ARRIVAL_MS = 1000
ARP_STEP_MS = 250
ERROR_MS = 2000
FAILURE_MS = 500

# ponytail: tune by ear; user-editable table is a later milestone
CHORDS = {
    "shell":   (60, 65, 67),        # sus4
    "read":    (60, 64, 67, 74),    # add9
    "mutate":  (60, 63, 67),        # minor
    "network": (60, 64, 66, 71),    # lydian maj7
    "agent":   (67, 71, 74),        # V, above
    "other":   HOME,
}
CATEGORY = {
    "Bash": "shell",
    **dict.fromkeys(("Read", "Grep", "Glob", "LS", "ToolSearch", "LSP", "Skill"), "read"),
    **dict.fromkeys(("Edit", "Write", "MultiEdit", "NotebookEdit"), "mutate"),
    **dict.fromkeys(("WebSearch", "WebFetch"), "network"),
    **dict.fromkeys(("Agent", "Task"), "agent"),
}


def category(tool_name) -> str:
    if tool_name in CATEGORY:
        return CATEGORY[tool_name]
    return "network" if str(tool_name).startswith("mcp__") else "other"


class Harmony:
    def __init__(self):
        self.run_open = False
        self.calls: dict[str, dict] = {}   # toolCallId -> gesture record
        self.log: list[dict] = []          # every gesture: label, start, end (None = open), pitches
        self._prev: set[int] = set()
        self._drone: dict | None = None

    # -- events -------------------------------------------------------------

    def _gesture(self, label, start, end, pitches):
        g = {"label": label, "start": start, "end": end, "pitches": tuple(pitches)}
        self.log.append(g)
        return g

    def _close_open(self, t, labels=None):
        for g in self.log:
            if g["end"] is None and (labels is None or g["label"].split(":")[0] in labels):
                g["end"] = t

    def apply(self, e: dict) -> None:
        t = e["timestamp"]
        match e["type"]:
            case "RUN_STARTED":
                self._close_open(t)  # interrupt resolves; stale chords release
                self.calls.clear()
                self.run_open = True
                self._gesture("arrival", t, t + ARRIVAL_MS, HOME)
            case "TOOL_CALL_START":
                cat = category(e.get("toolCallName"))
                self.calls[e.get("toolCallId")] = self._gesture(f"chord:{cat}", t, None, CHORDS[cat])
            case "TOOL_CALL_RESULT":
                g = self.calls.pop(e.get("toolCallId"), None)
                if g is not None:
                    g["end"] = max(t, g["start"] + MIN_HOLD_MS)
                    if (e.get("metadata") or {}).get("error"):
                        self._gesture("failure", t, t + FAILURE_MS, FAILURE)
            case "TEXT_MESSAGE_START":
                base = set().union(*(g["pitches"] for g in self.calls.values())) or set(HOME)
                for i, p in enumerate(sorted(base)):
                    self._gesture("arpeggio", t + i * ARP_STEP_MS, t + (i + 1) * ARP_STEP_MS, (p + 12,))
            case "RUN_FINISHED":
                self._close_open(t)
                self.calls.clear()
                self.run_open = False
                if (e.get("outcome") or {}).get("type") == "interrupt":
                    self._gesture("interrupt", t, None, INTERRUPT)
            case "RUN_ERROR":
                self._close_open(t)
                self.calls.clear()
                self.run_open = False
                self._gesture("error", t, t + ERROR_MS, ERROR)
        # ponytail: log grows unbounded; fine offline, the realtime daemon (m3) prunes closed gestures

    # -- frames -------------------------------------------------------------

    def notes(self, now: int, frame_ms: int = 40) -> tuple[set[int], set[int]]:
        """(active, onsets) for the frame ending at `now`. Call in ascending time."""
        active, onsets = set(), set()
        live = [g for g in self.log if g["label"] != "drone"
                and g["start"] <= now < (g["end"] if g["end"] is not None else now + 1)]
        for g in live:
            active |= set(g["pitches"])
            if (now - g["start"]) % REONSET_MS < frame_ms:
                onsets |= set(g["pitches"])
        if self.run_open and not active:
            if self._drone is None or self._drone["end"] is not None:
                self._drone = self._gesture("drone", now, None, (DRONE,))
            active.add(DRONE)
            if (now - self._drone["start"]) % REONSET_MS < frame_ms:
                onsets.add(DRONE)
        elif self._drone is not None and self._drone["end"] is None:
            self._drone["end"] = now
        onsets |= active - self._prev
        self._prev = active
        return active, onsets & active
