"""Minion in Pydantic AI, through MCP (stdio).

    pip install "pydantic-ai-slim[mcp,openai]"                  # verified: pydantic-ai-slim 2.56.0 (fastmcp-slim 4.1.0)
    python examples/frameworks/pydantic_ai_mcp.py               # connect and list the tools (no API key needed)
    python examples/frameworks/pydantic_ai_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


async def main(task: str | None) -> None:
    minion = MCPToolset(
        StdioTransport(command=COMMAND, args=ARGS),
        read_timeout=900,  # the default is 5 min; a hand-off to a human can wait 10 min
        include_instructions=True,  # add Minion's usage notes to the agent's instructions
    )
    async with minion:  # `async with agent:` does the same for every toolset of an agent
        tools = await minion.list_tools()
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        reply = await minion.direct_call_tool("desktop", {"action": "profiles"})  # needs no desktop
        print("desktop(action='profiles') ->", str(reply).splitlines()[0])

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            agent = Agent("openai:gpt-5", toolsets=[minion])
            print((await agent.run(task)).output)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
