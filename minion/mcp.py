"""MCP server (stdio, zero dependencies): gives any MCP client desktops to use.

    claude mcp add minion -- uvx minion-desktop mcp            # nine tools
    claude mcp add minion -- uvx minion-desktop mcp --compact  # one `computer` tool (smallest context)

Implements the Model Context Protocol's tools surface (initialize, tools/list, tools/call,
ping, progress notifications) over newline-delimited JSON-RPC. The tools themselves live in
minion/tools.py and are shared with the HTTP API and the Python function-calling toolkit.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback

from . import __version__, profiles
from .tools import INSTRUCTIONS, Toolkit

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]


class Server:
    def __init__(self, preload: str | None = None, idle_freeze: float = 600, compact: bool = False):
        self.out_lock = threading.Lock()
        self.toolkit = Toolkit(in_process_viewer=True)
        self.compact = compact
        self.protocol = PROTOCOL_VERSIONS[0]
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
        self.send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})

    # -- protocol -----------------------------------------------------------
    def handle(self, msg) -> None:
        if not isinstance(msg, dict):
            self.error(None, -32600, "Invalid request: expected a JSON object")
            return
        method = msg.get("method")
        mid = msg.get("id")
        if not isinstance(method, str):
            if mid is not None and "result" not in msg and "error" not in msg:
                self.error(mid, -32600, "Invalid request: missing method")
            return  # responses to requests we never send
        if mid is None:
            return  # notifications: initialized, cancelled, ...
        try:
            if method == "initialize":
                params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                requested = params.get("protocolVersion")
                self.protocol = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "minion", "title": "Minion desktops", "version": __version__},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.toolkit.definitions("mcp", compact=self.compact)}
            elif method == "tools/call":
                params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                threading.Thread(target=self._call_tool, args=(mid, params), daemon=True).start()
                return
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                self.error(mid, -32601, f"Method not found: {method}")
                return
            self.send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as e:
            self.error(mid, -32603, str(e))

    def _call_tool(self, mid, params: dict) -> None:
        name = params.get("name")
        args = params.get("arguments") or {}
        token = (params.get("_meta") or {}).get("progressToken") if isinstance(params.get("_meta"), dict) else None
        state = {"n": 0, "done": False}

        def progress(text: str) -> None:
            self.log(text)
            if token is None or state["done"]:  # never report progress for a finished request
                return
            state["n"] += 1
            self.send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/progress",
                    "params": {"progressToken": token, "progress": state["n"], "message": str(text)[-200:]},
                }
            )

        try:
            result = self.toolkit.call(name, args, progress=progress).to_mcp()
        except Exception as e:  # pragma: no cover - Toolkit.call already reports errors
            self.log(traceback.format_exc())
            result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        state["done"] = True
        self.send({"jsonrpc": "2.0", "id": mid, "result": result})


def main(preload: str | None = None, idle_freeze: float = 600, compact: bool = False) -> None:
    server = Server(preload=preload, idle_freeze=idle_freeze, compact=compact)
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
