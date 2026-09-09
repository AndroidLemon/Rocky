# Rocky is a transparent proxy, not an AG-UI client

**Superseded by [ADR 0004](0004-event-sink-adapters.md).** The proxy is now a
possible Adapter, not the architecture.

AG-UI is client-initiated: a client POSTs a `RunAgentInput` to an agent endpoint
and consumes the SSE stream that comes back. Rocky needs to be ambient — it must
hear agents a developer already has running, having launched none of them — so it
sits between the existing client and the agent endpoint, forwards the run
verbatim, and tees the event stream to the audio layer.

## Considered options

A conformant AG-UI client (`rocky run <url> "prompt"`) is the natural fit for the
protocol, but you only hear agents you started through Rocky, which is not
ambient. An inverted event sink that producers POST to would work for any agent,
but is not AG-UI and requires a shim per producer. An in-process middleware
library is the lowest-latency option and useless for any harness whose code you
don't own.

## Consequences

Stream fidelity becomes a hard constraint rather than a quality goal. Rocky must
decode enough of the stream to sonify it while what reaches the real client stays
byte-faithful — `RAW` and `CUSTOM` events preserved, auth headers passed through,
frame order untouched, response never buffered. Sniff-and-forward; do not
parse-and-re-serialize.

Record and replay come nearly free, because Rocky already sits in the path of
every event.
