# Agents & MCP

Minion ships an MCP server, so any MCP client can create and use desktops. The server has
no dependencies and speaks MCP over stdio. Web chat apps (ChatGPT, Claude.ai, Le Chat) connect by URL instead:
see [remote.md](remote.md). To add Minion to every agent app on your computer at once, run `minion connect`
([connect.md](connect.md)).

```bash
uvx minion-desktop mcp          # without installing anything (needs uv)
minion mcp                      # if Minion is installed
```

## Connect a client

| Client | How |
|---|---|
| **Claude Code** | `claude mcp add minion -- uvx minion-desktop mcp` |
| **Claude Desktop** | `claude_desktop_config.json` → `{"mcpServers": {"minion": {"command": "uvx", "args": ["minion-desktop", "mcp"]}}}` |
| **Cursor** | `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project), same JSON as Claude Desktop |
| **VS Code** | `.vscode/mcp.json` → `{"servers": {"minion": {"type": "stdio", "command": "uvx", "args": ["minion-desktop", "mcp"]}}}` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json`, same JSON as Claude Desktop |
| **OpenAI Codex CLI** | `~/.codex/config.toml` → `[mcp_servers.minion]` with `command = "uvx"` and `args = ["minion-desktop", "mcp"]` |
| **Gemini CLI** | `~/.gemini/settings.json` → `{"mcpServers": {"minion": {"command": "uvx", "args": ["minion-desktop", "mcp"]}}}` |
| **Anything else** | a stdio server: command `uvx`, arguments `minion-desktop mcp` |

Prefer an installed binary? Use `"command": "minion", "args": ["mcp"]`. To run from a git checkout,
use `uvx --from git+https://github.com/apophisss/minion minion mcp`.

### Options

| Variable / flag | Default | Meaning |
|---|---|---|
| `--preload office,research` | none | prepare these profiles' images in the background when the server starts |
| `--compact` | off | one `computer` tool with CLI-style commands instead of nine tools |
| `--no-images` | off | text only: no `screenshot` tool, and images are left out of results. Use it for clients that pass images to the model as base64 text (LlamaIndex, Google ADK, AutoGen) |
| `--idle-freeze SECONDS` / `MINION_IDLE_FREEZE` | `600` | freeze desktops nobody used or watched for this long (`0` = never) |
| `MINION_DEFAULT_PROFILE` | `browser` | profile for `desktop(action="create")` without a profile |
| `MINION_MCP_CREATE_WAIT` | `240` | seconds `create` waits for a first-time image download before replying "still preparing" |
| `MINION_BACKEND` | `auto` | `docker`, `podman` or `local` |
| `MINION_FILES_ROOT` | the working directory, or `~/Minion` | the only folder on your machine that the `files` tool's `upload`/`download` may use (`/` allows any path) |

## The tools

| Tool | What it does |
|---|---|
| `desktop` | `create` (profile, name, size, `count` for several in parallel), `list`, `profiles`, `remove`, `freeze`, `thaw`, `fork`, `snapshot`, `restore`, `replay` (HTML timeline), `macro` (everything done so far as a Python script that replays it without a model) |
| `see` | The screen as text: windows, then the focused window's controls with **stable** `@ids`, roles, names, values, states and centers. `changes=true` returns only what changed since the last look. Use `ocr=true` for canvases and images, and `full_text=true` to read long text |
| `screenshot` | A PNG. Use `marks=true` to draw `@ids`, `detail="low"` for half size (4× fewer tokens), `region=[x,y,w,h]` with `zoom=true` to magnify, and `grid=true` for a coordinate grid |
| `act` | A batch of mouse and keyboard actions: `click`, `double_click`, `right_click`, `move`, `drag`, `type`, `paste`, `fill`, `key`, `scroll`, `wait`, `wait_for`, `focus`, and more. It stops at the first failure, waits for the screen to settle, and reports what changed. `observe`: `summary` (default), `changes` (+ the changed UI as text), `see`, `screenshot` or `crop` (only the changed region) |
| `script` | **Code mode**: Python runs inside the desktop with `click/write/key/scroll/fill/see/elements/cells/wait_for/launch/run`. Loops and data entry take one call, and only what the program prints comes back |
| `open` | Launches a profile app (`writer`, `calc`, `firefox`, …), a URL, a file or a command, and waits for its window |
| `run` | A shell command inside the desktop (`sudo` is available). Returns stdout, stderr and the exit code |
| `files` | `upload` / `download` between this machine and the desktop, and `read` / `write` text files |
| `view` | A live link for the human. With `message`, it hands control to the human and waits until they press Done |

The default target of every tool is the desktop the agent created or used last. Pass `desktop` to pick another.

**Compact mode** (`minion mcp --compact`) exposes a single `computer` tool that takes CLI-style commands
(`see`, `click @12`, `type 'hi'`, `run ls`, `create office -n 2`). It cuts the tool definitions sent with every
request from about 2,100 tokens to about 230, and works well for small and local models.

## Shell agents and Agent Skills

An agent that can run shell commands needs no MCP at all: the `minion` CLI does everything the tools do
([cli.md](cli.md)). To teach it the CLI, install the bundled [Agent Skill](https://agentskills.io):

```bash
minion skill --install                       # ~/.claude/skills/minion/SKILL.md (Claude Code)
minion skill --install ~/.codex/skills       # or any agent's skills directory
minion skill >> AGENTS.md                    # or append it to an AGENTS.md / system prompt
```

A skill costs about 100 tokens (its description) until the agent decides it needs a desktop. Only then does
it read the rest, about 1,100 tokens. MCP tool definitions, by contrast, are sent with every request. For
Claude Code there is also a plugin that bundles the MCP server and the skill:

```bash
claude plugin marketplace add apophisss/minion
claude plugin install minion@minion
```

## Without MCP: function calling with any model

The same tools work in any agent loop you write yourself. `Toolkit.definitions(format)` gives the
definitions in your API's shape, and `Toolkit.run_calls(calls, format)` runs the model's tool calls (SDK
objects or plain dicts) and returns exactly what to send back, with screenshots placed where that API
accepts images. `INSTRUCTIONS` is a short system prompt that teaches the tools.

**OpenAI Chat Completions** (also Ollama, vLLM, LM Studio, Mistral, Groq, OpenRouter and other compatible APIs):

```python
from openai import OpenAI
from minion.tools import INSTRUCTIONS, Toolkit

tk, client = Toolkit(), OpenAI()
messages = [
    {"role": "system", "content": INSTRUCTIONS},
    {"role": "user", "content": "Book-keep these receipts in Calc: ..."},
]
while True:
    msg = (
        client.chat.completions.create(model="YOUR-MODEL", messages=messages, tools=tk.definitions("openai"))
        .choices[0]
        .message
    )
    messages.append(msg)
    if not msg.tool_calls:
        break
    messages += tk.run_calls(msg.tool_calls)
```

**Anthropic Messages API:**

```python
import anthropic
from minion.tools import INSTRUCTIONS, Toolkit

tk, client = Toolkit(), anthropic.Anthropic()
messages = [{"role": "user", "content": "Make a 3-slide deck about otters in Impress."}]
while True:
    reply = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        system=INSTRUCTIONS,
        thinking={"type": "adaptive"},
        tools=tk.definitions("anthropic"),
        messages=messages,
    )
    messages.append({"role": "assistant", "content": reply.content})
    if reply.stop_reason != "tool_use":
        break
    messages += tk.run_calls(reply.content, "anthropic")
```

**Gemini** (`google-genai`):

```python
from google import genai
from google.genai import types
from minion.tools import INSTRUCTIONS, Toolkit

tk, client = Toolkit(), genai.Client()
config = types.GenerateContentConfig(
    system_instruction=INSTRUCTIONS, tools=[types.Tool(function_declarations=tk.definitions("gemini"))]
)
contents = [types.Content(role="user", parts=[types.Part(text="Find three papers on RLHF and save the PDFs.")])]
while True:
    response = client.models.generate_content(model="YOUR-GEMINI-MODEL", contents=contents, config=config)
    contents.append(response.candidates[0].content)
    if not response.function_calls:
        break
    contents.append(types.Content(role="user", parts=tk.run_calls(response.function_calls, "gemini")))
```

**OpenAI Responses API:** `tools=tk.definitions("openai-responses")`, then
`items += response.output` and `items += tk.run_calls(response.output, "openai-responses")` (non-call items
are skipped).

Pass `compact=True` to `definitions()` for the single `computer` tool. Frameworks that wrap plain Python
functions can use `tk.functions()`, a dict of text-in, text-out callables. For recipes for LangChain, CrewAI,
LlamaIndex, smolagents, Pydantic AI, Google ADK, AutoGen and the OpenAI Agents SDK, see
[integrations.md](integrations.md). Other languages can call the same tools over HTTP
([http-api.md](http-api.md)).

## Tips for agents (paste into a system prompt if you like)

- **Look with `see` first.** It is exact and usually costs fewer tokens than a screenshot. Click or fill by `@id`.
  Use a screenshot when the layout, an image or a chart matters. Ids are stable, so after the first look
  use `see(changes=true)` or `act(..., observe="changes")`, which usually costs a few dozen tokens.
- **Write a script for anything repetitive.** Twenty rows of data entry or a loop over files belongs in one
  `script` call, not twenty `act` calls.
- **Batch actions.** For example,
  `act(actions=[{"action": "fill", "target": "@4", "text": "alice"}, {"action": "click", "target": "Sign in"}])`.
  The reply says what changed (new windows, focus, the changed region), which often makes another `see` unnecessary.
- **Read documents as text, and use the shell for data.** `files(action="read")` returns any document's text
  (docx, xlsx with formulas, pptx, pdf, odt…), `files(action="convert")` changes formats, and `run` is faster
  than the GUI for data (`python3 -c …`). Use the GUI for what needs eyes.
- **Open apps by name.** `open("gimp")`, `open("vscode")` or `open("dbeaver")` installs the app the first time and
  answers with a few tips for it. `open("figma")` and `open("google sheets")` open web apps.
- **Use menus and file dialogs directly.** `see(menus=true)` lists every menu command with its shortcut;
  `{"action": "menu", "item": "File > Export As > Export as PDF..."}` runs one. In an Open/Save dialog,
  `{"action": "path", "path": "~/Documents/out.pdf"}` types the full path and confirms.
- **Wait for things, not for time.** `{"action": "wait_for", "text": "Saved"}` returns as soon as the text appears.
- **Keyboard shortcuts work everywhere.** Examples: `ctrl+l` then type a URL, `ctrl+s`, `alt+Left` (back), `ctrl+Tab`, `F5`.
- **Fork before risky steps** (`desktop(action="fork")`) and keep going on the copy.
- **Hand off to the human** for logins, 2FA or CAPTCHAs: `view(message="Please sign in, then press Done")`.

## Coordinates and targets

Targets accept `"@12"` (from the latest `see`), visible text (`"Save"`, `"Sign in"`), or `"x,y"` pixels.
Pixels in a full screenshot are desktop pixels (1280×800 by default). For a zoomed region, the screenshot
reply states the mapping. When text matches several controls, Minion picks the best (interactive, exact, in
the focused window) and tells you to use an `@id` to choose another.

## Security notes

A desktop is a sandbox, not a vault. Anything an agent reads on screen can be adversarial (prompt injection).
Don't put long-lived credentials in desktops. Hand off to a human for sign-ins. Use `--offline` desktops
for untrusted documents. See [SECURITY.md](../SECURITY.md).
