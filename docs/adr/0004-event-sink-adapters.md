# Rocky is an event sink; harnesses opt in through Adapters

Supersedes ADR 0001's architecture.

ADR 0001 put Rocky in front of an AG-UI HTTP endpoint as a transparent proxy so
it could hear agents a developer already had running. That only hears agents
already exposed as AG-UI endpoints, which excludes Claude Code and every CLI
harness the developer actually runs. Reach, not ambience, is the property that
matters, so Rocky is inverted: it is a local server that receives AG-UI events,
and any harness that can produce them can be heard.

The interface is the AG-UI event schema, validated with the official
`ag-ui-protocol` models. `POST /events` takes AG-UI events directly. An Adapter
turns one harness's native signals into those events. The first Adapter is a
Claude Code plugin: a single `hooks.json` of HTTP hooks that POST raw hook
payloads to `POST /claude-code`, where Rocky translates them. Translation lives
in Rocky so it is testable Python and the plugin needs no scripts.

## Considered options

Keeping the proxy and adding shims per harness was rejected because the proxy
would then be one adapter pretending to be the architecture. Translating inside
hook scripts was rejected because Claude Code has native HTTP hooks, so scripts
would be pure overhead. Tailing session transcripts was rejected because the
format is documented as unstable and only reaches block granularity.

## Consequences

- Thread = the harness's session id; Run = one prompt's turn. A permission
  prompt is an Interrupt: it ends the Run, and the next activity starts a new Run
  chained by `parentRunId`, exactly as ADR 0002 requires.
- Streamed text arrives per completed assistant message (`MessageDisplay`
  with `final`), occasionally per content block, never per token or per line
  as the docs claim. Measured 2026-09-09: one delta per message, 30 to 285
  characters. A text gesture is therefore roughly once per turn segment, and
  thinking is never delivered. Claude Code's reasoning is inaudible.
- Hooks POST asynchronously so a session with Rocky stopped costs nothing and
  shows no errors. Ordering over localhost is measured by `capture check`, not
  assumed; if it ever fails, the hooks go synchronous with a short timeout.
- Record and replay stay nearly free: every event passes through one `sink`,
  and a Capture is that stream as JSONL.
- The ADR 0001 proxy remains a possible later Adapter for agents that already
  speak AG-UI. Its stream-fidelity constraint applies to that Adapter only.
