"""Minion in LlamaIndex, through llama-index-tools-mcp (stdio).

    pip install llama-index-tools-mcp llama-index-llms-openai   # verified: llama-index-tools-mcp 0.6.0, llama-index-core 0.14.25
    python examples/frameworks/llamaindex_mcp.py                # connect and list the tools (no API key needed)
    python examples/frameworks/llamaindex_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

McpToolSpec takes any MCP ClientSession: one session keeps one Minion server for the whole run
(BasicMCPClient("uvx", args=[...], timeout=900) also works, but starts a new server for every call).
LlamaIndex hands each result to the model as str(result), so a screenshot would arrive as base64 text:
we leave `screenshot` out and let the agent read the screen with `see`.
MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.tools.mcp import McpToolSpec
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


async def main(task: str | None) -> None:
    server = StdioServerParameters(command=COMMAND, args=ARGS)
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = [t for t in await McpToolSpec(client=session).to_tool_list_async() if t.metadata.name != "screenshot"]
        print("Loaded", len(tools), "tools:", ", ".join(t.metadata.name for t in tools))

        desktop = next(t for t in tools if t.metadata.name == "desktop")
        reply = await desktop.acall(action="profiles")  # needs no desktop
        print("desktop(action='profiles') ->", reply.raw_output.content[0].text.splitlines()[0])

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            from llama_index.llms.openai import OpenAI

            agent = FunctionAgent(
                tools=tools, llm=OpenAI(model="gpt-5"), system_prompt="You operate a Linux desktop with Minion."
            )
            print(await agent.run(task, max_iterations=50))  # the default is 20


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
