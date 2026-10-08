import sys, anyio
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
PY1 = sys.argv[1]
async def main():
    targets = {
        "stdio": StdioServerParameters(command=PY1, args=["v1_server.py", "stdio"]),
        "streamable-http": "http://127.0.0.1:8767/mcp",
    }
    for label, target in targets.items():
        got = anyio.Event()
        async def mh(m):
            if not isinstance(m, Exception) and m.method == "notifications/tools/list_changed": got.set()
        async with Client(target, message_handler=mh) as c:   # mode="auto"
            print(label, "negotiated:", c.protocol_version, "server:", c.server_info.name, c.server_info.version)
            print("  sub ->", (await c.call_tool("sub", {"a": 5, "b": 3})).structured_content)
            await c.call_tool("grow", {})
            with anyio.fail_after(5): await got.wait()
            print("  tools after list_changed:", [t.name for t in (await c.list_tools(cache_mode="refresh")).tools])
anyio.run(main)
