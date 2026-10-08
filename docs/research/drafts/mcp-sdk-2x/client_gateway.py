"""Client for gateway.py over Streamable HTTP with a bearer token.

Lists tools, adds a tool at runtime (via the gateway's admin REST API), waits for the
tools/list_changed notification, re-lists, and calls the new tool. Runs once as a
2026-07-28 client (mode="auto") and once as a 2025-11-25 client (mode="legacy").
"""
import sys

import anyio
import httpx2

from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.client.subscriptions import ToolsListChanged

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
TOKEN = "secret"
HDRS = {"Authorization": f"Bearer {TOKEN}"}


async def admin(method: str, path: str, json=None) -> dict:
    async with httpx2.AsyncClient() as h:
        r = await h.request(method, BASE + path, json=json, headers=HDRS)
        r.raise_for_status()
        return r.json()


async def run(mode: str, tool_name: str) -> None:
    print(f"\n===== mode={mode!r} =====")
    got_legacy_notification = anyio.Event()

    async def message_handler(msg) -> None:
        if isinstance(msg, Exception):
            print("  transport exception:", repr(msg))
        elif msg.method == "notifications/tools/list_changed":
            print("  [message_handler] notifications/tools/list_changed")
            got_legacy_notification.set()

    async with httpx2.AsyncClient(headers=HDRS, timeout=httpx2.Timeout(30.0, read=300.0)) as http:
        transport = streamable_http_client(f"{BASE}/mcp", http_client=http)
        async with Client(transport, mode=mode, message_handler=message_handler, read_timeout_seconds=30) as client:
            print("protocol_version:", client.protocol_version)
            print("server_info:", client.server_info.name if client.server_info else None)
            print("capabilities.tools:", client.server_capabilities.tools)
            print("tools before:", [t.name for t in (await client.list_tools()).tools])
            print("echo ->", (await client.call_tool("echo", {"text": "hi"})).content[0].text)

            spec = {
                "name": tool_name,
                "description": "Greets",
                "input_schema": {"type": "object", "properties": {"who": {"type": "string"}}, "required": ["who"]},
                "template": "Hello {who}!",
            }
            if client.protocol_version == "2026-07-28":
                async with client.listen(tools_list_changed=True) as sub:
                    print("admin add ->", await admin("POST", "/admin/tools", spec))
                    with anyio.fail_after(5):
                        async for ev in sub:
                            print("  [listen] event:", ev)
                            assert isinstance(ev, ToolsListChanged)
                            break
            else:
                print("admin add ->", await admin("POST", "/admin/tools", spec))
                with anyio.fail_after(5):
                    await got_legacy_notification.wait()

            # cache_mode="refresh" bypasses the client's response cache (it is evicted on the notification anyway)
            print("tools after:", [t.name for t in (await client.list_tools(cache_mode="refresh")).tools])
            r = await client.call_tool(tool_name, {"who": "Minion"})
            print(f"{tool_name} -> text={r.content[0].text!r} structured={r.structured_content} is_error={r.is_error}")
            r = await client.call_tool("does_not_exist", {})
            print("unknown tool -> is_error:", r.is_error, r.content[0].text)
            print("admin remove ->", await admin("DELETE", f"/admin/tools/{tool_name}"))
            await anyio.sleep(0.3)


async def unauthorized() -> None:
    print("\n===== no token =====")
    try:
        async with Client(f"{BASE}/mcp", mode="legacy") as client:
            await client.list_tools()
    except Exception as e:  # noqa: BLE001
        print("rejected:", type(e).__name__, str(e)[:120])
    async with httpx2.AsyncClient() as h:
        r = await h.post(f"{BASE}/mcp", json={})
        print("raw POST status:", r.status_code, r.text)


async def main() -> None:
    await run("auto", "greet_modern")
    await run("legacy", "greet_legacy")
    await unauthorized()
    async with httpx2.AsyncClient() as h:
        print("\n/health ->", (await h.get(f"{BASE}/health")).json())


anyio.run(main)
