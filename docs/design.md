# How Minion is designed

Minion answers one question: *what is the cheapest, most reliable way to give any AI agent a whole
computer?* Every design choice below trades something away to make agents faster, cheaper, or more
reliable.

## 1. A computer, not a browser

Agents need more than web pages: spreadsheets, word processors, IDEs, terminals, file dialogs, installers,
and Windows programs. A Minion desktop is a real Linux desktop (Debian, X11) in a container, so *any*
program works:

- **Profiles** pre-install and tune the common jobs: `browser`, `office`, `dev`, `research`, `data`,
  `windows` (Wine) and `base`.
- **`minion-install`** gets anything else in one command: apt packages, `.deb` / `.AppImage` / archive
  URLs, `pip:` and `npm:` packages.
- **`run`** is a real shell with `sudo`, and **`files`** moves data in and out.

## 2. Text first, pixels when needed (token efficiency)

Screenshots are the most expensive thing an agent can look at. A 1280×800 image costs about 1,365 tokens,
and the model still has to guess coordinates. Minion reads the screen the way a screen reader does:

| Technique | What it saves |
|---|---|
| **`see`**: the accessibility tree (GTK, Qt, Firefox, Chromium, LibreOffice) as a compact list of controls with `@ids`, collapsing wrappers, twins and browser chrome; spreadsheet cells as `A1: value` | Exact text. Often fewer tokens than a screenshot (a terminal is about 50 tokens instead of 1,365) |
| **Stable `@ids`**: the same control keeps its id across looks | The agent doesn't have to re-read the screen to act |
| **`see(changes=true)` / `act(observe="changes")`**: only what changed since the last look | After typing, about 20 tokens instead of about 1,000 |
| **Act-and-report**: every action waits for the UI to settle, then says what changed (windows opened or closed, focus, changed region) | A separate "did it work?" look is usually unnecessary |
| **`screenshot(detail="low")`** | 341 instead of 1,365 tokens |
| **`act(observe="crop")`**: an image of just the changed region | About 200 tokens |
| **`marks=true`**: `@ids` drawn on the screenshot | Pixel-precise clicking without coordinate guessing |
| **OCR fallback** when an app has no accessibility tree | Text even from canvases and Wine apps |
| **Code mode (`script`)**: Python runs *inside* the desktop with `click/write/key/see/cells/...` | 50 GUI steps in one tool call. Only what the program prints comes back |
| **Compact mode**: one `computer` tool with CLI syntax | Tool definitions shrink from about 2,100 to about 230 tokens per request |

## 3. Featherweight (resource efficiency)

- **No desktop environment, no VNC, no browser bundle.** Each desktop runs Xvfb, a minimal window manager (JWM),
  D-Bus/AT-SPI and a small Python agent: about 60 MB idle. Desktops are ready in about 1.5 s.
- **Shared layers.** Every profile extends another (`base → browser → office → data`), so ten desktops share
  one copy of the base image on disk and in the page cache.
- **Idle freezing.** A desktop nobody uses or watches is paused with the cgroup freezer (0% CPU). The next call
  thaws it in about 0.2 s, and an optional idle *stop* frees its RAM while keeping its files.
- **Nothing runs unless asked.** The accessibility library loads on the first `see`, and the live view streams
  frames only while someone watches and only when the screen changed.
- **Calm pixels.** Animations, smooth scrolling, overlay scrollbars and caret blinking are off. This saves CPU
  and makes "the screen settled" detection exact.

## 4. One toolset, every agent

The tools are defined once (`minion/tools.py`) and served everywhere:

```
                 ┌─ MCP (stdio)  ── Claude Code/Desktop, Cursor, VS Code, Codex, Gemini CLI, OpenAI Agents SDK,
                 │                   LangChain, LlamaIndex, CrewAI, smolagents, Pydantic AI, ADK, AutoGen …
 minion/tools ───┼─ Function calling ── Toolkit.definitions("openai" | "anthropic" | "gemini" | …) + Toolkit.call()
                 │                      (any model API, local models via Ollama/vLLM)
                 ├─ HTTP ── /api/tools/* + /openapi.json (GPT Actions, n8n, Dify, any language)
                 ├─ TypeScript client (clients/typescript)
                 └─ CLI ── shell agents (Claude Code, Codex CLI, Aider, Open Interpreter, Goose)
 Desktop SDK ────┼─ Python (`Desktop`)
                 └─ native computer-use adapters: Claude toolset, OpenAI computer use, Gemini computer use
```

Results carry text and images in one neutral shape, with converters for each API's message format.
Errors come back as results with readable messages, so an agent loop never crashes on a bad click.

## 5. Parallel by default

Desktops are cheap, so they are made to be used several at a time: `desktop(action="create", count=N)` or
`Desktop.create_many()` starts N in parallel, `fork` clones one before a risky step, and every tool takes
`desktop=NAME`. HTTP callers can pass a session id so each agent keeps its own "current desktop".

## 6. Humans in the loop, safely

The live view (no VNC; JPEG frames over HTTP long-polling) lets a person watch and take over. An agent can
hand off with a message and wait for *Done*. The flight recorder keeps every step with a thumbnail. The
host side is pure standard-library Python with no network listeners by default. The HTTP server is
token-protected, localhost-only, and hardened against CSRF and DNS rebinding.

## 7. Small enough to trust

About 10k lines of Python with no dependencies. The in-desktop agent is copied into every desktop at creation, so the
host and desktops always agree, and upgrading never requires rebuilding images.
