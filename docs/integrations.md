# Integrations

Minion works with any agent stack. Agent frameworks and MCP clients use its **MCP server**, agents with a shell
use the **`minion` CLI**, and anything that can call functions uses the **toolkit** (Python or HTTP).

## Integration paths

| Path | For | Start with |
|---|---|---|
| **MCP** (stdio) | Claude Code/Desktop, Cursor, VS Code, Codex, Gemini CLI ([agents.md](agents.md)) and the [frameworks below](#agent-frameworks-mcp) | `uvx minion-desktop mcp` |
| **CLI** | Agents with a shell: Claude Code, Codex CLI, Aider, Open Interpreter, Goose | `minion up office` · `minion see` · `minion click @12` ([cli.md](cli.md)) |
| **Python SDK** | Your own code and agent loops | `from minion import Desktop` ([python.md](python.md)) |
| **Function-calling toolkit** | Any LLM API with tool calling, local models included | `Toolkit().definitions("openai")`, then `messages += tk.run_calls(msg.tool_calls)` ([below](#any-llm-with-function-calling)) |
| **HTTP / OpenAPI** | Other languages, remote agents, no-code tools | `minion serve`, then `/api/tools` and `/openapi.json` ([http-api.md](http-api.md)) |
| **TypeScript** | Node.js agents, the Vercel AI SDK | [`clients/typescript`](../clients/typescript): `new Minion()`, `toVercelAiTools()` |
| **Agent Skill** | Agents that load `SKILL.md` skills (Claude Code, Codex CLI, Cursor, …) | `minion skill --install [DIR]`, or the Claude Code plugin ([agents.md](agents.md#shell-agents-and-agent-skills)) |
| **Claude computer use** | Claude's computer-use toolset | `MinionComputer(desk)` ([computer-use.md](computer-use.md)) |
| **OpenAI / Gemini computer use** | Models with their own computer-use tool | `minion.integrations.openai` / `minion.integrations.gemini`: `cu.run(response.output)` ([computer-use-openai-gemini.md](computer-use-openai-gemini.md)) |

## Agent frameworks (MCP)

All of these frameworks connect to the same stdio server: command `uvx`, arguments `["minion-desktop", "mcp"]`.
If Minion is installed, use command `minion` with arguments `["mcp"]`.

**What was verified.** For each framework, a script in [`examples/frameworks/`](../examples/frameworks/) starts
Minion's MCP server through the framework's own MCP support. It then loads the tools and calls
`desktop(action="profiles")` through the framework. `examples/frameworks/check_all.sh` re-runs all of them in fresh
virtual environments. Each snippet below was also run exactly as written, with the model endpoint pointed at a closed
local port. Every snippet started the server, loaded the tools and built the agent, then stopped when it reached the
model. **No model was called**, so the model side is unverified. Where noted, a full agent turn was also run against
a scripted stand-in model.

| Framework | Install | Verified with (2026-10-14, Python 3.12) |
|---|---|---|
| [OpenAI Agents SDK](#openai-agents-sdk) | `pip install openai-agents` | openai-agents 0.23.1 · mcp 2.3.0 |
| [LangChain / LangGraph](#langchain--langgraph) | `pip install langchain-mcp-adapters "langchain[openai]"` | langchain-mcp-adapters 0.3.2 · langchain 1.4.5 · langgraph 1.2.15 · mcp 1.30.0 |
| [LlamaIndex](#llamaindex) | `pip install llama-index-tools-mcp llama-index-llms-openai` | llama-index-tools-mcp 0.6.0 · llama-index-core 0.14.25 · mcp 2.3.0 |
| [CrewAI](#crewai) | `pip install crewai "crewai-tools[mcp]"` | crewai 1.15.28 · crewai-tools 1.15.28 · mcp 1.28.1 |
| [smolagents](#smolagents) | `pip install "smolagents[mcp]" "mcp<2"` | smolagents 1.26.0 · mcpadapt 0.1.20 · mcp 1.30.0 |
| [Pydantic AI](#pydantic-ai) | `pip install "pydantic-ai-slim[mcp,openai]"` | pydantic-ai-slim 2.56.0 · fastmcp-slim 4.1.0 · mcp 2.3.0 |
| [Google ADK](#google-adk) | `pip install "google-adk[mcp]"` | google-adk 2.12.0 · mcp 2.3.0 |
| [AutoGen AgentChat](#autogen-agentchat) | `pip install autogen-agentchat "autogen-ext[mcp,openai]" "mcp<2"` | autogen-agentchat 0.7.5 · autogen-ext 0.7.5 · mcp 1.30.0 |

Four things matter in every framework:

- **Timeouts.** A Minion call can take minutes: a first-time image download, a long `run`, or a `view` hand-off
  that waits up to 10 minutes for a human. Several frameworks time out after 5 s. Where a framework has a
  timeout, the snippets raise it to 900 s.
- **One session.** The MCP server remembers which desktop the agent uses, and it serves the live view from its
  own process. Frameworks that start a new server for every call (LangChain `client.get_tools()`, LlamaIndex
  `BasicMCPClient`, CrewAI `Agent(mcps=[...])`) lose both. Their tools fall back to the most recently created
  desktop, and live-view links stop working once the call returns. The snippets below keep one session.
- **Environment.** The MCP SDK starts the server with only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM` and `USER`.
  If you need `DOCKER_HOST` or `MINION_*` variables, pass them with `env` (every stdio config below accepts it).
- **Instructions.** Minion's server sends usage notes in the MCP handshake, but only Pydantic AI passes them to the
  model (with `include_instructions=True`). Elsewhere, put the tips from [agents.md](agents.md) in the agent's
  instructions.

### OpenAI Agents SDK

```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    async with MCPServerStdio(
        name="minion",
        params={"command": "uvx", "args": ["minion-desktop", "mcp"]},
        client_session_timeout_seconds=900,  # default: 5 s
        cache_tools_list=True,
    ) as minion:
        agent = Agent(name="Desktop agent", instructions="Use Minion's desktops. Read screens with see().",
                      model="gpt-5", mcp_servers=[minion])
        task = "Open example.com and tell me its heading."
        result = await Runner.run(agent, task, max_turns=50)  # default: 10 turns
        print(result.final_output)

asyncio.run(main())
```

Also verified: the tools as the agent hands them to the model (`agent.get_mcp_tools()`), including the
SDK's strict-schema conversion (`mcp_config={"convert_schemas_to_strict": True}`) for every tool.

### LangChain / LangGraph

```python
import asyncio
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

client = MultiServerMCPClient(
    {"minion": {"transport": "stdio", "command": "uvx", "args": ["minion-desktop", "mcp"]}}
)

async def main():
    async with client.session("minion") as session:  # one Minion server for the whole run
        tools = await load_mcp_tools(session)
        agent = create_agent("openai:gpt-5", tools, system_prompt="Use Minion's desktops. Read screens with see().")
        task = {"role": "user", "content": "Open example.com and tell me its heading."}
        result = await agent.ainvoke({"messages": [task]})
        print(result["messages"][-1].content)

asyncio.run(main())
```

`await client.get_tools()` also works, but it starts a new Minion server for every tool call.

### LlamaIndex

```python
import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from llama_index.tools.mcp import McpToolSpec
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = StdioServerParameters(command="uvx", args=["minion-desktop", "mcp"])
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await McpToolSpec(client=session).to_tool_list_async()
        tools = [t for t in tools if t.metadata.name != "screenshot"]  # see below
        agent = FunctionAgent(tools=tools, llm=OpenAI(model="gpt-5"),
                              system_prompt="Use Minion's desktops. Read screens with see().")
        print(await agent.run("Open example.com and tell me its heading.", max_iterations=50))  # default: 20

asyncio.run(main())
```

`McpToolSpec` accepts any MCP `ClientSession`, so one server serves the whole run. The documented shortcut,
`BasicMCPClient("uvx", args=[...], timeout=900)`, starts a new server for every call. LlamaIndex hands the model
`str()` of each result, so a screenshot would arrive as base64 text. That is why the snippet leaves `screenshot` out.
Alternatively, start the server with `args=["minion-desktop", "mcp", "--no-images"]`: it hides `screenshot` and
leaves images out of every result.

### CrewAI

```python
from crewai import Agent, Crew, Task
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

server = StdioServerParameters(command="uvx", args=["minion-desktop", "mcp"])
with MCPServerAdapter(server, connect_timeout=60) as tools:
    agent = Agent(role="Desktop operator", goal="Get things done on a Linux desktop",
                  backstory="You use Minion desktops: see() reads the screen, act() clicks and types.",
                  tools=tools, llm="gpt-5")
    task = Task(description="Open example.com and tell me its heading.", expected_output="The heading",
                agent=agent)
    print(Crew(agents=[agent], tasks=[task]).kickoff())
```

Use `MCPServerAdapter` rather than `Agent(mcps=[MCPServerStdio(...)])`. The `mcps` route starts a server for every
call. It also cuts each call off after 30 s and sends it again, up to three times, so a slow action would run three
times. The adapter passes only text to the model, so screenshots never reach it; `see` does.

### smolagents

```python
from mcp import StdioServerParameters
from smolagents import CodeAgent, InferenceClientModel, ToolCollection

server = StdioServerParameters(command="uvx", args=["minion-desktop", "mcp"])
with ToolCollection.from_mcp(server, trust_remote_code=True, structured_output=False) as minion:
    agent = CodeAgent(tools=[*minion.tools], model=InferenceClientModel())
    print(agent.run("Open example.com and tell me its heading."))
```

Pin `mcp<2`: mcpadapt 0.1.20 fails to import with version 2 of the MCP SDK. smolagents keeps only the first content
block of each result, so a screenshot arrives as an image without its caption. Also verified: a `CodeAgent`'s Python
executor calling a Minion tool.

### Pydantic AI

```python
import asyncio
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

minion = MCPToolset(
    StdioTransport(command="uvx", args=["minion-desktop", "mcp"]),
    read_timeout=900,  # default: 5 min
    include_instructions=True,  # adds Minion's usage notes to the agent's instructions
)
agent = Agent("openai:gpt-5", toolsets=[minion])

async def main():
    async with agent:  # starts Minion's server once for all runs
        result = await agent.run("Open example.com and tell me its heading.")
        print(result.output)

asyncio.run(main())
```

Pydantic AI 2 replaced `MCPServerStdio` with `MCPToolset`, which is built on FastMCP. Also verified: a full agent turn
with a scripted `FunctionModel` (tool call, Minion, result back to the model).

### Google ADK

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

root_agent = LlmAgent(
    model="gemini-3.5-flash",
    name="desktop_agent",
    instruction="Use Minion's desktops. Read screens with see().",
    tools=[McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(command="uvx", args=["minion-desktop", "mcp"]),
            timeout=900,  # also the per-call read timeout (default: 5 s)
        ),
        tool_filter=lambda tool, ctx=None: tool.name != "screenshot",  # see below
    )],
)
```

Run it like any ADK agent: `adk run`, `adk web`, or a `Runner` (the example script uses `InMemoryRunner`). ADK
returns tool results to Gemini as JSON, which is why the snippet filters out `screenshot`. Also verified: a full
agent turn with a scripted model.

### AutoGen AgentChat

```python
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

async def main():
    params = StdioServerParams(command="uvx", args=["minion-desktop", "mcp"],
                               read_timeout_seconds=900)  # default: 5 s
    async with McpWorkbench(params) as minion:
        agent = AssistantAgent("desktop_agent", model_client=OpenAIChatCompletionClient(model="gpt-5"),
                               workbench=minion, max_tool_iterations=50,  # default: 1
                               system_message="Use Minion's desktops. Read screens with see(), not screenshot.")
        await Console(agent.run_stream(task="Open example.com and tell me its heading."))

asyncio.run(main())
```

Pin `mcp<2`: autogen-ext 0.7.5 fails to import with version 2 of the MCP SDK. `AssistantAgent` turns tool results
into text and inlines images as base64, so ask the agent to use `see` instead. Also verified: a full agent turn with
`ReplayChatCompletionClient`.

### Screenshots and `see`

`see` returns text, so it works the same in every framework. How images from `screenshot` (and from `act` results
that include one) reach the model depends on the framework:

| Framework | A screenshot reaches the model as |
|---|---|
| OpenAI Agents SDK, LangChain, Pydantic AI | An image |
| smolagents | An image, without its caption |
| CrewAI | Text only; the image is dropped |
| LlamaIndex, Google ADK, AutoGen | Base64 text, typically 50–300 KB per screenshot. Leave `screenshot` out and use `see`, or run `minion mcp --no-images` |

## Agents with a shell

Claude Code, Codex CLI, Aider, Open Interpreter, Goose, and any other agent that can run commands can use the
`minion` CLI directly, with no MCP setup. (Most of them can also load the MCP server; see [agents.md](agents.md).)
Install Minion where the agent runs (`uv tool install minion-desktop`), then give the agent something like this:

> You have Linux desktops through the `minion` command. `minion up office` starts one (profiles: browser, office, dev,
> research, data, windows, base). `minion see` prints the screen as text with `@ids`. Act with `minion click @12`,
> `minion type "text"`, `minion key ctrl+s` and `minion fill @4 "text"`. `minion shot -o screen.png` saves a
> screenshot, and `minion run "cmd"` runs a shell command inside the desktop. Every action prints what changed.
> `minion --help` lists everything.

```bash
minion up office && minion open writer
minion see                                   # windows, then controls: @12 document text "..." [editable] (603,424)
minion click @12 && minion type "Hello from an agent" && minion key ctrl+s
minion shot -o screen.png --marks            # a screenshot with the @ids drawn on it
```

`minion skill` prints a fuller version of these instructions as an Agent Skill (`SKILL.md`), and
`minion skill --install DIR` installs it for agents that load skills. Add `--json` for machine-readable output. In Aider, `/run minion see` can add the screen to the chat. If your agent
sandboxes its commands, allow `minion` to reach Docker.

## Any LLM with function calling

Without an MCP client, use `minion.tools`. It exports the same tools in each model API's format and runs the calls:

```python
from minion.tools import INSTRUCTIONS, Toolkit

tk = Toolkit()
tools = tk.definitions("openai")          # or "openai-responses", "anthropic", "gemini", "mcp"
# give `tools` (and INSTRUCTIONS as the system prompt) to your model; when it calls tools:
messages += tk.run_calls(msg.tool_calls)  # runs them and returns the reply messages in that API's shape
result = tk.call(name, arguments)         # or one call at a time: ToolResult(.text, .images, .is_error)
```

Complete loops for OpenAI, Anthropic and Gemini are in [agents.md](agents.md#without-mcp-function-calling-with-any-model).

`minion tools --format openai` prints the same definitions from the shell. Over HTTP (`minion serve`), any language
can do the same:

```bash
curl -s -H "Authorization: Bearer $TOKEN" "localhost:4747/api/tools?format=openai"
curl -s -H "Authorization: Bearer $TOKEN" -X POST localhost:4747/api/tools/call \
     -d '{"name": "desktop", "arguments": {"action": "create", "profile": "browser"}}'
```

A call returns `{"content": [...], "isError": false}`. Each content item is either
`{"type": "text", "text": "..."}` or `{"type": "image", "data": "<base64>", "mimeType": "image/png"}`.
