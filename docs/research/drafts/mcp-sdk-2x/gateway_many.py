
import gateway, mcp.types as types
from gateway import *  # noqa
for i in range(120):
    gateway.registry._tools[f"t{i:03d}"] = gateway.ToolEntry(types.Tool(name=f"t{i:03d}", input_schema={"type":"object"}), gateway._echo)
app = gateway.app
