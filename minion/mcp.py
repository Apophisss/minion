"""MCP server (zero dependencies): gives any MCP client desktops to use.

    claude mcp add minion -- uvx minion-desktop mcp            # nine tools
    claude mcp add minion -- uvx minion-desktop mcp --compact  # one `computer` tool (smallest context)
    uvx minion-desktop mcp --no-images                          # text only, for clients that can't show images

Implements the Model Context Protocol's tools surface (initialize, tools/list, tools/call,
ping, progress notifications, cancellation). `Session` is the JSON-RPC handling; two transports
share it: stdio below (newline-delimited JSON-RPC) and Streamable HTTP at `/mcp` in `minion serve`
and `minion share` (minion/server.py). The tools themselves live in minion/tools.py and are shared
with the HTTP API and the Python function-calling toolkit.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from collections import OrderedDict

from . import __version__, profiles
from .tools import Toolkit, instructions

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]


def rpc_error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def is_tool_call(msg) -> bool:
    """A tools/call request. Transports run these off their reading thread, so pings and
    cancellations still get through while a tool works."""
    return isinstance(msg, dict) and msg.get("method") == "tools/call" and msg.get("id") is not None


def _key(mid):
    """A request id usable as a set member (JSON-RPC ids are strings or numbers)."""
    return mid if isinstance(mid, (str, int, float)) and not isinstance(mid, bool) else None


class Session:
    """One MCP conversation, independent of the transport: protocol state and the answer to each
    JSON-RPC message. Over stdio there is one per process; over HTTP, one per Mcp-Session-Id, each
    with its own toolkit (and so its own "current desktop")."""

    def __init__(self, toolkit, *, compact: bool = False, log=None):
        self.toolkit = toolkit
        self.compact = compact
        self.protocol = PROTOCOL_VERSIONS[0]
        self.log = log or (lambda text: None)
        self._cancelled: OrderedDict = OrderedDict()  # ids the client gave up on: no result is sent
        self._lock = threading.Lock()

    def handle(self, msg, notify=None) -> dict | None:
        """The reply to one JSON-RPC message, or None when none is due (notifications, responses,
        cancelled calls). tools/call blocks while the tool runs and passes its progress
        notifications to `notify(message)`."""
        if not isinstance(msg, dict):
            return rpc_error(None, -32600, "Invalid request: expected a JSON object")
        method = msg.get("method")
        mid = msg.get("id")
        if not isinstance(method, str):
            if mid is not None and "result" not in msg and "error" not in msg:
                return rpc_error(mid, -32600, "Invalid request: missing method")
            return None  # responses to requests we never send
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if mid is None:  # notifications: initialized, cancelled, ...
            if method == "notifications/cancelled":
                self.cancel(params.get("requestId"))
            return None
        try:
            if method == "tools/call":
                return self._call_tool(mid, params, notify)
            if method == "initialize":
                requested = params.get("protocolVersion")
                self.protocol = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "minion", "title": "Minion desktops", "version": __version__},
                    # usage notes for exactly the tools listed (compact: `computer`; text-only: no screenshot)
                    "instructions": instructions(compact=self.compact, images=self.toolkit.images),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                return rpc_error(mid, -32601, f"Method not found: {method}")
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except Exception as e:
            return rpc_error(mid, -32603, str(e))

    def tools(self) -> list[dict]:
        """The tools this session lists: one `computer` tool in compact mode, else the nine (eight
        without screenshot for text-only clients)."""
        return self.toolkit.definitions("mcp", compact=self.compact)

    def cancel(self, request_id) -> None:
        """notifications/cancelled: the call may finish, but its result is not sent (MCP spec)."""
        key = _key(request_id)
        if key is None:
            return
        with self._lock:
            self._cancelled[key] = True
            while len(self._cancelled) > 1000:  # cancellations of calls that already finished
                self._cancelled.popitem(last=False)

    def _call_tool(self, mid, params: dict, notify) -> dict | None:
        name = params.get("name")
        if name not in self.toolkit.names:  # a protocol error, not a tool result (MCP spec)
            listed = ", ".join(t["name"] for t in self.tools())  # the hidden ones still work, but aren't offered
            return rpc_error(mid, -32602, f"Unknown tool: {name}; tools: {listed}")
        args = params.get("arguments") or {}
        token = (params.get("_meta") or {}).get("progressToken") if isinstance(params.get("_meta"), dict) else None
        state = {"n": 0, "done": False}

        def progress(text: str) -> None:
            self.log(text)
            if token is None or notify is None or state["done"]:  # never report progress for a finished request
                return
            state["n"] += 1
            try:
                notify(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"progressToken": token, "progress": state["n"], "message": str(text)[-200:]},
                    }
                )
            except Exception:  # the client went away: the tool keeps going
                pass

        try:
            result = self.toolkit.call(name, args, progress=progress).to_mcp()
        except Exception as e:  # pragma: no cover - Toolkit.call already reports errors
            self.log(traceback.format_exc())
            result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        state["done"] = True
        key = _key(mid)
        with self._lock:
            if key is not None and self._cancelled.pop(key, None):  # the client cancelled it: no response
                return None
        return {"jsonrpc": "2.0", "id": mid, "result": result}


class Server:
    """The stdio transport: newline-delimited JSON-RPC on stdin and stdout, one Session per process."""

    def __init__(
        self, preload: str | None = None, idle_freeze: float = 600, compact: bool = False, images: bool = True
    ):
        self.out_lock = threading.Lock()
        self.toolkit = Toolkit(in_process_viewer=True, images=images)
        self.session = Session(self.toolkit, compact=compact, log=self.log)
        if preload:
            threading.Thread(target=self._preload, args=(preload,), daemon=True).start()
        if idle_freeze and idle_freeze > 0:
            from .reaper import start_reaper

            start_reaper(self.toolkit.backend, idle_freeze)

    # -- io -----------------------------------------------------------------
    def send(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        with self.out_lock:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()

    def log(self, text: str) -> None:
        sys.stderr.write(f"[minion] {text}\n")
        sys.stderr.flush()

    def _preload(self, names: str) -> None:
        for n in [x.strip() for x in names.split(",") if x.strip()]:
            try:
                self.toolkit.backend.prepare(profiles.get(n), progress=None)
                self.log(f"profile {n} ready")
            except Exception as e:
                self.log(f"preload {n} failed: {e}")

    def error(self, mid, code: int, message: str) -> None:
        self.send(rpc_error(mid, code, message))

    # -- protocol -----------------------------------------------------------
    def handle(self, msg) -> None:
        if is_tool_call(msg):  # in a thread, so the server keeps reading (pings, cancellations)
            threading.Thread(target=self._answer, args=(msg,), daemon=True).start()
        else:
            self._answer(msg)

    def _answer(self, msg) -> None:
        reply = self.session.handle(msg, notify=self.send)
        if reply is not None:
            self.send(reply)


def main(preload: str | None = None, idle_freeze: float = 600, compact: bool = False, images: bool = True) -> None:
    # MCP messages are UTF-8 JSON lines. Windows pipes default to the ANSI code page (and CRLF), which would
    # garble or crash on non-Latin text, so set the encoding explicitly.
    for stream, kw in ((sys.stdin, {"errors": "replace"}), (sys.stdout, {"newline": "\n"})):
        try:
            stream.reconfigure(encoding="utf-8", **kw)
        except (AttributeError, ValueError):  # not a TextIOWrapper (e.g. replaced in tests)
            pass
    server = Server(preload=preload, idle_freeze=idle_freeze, compact=compact, images=images)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            server.error(None, -32700, "Parse error")
            continue
        if isinstance(msg, list):  # JSON-RPC batch (2025-03-26)
            for m in msg:
                server.handle(m)
        else:
            server.handle(msg)


if __name__ == "__main__":
    main()
