"""mcp 1.30.0 FastMCP server (a typical third-party server) - run under venv1."""
import sys
from mcp.server.fastmcp import FastMCP, Context
mcp = FastMCP("v1-server", port=8767)

@mcp.tool()
def sub(a: int, b: int) -> int:
    return a - b

def extra(x: int) -> int:
    return x + 1000

@mcp.tool()
async def grow(ctx: Context) -> str:
    mcp.add_tool(extra)
    await ctx.session.send_tool_list_changed()
    return "grown"

if __name__ == "__main__":
    mcp.run(transport=sys.argv[1] if len(sys.argv) > 1 else "stdio")
