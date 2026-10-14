"""Minion in CrewAI, through crewai-tools' MCPServerAdapter (stdio).

    pip install crewai "crewai-tools[mcp]"                      # verified: crewai 1.15.28, crewai-tools 1.15.28 (mcp 1.28.1)
    python examples/frameworks/crewai_mcp.py                    # connect and list the tools (no API key needed)
    python examples/frameworks/crewai_mcp.py "Open example.com and tell me the heading"   # needs OPENAI_API_KEY

MCPServerAdapter keeps one Minion server for the whole crew and sets no per-call timeout. (Agent(mcps=[...])
also loads the tools, but starts a new server for every call and gives up after 30 s.)
MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import os
import shlex
import sys

from crewai import Agent, Crew, Task
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))


def main(task: str | None) -> None:
    server = StdioServerParameters(command=COMMAND, args=ARGS)
    with MCPServerAdapter(server, connect_timeout=60) as tools:
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        desktop = next(t for t in tools if t.name == "desktop")
        print("desktop(action='profiles') ->", desktop.run(action="profiles").splitlines()[0])  # needs no desktop

        if task:  # a real run: needs OPENAI_API_KEY (and Docker, to create desktops)
            agent = Agent(
                role="Desktop operator",
                goal="Get things done on a Linux desktop",
                backstory="You drive Minion desktops: see() to read the screen, act() to click and type.",
                tools=tools,
                llm="gpt-5",
            )
            job = Task(description=task, expected_output="A short report of the result.", agent=agent)
            print(Crew(agents=[agent], tasks=[job]).kickoff())


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or None)
