"""A user-written tool server (MCPServer, the 2.x name for FastMCP), run as a stdio subprocess.

Run directly:  python stdio_tool_server.py      (speaks MCP on stdin/stdout)
"""
import os
import sys

from pydantic import BaseModel

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("user-tools", version="0.1.0", instructions="Example user tool server")


class Weather(BaseModel):
    city: str
    temp_c: float


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool()
def weather(city: str) -> Weather:
    """Structured output via a pydantic return type."""
    return Weather(city=city, temp_c=21.5)


@mcp.tool()
def fail(msg: str) -> str:
    """Always fails -> CallToolResult(is_error=True)."""
    raise ToolError(f"boom: {msg}")


@mcp.tool()
def show_env(name: str) -> str:
    """Return an env var (to prove StdioServerParameters.env works)."""
    return os.environ.get(name, "<unset>")


@mcp.tool()
async def slow(seconds: float) -> str:
    """Sleep (to test client timeouts)."""
    import anyio

    await anyio.sleep(seconds)
    return "done"


def _late_tool(x: int) -> int:
    """A tool added at runtime."""
    return x * 10


@mcp.tool()
async def enable_late_tool(ctx: Context) -> str:
    """Adds a tool at runtime and notifies BOTH protocol eras."""
    mcp.add_tool(_late_tool, name="late_tool")
    await ctx.notify_tools_changed()              # 2026-07-28 clients (subscriptions/listen)
    await ctx.session.send_tool_list_changed()    # 2025-xx legacy clients (standalone channel)
    return "late_tool enabled"


@mcp.resource("config://app")
def app_config() -> str:
    """Static resource."""
    return '{"debug": true}'


@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """Templated resource."""
    return f"Hello, {name}!"


@mcp.prompt()
def review_code(code: str) -> str:
    """A prompt."""
    return f"Please review this code:\n\n{code}"


if __name__ == "__main__":
    print("stdio server starting", file=sys.stderr)  # stderr only! stdout is the protocol channel
    mcp.run()  # default transport="stdio"
