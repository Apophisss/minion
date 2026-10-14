"""Minion in the OpenAI Agents SDK, through MCP (stdio).

    pip install openai-agents                                   # verified: openai-agents 0.23.1
    python examples/frameworks/openai_agents_mcp.py             # connect and list the tools (no API key needed)
    python examples/frameworks/openai_agents_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from agents.run_context import RunContextWrapper

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


async def main(task: str | None) -> None:
    async with MCPServerStdio(
        name="minion",
        params={"command": COMMAND, "args": ARGS},
        client_session_timeout_seconds=900,  # the default is 5 s; desktop calls can take minutes
        cache_tools_list=True,
    ) as minion:
        agent = Agent(
            name="Desktop agent",
            instructions="You operate a Linux desktop with Minion's tools. Prefer see() over screenshots.",
            model="gpt-5",
            mcp_servers=[minion],
        )
        tools = await agent.get_mcp_tools(RunContextWrapper(context=None))  # what the model will be given
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        result = await minion.call_tool("desktop", {"action": "profiles"})  # needs no desktop
        print("desktop(action='profiles') ->", result.content[0].text.splitlines()[0])

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            print((await Runner.run(agent, task, max_turns=50)).final_output)  # the default is 10 turns


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
