"""JSON-lines RPC client for the in-desktop agent, over a subprocess pipe or a UNIX socket."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from collections.abc import Callable

from .errors import AgentError, BackendError


class ConnectionLost(BackendError):
    """The connection to the desktop's agent dropped (desktop stopped, paused or removed)."""


class Transport:
    def write(self, data: bytes) -> None: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...
    def error_text(self) -> str:
        return ""


class ProcessTransport(Transport):
    """Talks through a helper process, e.g. `docker exec -i <c> python3 bridge.py`."""

    def __init__(self, cmd: list[str]):
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
        except FileNotFoundError as e:
            raise BackendError(f"{cmd[0]} is not installed or not on PATH") from e
        self._err = b""
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        try:
            for chunk in iter(lambda: self.proc.stderr.read(4096), b""):
                self._err = (self._err + chunk)[-4096:]
        except (OSError, ValueError):
            pass

    def write(self, data: bytes) -> None:
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as e:
            raise ConnectionLost(self.error_text() or "connection to the desktop was closed") from e

    def readline(self) -> bytes:
        try:
            return self.proc.stdout.readline()
        except (OSError, ValueError):  # closed underneath us
            return b""

    def close(self) -> None:
        for f in (self.proc.stdin, self.proc.stdout):
            try:
                f.close()
            except OSError:
                pass
        try:
            self.proc.terminate()
            self.proc.wait(2)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()

    def error_text(self) -> str:
        return self._err.decode("utf-8", "replace").strip()


class SocketTransport(Transport):
    def __init__(self, path: str):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(path)
        except OSError as e:
            raise ConnectionLost(f"cannot connect to the desktop agent at {path}: {e}") from e
        self.file = self.sock.makefile("rb")
        self.wlock = threading.Lock()

    def write(self, data: bytes) -> None:
        with self.wlock:
            try:
                self.sock.sendall(data)
            except OSError as e:
                raise ConnectionLost(str(e)) from e

    def readline(self) -> bytes:
        try:
            return self.file.readline()
        except OSError:
            return b""

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result = None
        self.error: Exception | None = None


class Channel:
    """Thread-safe, multiplexed request/response channel (many calls in flight)."""

    def __init__(self, connect: Callable[[], Transport], label: str = "desktop"):
        self._connect = connect
        self.label = label
        self._t: Transport | None = None
        self._lock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        self._next = 0

    def _reader(self, t: Transport) -> None:
        while True:
            line = t.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self._lock:
                pend = self._pending.pop(msg.get("id"), None)
            if pend is None:
                continue
            if "error" in msg and msg["error"]:
                err = msg["error"]
                pend.error = AgentError(err.get("message", "unknown error"), err.get("code", -32000))
            else:
                pend.result = msg.get("result")
            pend.event.set()
        detail = t.error_text()
        with self._lock:
            if self._t is t:
                self._t = None
            pending, self._pending = self._pending, {}
        t.close()
        for pend in pending.values():
            pend.error = ConnectionLost(detail or f"lost connection to {self.label}")
            pend.event.set()

    def _ensure(self) -> Transport:
        if self._t is None:
            t = self._connect()
            self._t = t
            threading.Thread(target=self._reader, args=(t,), daemon=True).start()
        return self._t

    def call(self, method: str, params: dict | None = None, timeout: float = 120.0):
        pend = _Pending()
        with self._lock:
            t = self._ensure()
            self._next += 1
            rid = self._next
            self._pending[rid] = pend
        data = (
            json.dumps({"id": rid, "method": method, "params": params or {}}, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode()
        try:
            t.write(data)
        except ConnectionLost:
            with self._lock:
                self._pending.pop(rid, None)
                if self._t is t:
                    self._t = None
            t.close()
            raise
        if not pend.event.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise AgentError(f"{method} timed out after {timeout:.0f}s on {self.label}")
        if pend.error is not None:
            raise pend.error
        return pend.result

    def close(self) -> None:
        with self._lock:
            t, self._t = self._t, None
        if t is not None:
            t.close()
