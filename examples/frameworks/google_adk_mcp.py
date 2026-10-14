"""Minion in Google ADK, through McpToolset (stdio).

    pip install "google-adk[mcp]"                               # verified: google-adk 2.12.0 (mcp 2.3.0)
    python examples/frameworks/google_adk_mcp.py                # connect and list the tools (no API key needed)
    python examples/frameworks/google_adk_mcp.py "Open example.com and tell me the heading"   # needs GOOGLE_API_KEY

MINION_MCP overrides the server command (default: "uvx minion-desktop mcp"), e.g. MINION_MCP="minion mcp".
"""

import asyncio
import os
import shlex
import sys

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

COMMAND, *ARGS = shlex.split(os.environ.get("MINION_MCP", "uvx minion-desktop mcp"))

minion = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command=COMMAND, args=ARGS),
        timeout=900,  # also the per-call read timeout: the default 5 s is too short for desktop work
    ),
    # ADK sends tool results to Gemini as JSON, so a screenshot would travel as base64 text: use see() instead
    tool_filter=lambda tool, ctx=None: tool.name != "screenshot",
)
root_agent = LlmAgent(
    model="gemini-3.5-flash",
    name="desktop_agent",
    instruction="You operate a Linux desktop with Minion's tools. Prefer see() over screenshots.",
    tools=[minion],
)


async def main(task: str | None) -> None:
    try:
        tools = await minion.get_tools()
        print("Loaded", len(tools), "tools:", ", ".join(t.name for t in tools))

        if task:  # a real run: needs GOOGLE_API_KEY (and Docker, to create desktops)
            runner = InMemoryRunner(agent=root_agent)
            session = await runner.session_service.create_session(app_name=runner.app_name, user_id="me")
            message = types.Content(role="user", parts=[types.Part(text=task)])
            async for event in runner.run_async(user_id="me", session_id=session.id, new_message=message):
                if event.is_final_response() and event.content and event.content.parts:
                    print(event.content.parts[0].text)
    finally:
        await minion.close()


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or None))
