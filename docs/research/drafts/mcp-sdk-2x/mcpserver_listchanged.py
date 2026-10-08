"""MCPServer over stdio advertising tools.listChanged=true to legacy clients (workaround)."""
from mcp.server import NotificationOptions, Server
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("mcps-lc")
_ll = mcp._lowlevel_server  # private
_orig = Server.create_initialization_options
_ll.create_initialization_options = lambda notification_options=None, *a, **k: _orig(_ll, notification_options or NotificationOptions(tools_changed=True), *a, **k)
@mcp.tool()
def hi() -> str:
    return "hi"
if __name__ == "__main__":
    mcp.run()
