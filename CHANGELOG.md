# Changelog

## 1.0.0

The first release of Minion: instant desktops that any AI agent can use.

**Desktops**
- Desktops in Docker/Podman (or native Xvfb on Linux) that are ready in about 1.5 s, use 55–105 MB RAM idle,
  and freeze to 0% CPU automatically.
- Profiles: `base`, `browser`, `office`, `dev`, `research`, `data` and `windows` (Wine), each tuned for agents:
  no first-run wizards, pop-ups, cookie banners, recovery dialogs or AutoCorrect. Custom profiles are TOML files.
  `minion-install` adds any app at runtime: apt packages, `.deb`/`.AppImage`/archive URLs, `pip:` and `npm:`.

**Seeing**
- `see`: the screen as text with **stable** `@ids` from the accessibility tree, with OCR as a fallback.
- `see` covers web pages (including text inside cells, divs and inline code), editors (numbered lines with indentation),
  terminals, dropdowns with their value and options, and spreadsheet cells as `A1: value (=formula)`, with failed
  formulas as `#ERROR`.
- `see(changes=true)` returns only what changed since the last look at that window, including new terminal output and
  changed editor lines. Moves and truncation don't count as changes. Long diffs fall back to the full view and say why.

**Acting**
- Actions wait for the screen to settle, for web pages and documents to be ready, and for dialogs that appear a moment
  later. Each one reports what changed.
- Text targets match exactly: "Delete" never clicks "Delete all". A miss fails with the closest controls and their
  `@ids` instead of clicking something else.
- `fill` only types into text fields. `select` picks dropdown options. Unknown key names are errors.
- Typing in LibreOffice is lossless for any language, and its coordinates are correct from the first look.
- **Code mode** (`script`): Python runs inside the desktop with a GUI API, so loops cost one call.
- **Macros**: export the recorded session as a Python script that replays it without a model.

**Every agent**
- One toolset (`minion/tools.py`), served as:
  - an MCP server over stdio or Streamable HTTP (`/mcp`): 9 tools, or one `computer` tool with `--compact`, and
    `--no-images` for text-only clients
  - function-calling definitions for OpenAI (Chat Completions and Responses), Anthropic and Gemini, with
    `Toolkit.run_calls()`
  - HTTP tool endpoints with OpenAPI
  - a CLI and an Agent Skill (`minion skill`)
  - a Python SDK and a TypeScript client (with Vercel AI SDK tools)
- Native computer-use adapters for Claude (`computer_toolset_20260801` and earlier tools), OpenAI and Gemini.
- Verified recipes for the OpenAI Agents SDK, LangChain/LangGraph, LlamaIndex, CrewAI, smolagents, Pydantic AI,
  Google ADK and AutoGen.

**Getting started**
- One-line installers (`install.sh`, `install.ps1`), the `minion setup` wizard, and `minion connect`, which adds
  Minion to Claude Desktop, Claude Code, Cursor, VS Code, Windsurf/Devin, Gemini CLI, Codex, LM Studio, Cline and Kiro.
- One-click installs: a Claude Desktop extension (`minion.mcpb`), buttons for VS Code, Visual Studio, Cursor,
  LM Studio, Goose and Kiro, a Claude Code plugin, and an MCP Registry entry.
- `npx -y minion-desktop mcp` for MCP clients that expect an npx command: the npm package runs Minion from PyPI,
  in the same version, with uvx or pipx.
- `minion share`: a public HTTPS MCP URL (Cloudflare quick tunnel) for ChatGPT, Claude.ai and Le Chat.

**Working alongside people**
- Parallel desktops: `create count=N`, `Desktop.create_many()`, `fork`, `snapshot`/`restore`, and per-session
  current desktops.
- Live view with take-over, human hand-off (`view --ask`), a dashboard, and a flight recorder (HTML/GIF/script).
- Security: the HTTP server has a random token and CSRF and DNS-rebinding protection. Host file transfers are
  confined to one folder. Share URLs carry their own token.
