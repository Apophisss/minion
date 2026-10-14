"""Minion in Microsoft AutoGen (AgentChat), through autogen-ext's McpWorkbench (stdio).

    pip install autogen-agentchat "autogen-ext[mcp,openai]" "mcp<2"   # verified: autogen-agentchat / autogen-ext 0.7.5 (mcp 1.30.0)
    python examples/frameworks/autogen_mcp.py                   # connect and list the tools (no API key needed)
    python examples/frameworks/autogen_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

mcp<2: autogen-ext 0.7.5 fails to import with version 2 of the MCP SDK.
MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


async def main(task: str | None) -> None:
    params = StdioServerParams(command=COMMAND, args=ARGS, read_timeout_seconds=900)  # the default is 5 s
    async with McpWorkbench(params) as minion:
        tools = await minion.list_tools()
        print("Loaded", len(tools), "tools:", ", ".join(t["name"] for t in tools))

        result = await minion.call_tool("desktop", {"action": "profiles"})  # needs no desktop
        print("desktop(action='profiles') ->", result.to_text().splitlines()[0])

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            from autogen_ext.models.openai import OpenAIChatCompletionClient

            agent = AssistantAgent(
                "desktop_agent",
                model_client=OpenAIChatCompletionClient(model="gpt-5"),
                workbench=minion,
                # AssistantAgent passes tool results as text (a screenshot becomes base64), so read with see()
                system_message="You operate a Linux desktop with Minion's tools. Read the screen with see(), not screenshot.",
                max_tool_iterations=50,  # the default is 1
            )
            await Console(agent.run_stream(task=task))


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
