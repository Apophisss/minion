<p align="center">
  <img src="docs/assets/hero.png" alt="Minion: instant desktops for AI agents" width="100%">
</p>

<h3 align="center">Give every AI agent its own computer.</h3>

<p align="center">
  Featherweight Linux desktops (office, dev, research, browser, data, Windows apps) that any agent can use:<br>
  over <b>MCP</b>, <b>function calling</b> for any model, <b>HTTP/OpenAPI</b>, a <b>CLI</b>, <b>Python</b> or <b>TypeScript</b>.<br>
  Agents read the screen as text, act in batches or in code, and use any program or website.
</p>

<p align="center">
  <a href="https://pypi.org/project/minion-desktop/"><img src="https://img.shields.io/pypi/v/minion-desktop?color=6366f1" alt="PyPI"></a>
  <a href="https://github.com/apophisss/minion/actions/workflows/ci.yml"><img src="https://github.com/apophisss/minion/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-6366f1" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/dependencies-0-22c55e" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/MCP-ready-8b5cf6" alt="MCP">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-6366f1" alt="MIT"></a>
</p>

```bash
pipx install minion-desktop        # or: uv tool install minion-desktop   (needs Docker)
minion up office                   # a full office desktop, ready in ~1.5 s
minion open writer                 # LibreOffice Writer opens
minion see                         # the screen as text: every control has an @id
minion click "Bold" && minion type "Hello from an agent"
minion view                        # watch it live in your browser
```

<p align="center"><img src="docs/assets/demo.gif" alt="An agent searching Wikipedia on a Minion desktop, recorded by Minion's flight recorder" width="720"></p>
<p align="center"><sub>An agent on a <code>research</code> desktop. The GIF was made by Minion's built-in flight recorder (<code>minion replay -o demo.gif</code>).</sub></p>

---

## Why Minion

- **🖥️ Any program, any website.** Every desktop is a real Linux computer: browsers, LibreOffice, IDEs, terminals,
  file dialogs and installers, plus Windows programs through the `windows` (Wine) profile. Anything missing is one
  command away: `minion-install gimp`, a `.deb`/`.AppImage` URL, `pip:` or `npm:`.
- **🧠 Agents read the screen as text.** `see` turns any window into a list of controls with **stable `@ids`**, taken
  from the accessibility tree with OCR as a fallback: `@12 button "Save" (210,62)`. Spreadsheets come out as
  `A1: value`. The text is exact and clickable, and when pixels matter, screenshots can draw the `@ids` for you.
- **🪙 Built to save tokens.** You get diffs instead of re-reads (`see(changes=true)`: about 60 tokens instead of about 900). **Code mode**
  runs a 50-step GUI loop in one call, actions report what changed so no extra look is needed, crops and half-size
  screenshots cut image cost, and a **compact mode** shrinks the tool definitions from about 2,100 tokens to 230.
- **🪶 Featherweight.** One small container per desktop (Xvfb, a 2-process window manager and taskbar, a small agent),
  with no VNC and no desktop environment. Desktops are ready in about 1.5 s and use about 60 MB when idle. Idle desktops are frozen
  automatically (0% CPU) and wake in about 0.2 s.
- **🔌 Works with every agent.** One toolset is served everywhere: MCP for Claude Code, Cursor, VS Code, Codex,
  Gemini CLI, OpenAI Agents SDK, LangChain, CrewAI and others; function-calling definitions for OpenAI, Anthropic,
  Gemini and local models; HTTP with OpenAPI; a CLI and an Agent Skill for shell agents; Python and TypeScript SDKs; and native
  adapters for **Claude, OpenAI and Gemini computer use**.
- **⚡ Parallel by design.** `create count=8` starts a desktop per worker, `fork` clones one before a risky step,
  and sessions keep agents apart.
- **🙋 Humans in the loop.** A live view in the browser offers one-click *take control*. Agents can **hand off** ("please
  sign in") and wait for *Done*.
- **🎞️ Teach once, replay forever.** Every action is recorded. Export an HTML timeline or GIF, or turn the session into
  a **Python script that replays it with no model at all**.
- **📦 Zero dependencies.** The host side is pure Python standard library. Desktops run in Docker or Podman
  (macOS, Windows, Linux), or natively on Linux.

## Quick start

**1. Install** (Python 3.11+ and [Docker](https://docs.docker.com/get-docker/) or Podman):

```bash
pipx install minion-desktop          # or: uv tool install minion-desktop / pip install minion-desktop
minion doctor                        # checks your setup
```

The first desktop of each profile downloads its image (188–710 MB, shared layers): `minion pull office research`.

**2. Connect your agent.** With MCP:

```bash
claude mcp add minion -- uvx minion-desktop mcp           # Claude Code (9 tools)
claude mcp add minion -- uvx minion-desktop mcp --compact # one `computer` tool, smallest context
```

Or install the Claude Code plugin, which adds the MCP tools plus a skill that teaches efficient use:
`claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`.

<details>
<summary><b>Claude Desktop, Cursor, VS Code, Windsurf, Codex, Gemini CLI, …</b></summary>

Most clients take the same JSON (Claude Desktop: `claude_desktop_config.json`, Cursor: `~/.cursor/mcp.json`, Windsurf: `~/.codeium/windsurf/mcp_config.json`, Gemini CLI: `~/.gemini/settings.json`):

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

VS Code (`.vscode/mcp.json`):

```json
{ "servers": { "minion": { "type": "stdio", "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

OpenAI Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.minion]
command = "uvx"
args = ["minion-desktop", "mcp"]
```

Framework recipes (OpenAI Agents SDK, LangChain/LangGraph, LlamaIndex, CrewAI, smolagents, Pydantic AI, Google ADK, AutoGen) are in [docs/integrations.md](docs/integrations.md).
</details>

Then just ask: *"Create an office desktop, write a one-page brief about our Q3 numbers in Writer and save it as brief.docx."*

**3. Or drive it from a shell.** Any agent with a terminal (Claude Code, Codex CLI, Aider, Open Interpreter, Goose) can use the CLI directly:

```bash
minion up research
minion open "en.wikipedia.org"
minion fill "Search Wikipedia" "Ada Lovelace" && minion key Return
minion wait-for "Analytical Engine"
minion see --full                       # read the article as text
minion shot -o page.png --marks         # a screenshot with @ids drawn on it
minion run "pdftotext -layout ~/Downloads/paper.pdf - | head"
minion cp :~/Documents/notes.md .       # copy files out (and in)
```

## Works with every agent

| Your agent | Connect with |
|---|---|
| MCP clients and frameworks (Claude Code/Desktop, Cursor, VS Code, Codex, Gemini CLI, OpenAI Agents SDK, LangChain, CrewAI, LlamaIndex, smolagents, Pydantic AI, ADK, AutoGen) | `uvx minion-desktop mcp` ([recipes](docs/integrations.md)) |
| Any model with function calling (OpenAI, Anthropic, Gemini, Mistral, local models via Ollama/vLLM) | `Toolkit().definitions("openai" \| "anthropic" \| "gemini")` + `Toolkit().run_calls()` ([docs](docs/agents.md#without-mcp-function-calling-with-any-model)) |
| Anything that speaks HTTP (n8n, Dify, GPT Actions, any language) | `minion serve` → `/api/tools/*` and `/openapi.json` ([docs](docs/http-api.md)) |
| Shell agents | the `minion` CLI ([docs](docs/cli.md)) |
| Agents that read [Agent Skills](https://agentskills.io) (Claude Code, Codex CLI, Cursor, Gemini CLI, Copilot, Goose, …) | `minion skill --install [DIR]` writes a `SKILL.md` that teaches the CLI (about 100 tokens until it is used) |
| Python / TypeScript code | `from minion import Desktop` ([docs](docs/python.md)) · [`clients/typescript`](clients/typescript) |
| Native computer-use models | Claude toolset ([docs](docs/computer-use.md)) · OpenAI and Gemini computer use ([docs](docs/computer-use-openai-gemini.md)) |

A complete agent with **any** OpenAI-compatible model (`"anthropic"`, `"gemini"` and `"openai-responses"` work
the same way):

```python
from openai import OpenAI
from minion.tools import Toolkit

tk = Toolkit()
client = OpenAI()  # or OpenAI(base_url="http://localhost:11434/v1", api_key="ollama") for a local model
messages = [{"role": "user", "content": "On a research desktop, find the population of Iceland on Wikipedia."}]
while True:
    msg = (
        client.chat.completions.create(model="YOUR-MODEL", messages=messages, tools=tk.definitions("openai"))
        .choices[0]
        .message
    )
    messages.append(msg)
    if not msg.tool_calls:
        break
    messages += tk.run_calls(msg.tool_calls)  # runs every call, returns the messages to send back
print(msg.content)
```

## Python, and code mode

```python
from minion import Desktop

with Desktop.create("office", keep=False) as desk:  # removed when the block ends
    desk.open("calc")
    result = desk.script("""
for item, price in [("Coffee", 3.5), ("Bagel", 2.25), ("Juice", 4)]:
    write(f"{item}\\t{price}\\n")             # Tab moves right, Return goes down
write("Total\\t=SUM(B1:B3)\\n")
print(cells()["B4"])                          # visible cells as {"A1": ...}
""")
    print(result.stdout)  # 9.75
    desk.key("ctrl+s")
    desk.fill("Name", "q3.xlsx")
    desk.key("Return")
    desk.wait_for("q3.xlsx")
    desk.download("~/Documents/q3.xlsx", ".")
```

`script` runs Python **inside** the desktop with `click · write · key · scroll · fill · see · elements · cells ·
wait_for · launch · run`. Loops cost one call, and only what the code prints comes back. The `Desktop` API also
has `screenshot · see · act · open · run · upload · download · clipboard · windows · freeze · fork · snapshot ·
restore · recording · create_many`. See [docs/python.md](docs/python.md).

## Native computer use (Claude, OpenAI, Gemini)

Minion is a ready environment for each vendor's computer-use model, with screenshot scaling and coordinate mapping
handled for you:

```python
import anthropic
from minion import Desktop
from minion.integrations.anthropic import MinionComputer, allow_all

desk = Desktop.create("office")
with MinionComputer(desk, confirm=allow_all) as computer:  # the desktop is the sandbox
    runner = anthropic.Anthropic().beta.messages.tool_runner(
        model="claude-opus-5-5",
        max_tokens=16000,
        tools=[computer],
        messages=[{"role": "user", "content": "Make a 3-slide deck about otters in Impress."}],
    )
    for message in runner:
        print(message)
```

Claude's `computer_toolset_20260801` (all 17 actions) and the earlier `computer_20251124` are covered in
[docs/computer-use.md](docs/computer-use.md). OpenAI and Gemini computer use are covered in
[docs/computer-use-openai-gemini.md](docs/computer-use-openai-gemini.md).

## Profiles

| Profile | What's inside | Download | Idle RAM |
|---|---|---|---|
| 🌐 `browser` | Firefox with uBlock Origin (ads, trackers, cookie banners, newsletter pop-ups), downloads straight to `~/Downloads` | 352 MB | ~55–100 MB |
| 📄 `office` | LibreOffice Writer, Calc, Impress + text editor + file manager + Firefox. Saves Microsoft formats by default | 511 MB | ~85 MB |
| 🛠️ `dev` | git, Python, Node.js, build tools, Geany IDE, a real terminal (readable by `see`), Firefox + Chromium | 703 MB | ~55 MB |
| 🔎 `research` | Firefox + `pdftotext`, `pandoc`, a notes editor, Python with requests and BeautifulSoup | 410 MB | ~55 MB |
| 📊 `data` | `office` + pandas, NumPy, SciPy, matplotlib, seaborn, openpyxl, SQLite | 662 MB | ~105 MB |
| 🪟 `windows` | Wine 10 for 64- and 32-bit Windows `.exe`/`.msi` programs, plus Firefox to download them. x86-64 hosts ([docs](docs/windows-apps.md)) | 707 MB | ~56 MB (~270 MB with a program open) |
| 🧩 `base` | X server, window manager, terminal and the agent. The foundation to build on | 188 MB | ~65 MB |

**Your own profile** is a 5-line TOML file in `~/.config/minion/profiles/`. It is built automatically the first time you use it:

```toml
# ~/.config/minion/profiles/designer.toml
extends = "browser"
description = "Firefox plus GIMP and Inkscape."
packages = ["gimp", "inkscape"]
apps = [{ name = "GIMP", command = "gimp" }, { name = "Inkscape", command = "inkscape" }]
```

Or add software at runtime: `minion run "minion-install gimp https://example.com/tool.AppImage pip:yt-dlp"`.
See [docs/profiles.md](docs/profiles.md).

## How agents see the screen

`see` is the agent's main sense. Here it is on a LibreOffice window:

```text
Screen 1280x800 · 1 window
  [1] "Untitled 1 — LibreOffice Writer" — libreoffice-writer (focused) at 0,0 1280x770

UI of "Untitled 1 — LibreOffice Writer" (click/fill with @id; (x,y) is the element center):
@1 menu "File" (22,38)
@2 menu "Edit" (62,38)
…
@12 document text "Untitled 1 - LibreOffice Document" [editable] (603,424)
  @13 heading "Q3 Market Brief" (603,247)
  @14 paragraph "Prepared by an AI agent on a Minion desktop. No human touched the keyboard." (603,282)
```

After an action, `observe="changes"` (or `see(changes=true)`) returns only the difference:

```text
✓ typed 30 chars
→ screen changed <1% (region 404,226 236x20)
Changes since your last look 1.0s ago (81 elements unchanged; their @ids still work):
  + @84 paragraph "Quarterly numbers look strong." [focused] (603,234)
  ~ @80 label "4 words, 30 characters" (281,730)
```

When pixels matter, `screenshot --marks` labels every control with its `@id`:

<p align="center"><img src="docs/assets/marks.png" alt="Screenshot with @id marks on every clickable element" width="720"></p>

## Efficiency, measured

| | Tokens | |
|---|---|---|
| Screenshot 1280×800 | ~1,365 | the baseline |
| `screenshot(detail="low")` | ~341 | half size |
| `act(observe="crop")`, only the changed region | ~200 | |
| `see` of a LibreOffice window | ~920 | exact text plus clickable ids |
| `see(changes=true)` after typing a sentence | **~60** | stable ids, diff only |
| `see` of a terminal | ~50–90 | |
| Tool definitions: 9 tools / compact `computer` | ~2,100 / **~230** | sent with every request |
| 5 rows of spreadsheet entry: `act` ×5 / `script` ×1 | 5 calls / **1 call** | no model round trip per step |

| Resources | |
|---|---|
| Ready in | 1.2–1.8 s (every profile) |
| Idle RAM | 54–105 MB per desktop (Firefox/LibreOffice add their own when open) |
| Frozen | 0.00% CPU, thawed in ~0.2 s on the next call |
| 3 desktops in parallel | 3.0 s |

These were measured on a 2-vCPU VM. Reproduce them with `python scripts/bench.py`.

## Watch, take over, hand off

`minion view` (or the `view` tool) opens a live view of any desktop in your browser. Click **Take control** to use
your own mouse and keyboard. An agent can call `view(message="Please sign in to your Google account")`: you get a
banner, sign in, press **Done**, and the agent continues. A good pattern is to log in once, `snapshot`, then `fork`
the logged-in desktop for each task. `minion serve` adds a dashboard with live thumbnails:

<p align="center"><img src="docs/assets/dashboard.png" alt="The Minion dashboard with live desktop thumbnails" width="860"></p>

## How it works

```mermaid
flowchart LR
  subgraph host["Your machine"]
    A["Any agent<br/>(MCP, function calling, HTTP, CLI, SDK)"] --> T["minion tools<br/>(pure-stdlib Python)"]
    T --> V["Live view and dashboard<br/>(minion serve)"]
  end
  subgraph desk["Desktop (one container each)"]
    S["minion agent<br/>RPC over docker exec"] --> X["Xvfb + JWM"]
    S --> AT["AT-SPI<br/>accessibility tree"]
    S --> O["Tesseract OCR"]
    S --> C["code mode<br/>(Python inside)"]
    X --> Apps["Firefox · LibreOffice · Terminal · Wine · …"]
  end
  T -->|"docker exec (no open ports)"| S
```

Read [docs/design.md](docs/design.md) for the reasoning behind each choice, and [docs/architecture.md](docs/architecture.md) for the internals.

## Security

Each desktop is an unprivileged container with no host mounts by default. Use `--offline` to cut network access,
or limit resources with `--memory` and `--cpus`. The HTTP server binds to `127.0.0.1`, needs a random token, and refuses
cross-site and DNS-rebinding requests. The desktop user has passwordless `sudo` **inside** the container, so agents
can install software. Treat everything on a screen as untrusted input (prompt injection), and keep credentials
out of desktops unless a human hands off. Read [SECURITY.md](SECURITY.md).

## Documentation

[Design](docs/design.md) · [Agents & MCP](docs/agents.md) · [Integrations](docs/integrations.md) · [CLI](docs/cli.md) · [Python](docs/python.md) · [HTTP API](docs/http-api.md) · [Claude computer use](docs/computer-use.md) · [OpenAI & Gemini computer use](docs/computer-use-openai-gemini.md) · [Profiles](docs/profiles.md) · [Windows apps](docs/windows-apps.md) · [Architecture](docs/architecture.md) · [FAQ](docs/faq.md)

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions include new
profiles (`minion/profiles/*.toml`), better `see` output for specific apps, and integration recipes.

## License

[MIT](LICENSE). The desktops contain open-source software under their own licenses (Debian, Firefox, LibreOffice, Wine, …).
