# OVERVIEW.md

One-line-per-file map of this repo, with function signatures for the Python
files, so an agent can find the right file without reading everything first.
Keep this up to date when files are added, removed, or their public
functions/signatures change — see AGENTS.md.

## Root

- `pyproject.toml` — package metadata (`rocky`, Python >=3.12), one dependency `ag-ui-protocol`, hatchling build.
- `uv.lock` — locked dependency versions for `uv`.
- `.gitignore` — ignores `__pycache__/`, bench-generated `.wav`/`.png`, `.remember/`, `.claude/settings.local.json`, `.claude/.cc-writes/`, `captures/*` (except `.gitkeep`), `.venv/`.
- `CONTEXT.md` — Rocky's glossary/ubiquitous language (Thread, Run, Voice, Audible, Adapter, Phase, Ensemble Phase, Stall, Interrupt, Capture, Register, Note, Style Prompt, Blend Weights). Read this before naming anything new.
- `test_rocky.py` — the one integration test, scripts a full Claude Code session through `translate()` + `capture` and asserts the exact event sequence.
  - `hook(name, **fields) -> dict` — builds one fake Claude Code hook payload for session `"sess-1"`.
  - `main() -> None` — runs `SCRIPT` through `translate`, checks event types/fields against `EXPECTED`, round-trips through `capture.append`/`capture.replay`/`capture.check`. Run: `uv run python test_rocky.py`.
- `captures/.gitkeep` — placeholder; real captures (`<thread>.jsonl`, `<thread>.hooks.jsonl`) are written here at runtime and gitignored.

## `rocky/` — the ingress package

- `rocky/__init__.py` — empty.
- `rocky/server.py` — the HTTP ingress. Run: `python -m rocky.server` (env `ROCKY_PORT`, default 7337).
  - `sink(event, thread: str) -> None` — every translated/validated event ends here; currently just `capture.append`. The music engine will plug in at this line.
  - `class Handler(BaseHTTPRequestHandler)` — `do_POST` handles two routes:
    - `POST /claude-code` — raw Claude Code hook payload → `capture.append_raw` → `claude_code.translate` (per-session `SessionState`, guarded by a global `_lock`) → `sink`.
    - `POST /events` — one AG-UI event or a list, validated via `TypeAdapter(Event)`, timestamped if missing, routed to `sink` under `_last_thread` (AG-UI only names the thread on `RUN_STARTED`).
  - Module-level state: `_sessions: dict[str, SessionState]`, `_lock`, `_last_thread`.
- `rocky/claude_code.py` — translates Claude Code hook payloads into AG-UI events. Thread = `session_id`, Run = `prompt_id`; an Interrupt (permission prompt) ends a Run and the next activity starts a new one chained by `parent_run_id` (see ADR 0002). Never drops or raises: unknown hooks are ignored, orphans are repaired.
  - `class SessionState` (dataclass) — per-session mutable state: `thread_id`, `run_id`, `interrupted`, `finished: set` (run ids already ended), `open: dict` (open `message_id -> agent_id`), `last_message_id`, `last_tool_call_id` (the Interrupt names it, since `PermissionRequest` carries no `tool_use_id`).
  - `now_ms() -> int`
  - `translate(p: dict, s: SessionState) -> list[ev.BaseEvent]` — the core translator; dispatches on `p["hook_event_name"]` (`SessionStart`, `UserPromptSubmit`, `MessageDisplay`, `PreToolUse`, `PostToolUse`/`PostToolUseFailure`, `PermissionRequest`, `Notification`, `Stop`, `StopFailure`, `SubagentStart`/`SubagentStop`, `SessionEnd`; anything else → `[]`). `PostToolUse` reads `tool_response` (a dict with `stdout` or `content`; the documented `tool_result` is a fallback), truncated to 2000 chars. `MessageDisplay` arrives once per completed message with `final`, not per token.
- `rocky/capture.py` — records/replays/validates AG-UI event streams as JSONL. CLI: `python -m rocky.capture replay captures/<id>.jsonl [--speed 1.0]` / `check captures/<id>.jsonl`.
  - `append(event, thread: str) -> None` — appends one validated AG-UI event to `captures/<thread>.jsonl`.
  - `append_raw(payload: dict, thread: str) -> None` — appends the raw hook payload (plus a `received` timestamp) to `captures/<thread>.hooks.jsonl`, so the translator can be re-run offline against the native stream.
  - `load(path) -> list[Event]` — parses a capture file back into AG-UI `Event` objects.
  - `replay(path, speed: float = 1.0) -> Iterator[Event]` — yields events, sleeping the original inter-event gap (`speed=0` disables sleeping).
  - `check(path) -> list[str]` — ordering-problem checker (backwards timestamps, `TOOL_CALL_RESULT` before its `TOOL_CALL_START`, overlapping `RUN_STARTED`); empty list means clean.

## `plugin/` — Claude Code Adapter

- `plugin/.claude-plugin/plugin.json` — plugin manifest (`name: rocky`, describes streaming session lifecycle to the local sonification server).
- `plugin/hooks/hooks.json` — wires every relevant Claude Code hook (`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `StopFailure`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `Notification`, `MessageDisplay`, `SubagentStart`, `SubagentStop`) as async HTTP POSTs to `http://127.0.0.1:7337/claude-code`.

## `.claude/`

- `.claude/settings.json` — enables the `mattpocock-skills@mattpocock` plugin and wires the same 13 hooks as `plugin/hooks/hooks.json` to `http://127.0.0.1:7337/claude-code`, so every Claude Code session opened in this repo is forwarded to Rocky without installing the plugin.
- `.claude/skills/rocky-selftest/SKILL.md` — the `rocky-selftest` skill: from inside a session, confirm the server is listening (`lsof`, not curl; the sandbox blocks localhost), produce each gesture (tool call, an approval-prompt Interrupt that only fires in `default` permission mode, streamed text), then read back and report on the capture.

## `docs/` — design record

- `docs/benchmark-mrt2.md` — result of the realtime-feasibility benchmark: `mrt2_base` sustains 25 fps from Python at ~0.53× realtime (p50 20.9 ms / p99 23.1 ms / budget 40 ms), on an Apple M5 Max. One instance only; two concurrent instances would need 1.06× and can't both sustain. Reproduced by `bench/bench.py`, `bench/probe_blend.py`, `bench/sustained.py`.
- `docs/sound-design-findings.md` — measured facts from probing `mrt2_base` directly (not reasoned about): style prompts implying "less" (`minimal`, `sparse`, `faint`, `simple`, `few harmonics`) render pure silence; unused note-vector pitches must be masked (`-1`) not off (`0`), or held notes decay in a few seconds; note conditioning does control pitch; registers must be spaced inharmonically (octaves/consonant intervals fuse); phases are spectrally distinct once prompts avoid "less"-words; chord tones (including added 7ths and adjacent-semitone clusters) render as separate, audibly distinct bands but decay over a long continuous hold and need re-articulation; sequenced melodies track their schedule at 1–4 notes/sec (faster tracks better; ~250 ms is a workable minimum gesture duration); a bass drone survives under a melody if it shares no harmonics with it.
- `docs/adr/0001-transparent-proxy-not-client.md` — **superseded by ADR 0004.** Original design: Rocky as a transparent AG-UI proxy sitting between an existing client and agent endpoint, sniffing and forwarding events byte-faithfully.
- `docs/adr/0002-thread-owns-the-voice.md` — a Voice (musical identity + Register) is keyed on `threadId`, not `runId`, so human-in-the-loop approval (which ends one Run and starts another) doesn't relocate an agent's pitch range. Voices are reaped: Audible while their Thread has an open Run, an unanswered Interrupt, or is within a short post-completion linger; Registers reclaimed least-recently-audible.
- `docs/adr/0003-style-blending-morphs-it-does-not-layer.md` — Magenta RT2 style blending is a weight-normalized mean of MusicCoCa embeddings (an interpolation, quantized to RVQ tokens), never a layered mix — so per-agent identity must live in the note channel/Registers, not in per-agent Style Prompts. Style is one global value with ≤6 prompt slots (`kMaxPrompts`), carrying only the Ensemble Phase's mood. The blend is a step function post-quantization; Magenta's own Collider throttles weight updates to 10 Hz.
- `docs/adr/0004-event-sink-adapters.md` — **current architecture, supersedes ADR 0001.** Rocky is an inverted event sink (a local server receiving AG-UI events at `POST /events`) rather than a proxy in front of one AG-UI endpoint, because that's the only way to reach harnesses (like Claude Code) that never expose an AG-UI endpoint. Harnesses opt in through Adapters; the first is the Claude Code plugin (`plugin/`), whose hooks POST raw payloads to `POST /claude-code` for translation inside Rocky (`rocky/claude_code.py`). Thread = harness session id, Run = one prompt's turn, permission prompts are Interrupts (per ADR 0002). Hooks POST asynchronously; ordering is measured by `rocky capture check`, not assumed. Records the measured hook granularity: `MessageDisplay` fires once per completed message (30–285 chars), never per token.

## `bench/` — Magenta RT2 latency/sound-design probes

All scripts import `magenta_rt.mlx.system.MagentaRT2SystemMlxfn` directly (no dependency on `rocky/`) and are meant to be run standalone, typically via `uv run --with matplotlib` for the ones needing `matplotlib`/`soundfile`. Most `main()`s take no args and print verdicts to stdout; a few write `.wav`/`.json` artifacts (gitignored except the `.json` schedules).

- `bench/bench.py` — realtime-sustain benchmark: measures `generate()` latency (p50/p99) at `frames=1/5/25` under simulated Rocky control load (notes churning, style re-blended at 10 Hz) against the 40 ms/frame budget. Source of `docs/benchmark-mrt2.md`.
  - `rss_gb() -> float`, `pct(xs, p) -> float`, `blend(embeddings, weights) -> np.ndarray`, `notes_for(active, first_frame) -> list[int]`, `main() -> None`.
- `bench/probe_blend.py` — checks whether the ~101 ms style-blend/quantize latency outlier is a one-off warmup cost or a recurring stall (it's warmup-only; steady state is sub-ms). Module-level `blend(w)`; no `main()`, runs top-level.
- `bench/sustained.py` — 60 s scripted Rocky session (phases escalating idle→reasoning→tool→awaiting→error, tool calls sustaining as held notes) at `frames=1`, writes `rocky_session.wav`, asserts no frame exceeds budget and output isn't silence.
  - `main() -> None`.
- `bench/probe_simple.py` — minimal single-variable probes: `probe_notes.wav` (one style, notes added/removed, tests Register separability) and `probe_phases.wav` (four phases, fresh state each, no notes). Establishes that unused pitches must be masked (`-1`) and phase prompts must avoid "less"-words.
  - `render(mrt, style_emb, sections, reset_each=False, cfg_mc=CFG_MUSICCOCA) -> np.ndarray`, `main() -> None`.
- `bench/probe_chords.py` — tests whether the notes channel renders chord *quality* (home→dom7→cluster→home, continuous state, no gaps). Writes `probe_chords.wav` + `probe_chords.json` (schedule).
  - `main() -> None`.
- `bench/probe_melody.py` — tests whether a sequenced melody (diminished arpeggio at 1/2/4 notes/sec, plus one section with a pedal drone) lands on schedule. Writes `probe_melody.wav` + `probe_melody.json`.
  - `main() -> None`.
- `bench/exp_count.py` — can a listener hear *how many* agents are working? Tests triad vs. inharmonic-spread pitch sets, and organ vs. clean timbre, on a 1→2→3→1 ladder. Writes `count_<timbre>_<pitchset>.wav`.
  - `ladder(mrt, emb, pitches) -> tuple[np.ndarray, list[float]]`, `main() -> None`.
- `bench/exp_sustain.py` — why don't held notes sustain? 2×2 test of unused-pitch value (`0` vs `-1`) × prompt (minimal vs. loud-sustained). Writes `exp_sustain.wav`. Source of the `-1`-vs-`0` masking finding.
  - `run(mrt, emb, unused_val) -> np.ndarray`, `main() -> None`.
- `bench/measure_pitch.py` — decisive test of whether the notes vector controls pitch: measures per-pitch band energy across a 1→2→3→1 ladder from a WAV (hardcoded pitches/steps, predates the schedule-JSON approach).
  - `hz(midi) -> float`, `band_energy(seg, sr, f0, width=0.04) -> float`, `main() -> None`. Usage: `python measure_pitch.py <wav>` (reads `sys.argv[1]`).
- `bench/measure_timeline.py` — schedule-driven successor to `measure_pitch.py`: reads a probe's `<name>.json` schedule and verifies each scheduled (pitch, window) has more band energy than unscheduled windows of that pitch, so it can't go stale against the probe like `analyze_phases.py` did.
  - `hz(midi) -> float`, `band_energy(mono, sr, start, dur, f0, width=0.025) -> float`, `main() -> None`. Usage: `python measure_timeline.py <wav> <schedule.json>`.
- `bench/analyze_phases.py` — checks whether phase prompts (`idle`/`working`/`needs-you`/`error`) actually change the audio (rms/spectral-centroid/rolloff/zcr) or only the label, by hardcoded section timing against `probe_phases.wav`. Superseded in spirit by `measure_timeline.py`'s JSON-driven approach — no `main()`, runs top-level.
- `bench/spectro.py` — renders an annotated spectrogram PNG for visual sanity-checking. Usage: `python spectro.py notes|phases|sustain|<schedule.json> <wav> <png>`.
  - `layout(kind) -> list[tuple[str, float, float]] | None` — section (label, start, dur) layout, either hardcoded (`notes`/`phases`/`sustain`) or read from a probe's schedule JSON.
  - `main() -> None`.
- `bench/probe_chords.json` — recorded schedule (section labels/timings/pitches) from the last `probe_chords.py` run; consumed by `measure_timeline.py`/`spectro.py`.
- `bench/probe_melody.json` — same, for `probe_melody.py`.
