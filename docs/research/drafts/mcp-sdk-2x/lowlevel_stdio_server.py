"""Low-level Server over stdio with listChanged advertised to legacy clients."""
import anyio
import mcp.types as types
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler

bus = InMemorySubscriptionBus()

async def list_tools(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name="ping2", input_schema={"type": "object"})])

async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text="pong")])

server = Server("ll-stdio", version="1.0", on_list_tools=list_tools, on_call_tool=call_tool,
                on_subscriptions_listen=ListenHandler(bus))

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options(NotificationOptions(tools_changed=True)))

anyio.run(main)
