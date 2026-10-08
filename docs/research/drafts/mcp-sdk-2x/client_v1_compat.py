"""mcp 1.30.0 (v1 API) client against the 2.3.0 gateway - simulates a Hermes-style Python 1.x client."""
import anyio, httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import mcp.types as t

HDRS = {"Authorization": "Bearer secret"}
async def main():
    got = anyio.Event()
    async def handler(msg):
        if isinstance(msg, t.ServerNotification) and isinstance(msg.root, t.ToolListChangedNotification):
            print("  [v1 message_handler] tools/list_changed"); got.set()
    async with streamablehttp_client("http://127.0.0.1:8765/mcp", headers=HDRS) as (r, w, get_sid):
        async with ClientSession(r, w, message_handler=handler) as s:
            init = await s.initialize()
            print("v1 init:", init.protocolVersion, init.serverInfo.name, init.capabilities.tools)
            print("v1 tools:", [x.name for x in (await s.list_tools()).tools], "session:", get_sid())
            async with httpx.AsyncClient() as h:
                await h.post("http://127.0.0.1:8765/admin/tools", headers=HDRS, json={"name": "v1tool", "template": "v1 says {x}", "input_schema": {"type":"object","properties":{"x":{"type":"string"}}}})
            with anyio.fail_after(5): await got.wait()
            print("v1 tools after:", [x.name for x in (await s.list_tools()).tools])
            res = await s.call_tool("v1tool", {"x": "yo"})
            print("v1 call:", res.content[0].text, res.structuredContent, res.isError)
anyio.run(main)
