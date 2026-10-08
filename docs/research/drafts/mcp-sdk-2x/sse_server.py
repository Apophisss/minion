"""Legacy HTTP+SSE server (superseded transport) - for testing sse_client."""
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("sse-demo")

@mcp.tool()
def mul(a: int, b: int) -> int:
    return a * b

app = mcp.sse_app()  # routes: GET /sse (event stream), POST /messages/?session_id=...
