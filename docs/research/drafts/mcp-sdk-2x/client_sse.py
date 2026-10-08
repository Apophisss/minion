import anyio
from mcp import Client
from mcp.client.sse import sse_client

async def main():
    for mode in ("auto", "legacy"):
        transport = sse_client("http://127.0.0.1:8766/sse", headers={"Authorization": "Bearer x"}, timeout=5, sse_read_timeout=300)
        async with Client(transport, mode=mode) as c:
            r = await c.call_tool("mul", {"a": 6, "b": 7})
            print(mode, c.protocol_version, [t.name for t in (await c.list_tools()).tools], r.structured_content)
anyio.run(main)
