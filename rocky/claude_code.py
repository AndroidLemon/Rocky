"""Claude Code hook payloads -> AG-UI events.

Thread = session_id. Run = prompt_id. An Interrupt (permission prompt) ends the
Run; the next activity starts a new Run chained by parent_run_id (ADR 0002).
Never drops, never raises: unknown hooks are ignored, orphans are repaired.
"""

import json
import time
import uuid
from dataclasses import dataclass, field

from ag_ui.core import Interrupt, RunFinishedInterruptOutcome, RunFinishedSuccessOutcome
from ag_ui.core import events as ev

INTERRUPT_NOTIFICATIONS = {"permission_prompt", "agent_needs_input", "elicitation_dialog"}


@dataclass
class SessionState:
    thread_id: str | None = None
    run_id: str | None = None
    interrupted: bool = False
    finished: set = field(default_factory=set)  # run ids that already ended; never reuse
    open: dict = field(default_factory=dict)  # open message_id -> agent_id (None = main)
    last_message_id: str | None = None


def now_ms() -> int:
    return int(time.time() * 1000)


def translate(p: dict, s: SessionState) -> list[ev.BaseEvent]:
    s.thread_id = p.get("session_id") or s.thread_id or "unknown"
    name = p.get("hook_event_name")
    agent = p.get("agent_id")
    out: list[ev.BaseEvent] = []

    def close_messages(of_agent="*"):
        for mid, owner in list(s.open.items()):
            if of_agent == "*" or owner == of_agent:
                del s.open[mid]
                out.append(ev.TextMessageEndEvent(message_id=mid))

    def close_all():
        close_messages()

    def ensure_run():
        if s.run_id is None:
            rid = p.get("prompt_id")
            s.run_id = rid if rid and rid not in s.finished else str(uuid.uuid4())
            out.append(ev.RunStartedEvent(thread_id=s.thread_id, run_id=s.run_id))
        elif s.interrupted:
            old, s.run_id, s.interrupted = s.run_id, str(uuid.uuid4()), False
            out.append(ev.RunStartedEvent(thread_id=s.thread_id, run_id=s.run_id, parent_run_id=old))

    def finish(outcome):
        close_all()
        out.append(ev.RunFinishedEvent(thread_id=s.thread_id, run_id=s.run_id, outcome=outcome))
        s.finished.add(s.run_id)

    def interrupt(tool_call_id=None):
        if s.interrupted:
            return
        ensure_run()
        close_all()
        finish(RunFinishedInterruptOutcome(interrupts=[
            Interrupt(id=tool_call_id or str(uuid.uuid4()), reason="needs_human", tool_call_id=tool_call_id)]))
        s.interrupted = True

    match name:
        case "SessionStart":
            out.append(ev.CustomEvent(name="session_start", value={"reason": p.get("reason")}))
        case "UserPromptSubmit":
            if s.run_id is not None and not s.interrupted:
                finish(RunFinishedSuccessOutcome())  # missed Stop; keep the capture well-formed
            s.run_id, s.interrupted = None, False
            ensure_run()
        case "MessageDisplay":
            # Real payload: message_id, index, final, delta (text blocks only; thinking never arrives)
            text = p.get("delta") or p.get("text") or ""
            mid = p.get("message_id") or str(uuid.uuid4())
            if not text and mid not in s.open:
                return []  # print mode fires one empty display; not a gesture
            ensure_run()
            if mid not in s.open:
                s.open[mid] = agent
                s.last_message_id = mid
                out.append(ev.TextMessageStartEvent(message_id=mid, role="assistant"))
            if text:
                out.append(ev.TextMessageContentEvent(message_id=mid, delta=text))
            if p.get("final"):
                del s.open[mid]
                out.append(ev.TextMessageEndEvent(message_id=mid))
        case "PreToolUse":
            ensure_run()
            close_messages(agent)
            tid = p.get("tool_use_id") or str(uuid.uuid4())
            out += [
                ev.ToolCallStartEvent(tool_call_id=tid, tool_call_name=p.get("tool_name", "?"),
                                      parent_message_id=s.last_message_id),
                ev.ToolCallArgsEvent(tool_call_id=tid, delta=json.dumps(p.get("tool_input", {}))),
                ev.ToolCallEndEvent(tool_call_id=tid),
            ]
        case "PostToolUse" | "PostToolUseFailure":
            ensure_run()
            tid = p.get("tool_use_id") or str(uuid.uuid4())
            if name == "PostToolUse":
                r = p.get("tool_result")
                content = r.get("content", "") if isinstance(r, dict) else r
                content = content if isinstance(content, str) else json.dumps(content)
                meta = None
            else:
                content, meta = str(p.get("error", "")), {"error": True}
            # ponytail: truncated, Rocky never reads tool output
            out.append(ev.ToolCallResultEvent(message_id=str(uuid.uuid4()), tool_call_id=tid,
                                              content=content[:2000], role="tool", metadata=meta))
        case "PermissionRequest":
            interrupt(p.get("tool_use_id"))
        case "Notification":
            if p.get("notification_type") in INTERRUPT_NOTIFICATIONS:
                interrupt()
        case "Stop":
            ensure_run()
            finish(RunFinishedSuccessOutcome())
            s.run_id = None
        case "StopFailure":
            ensure_run()
            close_all()
            out.append(ev.RunErrorEvent(message=p.get("error_message", ""), code=p.get("error_type")))
            s.finished.add(s.run_id)
            s.run_id = None
        case "SubagentStart":
            out.append(ev.SubagentStartedEvent(subagent_run_id=agent or "?", name=p.get("agent_type", "?")))
            agent = None  # the start event belongs to the parent
        case "SubagentStop":
            close_messages(agent)
            out.append(ev.SubagentFinishedEvent(subagent_run_id=agent or "?"))
            agent = None
        case "SessionEnd":
            close_all()
            if s.run_id is not None and not s.interrupted:
                finish(RunFinishedSuccessOutcome())
            s.run_id = None
            out.append(ev.CustomEvent(name="session_end", value={"reason": p.get("reason")}))
        case _:
            return []

    ts = now_ms()
    for e in out:
        e.timestamp = ts
        if agent and "subagent_run_id" in type(e).model_fields and e.subagent_run_id is None:
            e.subagent_run_id = agent
    return out
