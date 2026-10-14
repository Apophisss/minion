# Connect your agent apps

`minion connect` adds Minion's MCP server to the agent apps on your computer. It supports Claude Desktop, Claude
Code, Cursor, VS Code (and GitHub Copilot CLI), Devin Desktop (formerly Windsurf), Gemini CLI, Codex, LM Studio,
Cline, Kiro and Zed. New to Minion? [install.md](install.md) covers installing it, and the one-click buttons.

```bash
minion connect              # finds your apps and asks which ones to connect
minion connect --list       # every app, its config file, and whether it is connected
minion connect cursor zed   # just these apps, even if Minion didn't find them
minion connect --dry-run    # show the changes as a diff, without making them
minion connect --remove     # take Minion out again
minion connect --compact    # connect them to `minion mcp --compact`: one tool, the smallest context
```

`minion setup`, the first-run wizard that the installers end with, connects your apps too.

## What it changes

- **One entry, named `minion`.** It is merged into each app's config, and nothing else changes: the rest of the
  file keeps its content and its layout. If the entry is there already, it is updated, and fields you added
  (such as `env`) are kept.
- **A backup first.** Before it changes a file, Minion copies it next to the original as
  `<file>.minion-<date>-<time>.bak`.
- **Idempotent.** Running it again changes nothing. `--remove` takes the entry out again.
- **Never a broken file.** If a file isn't plain JSON or valid TOML, Minion leaves it alone and prints the exact
  snippet to paste. Comments and trailing commas are the usual reason, and they are common in Zed, VS Code and
  Gemini CLI settings. Once you have pasted it, `minion connect` shows the app as connected.
- **Absolute paths.** GUI apps (Claude Desktop on macOS especially) start MCP servers with a minimal `PATH`, so
  the entry names programs by their full path:
  - If Minion is installed (`uv tool install`, pipx, or a virtual environment), the entry runs that `minion`
    command, for example `/Users/you/.local/bin/minion mcp`.
  - If you ran it with `uvx`, the entry runs uvx, for example `/Users/you/.local/bin/uvx minion-desktop mcp`.

Minion talks to Docker for every desktop. When an app starts it without Docker on its `PATH`, Minion looks in the
usual install folders: `/usr/local/bin`, `/opt/homebrew/bin`, `~/.docker/bin`,
`/Applications/Docker.app/Contents/Resources/bin`, `~/.orbstack/bin`, `~/.rd/bin` (Rancher Desktop), `/opt/podman/bin`,
and `C:\Program Files\Docker\Docker\resources\bin` on Windows.

## Each app, by hand

Each section below has the snippet to add by hand. In each one, replace `/path/to/minion` with the output of
`which minion` (macOS, Linux) or `where minion` (Windows). Without an installed Minion, use the full path of
`uvx` as the command, with the arguments `["minion-desktop", "mcp"]`.

### Claude Desktop

| OS | Config file |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`. The installer from claude.com is an MSIX package that reads `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json` first; Minion edits the file the app reads |
| Linux (beta) | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "minion": { "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

Then quit Claude Desktop completely and open it again: Cmd+Q on macOS, or **Quit** from the tray icon on Windows
and Linux. Closing the window is not enough. In developer mode, **Developer > Reload MCP Configuration** works
too. Organizations can turn off local MCP servers for their members. See
[Connect to local MCP servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

### Claude Code

Minion runs `claude mcp add --scope user minion -- /path/to/minion mcp` when the `claude` command is installed.
Otherwise it writes the same entry to `~/.claude.json` (`%USERPROFILE%\.claude.json` on Windows, or
`$CLAUDE_CONFIG_DIR/.claude.json`), under the top-level `mcpServers`:

```json
"minion": { "type": "stdio", "command": "/path/to/minion", "args": ["mcp"] }
```

Start a new `claude` session to load it. For the MCP tools plus a skill that teaches efficient use, there is also
the plugin: `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion`. See
[Claude Code and MCP](https://code.claude.com/docs/en/mcp).

### Cursor

The file is `~/.cursor/mcp.json` (`%USERPROFILE%\.cursor\mcp.json` on Windows):

```json
{
  "mcpServers": {
    "minion": { "type": "stdio", "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

Restart Cursor afterwards. See [Cursor and MCP](https://cursor.com/docs/mcp).

### VS Code and GitHub Copilot CLI

Since version 1.140, VS Code reads servers for all workspaces from `~/.copilot/mcp-config.json`
(`%USERPROFILE%\.copilot\mcp-config.json` on Windows, or `$COPILOT_HOME/mcp-config.json`). VS Code Insiders and
GitHub Copilot CLI read the same file. VS Code calls its older user-profile `mcp.json` deprecated, so this is the
file Minion writes:

```json
{
  "mcpServers": {
    "minion": { "type": "stdio", "command": "/path/to/minion", "args": ["mcp"], "tools": ["*"] }
  }
}
```

VS Code notices the change by itself, and it asks you to trust the server the first time it starts.

VS Code 1.139 and older read only the user-profile `mcp.json` (**MCP: Open User Configuration**). In that file the
entry goes under `"servers"`: `"minion": {"type": "stdio", "command": "/path/to/minion", "args": ["mcp"]}`. The
install buttons and `code --add-mcp` also write that file, and `code --add-mcp` rewrites all of it, losing any
comments. Keep Minion in one of the two files only, or VS Code shows it twice. `minion connect` warns you if both
files have it. See [MCP servers in VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers),
[VS Code 1.140](https://code.visualstudio.com/updates/v1_140) and
[Copilot CLI and MCP](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers).

### Devin Desktop and Windsurf

On June 2, 2026, Windsurf became Devin Desktop. Devin Desktop and the Devin CLI read
`~/.config/devin/mcp_config.json` (`%APPDATA%\devin\mcp_config.json` on Windows). When that folder exists, Minion
connects Devin. It connects Windsurf's own `~/.codeium/windsurf/mcp_config.json` only when Devin is absent,
because Devin also imports Windsurf's servers. Both files use the same format:

```json
{
  "mcpServers": {
    "minion": { "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

Restart Devin Desktop or start a new `devin` session. With Windsurf, press refresh in Cascade's MCP panel. See
[Devin configuration files](https://docs.devin.ai/cli/reference/configuration/config-file).

### Gemini CLI

The file is `~/.gemini/settings.json` (`%USERPROFILE%\.gemini\settings.json` on Windows, or
`$GEMINI_CLI_HOME/.gemini/settings.json`). The entry goes in the top-level `mcpServers`:

```json
"mcpServers": {
  "minion": { "command": "/path/to/minion", "args": ["mcp"] }
}
```

Start a new `gemini` session, or run `/mcp reload`. Gemini Code Assist's agent mode in VS Code reads the same
file. In a folder you haven't trusted, Gemini CLI doesn't start MCP servers. See
[Gemini CLI and MCP servers](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md).

### Codex

The file is `~/.codex/config.toml` (`%USERPROFILE%\.codex\config.toml` on Windows, or `$CODEX_HOME/config.toml`).
The Codex CLI, the IDE extension and the ChatGPT desktop app share it:

```toml
[mcp_servers.minion]
command = "/path/to/minion"
args = ["mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 900
```

By default, Codex gives a server 10 seconds to start and a tool 60 seconds to finish. A first `uvx` download, a
desktop's first image download, or a hand-off that waits for you in the live view takes longer. Minion adds the two
timeouts when they are missing, and it keeps values you set. Start a new `codex` session, or restart the app or
the IDE extension. See [Codex and MCP](https://learn.chatgpt.com/docs/extend/mcp).

### LM Studio

The file is `~/.lmstudio/mcp.json` (`%USERPROFILE%\.lmstudio\mcp.json` on Windows). If LM Studio keeps its files
elsewhere, `~/.lmstudio-home-pointer` names that folder, and Minion follows it.

```json
{
  "mcpServers": {
    "minion": { "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

LM Studio loads the servers as soon as the file is saved. See [LM Studio and MCP](https://lmstudio.ai/blog/mcp).

### Cline

Cline 4 (in VS Code, JetBrains and its CLI) shares `~/.cline/data/settings/cline_mcp_settings.json`. The
`CLINE_MCP_SETTINGS_PATH` variable can move it.

```json
{
  "mcpServers": {
    "minion": { "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

Cline notices the change by itself. See [Cline and MCP](https://docs.cline.bot/mcp/mcp-overview).

### Kiro

The file is `~/.kiro/settings/mcp.json` (or `$KIRO_HOME/settings/mcp.json`):

```json
{
  "mcpServers": {
    "minion": { "command": "/path/to/minion", "args": ["mcp"] }
  }
}
```

Kiro applies the change when the file is saved. See [Kiro MCP configuration](https://kiro.dev/docs/mcp/configuration/).

### Zed

| OS | Config file |
|---|---|
| macOS, Linux | `~/.config/zed/settings.json` (Linux: `$XDG_CONFIG_HOME/zed/settings.json` if set) |
| Windows | `%APPDATA%\Zed\settings.json` |

Zed's settings file usually starts with comments, so Minion prints this snippet for you to paste inside the outer
`{ }`:

```json
"context_servers": {
  "minion": { "command": "/path/to/minion", "args": ["mcp"] }
}
```

Zed reloads its settings by itself. See [Zed and MCP](https://zed.dev/docs/ai/mcp).

### Goose

Goose keeps its settings in YAML, which Minion doesn't edit. Add this under `extensions:` in
`~/.config/goose/config.yaml` (`%APPDATA%\Block\goose\config\config.yaml` on Windows), then restart Goose:

```yaml
extensions:
  minion:
    name: minion
    type: stdio
    enabled: true
    cmd: /path/to/minion
    args: [mcp]
    timeout: 900
```

See [Goose configuration files](https://goose-docs.ai/docs/guides/config-files/).

### Anything else

Any MCP client can start Minion as a stdio server: the command `/path/to/minion` with the argument `mcp`. For
agent frameworks, see [integrations.md](integrations.md).

## Troubleshooting

- **The tools don't show up.** Restart the app as described above, then check `minion connect --list`. Run the
  entry's command yourself, for example `/path/to/minion mcp`: it should start and wait quietly (press Ctrl+C).
- **"Docker was not found" from inside an app.** Minion looks for Docker in the usual folders (listed above). If
  yours is elsewhere, add `"env": {"MINION_DOCKER": "/full/path/to/docker"}` to the entry.
- **Docker reached through `DOCKER_HOST`** (a Colima or Podman socket, a remote host). Apps don't see the
  variables of your shell, so add it to the entry: `"env": {"DOCKER_HOST": "unix:///Users/you/.colima/default/docker.sock"}`.
  For Codex, add a `[mcp_servers.minion.env]` table. Docker contexts (`docker context use`) need nothing extra.
  `minion connect` keeps these fields when it updates the entry.
- **Undo.** `minion connect --remove`, or copy back a `.minion-*.bak` file.
