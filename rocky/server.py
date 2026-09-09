"""Rocky ingress. Run: python -m rocky.server  (ROCKY_PORT, default 7337)

POST /claude-code   raw Claude Code hook payload -> translated -> sink
POST /events        one AG-UI event or a list       -> validated -> sink
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pydantic import TypeAdapter, ValidationError
from ag_ui.core import Event

from rocky import capture
from rocky.claude_code import SessionState, now_ms, translate

_parse = TypeAdapter(Event).validate_python
_sessions: dict[str, SessionState] = {}
_lock = threading.Lock()  # ponytail: global lock, per-session if it ever matters


_last_thread = "unknown"


def sink(event, thread: str) -> None:
    """Every event ends here. The music engine plugs in at this line."""
    capture.append(event, thread)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _reply(self, code, body=b"{}"):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
        except ValueError:
            return self._reply(400, b'{"error":"bad json"}')

        if self.path == "/claude-code":
            sid = body.get("session_id", "unknown")
            with _lock:
                events = translate(body, _sessions.setdefault(sid, SessionState()))
                for e in events:
                    sink(e, sid)
            print(f"{sid[:8]} {body.get('hook_event_name'):20} -> {' '.join(e.type.value for e in events)}", flush=True)
            return self._reply(200)

        if self.path == "/events":
            try:
                events = [_parse(x) for x in (body if isinstance(body, list) else [body])]
            except (ValidationError, TypeError) as err:
                return self._reply(400, json.dumps({"error": str(err)}).encode())
            global _last_thread
            with _lock:
                for e in events:
                    e.timestamp = e.timestamp or now_ms()
                    # AG-UI names the thread only on RUN_STARTED; later events inherit it
                    _last_thread = getattr(e, "thread_id", None) or _last_thread
                    sink(e, _last_thread)
            return self._reply(200)

        self._reply(404)


if __name__ == "__main__":
    port = int(os.environ.get("ROCKY_PORT", 7337))
    print(f"rocky listening on http://127.0.0.1:{port}  (captures -> {capture.DIR.resolve()})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
