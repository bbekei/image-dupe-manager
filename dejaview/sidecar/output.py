"""
sidecar/output.py — Injectable output stream for the sidecar JSON-RPC protocol.

Extracts the write/ok/err/notify functions from sidecar_main.py into a
testable class.  Production uses StdoutOutput (queue-based, non-blocking).
Tests use ListOutput (collects messages in a list).

Plan reference: Phase 1, Week 2 — Injectable output stream refactor.
"""

import json
import queue
import sys
import threading
from typing import Protocol, runtime_checkable


# ── Forwarded event set (consumed by frontend) ──────────────────────────────
FORWARDED_EVENTS = frozenset({
    "scan:discovery_progress",
    "scan:progress",
    "scan:status",
    "scan:duplicate_found",
    "scan:similarity_progress",
    "scan:error",
    "exec:progress",
    "exec:complete",
    "exec:error",
    "selection:progress",
    "selection:complete",
})

# ── JSON-RPC error codes ────────────────────────────────────────────────────
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@runtime_checkable
class Output(Protocol):
    """Interface for sidecar output streams."""

    def write(self, obj: dict) -> None: ...
    def ok(self, req_id, result) -> None: ...
    def err(self, req_id, code: int, message: str) -> None: ...
    def notify(self, event_name: str, detail: dict) -> None: ...


class StdoutOutput:
    """
    Production output: queue-based non-blocking writer to stdout.

    Scanner/executor threads call write()/notify() which enqueue JSON lines.
    A dedicated daemon thread drains the queue to stdout, preventing pipe
    backpressure from blocking the producer threads.
    """

    def __init__(self, stream=None):
        self._stream = stream or sys.stdout
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        while True:
            line = self._queue.get()
            if line is None:
                break
            try:
                self._stream.write(line)
                self._stream.flush()
            except OSError:
                break

    def write(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=True) + "\n"
        self._queue.put(line)

    def ok(self, req_id, result) -> None:
        self.write({"jsonrpc": "2.0", "id": req_id, "result": result})

    def err(self, req_id, code: int, message: str) -> None:
        self.write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    def notify(self, event_name: str, detail: dict) -> None:
        if event_name not in FORWARDED_EVENTS:
            return
        self.write({"jsonrpc": "2.0", "method": "event", "params": {"name": event_name, "detail": detail}})

    def shutdown(self) -> None:
        """Signal the writer thread to exit and wait for it."""
        self._queue.put(None)
        self._thread.join(timeout=5.0)


class ListOutput:
    """
    Test output: collects JSON-RPC messages in a list.

    No threads, no I/O.  Use for contract tests and unit tests that need
    to inspect what the sidecar would have written to stdout.
    """

    def __init__(self):
        self.messages: list[dict] = []

    def write(self, obj: dict) -> None:
        self.messages.append(obj)

    def ok(self, req_id, result) -> None:
        self.write({"jsonrpc": "2.0", "id": req_id, "result": result})

    def err(self, req_id, code: int, message: str) -> None:
        self.write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    def notify(self, event_name: str, detail: dict) -> None:
        if event_name not in FORWARDED_EVENTS:
            return
        self.write({"jsonrpc": "2.0", "method": "event", "params": {"name": event_name, "detail": detail}})

    @property
    def responses(self) -> list[dict]:
        """Return only JSON-RPC responses (have 'id')."""
        return [m for m in self.messages if "id" in m]

    @property
    def events(self) -> list[dict]:
        """Return only JSON-RPC notifications (no 'id')."""
        return [m for m in self.messages if "id" not in m]

    @property
    def errors(self) -> list[dict]:
        """Return only error responses."""
        return [m for m in self.messages if "error" in m]
