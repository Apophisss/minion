"""Start an MCP server over stdio, the way an agent app does, and check that it answers.

    python scripts/check_mcp.py minion mcp
    python scripts/check_mcp.py uvx minion-desktop mcp
    python scripts/check_mcp.py npx -y minion-desktop mcp
    python scripts/check_mcp.py uv run --directory EXTENSION server/main.py mcp    # an unpacked minion.mcpb

It sends initialize, notifications/initialized, tools/list and desktop(action="list"), prints what came back, and
fails unless the server is Minion with its 9 tools and stdout carried nothing but JSON-RPC. The desktop call needs
no Docker to answer: without it, the reply is an error that says what to install. Standard library only.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time

TOOLS = {"desktop", "see", "screenshot", "act", "open", "run", "script", "files", "view"}
TIMEOUT = 600  # a first start may download Python and the package


def main(command: list[str]) -> int:
    exe = shutil.which(command[0])  # npx is npx.cmd on Windows
    if not exe:
        print(f"check_mcp: {command[0]} not found")
        return 1
    started = time.monotonic()
    proc = subprocess.Popen([exe, *command[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8")
    lines: queue.Queue = queue.Queue()

    def pump() -> None:
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)  # the server exited

    threading.Thread(target=pump, daemon=True).start()

    def send(message: dict) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def reply(want: int) -> dict:
        deadline = started + TIMEOUT
        while True:
            line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
            if line is None:
                raise SystemExit(f"check_mcp: the server exited ({proc.wait()}) before answering request {want}")
            message = json.loads(line)  # anything else on stdout breaks MCP clients
            if message.get("id") == want:
                return message

    try:
        hello = {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "check_mcp", "version": "1"},
        }
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": hello})
        info = reply(1)["result"]["serverInfo"]
        print(f"initialize: {info['name']} {info['version']} ({time.monotonic() - started:.1f} s)")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in reply(2)["result"]["tools"]}
        print(f"tools/list: {len(names)} tools: {', '.join(sorted(names))}")
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "desktop", "arguments": {"action": "list"}},
            }
        )
        result = reply(3)["result"]
        print(f"desktop list: {'error: ' if result.get('isError') else ''}{result['content'][0]['text'][:300]}")
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    if info["name"] != "minion" or names != TOOLS:
        print(f"check_mcp: expected Minion's tools {sorted(TOOLS)}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(errors="replace")  # a Windows console may not have every character
    sys.exit(main(sys.argv[1:]))
