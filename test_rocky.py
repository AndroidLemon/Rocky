"""One scripted Claude Code session through the translator, capture and check.

Run: uv run python test_rocky.py
"""

import json
import tempfile
from pathlib import Path

from pydantic import TypeAdapter
from ag_ui.core import Event

from rocky import capture
from rocky.claude_code import SessionState, translate

S = "sess-1"


def hook(name, **fields):
    return {"session_id": S, "hook_event_name": name, "cwd": "/x", **fields}


SCRIPT = [
    hook("SessionStart", reason="startup"),
    hook("UserPromptSubmit", prompt_id="p1", prompt="do it"),
    hook("MessageDisplay", prompt_id="p1", message_id="m1", index=0, final=False, delta="Looking.\n"),
    hook("MessageDisplay", prompt_id="p1", message_id="m1", index=0, final=False, delta="Running.\n"),
    hook("PreToolUse", prompt_id="p1", tool_name="Bash", tool_input={"command": "ls"}, tool_use_id="tu1"),
    hook("PostToolUse", prompt_id="p1", tool_name="Bash", tool_input={"command": "ls"}, tool_use_id="tu1",
         tool_response={"stdout": "a b c", "stderr": ""}),
    hook("PreToolUse", prompt_id="p1", tool_name="Edit", tool_input={"file_path": "f"}, tool_use_id="tu2"),
    hook("PermissionRequest", prompt_id="p1", tool_name="Edit", tool_input={"file_path": "f"}),  # no tool_use_id in reality
    hook("Notification", prompt_id="p1", notification_type="permission_prompt"),  # duplicate signal, deduped
    hook("PostToolUseFailure", prompt_id="p1", tool_name="Edit", tool_input={}, tool_use_id="tu2", error="nope"),
    hook("SubagentStart", prompt_id="p1", agent_type="Explore", agent_id="ag1"),
    hook("MessageDisplay", prompt_id="p1", message_id="m2", final=False, delta="sub\n", agent_id="ag1", agent_type="Explore"),
    hook("SubagentStop", prompt_id="p1", agent_type="Explore", agent_id="ag1", last_assistant_message="sub"),
    hook("MessageDisplay", prompt_id="p1", message_id="m3", final=False, delta="Done.\n"),
    hook("MessageDisplay", prompt_id="p1", message_id="m3", final=True, delta=""),
    hook("Stop", prompt_id="p1", last_assistant_message="Done."),
    hook("SubagentStop", prompt_id="p1", agent_type="Stray", agent_id="ag2"),  # after Stop: must not reopen a run
    hook("UserPromptSubmit", prompt_id="p2", prompt="again"),
    hook("StopFailure", prompt_id="p2", error_type="rate_limit", error_message="slow down"),
    hook("SessionEnd", reason="other"),
]

EXPECTED = [
    "CUSTOM",
    "RUN_STARTED",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_CONTENT",
    "TEXT_MESSAGE_END",        # closed by PreToolUse
    "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END",
    "TOOL_CALL_RESULT",
    "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END",
    "RUN_FINISHED",            # interrupt
    "RUN_STARTED",             # resumed by PostToolUseFailure
    "TOOL_CALL_RESULT",
    "SUBAGENT_STARTED",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",   # subagent text
    "TEXT_MESSAGE_END",        # closed by SubagentStop
    "SUBAGENT_FINISHED",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",
    "TEXT_MESSAGE_END",        # closed by final=True
    "RUN_FINISHED",
    "SUBAGENT_FINISHED",
    "RUN_STARTED",
    "RUN_ERROR",
    "CUSTOM",
]


def main():
    state = SessionState()
    events = []
    for payload in SCRIPT:
        events += translate(payload, state)

    got = [e.type.value for e in events]
    assert got == EXPECTED, "\n".join(f"{a!s:28} {b}" for a, b in zip(got, EXPECTED)) + f"\n{len(got)} vs {len(EXPECTED)}"

    validate = TypeAdapter(Event).validate_python
    for e in events:
        validate(e.model_dump(by_alias=True, exclude_none=True))

    runs = [e for e in events if e.type.value == "RUN_STARTED"]
    assert runs[0].thread_id == S and runs[0].run_id == "p1"
    assert runs[1].parent_run_id == "p1" and runs[1].run_id != "p1", "resume must chain to the interrupted run"
    assert runs[2].run_id == "p2"

    fin = [e for e in events if e.type.value == "RUN_FINISHED"]
    assert fin[0].outcome.type == "interrupt" and fin[0].outcome.interrupts[0].tool_call_id == "tu2"
    assert fin[1].outcome is None or fin[1].outcome.type == "success"

    results = [e for e in events if e.type.value == "TOOL_CALL_RESULT"]
    assert results[0].content == "a b c"
    assert results[1].content == "nope" and results[1].metadata == {"error": True}

    sub_text = [e for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"][2]
    assert sub_text.subagent_run_id == "ag1"
    assert [e for e in events if e.type.value == "SUBAGENT_STARTED"][0].name == "Explore"

    err = [e for e in events if e.type.value == "RUN_ERROR"][0]
    assert err.code == "rate_limit" and err.message == "slow down"

    # Robustness: result for an unseen tool call, text with no open run.
    fresh = SessionState()
    orphan = translate(hook("PostToolUse", tool_name="Read", tool_input={}, tool_use_id="zz",
                            tool_response={"type": "create", "content": "x"}), fresh)
    assert [e.type.value for e in orphan] == ["RUN_STARTED", "TOOL_CALL_RESULT"] and orphan[1].content == "x"
    assert translate(hook("SomethingNew"), fresh) == []
    assert translate(hook("MessageDisplay", message_id="e", final=True, delta=""), fresh) == []
    # A late hook after Stop must not resurrect the finished run id.
    late = translate(hook("PostToolUse", prompt_id="p1", tool_name="Read", tool_input={}, tool_use_id="q",
                          tool_response={"stdout": ""}), state)
    assert late[0].type.value == "RUN_STARTED" and late[0].run_id not in ("p1", "p2")

    # Capture round trip.
    with tempfile.TemporaryDirectory() as d:
        capture.DIR = Path(d)
        t = 1000
        for e in events:
            e.timestamp = t
            t += 10
            capture.append(e, S)
        path = Path(d) / f"{S}.jsonl"
        lines = path.read_text().splitlines()
        assert len(lines) == len(events)
        assert json.loads(lines[1])["threadId"] == S  # camelCase wire format
        replayed = list(capture.replay(path, speed=0))
        assert [e.type.value for e in replayed] == EXPECTED
        assert capture.check(path) == []
        # Break ordering and confirm check catches it.
        bad = Path(d) / "bad.jsonl"
        bad.write_text("\n".join([lines[10], lines[7], lines[8], lines[9]]) + "\n")
        problems = capture.check(bad)
        assert any("before" in p for p in problems), problems

    print(f"ok: {len(events)} events")


if __name__ == "__main__":
    main()
