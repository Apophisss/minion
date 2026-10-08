import anyio, httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
H = {"Authorization": "Bearer secret"}
async def main():
    for mode in ("auto", "legacy"):
        got = []
        async def mh(m):
            if not isinstance(m, Exception): got.append(m.method)
        async with httpx2.AsyncClient(headers=H, timeout=httpx2.Timeout(30, read=300)) as http:
            async with Client(streamable_http_client("http://127.0.0.1:8768/mcp", http_client=http), mode=mode, message_handler=mh) as c:
                tools = (await c.list_tools()).tools
                print(mode, c.protocol_version, "tools:", len(tools), "first page next_cursor:", (await c.list_tools()).next_cursor)
                allt, cur = [], None
                while True:
                    pg = await c.list_tools(cursor=cur); allt += pg.tools; cur = pg.next_cursor
                    if cur is None: break
                print("  paginated total:", len(allt))
                print("  echo:", (await c.call_tool("echo", {"text": "x"})).content[0].text)
                if c.protocol_version == "2026-07-28":
                    async with c.listen(tools_list_changed=True) as sub:
                        await http.post("http://127.0.0.1:8768/admin/tools", json={"name": "zz_"+mode}, headers=H)
                        with anyio.move_on_after(2) as sc:
                            async for ev in sub: print("  listen event:", ev); break
                        if sc.cancelled_caught: print("  listen: no event")
                else:
                    await http.post("http://127.0.0.1:8768/admin/tools", json={"name": "zz_"+mode}, headers=H)
                    await anyio.sleep(1.5); print("  legacy notifications:", got)
anyio.run(main)
