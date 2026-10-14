# Claude Desktop extension (`minion.mcpb`)

An [MCP Bundle](https://github.com/modelcontextprotocol/mcpb) that installs Minion's MCP server in Claude Desktop in
one click. Users download `minion.mcpb` from
[the latest release](https://github.com/apophisss/minion/releases/latest/download/minion.mcpb) and double-click it
([docs/install.md](../../docs/install.md#claude-desktop)).

| File | What it is |
|---|---|
| `manifest.json` | The [MCPB manifest](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md) (version 0.4). The build stamps `version` from `minion/agent/__init__.py` |
| `pyproject.toml` | Makes the bundle a uv project: Python 3.11+, no dependencies, not built or installed (`package = false`) |
| `server/main.py` | The entry point: cleans up the settings Claude Desktop passes, then runs `minion mcp` |
| `icon.png` | 512×512, rendered from `minion/web/logo.svg` by `render_icon.py` |

The bundle itself is these files plus `LICENSE` and the `minion` package in `server/minion` (exactly the files the
wheel ships). Build it with:

```bash
python scripts/build_mcpb.py            # dist/minion.mcpb, and its SHA-256
python scripts/build_mcpb.py --smoke    # also start it the way Claude Desktop does and check the MCP handshake
python scripts/build_mcpb.py --stage /tmp/minion-mcpb && npx -y @anthropic-ai/mcpb@2.1.2 validate /tmp/minion-mcpb
```

The build uses only the standard library and is reproducible: sorted entries, fixed timestamps
(`SOURCE_DATE_EPOCH`, else 1980-01-01) and fixed permissions, so a commit always gives the same bytes with the same
Python. It refuses to build when the manifest's tool list differs from `minion/tools.py`, when a setting has no
default, or when the icon isn't a 512×512 PNG.

## Why a `uv` bundle that carries the source

MCPB has four server types: `node`, `python`, `binary` and, since manifest 0.4, `uv`. Claude Desktop ships Node.js
but not Python.

- **`uv`, chosen.** Claude Desktop runs `uv` for the extension: the computer's own uv if there is one, otherwise a
  copy it downloads. uv then provides a Python that matches `requires-python`, downloading it once if needed. So the
  user installs nothing but Docker. Minion has no dependencies, so the bundle carries its source (about 230 KB) and
  the first start needs no package index; it works offline once a Python is there. The extension's version is the
  bundle's version, so what users run is what they downloaded.
- **`python`** runs the user's own Python. A stock Mac has none that is 3.11+, and Claude Desktop refuses to
  install a `python` bundle as incompatible when it finds no Python at all
  ([mcpb#84](https://github.com/modelcontextprotocol/mcpb/issues/84)).
- **`uvx minion-desktop mcp`** in the manifest would need uv on the `PATH` that Claude Desktop gives servers (often
  not the case on macOS) and network access to PyPI at first start, and it would run whatever version PyPI has.
- **`binary`** (a frozen Python per OS and CPU) means building and signing an executable for every platform, for a
  pure-Python program. **`node`** would still need Python to run Minion.

Docker can't be bundled: users install Docker Desktop, OrbStack or Podman themselves. Without it, the server still
starts, and a tool call answers with how to install Docker.

## How it runs

Claude Desktop starts `uv run --directory <extension> server/main.py mcp`. uv creates `.venv` (and `uv.lock`) in the
extension's folder on first start; nothing is installed into it. `server/main.py` then:

1. stops with a clear message on Python older than 3.11 (if started some other way);
2. drops any `MINION_*` setting that arrives as an unfilled placeholder (`${user_config.…}`) and expands
   `${HOME}`, `${DESKTOP}`, `${DOCUMENTS}` and `${DOWNLOADS}`, should Claude Desktop pass a default unexpanded;
3. moves to the home folder, so that no relative path points into the extension's folder, which updates replace;
4. runs `minion mcp` from `server/minion`.

Other arguments go to the `minion` command, which helps when checking an installed extension:
`uv run --directory <extension> server/main.py doctor`.

## Settings

| Setting | Becomes | Default |
|---|---|---|
| Default desktop | `MINION_DEFAULT_PROFILE` | `browser` |
| Shared folder | `MINION_FILES_ROOT`: the `files` tool uploads only from this folder and downloads only into it | `${HOME}/Downloads` |

Every setting needs a default: Claude Desktop passes an optional setting that was never filled in as its literal
placeholder.

## Try it locally

```bash
python scripts/build_mcpb.py --smoke     # the closest thing to Claude Desktop without Claude Desktop
```

In Claude Desktop, drag `dist/minion.mcpb` onto **Settings → Extensions**. Its log is in `~/Library/Logs/Claude`
(macOS) or `%APPDATA%\Claude\logs` (Windows), in `mcp-server-*.log`.

## Release and signing

The release workflow builds the bundle after the PyPI upload and attaches it to the GitHub release as
`minion.mcpb`, so the `releases/latest/download/minion.mcpb` link always serves the newest one. The MCP Registry entry
(`server.json`) can list it as a second package with its SHA-256.

The bundle is unsigned (`mcpb info` says "Not signed"). To sign it, get a code-signing certificate and run
`npx -y @anthropic-ai/mcpb@2.1.2 sign dist/minion.mcpb --cert cert.pem --key key.pem`. Signing changes the file, so
compute the SHA-256 for `server.json` after signing.
