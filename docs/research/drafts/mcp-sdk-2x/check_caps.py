import sys, anyio
from mcp import Client, StdioServerParameters
async def main():
    for script in ("lowlevel_stdio_server.py", "mcpserver_listchanged.py"):
        for mode in ("legacy", "auto"):
            async with Client(StdioServerParameters(command=sys.executable, args=[script]), mode=mode) as c:
                r = await c.call_tool((await c.list_tools()).tools[0].name, {})
                print(script, mode, c.protocol_version, c.server_capabilities.tools, r.content[0].text)
anyio.run(main)
