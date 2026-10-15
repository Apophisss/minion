# Install Minion

Minion runs each desktop in a container on your computer, and your agent app reaches it over MCP. You need
**Docker running** (or OrbStack or Podman) and one of the ways below. Most take one click or one command.

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install_Minion-24BFA5?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D&quality=insiders)
[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)
[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)
[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

| You use | The fastest way |
|---|---|
| **Claude Desktop** | [Download `minion.mcpb`](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb) and double-click it. Nothing else to install ([details](#claude-desktop)) |
| **Claude Code** | `claude plugin marketplace add apophisss/minion && claude plugin install minion@minion` ([details](#claude-code)) |
| **Cursor, VS Code, Visual Studio, LM Studio, Goose, Kiro** | Its button above. The buttons start Minion with `uvx`, so they need [uv](#what-you-need) |
| **An app or a guide that uses `npx`** | The command `npx -y minion-desktop mcp` ([details](#with-npx)). It needs [uv](#what-you-need) or pipx too |
| **Several apps, or any other app** | The [one-line installer](#install-the-minion-command), which ends with [`minion setup`](#minion-setup) |
| **ChatGPT or Claude.ai on the web** | [`minion share`](#chatgpt-and-claudeai-on-the-web) |

**Contents:** [What you need](#what-you-need) · [Install the `minion` command](#install-the-minion-command) ·
[`minion setup`](#minion-setup) · [`minion connect`](#minion-connect) · [Add Minion to your app](#add-minion-to-your-app) ·
[ChatGPT and Claude.ai](#chatgpt-and-claudeai-on-the-web) · [Update and uninstall](#update-and-uninstall) ·
[Troubleshooting](#troubleshooting)

## What you need

| | macOS | Windows | Linux |
|---|---|---|---|
| **Containers** (required) | [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) or [OrbStack](https://orbstack.dev) (Colima and Podman work too) | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with WSL 2, or [Podman Desktop](https://podman-desktop.io) | [Docker Engine](https://docs.docker.com/engine/install/) or [Podman](https://podman.io/docs/installation) |
| **uv**, for the buttons and `uvx` | `brew install uv` | `winget install --id=astral-sh.uv -e` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

- [uv](https://docs.astral.sh/uv/getting-started/installation/) brings its own Python, and the one-line installers
  install uv for you. Installing with pip or pipx needs Python 3.11 or newer. The Claude Desktop extension needs
  neither: Claude Desktop runs it.
- Each profile's image is 187–707 MB (they share layers) and downloads the first time you use the profile. An idle
  desktop uses about 55–105 MB of memory.
- Apple Silicon runs the desktops natively. The `windows` profile (Wine) needs an x86-64 computer.
- Linux without containers: `MINION_BACKEND=local` runs desktops as Xvfb sessions of your own user (see the
  [FAQ](faq.md)).

## Install the `minion` command

You need it for `minion setup`, `minion connect` and the CLI; the Claude Desktop extension and the buttons don't.
For the Python SDK, `pip install minion-desktop` into your project's environment instead.

**macOS and Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh
```

**Windows** (PowerShell)

```powershell
irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex
```

The installers install uv if it's missing, install `minion` with `uv tool install` (no admin rights needed) and
finish with [`minion setup`](#minion-setup). To skip the setup, set `MINION_NO_SETUP=1`; to pass it arguments, end
the first command with `| sh -s -- --yes --profiles office`, or set `$env:MINION_SETUP_ARGS = '--yes --profiles office'`
before the second. To do it yourself:

```bash
uv tool install minion-desktop      # recommended: an isolated install, and uv brings Python 3.11+
pipx install minion-desktop         # with pipx
pip install minion-desktop          # into an active virtual environment (Python 3.11+)
uvx minion-desktop mcp              # no install: run the MCP server straight from PyPI
npx -y minion-desktop mcp           # the same through npm, for apps that expect npx (needs uv or pipx)
uv tool install git+https://github.com/apophisss/minion   # the latest code from GitHub
```

### `minion setup`

```bash
minion setup                          # check Docker, prepare the browser desktop, connect your agent apps
minion setup --profiles office,dev    # prepare other desktops instead ("none" to skip)
minion setup --yes                    # no questions: take the defaults
minion doctor                         # check the setup without changing anything
```

`minion setup` checks that Docker or Podman is installed and running (and says exactly how to fix it if not),
downloads the desktop images you pick, connects the agent apps it finds with `minion connect`, and suggests a first
prompt. Run it again whenever you like.

### `minion connect`

```bash
minion connect                  # find the agent apps on this computer and choose which to connect
minion connect cursor vscode    # or name them
minion connect --list           # every app Minion knows, its config file, and whether it's connected
minion connect --dry-run        # show the change as a diff, without making it
minion connect --remove         # take Minion out again
minion connect --compact        # connect `minion mcp --compact`: one tool, the smallest context
```

Apps: `claude-desktop`, `claude-code`, `cursor`, `vscode` (also VS Code Insiders and GitHub Copilot CLI), `devin`
(Devin Desktop, formerly Windsurf), `windsurf`, `gemini`, `codex`, `lmstudio`, `cline`, `kiro` and `zed`. `connect` adds one `minion` entry to each app's config and leaves the rest of the file as
it was, with a backup next to it. Running it twice changes nothing. A file it can't parse safely (JSON with comments,
say) is left alone, and you get the snippet to paste. It writes absolute paths, because apps started from the
desktop (Claude Desktop on macOS especially) don't see your shell's `PATH`. Each app's config file, and the
snippet to add by hand, are in [connect.md](connect.md).

## Add Minion to your app

Every app below runs the same stdio server, `uvx minion-desktop mcp` (the Claude Desktop extension carries its own
copy). The options `--compact` (one `computer` tool) and `--no-images` (text only) are in
[agents.md](agents.md#options).

### Claude Desktop

[![Download the Claude Desktop extension](https://img.shields.io/badge/Claude_Desktop-Download_extension-D97757?style=flat-square&logo=claude&logoColor=white)](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb)

1. Download [`minion.mcpb`](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb).
2. Double-click it, drag it onto Claude Desktop, or choose **Settings → Extensions → Advanced settings →
   Install Extension…**
3. Review it and select **Install**.
4. With Docker running, ask: *"Create an office desktop and write a one-page memo about otters in Writer."*

The extension carries Minion itself. Claude Desktop runs it with uv: your own uv if you have one, otherwise one it
downloads, and uv fetches Python the first time if your computer has none. So you don't install Python, uv or the
`minion` command.

**Settings** (Settings → Extensions → Minion desktops):

- **Default desktop**: the profile Claude gets when it doesn't choose one. Default: `browser`.
- **Shared folder**: the only folder on your computer that Claude can copy files into a desktop from, and the one
  where files it copies out of a desktop land. Default: your Downloads folder.

To update, download the new `minion.mcpb` and install it the same way: an extension installed from a file doesn't
update itself. On Team and Enterprise plans, owners can turn extensions off or allow only some.

Prefer a config file? Run `minion connect claude-desktop`, or open **Settings → Developer → Edit Config** and add
the entry below. Claude Desktop may not see `~/.local/bin`, where uv puts `uvx`, so put the full path from
`which uvx` in `command`.

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

### Claude Code

```bash
claude plugin marketplace add apophisss/minion && claude plugin install minion@minion   # MCP tools plus a skill
claude mcp add --scope user minion -- uvx minion-desktop mcp                             # or the MCP server alone
```

The plugin also teaches Claude to use the tools efficiently. `--scope user` makes the server available in every
project; without it, `claude mcp add` adds it to the current project only. `minion connect claude-code` does the
same.

### Cursor

[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)

The button opens Cursor's install dialog. The deeplink behind it is
`cursor://anysphere.cursor-deeplink/mcp/install?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D`
(the config is base64 JSON: `{"command":"uvx","args":["minion-desktop","mcp"]}`). By hand: `minion connect cursor`,
or add the entry from [Any other app](#any-other-app) to `~/.cursor/mcp.json`.

### VS Code and VS Code Insiders

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Minion-0098FF?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)
[![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install_Minion-24BFA5?style=flat-square)](https://insiders.vscode.dev/redirect/mcp/install?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D&quality=insiders)

The buttons go through vscode.dev, which redirects to VS Code's own install link,
`vscode:mcp/install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D`
(`vscode-insiders:` for Insiders). From a terminal:

```bash
code --add-mcp '{"name":"minion","command":"uvx","args":["minion-desktop","mcp"]}'
```

Or `minion connect vscode`. Then open Chat in agent mode and confirm that you trust the server.

### Visual Studio

[![Install in Visual Studio](https://img.shields.io/badge/Visual_Studio-Install_Minion-C16FDE?style=flat-square)](https://vs-open.link/mcp-install?%7B%22name%22%3A%22minion%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

Needs Visual Studio 2026, or Visual Studio 2022 17.14 or later, with GitHub Copilot. The link redirects to Visual
Studio's `vsweb+mcp:/install?…` handler with the same JSON as VS Code.

### LM Studio

[![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D)

Deeplink: `lmstudio://add_mcp?name=minion&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtaW5pb24tZGVza3RvcCIsIm1jcCJdfQ%3D%3D`.
By hand: `minion connect lmstudio`, or **Program → Install → Edit mcp.json**. Small local models do best with the
single `computer` tool: add `"--compact"` to `args`.

### Goose

[![Install in Goose](https://goose-docs.ai/img/extension-install-dark.svg)](https://goose-docs.ai/extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control)

Deeplink: `goose://extension?cmd=uvx&arg=minion-desktop&arg=mcp&timeout=900&id=minion&name=Minion&description=Linux%20desktops%20that%20agents%20read%20as%20text%20and%20control`.
It sets a 900-second timeout, because a first desktop downloads its image and a hand-off waits for you. By hand:
`goose configure` → **Add Extension** → **Command-line Extension**, command `uvx minion-desktop mcp`.

### Kiro

[![Add to Kiro](https://kiro.dev/images/add-to-kiro.svg)](https://kiro.dev/launch/mcp/add?name=minion&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22minion-desktop%22%2C%22mcp%22%5D%7D)

By hand: `minion connect kiro`, or add the entry from [Any other app](#any-other-app) to
`~/.kiro/settings/mcp.json`.

### Windsurf

Windsurf's Cascade has no install links. Run `minion connect windsurf`, or add the entry from
[Any other app](#any-other-app) to its `mcp_config.json` (Cascade's **…** menu → **Open MCP config file**; usually
`~/.codeium/windsurf/mcp_config.json`).

### Gemini CLI

```bash
gemini mcp add --scope user minion uvx minion-desktop mcp
```

Or `minion connect gemini`, which edits `~/.gemini/settings.json`.

### Codex

The Codex CLI, its IDE extension and the ChatGPT desktop app share `~/.codex/config.toml`:

```bash
codex mcp add minion -- uvx minion-desktop mcp
```

Codex allows 10 seconds to start a server and 60 seconds per tool call. A first start downloads Minion, and a first
desktop downloads its image, so raise both in `~/.codex/config.toml`:

```toml
[mcp_servers.minion]
command = "uvx"
args = ["minion-desktop", "mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 900
```

### Any other app

Minion is a stdio MCP server. Most apps take this JSON (VS Code's own `mcp.json` calls the key `servers`):

```json
{ "mcpServers": { "minion": { "command": "uvx", "args": ["minion-desktop", "mcp"] } } }
```

With Minion installed, `"command": "minion", "args": ["mcp"]` works too. If the app can't find `uvx` or `minion`, use
the full path (`which uvx` on macOS and Linux, `where uvx` on Windows). Agent frameworks (OpenAI Agents SDK,
LangChain, CrewAI and others) are covered in [integrations.md](integrations.md).

Minion is also in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Apophisss/minion)
as `io.github.Apophisss/minion`, for apps and directories that install from it.

### With npx

For apps and guides that expect an npx command, the npm package `minion-desktop` starts the same server. It is a
small launcher: it runs Minion from PyPI, in the same version as the npm package, with `uvx`, else `pipx run`, else
an installed `minion`. So it needs [uv](#what-you-need) or pipx, and Docker for the desktops, like every other way.

```json
{ "mcpServers": { "minion": { "command": "npx", "args": ["-y", "minion-desktop", "mcp"] } } }
```

`-y` lets npx install the package without asking. Options such as `"--compact"` go after `"mcp"`, and
`"env": {"MINION_SPEC": "git+https://github.com/apophisss/minion"}` runs another version or a fork. The launcher
also finds `uvx` in `~/.local/bin` and `~/.cargo/bin`, where uv's installer puts it, but the app has to find `npx`:
if it can't, use the full path from `which npx` (`where npx` on Windows).

## ChatGPT and Claude.ai on the web

Web apps can't start programs on your computer, so they can't run a stdio server. Instead, `minion share` starts
Minion's server with a fresh token, opens a tunnel to it and prints an HTTPS MCP URL to paste into ChatGPT,
Claude.ai or another app that connects to remote MCP servers. Ctrl+C stops sharing. The URL contains the token, so
treat it like a password, and read [remote.md](remote.md) first.

```bash
minion share
```

## Update and uninstall

| Installed with | Update | Uninstall |
|---|---|---|
| Claude Desktop extension | Install the new `minion.mcpb` | Remove Minion desktops in Settings → Extensions |
| `uvx` (buttons, most configs) | `uvx minion-desktop@latest --version`, then restart the app | `minion connect --remove`, or delete the entry |
| `npx` | Restart the app: npx looks for a newer `minion-desktop` when it starts | Delete the entry |
| uv | `uv tool upgrade minion-desktop` | `minion connect --remove`, then `uv tool uninstall minion-desktop` |
| pipx | `pipx upgrade minion-desktop` | `minion connect --remove`, then `pipx uninstall minion-desktop` |
| pip | `pip install -U minion-desktop` | `minion connect --remove`, then `pip uninstall minion-desktop` |
| Claude Code plugin | `claude plugin update minion@minion` | `claude plugin uninstall minion@minion` |

`uvx` keeps using the version it downloaded first; `@latest` checks for a newer one and refreshes uv's cache.
Desktops and their images stay until you remove them: `minion rm --all` removes the desktops, and
`docker image ls | grep minion` lists the images to `docker image rm`.

## Troubleshooting

Start with `minion doctor` (or `uvx minion-desktop doctor`): it checks Python, Docker and the images, and says how to
fix what's missing.

**The app says it can't start the server, or `spawn uvx ENOENT`.** Apps started from the desktop (Claude Desktop on
macOS especially) don't see your shell's `PATH`, so they can't find `uvx`. Run `minion connect <app>`, which writes
absolute paths, or replace `"uvx"` with the output of `which uvx`. Is uv installed at all? See
[What you need](#what-you-need).

**"Docker was not found" or "is Docker running?"** Start Docker Desktop, OrbStack or Podman and try again. On Linux,
`sudo systemctl start docker`, and add yourself to the `docker` group
([how](https://docs.docker.com/engine/install/linux-postinstall/)).

**The first desktop takes minutes.** It is downloading its image (187–707 MB). Download images ahead of time with
`minion pull office research`, or `minion setup --profiles office,research`.

**Tool calls time out.** Some apps stop waiting after a minute. Raise the app's MCP timeout to 900 seconds (Codex:
`tool_timeout_sec`, Goose: the extension's timeout); framework settings are in
[integrations.md](integrations.md#agent-frameworks-mcp).

**Claude Desktop doesn't install the extension.** Update Claude Desktop: the extension uses the MCPB 0.4 `uv` server
type. If the install fails while downloading uv (a checksum error has been seen on Windows on Arm), install uv
yourself (`winget install --id=astral-sh.uv -e`) and try again: Claude Desktop uses your uv when it finds one.
Claude Desktop's logs are in `~/Library/Logs/Claude` (macOS) and `%APPDATA%\Claude\logs` (Windows), in `mcp*.log`.

**A button does nothing.** The app must be installed, and your browser may ask before it opens another app. A
browser that blocks the request silently needs the app's own command (above) or `minion connect`.

**Where did a downloaded file go?** In Claude Desktop, to the shared folder (your Downloads by default). Elsewhere,
relative paths start wherever the app started the server, so ask for an absolute path, or set `MINION_FILES_ROOT` in
the server's `env` to confine uploads and downloads to one folder.

**Behind a proxy.** uv uses `HTTPS_PROXY`, and `UV_SYSTEM_CERTS=true` (`UV_NATIVE_TLS=true` in older uv) makes it
trust your system's certificates. Docker has its [own proxy settings](https://docs.docker.com/engine/cli/proxy/).

Still stuck? [Open an issue](https://github.com/apophisss/minion/issues) with the output of `minion doctor`.
