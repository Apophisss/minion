# Agents & MCP

Minion ships an MCP server, so any MCP client can create and use desktops. The server has
no dependencies and speaks MCP over stdio.

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
| `--idle-freeze SECONDS` / `MINION_IDLE_FREEZE` | `600` | freeze desktops nobody used or watched for this long (`0` = never) |
| `MINION_DEFAULT_PROFILE` | `browser` | profile for `desktop(action="create")` without a profile |
| `MINION_MCP_CREATE_WAIT` | `240` | seconds `create` waits for a first-time image download before replying "still preparing" |
| `MINION_BACKEND` | `auto` | `docker`, `podman` or `local` |

## The tools

| Tool | What it does |
|---|---|
| `desktop` | `create` (profile, name, size), `list`, `profiles`, `remove`, `freeze`, `thaw`, `fork`, `snapshot`, `restore`, `replay` (HTML timeline) |
| `see` | The screen as text: windows, then the focused window's controls with `@ids`, roles, names, values, states and centers. Use `ocr=true` for canvases and images, and `full_text=true` to read long text |
| `screenshot` | A PNG. Use `marks=true` to draw `@ids`, `region=[x,y,w,h]` with `zoom=true` to magnify, and `grid=true` for a coordinate grid |
| `act` | A batch of mouse and keyboard actions: `click`, `double_click`, `right_click`, `move`, `drag`, `type`, `paste`, `fill`, `key`, `scroll`, `wait`, `wait_for`, `focus`, and more. It stops at the first failure, waits for the screen to settle, and reports what changed |
| `open` | Launches a profile app (`writer`, `calc`, `firefox`, …), a URL, a file or a command, and waits for its window |
| `run` | A shell command inside the desktop (`sudo` is available). Returns stdout, stderr and the exit code |
| `files` | `upload` / `download` between this machine and the desktop, and `read` / `write` text files |
| `view` | A live link for the human. With `message`, it hands control to the human and waits until they press Done |

The default target of every tool is the desktop the agent created or used last. Pass `desktop` to pick another.

## Tips for agents (paste into a system prompt if you like)

- **Look with `see` first.** It is exact and usually costs fewer tokens than a screenshot. Click or fill by `@id`.
  Use a screenshot when the layout, an image or a chart matters.
- **Batch actions.** For example,
  `act(actions=[{"action": "fill", "target": "@4", "text": "alice"}, {"action": "click", "target": "Sign in"}])`.
  The reply says what changed (new windows, focus, the changed region), which often makes another `see` unnecessary.
- **Use the shell for files and data.** `run` is faster and more exact than the GUI: `soffice --headless --convert-to pdf`,
  `pdftotext`, `python3 -c …`, `sudo apt-get install -y gimp`. Use the GUI for what needs eyes.
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
