# AGENTS.md

Guidance for agents working in this repository.

## Start here

**Read [OVERVIEW.md](OVERVIEW.md) first.** It lists every file in the repo
with a description and, for Python files, function signatures — use it to
find the right file before grepping around. **Keep it up to date**: whenever
you add, remove, or rename a file, or change a public function's signature,
update its entry in OVERVIEW.md in the same change.

Also read [CONTEXT.md](CONTEXT.md) before naming anything — it's Rocky's
glossary (Thread, Run, Voice, Adapter, Phase, Register, Note, Style Prompt,
...) and each term lists synonyms to avoid.

## Commands

- Install deps: `uv sync`
- Run the ingress server: `python -m rocky.server` (env `ROCKY_PORT`, default 7337)
- Run the integration test: `uv run python test_rocky.py`
- Replay/validate a capture: `python -m rocky.capture replay captures/<id>.jsonl [--speed 1.0]` / `python -m rocky.capture check captures/<id>.jsonl`
- Run a bench/sound-design probe (needs the `magenta_rt` env — see below): `uv run python bench/<script>.py`, e.g. `bench/bench.py`, `bench/sustained.py`
- Render a probe's spectrogram (needs matplotlib): `uv run --with matplotlib python bench/spectro.py <notes|phases|sustain|schedule.json> <wav> <png>`

There is no lint/build step configured beyond `test_rocky.py`.

## Architecture

Rocky is an **event sink**, not a client (ADR 0004, superseding ADR 0001): a
local HTTP server (`rocky/server.py`) that receives AG-UI events and any
harness that can produce them can be heard. A harness that doesn't speak
AG-UI natively needs an **Adapter** — the only one so far is the Claude Code
plugin (`plugin/`), whose `hooks.json` POSTs raw hook payloads to
`POST /claude-code`, where `rocky/claude_code.py:translate()` turns them into
AG-UI events. Translation lives in Rocky (not in the plugin) so it stays
testable Python.

Key invariants, each backed by an ADR in `docs/adr/`:
- **Thread = session id, Run = one prompt's turn** (`translate()`'s dispatch
  in `rocky/claude_code.py`). A permission prompt is an Interrupt: it ends
  the Run and the next activity starts a new Run chained by `parent_run_id`.
- **A Thread owns the Voice, not a Run** (ADR 0002) — an agent's musical
  identity/pitch Register must not relocate just because a human approved a
  tool call.
- **Style blending morphs, it does not layer** (ADR 0003) — Magenta RT2 style
  blending is a normalized-mean interpolation of embeddings, so per-agent
  identity has to live in the note channel (Registers), never in per-agent
  Style Prompts.

Every translated/validated event passes through one place —
`rocky/server.py:sink()` — before it is captured to JSONL
(`rocky/capture.py`); the music engine will eventually plug in at that line.
`capture.py` also makes captures replayable at original timing and checkable
for ordering problems, which is how `test_rocky.py` verifies the whole
pipeline end to end.

`bench/` is a separate, standalone probe suite against
`magenta_rt.mlx.system.MagentaRT2SystemMlxfn` (no import of `rocky/`) used to
validate sound-design assumptions before building the audio engine; its
measured findings are recorded in `docs/sound-design-findings.md` and
`docs/benchmark-mrt2.md` rather than re-derived by reading the scripts.
`magenta_rt` lives in a separate Prosody/BioBeats virtualenv, not this
project's own env.
