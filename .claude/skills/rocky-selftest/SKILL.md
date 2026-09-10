---
name: rocky-selftest
description: Self-test the Rocky ingress from inside a Claude Code session. Use when asked to "self-test Rocky", "test the plugin", "check Rocky hears this session", or after changing rocky/claude_code.py or the hooks config.
---

# Rocky self-test

You are the agent being sonified. Produce each gesture Rocky listens for, then
read back the capture and report what arrived. Do every step even if an earlier
one fails; the report is the deliverable.

## 1. Confirm Rocky is listening

```
lsof -nP -iTCP:7337 -sTCP:LISTEN
```

Expect a python process on the line. If nothing is listed, stop and tell the
user to run `uv run python -m rocky.server` in another terminal; nothing else
can be tested.

Do not probe with curl: the Bash sandbox blocks localhost, so curl reports
"connection refused" even when the server is up. Hooks are sent by Claude Code
itself, outside the sandbox, and reach the server normally.

## 2. Produce the gestures

Do these in order, as separate tool calls, so each hook fires distinctly:

1. **Tool call**: run `ls bench` with Bash.
2. **Interrupt**: use the Write tool to create `captures/selftest.txt` with one
   line of text. In default permission mode this asks the user to approve.
   Tell the user beforehand that an approval prompt is expected and to approve it.
3. **Streamed text**: after the tools, reply to the user with at least four
   short lines of ordinary prose (not a list, not code) so `MessageDisplay`
   fires per completed line.

## 3. Read back the capture

Find your own session id from any hook payload: `ls -t captures/*.hooks.jsonl | head -1`.
Then:

```
f=$(ls -t captures/*.jsonl | grep -v hooks | head -1)
uv run python -m rocky.capture check "$f"
python3 -c "import json,collections; print(collections.Counter(json.loads(l)['type'] for l in open('$f')))"
```

## 4. Report

State plainly, one line each, whether the capture contains:

- `check` result (clean or the listed problems)
- `TOOL_CALL_START` + `TOOL_CALL_RESULT` for the Bash call
- a `RUN_FINISHED` with outcome `interrupt` followed by `RUN_STARTED` with `parentRunId`
- `TEXT_MESSAGE_CONTENT` events with non-empty deltas
- anything unexpected (repeated run ids, missing `RUN_FINISHED`, unknown hooks in `*.hooks.jsonl`)

If a gesture is missing, quote the matching raw payload line from
`captures/<session>.hooks.jsonl` so the translator can be fixed offline.
Finally remove `captures/selftest.txt`.
