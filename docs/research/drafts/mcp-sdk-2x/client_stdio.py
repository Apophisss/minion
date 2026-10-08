"""Client side against a stdio server: Client (high level) and ClientSession (low level)."""
import sys
from pathlib import Path

import anyio

import mcp.types as types
from mcp import Client, ClientSession, MCPError, StdioServerParameters, stdio_client
from mcp.client.subscriptions import ToolsListChanged

HERE = Path(__file__).parent
PARAMS = StdioServerParameters(
    command=sys.executable,
    args=[str(HERE / "stdio_tool_server.py")],
    env={"MY_SECRET": "s3cr3t"},  # merged over a minimal allow-list (HOME, PATH, ...); parent env NOT inherited
    cwd=str(HERE),
)


async def high_level(mode: str) -> None:
    print(f"\n===== Client(StdioServerParameters, mode={mode!r}) =====")
    received: list[str] = []

    async def message_handler(msg) -> None:  # legacy-era notifications arrive here
        if isinstance(msg, Exception):
            print("  transport exception:", msg)
            return
        received.append(msg.method)

    async with Client(PARAMS, mode=mode, read_timeout_seconds=30, message_handler=message_handler) as client:
        print("protocol_version:", client.protocol_version)
        print("server_info:", client.server_info)
        print("capabilities.tools:", client.server_capabilities.tools)
        print("instructions:", client.instructions)

        # list_tools with pagination loop
        tools: list[types.Tool] = []
        cursor = None
        while True:
            page = await client.list_tools(cursor=cursor)
            tools.extend(page.tools)
            cursor = page.next_cursor
            if cursor is None:
                break
        print("tools:", [t.name for t in tools])
        print("add.input_schema:", tools[0].input_schema)
        w = next(t for t in tools if t.name == "weather")
        print("weather.output_schema:", w.output_schema)

        r = await client.call_tool("add", {"a": 2, "b": 3})
        print("add ->", "content:", r.content, "| structured:", r.structured_content, "| is_error:", r.is_error)
        r = await client.call_tool("weather", {"city": "TLV"})
        print("weather -> structured:", r.structured_content)
        r = await client.call_tool("fail", {"msg": "x"})
        print("fail -> is_error:", r.is_error, "| text:", r.content[0].text)
        r = await client.call_tool("add", {"a": "not-int", "b": 1})
        print("bad args -> is_error:", r.is_error, "| text:", r.content[0].text[:90])
        r = await client.call_tool("show_env", {"name": "MY_SECRET"})
        print("env MY_SECRET ->", r.content[0].text)
        try:
            await client.call_tool("nope", {})
        except MCPError as e:
            print("unknown tool -> MCPError code", e.code, e.message)
        r = await client.call_tool("nope2", {}) if False else None

        # per-call timeout
        try:
            await client.call_tool("slow", {"seconds": 5}, read_timeout_seconds=0.5)
        except MCPError as e:
            print("timeout -> MCPError code", e.code, "|", e.message)

        res = await client.list_resources()
        print("resources:", [(x.uri, x.name) for x in res.resources])
        tmpl = await client.list_resource_templates()
        print("resource templates:", [x.uri_template for x in tmpl.resource_templates])
        rr = await client.read_resource("greeting://Ofir")
        print("read greeting ->", rr.contents[0].text)
        pr = await client.list_prompts()
        print("prompts:", [(p.name, [a.name for a in (p.arguments or [])]) for p in pr.prompts])
        gp = await client.get_prompt("review_code", {"code": "print(1)"})
        print("get_prompt ->", gp.messages[0].content.text[:40])

        # runtime tool add + list_changed notification
        if client.protocol_version == "2026-07-28":
            async with client.listen(tools_list_changed=True) as sub:
                print("listen honored:", sub.honored)
                await client.call_tool("enable_late_tool", {})
                with anyio.fail_after(5):
                    async for event in sub:
                        print("subscription event:", event)
                        assert isinstance(event, ToolsListChanged)
                        break
        else:
            await client.call_tool("enable_late_tool", {})
            with anyio.fail_after(5):
                while "notifications/tools/list_changed" not in received:
                    await anyio.sleep(0.05)
            print("message_handler got:", received)
        tl = await client.list_tools(cache_mode="refresh")
        print("tools after change:", [t.name for t in tl.tools])
        print("late_tool ->", (await client.call_tool("late_tool", {"x": 4})).structured_content)


async def low_level() -> None:
    print("\n===== raw stdio_client + ClientSession (legacy initialize handshake) =====")

    async def on_msg(msg) -> None:
        if not isinstance(msg, Exception):
            print("  [notification]", msg.method)

    async with stdio_client(PARAMS) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=30, message_handler=on_msg) as session:
            init = await session.initialize()
            print("initialize ->", init.protocol_version, init.server_info.name, init.capabilities.tools)
            tl = await session.list_tools()  # NOTE: 2.x ClientSession.list_tools has no cursor= kw; use params=
            print("tools:", [t.name for t in tl.tools], "next_cursor:", tl.next_cursor)
            tl2 = await session.list_tools(params=types.PaginatedRequestParams(cursor=None))
            print("tools via params:", len(tl2.tools))
            r = await session.call_tool("add", {"a": 40, "b": 2})
            print("add ->", r.structured_content)
            await session.call_tool("enable_late_tool", {})
            await anyio.sleep(0.3)


async def main() -> None:
    await high_level("auto")
    await high_level("legacy")
    await low_level()


anyio.run(main)
