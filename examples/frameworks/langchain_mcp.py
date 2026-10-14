"""Minion in LangChain / LangGraph, through langchain-mcp-adapters (stdio).

    pip install langchain-mcp-adapters "langchain[openai]"     # verified: langchain-mcp-adapters 0.3.2, langchain 1.4.5
    python examples/frameworks/langchain_mcp.py                 # connect and list the tools (no API key needed)
    python examples/frameworks/langchain_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

One session for the whole run: client.get_tools() would start a new Minion server for every tool call.
MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


async def main(task: str | None) -> None:
    client = MultiServerMCPClient({"minion": {"transport": "stdio", "command": COMMAND, "args": ARGS}})
    async with client.session("minion") as session:
        tools = await load_mcp_tools(session)
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        desktop = next(t for t in tools if t.name == "desktop")
        reply = await desktop.ainvoke({"action": "profiles"})  # needs no desktop; a list of content blocks
        print("desktop(action='profiles') ->", reply[0]["text"].splitlines()[0])

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            agent = create_agent("openai:gpt-5", tools, system_prompt="You operate a Linux desktop with Minion.")
            result = await agent.ainvoke({"messages": [{"role": "user", "content": task}]})
            print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
