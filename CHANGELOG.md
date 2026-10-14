# Changelog

## 0.1.0 (unreleased)

The first release of Minion as instant desktops for AI agents.

- Desktops in Docker/Podman (or native Xvfb on Linux) that are ready in about 1.5 s, use 55–105 MB RAM idle,
  and freeze to 0% CPU automatically.
- Profiles: `base`, `browser`, `office`, `dev`, `research` and `data`, each tuned for agents (no first-run wizards,
  pop-ups, cookie banners or recovery dialogs), plus custom profiles as TOML files.
- `see`: the screen as text with clickable `@ids` from the accessibility tree, with OCR fallback, compact
  browser output and spreadsheet cells.
- Actions that wait for the screen to settle and report what changed, plus targets by `@id`, text or pixels.
- Interfaces: MCP server (8 tools), CLI, Python SDK, HTTP API, and a Claude computer-use toolset driver.
- Live view with take-over and human hand-off, a dashboard, and a flight recorder (HTML/GIF).
- Fork, snapshot and restore.
