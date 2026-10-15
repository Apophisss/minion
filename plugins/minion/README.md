# Minion for Claude Code

Minion gives Claude real Linux desktops to work in: isolated, disposable computers with a browser, LibreOffice,
development tools or Windows programs (through Wine). Claude reads each screen as text with stable `@ids`, acts
with the mouse and keyboard, opens any app by name (it is installed the first time), runs menu commands, fills
file dialogs, and reads documents as text. Nothing it does touches your own computer.

This plugin adds two things:

- **The Minion MCP server** (`uvx minion-desktop@<version> mcp`): tools to create desktops, see the screen, act,
  open apps, run commands, script the GUI, move files and hand off to you for logins.
- **The Minion skill**, which teaches Claude to work efficiently: text before screenshots, diffs instead of
  re-reading, batched actions, and code mode for anything repetitive.

**Requirements:** [Docker](https://docs.docker.com/get-docker/) (or OrbStack or Podman) and
[uv](https://docs.astral.sh/uv/). Desktop images download on first use.

**Try it:** ask Claude to "use Minion to open a browser desktop, go to wikipedia.org and tell me today's featured
article".

Documentation: https://github.com/apophisss/minion
