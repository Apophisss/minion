# Changelog

## 0.1.0 (unreleased)

The first release of Minion as instant desktops for AI agents.

- Desktops in Docker/Podman (or native Xvfb on Linux) that are ready in about 1.5 s, use 55–105 MB RAM idle,
  and freeze to 0% CPU automatically.
- Profiles: `base`, `browser`, `office`, `dev`, `research`, `data` and `windows` (Wine), each tuned for agents
  (no first-run wizards, pop-ups, cookie banners or recovery dialogs), plus custom profiles as TOML files.
  `minion-install` adds any app at runtime: apt packages, `.deb`/`.AppImage`/archive URLs, `pip:` and `npm:`.
- `see`: the screen as text with **stable** `@ids` from the accessibility tree, with OCR fallback, compact
  browser output and spreadsheet cells. `see(changes=true)` returns only what changed since the last look.
- Actions that wait for the screen to settle and report what changed, plus targets by `@id`, text or pixels.
  `observe` can add the changed UI, a full `see`, a screenshot, or a crop of the changed region.
- **Code mode** (`script`): Python runs inside the desktop with a GUI API, so loops cost one call.
- **Macros**: export the recorded session as a Python script that replays it without a model.
- **One toolset for every agent** (`minion/tools.py`): an MCP server (9 tools, or one `computer` tool with
  `--compact`), function-calling definitions for OpenAI (Chat Completions and Responses), Anthropic and Gemini
  with `Toolkit.run_calls()` to execute a model's calls, HTTP tool endpoints with OpenAPI, a CLI, a Python SDK
  and a TypeScript client.
- Native computer-use adapters for Claude (`computer_toolset_20260801` and earlier tools), OpenAI and Gemini.
- Parallel desktops: `create count=N`, `Desktop.create_many()`, `fork`, and per-session current desktops over HTTP.
- Live view with take-over and human hand-off, a dashboard, and a flight recorder (HTML/GIF/script).
- Fork, snapshot and restore.
- HTTP server hardened with a random token, CSRF and DNS-rebinding protection.
