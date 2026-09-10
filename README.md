# Rocky

Rocky sonifies live agent activity. It listens to [AG-UI](https://docs.ag-ui.com)
events and turns them into continuous music, so a developer can hear what
their agents are doing without reading a log: a chord while a tool call is in
flight, a tension chord held while an agent waits for approval, resolution back
to home when work resumes, silence when nothing is running.

The music engine is [Magenta RealTime 2](https://github.com/magenta/magenta-realtime)
(`mrt2_base`), driven through its note-conditioning channel.

## How it works

```
Claude Code hooks ──POST /claude-code──▶ rocky/claude_code.py (translate)
                                                   │
any AG-UI producer ──POST /events──────────────────┼──▶ sink() ──▶ captures/<thread>.jsonl
                                                                        │
                                          rocky/harmony.py (event grammar) ──▶ rocky/render.py ──▶ WAV
```

Rocky is an **event sink** (ADR 0004): a local HTTP server any harness can post
AG-UI events to. Harnesses that don't speak AG-UI natively get an **Adapter**;
the first is a Claude Code plugin whose hooks forward raw payloads for
translation inside Rocky. Every session leaves a replayable **Capture**, and
the music is tuned against Captures, never against live agents.

The **event grammar** (`rocky/harmony.py`) maps events to gestures:

| Event | Gesture |
|---|---|
| `RUN_STARTED` | arrival on the home triad, then a root drone while the Run is open |
| `TOOL_CALL_START` … `TOOL_CALL_RESULT` | a chord held for the call's duration, quality by tool category (shell, read, mutate, network, agent) |
| `TEXT_MESSAGE_START` | short ascending arpeggio |
| `RUN_FINISHED` with an interrupt outcome | G7 held until the human answers; the chained Run resolves it |
| `RUN_ERROR` | semitone cluster |
| `RUN_FINISHED` | silence until the next Run |

## Status

Milestone 1 (ingress, Claude Code adapter, captures) and milestone 2 (event
grammar, offline renderer) are done. Captures render to WAV offline for
listening; the realtime engine wired at `sink()` is milestone 3.

## Run it

```sh
uv sync
uv run python -m rocky.server            # listens on http://127.0.0.1:7337
uv run python test_rocky.py              # ingress round trip
.venv/bin/python test_harmony.py         # event grammar
```

Opening Claude Code in this repo forwards the session to Rocky automatically
(`.claude/settings.json`); other projects can install `plugin/`.

Rendering a Capture needs an environment with `magenta_rt` (Apple Silicon,
Metal); see `rocky/render.py` for the invocation. Measured engine behaviour
lives in `docs/sound-design-findings.md` and `docs/benchmark-mrt2.md`.

## Reading order

- `OVERVIEW.md` — every file, one line each, with function signatures
- `CONTEXT.md` — the glossary (Thread, Run, Voice, Interrupt, Chord, Gesture, …)
- `docs/adr/` — the decisions and why
