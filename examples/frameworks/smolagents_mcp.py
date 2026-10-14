"""Minion in smolagents (Hugging Face), through an MCP tool collection (stdio).

    pip install "smolagents[mcp]" "mcp<2"                       # verified: smolagents 1.26.0 (mcpadapt 0.1.20, mcp 1.30.0)
    python examples/frameworks/smolagents_mcp.py                # connect and list the tools (no API key needed)
    python examples/frameworks/smolagents_mcp.py "Open example.com and tell me the heading"   # needs HF_TOKEN

mcp<2: mcpadapt 0.1.20 fails to import with version 2 of the MCP SDK.
MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import os
import shlex
import sys

from mcp import StdioServerParameters
from smolagents import CodeAgent, InferenceClientModel, ToolCollection

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


def main(task: str | None) -> None:
    server = StdioServerParameters(command=COMMAND, args=ARGS)
    with ToolCollection.from_mcp(server, trust_remote_code=True, structured_output=False) as minion:
        tools = list(minion.tools)
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        desktop = next(t for t in tools if t.name == "desktop")
        print("desktop(action='profiles') ->", desktop(action="profiles").splitlines()[0])  # needs no desktop

        if task:  # a real run: needs a Hugging Face token (and Docker, to create desktops)
            agent = CodeAgent(tools=tools, model=InferenceClientModel())
            print(agent.run(task))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or None)
