"""`minion connect`: add Minion's MCP server to the agent apps on this computer.

Every app keeps its MCP servers in a config file, and `connect` merges one entry, "minion", into it:

- Everything else in the file stays as it is, and a backup goes next to the file before any change.
- Running it again changes nothing, and `--remove` takes the entry out again.
- A file that is not plain JSON or TOML (JSON with comments, say) is never rewritten. You get the exact
  snippet to paste instead.

The entry starts Minion by absolute path, because GUI apps (Claude Desktop on macOS especially) start MCP
servers with a minimal PATH.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .errors import MinionError, NotFound

NAME = "minion"  # the server's name in every app's config
DOCS = "https://github.com/apophisss/minion/blob/main/docs/connect.md"


# -- how apps should start Minion ----------------------------------------------
@dataclass
class Launch:
    command: str
    args: list[str]
    how: str = ""  # "installed", "uvx" or "python"

    def __str__(self) -> str:
        return cmdline([self.command, *self.args])


def cmdline(parts: list[str]) -> str:
    """A command as you would type it in this OS's shell (for showing, not for running)."""
    return subprocess.list2cmdline(parts) if os.name == "nt" else " ".join(shlex.quote(p) for p in parts)


def launcher(compact: bool = False) -> Launch:
    """The command that starts this copy of Minion's MCP server, with absolute paths.

    From uvx's throwaway cache it is uvx itself (the cache can be cleaned at any time). From an install that
    stays put (`uv tool install`, pipx, a venv) it is that install's `minion` executable."""
    extra = ["--compact"] if compact else []
    if _in_uv_cache(sys.prefix):
        spec = _source_spec()
        args = (["--from", spec, "minion"] if spec else ["minion-desktop"]) + ["mcp", *extra]
        return Launch(_find_uvx() or "uvx", args, "uvx")
    exe = _minion_executable(sys.argv[0] if sys.argv else "", sys.executable)
    if exe:
        return Launch(exe, ["mcp", *extra], "installed")
    return Launch(sys.executable, ["-m", "minion", "mcp", *extra], "python")


def _in_uv_cache(prefix: str) -> bool:
    """uvx runs tools from environments in uv's cache: ~/.cache/uv/archive-v0/<id> and the like."""
    return any(re.fullmatch(r"archive-v\d+", part.lower()) for part in Path(prefix).parts)


def _source_spec() -> str | None:
    """A `uvx --from` spec when this copy came from git or a folder rather than PyPI."""
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        raw = distribution("minion-desktop").read_text("direct_url.json")
        info = json.loads(raw) if raw else {}
    except (PackageNotFoundError, ValueError, OSError):
        return None
    url, vcs = info.get("url", ""), info.get("vcs_info")
    if not url:
        return None
    if vcs:
        rev = vcs.get("requested_revision") or vcs.get("commit_id")
        return f"{vcs.get('vcs', 'git')}+{url}" + (f"@{rev}" if rev else "")
    if url.startswith("file:"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        return url2pathname(urlparse(url).path)
    return url


def _find_uvx() -> str | None:
    exe = "uvx.exe" if os.name == "nt" else "uvx"
    places = [Path(os.environ["UV"]).with_name(exe)] if os.environ.get("UV") else []  # uv sets UV to itself
    found = shutil.which("uvx")
    if found:
        places.append(Path(found))
    home = _home()
    places += [home / ".local" / "bin" / exe, home / ".cargo" / "bin" / exe]
    places += [Path("/opt/homebrew/bin/uvx"), Path("/usr/local/bin/uvx")]
    for path in places:
        if path.is_file():
            return str(path.absolute())
    return None


def _minion_executable(argv0: str, python: str) -> str | None:
    """The `minion` command that is running now (as the user typed it, e.g. ~/.local/bin/minion), or the one
    next to this Python."""
    exe = ".exe" if os.name == "nt" else ""
    places = []
    if argv0 and Path(argv0).stem.lower() in ("minion", "minion-desktop"):
        places += [argv0, argv0 + exe] if exe and not argv0.lower().endswith(exe) else [argv0]
    places.append(str(Path(python).parent / f"minion{exe}"))
    for path in places:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return os.path.abspath(path)
    return None


# -- where apps keep their config ------------------------------------------------
def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _env_dir(var: str, default: Path) -> Path:
    value = os.environ.get(var)
    return Path(value).expanduser() if value else default


def _app_data(folder: str) -> Path:
    """Where desktop (Electron) apps keep their settings: Application Support, %APPDATA% or ~/.config."""
    if sys.platform == "win32":
        return _env_dir("APPDATA", _home() / "AppData" / "Roaming") / folder
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / folder
    return _env_dir("XDG_CONFIG_HOME", _home() / ".config") / folder


def _claude_desktop() -> Path:
    name = "claude_desktop_config.json"
    if sys.platform != "win32":
        return _app_data("Claude") / name
    # The installer from claude.com is an MSIX package: Windows redirects its %APPDATA% into the package's
    # LocalCache and reads a file there first. Use the copy the app reads, else the folder it uses.
    packages = _env_dir("LOCALAPPDATA", _home() / "AppData" / "Local") / "Packages"
    folders = [*sorted(packages.glob("Claude_*/LocalCache/Roaming/Claude")), _app_data("Claude")]
    for folder in folders:
        if (folder / name).is_file():
            return folder / name
    return next((f for f in folders if f.is_dir()), folders[-1]) / name


def _claude_code() -> Path:
    return _env_dir("CLAUDE_CONFIG_DIR", _home()) / ".claude.json"


def _codex() -> Path:
    return _env_dir("CODEX_HOME", _home() / ".codex") / "config.toml"


def _xdg_config() -> Path:
    if sys.platform == "win32":
        return _env_dir("APPDATA", _home() / "AppData" / "Roaming")
    return _env_dir("XDG_CONFIG_HOME", _home() / ".config")


def _copilot() -> Path:
    """VS Code (1.140 and newer) and GitHub Copilot CLI read user-level MCP servers from this file. VS Code calls its
    older user-profile mcp.json deprecated."""
    return _env_dir("COPILOT_HOME", _home() / ".copilot") / "mcp-config.json"


def _devin() -> Path:
    """Devin Desktop (Windsurf's successor) and the Devin CLI share this file."""
    return _xdg_config() / "devin" / "mcp_config.json"


def _zed() -> Path:
    if sys.platform == "win32":
        return _app_data("Zed") / "settings.json"
    if sys.platform == "darwin":  # Zed uses ~/.config on macOS too
        return _home() / ".config" / "zed" / "settings.json"
    return _xdg_config() / "zed" / "settings.json"


def _lmstudio() -> Path:
    """LM Studio's home: the folder named in ~/.lmstudio-home-pointer, else ~/.cache/lm-studio (older
    installs), else ~/.lmstudio. The same order as LM Studio's own SDK."""
    home = _home()
    try:
        pointed = (home / ".lmstudio-home-pointer").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        pointed = ""
    if pointed:
        return Path(pointed).expanduser() / "mcp.json"
    legacy = home / ".cache" / "lm-studio"
    return (legacy if legacy.is_dir() else home / ".lmstudio") / "mcp.json"


def _cline() -> Path:
    """Cline 4 (VS Code, JetBrains and its CLI) keeps one shared MCP settings file."""
    if os.environ.get("CLINE_MCP_SETTINGS_PATH"):
        return Path(os.environ["CLINE_MCP_SETTINGS_PATH"]).expanduser()
    data = _env_dir("CLINE_DATA_DIR", _env_dir("CLINE_DIR", _home() / ".cline") / "data")
    return data / "settings" / "cline_mcp_settings.json"


def claude_cli() -> str | None:
    """The `claude` command: on PATH, or where its native installer puts it."""
    found = shutil.which("claude")
    if found:
        return found
    exe = "claude.exe" if os.name == "nt" else "claude"
    for path in (_home() / ".local" / "bin" / exe, _home() / ".claude" / "local" / exe):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _has(*parts: str) -> Callable[[Path], bool]:
    """Detect an app by a folder in the home directory, e.g. ~/.cursor."""
    return lambda _path: _home().joinpath(*parts).is_dir()


def _folder_exists(path: Path) -> bool:
    return path.parent.is_dir()


def _or_command(name: str, detect: Callable[[Path], bool]) -> Callable[[Path], bool]:
    return lambda path: detect(path) or shutil.which(name) is not None


def _claude_desktop_found(path: Path) -> bool:
    if path.parent.is_dir():
        return True
    if sys.platform == "darwin":
        return Path("/Applications/Claude.app").is_dir() or (_home() / "Applications" / "Claude.app").is_dir()
    return sys.platform.startswith("linux") and shutil.which("claude-desktop") is not None


def _vscode_found(path: Path) -> bool:
    profiles = [_app_data(flavor) / "User" for flavor in ("Code", "Code - Insiders")]
    commands = ("code", "code-insiders", "copilot")
    return path.parent.is_dir() or any(p.is_dir() for p in profiles) or any(shutil.which(c) for c in commands)


def _devin_found(_path: Path | None = None) -> bool:
    return _devin().parent.is_dir() or shutil.which("devin") is not None


def _windsurf_found(_path: Path) -> bool:
    """Windsurf became Devin Desktop, which reads its own file (and imports Windsurf's): one entry is enough."""
    return _home().joinpath(".codeium", "windsurf").is_dir() and not _devin_found()


def _cline_found(path: Path) -> bool:
    return path.parent.is_dir() or _env_dir("CLINE_DIR", _home() / ".cline").is_dir()


def _plain(launch: Launch) -> dict:
    return {"command": launch.command, "args": list(launch.args)}


def _stdio(launch: Launch) -> dict:
    return {"type": "stdio", **_plain(launch)}


def _copilot_entry(launch: Launch) -> dict:
    return {**_stdio(launch), "tools": ["*"]}  # Copilot's default (every tool), spelled out


def _opencode() -> Path:
    """opencode's global config (opencode.jsonc if that is the one in use)."""
    folder = _env_dir("XDG_CONFIG_HOME", _home() / ".config") / "opencode"
    jsonc = folder / "opencode.jsonc"
    return jsonc if jsonc.exists() and not (folder / "opencode.json").exists() else folder / "opencode.json"


def _opencode_entry(launch: Launch) -> dict:  # opencode 1.x: mcp.<name>
    return {"type": "local", "command": [launch.command, *launch.args], "enabled": True}


def _opencode_v2_entry(launch: Launch) -> dict:  # opencode 2: mcp.servers.<name>, connected unless "disabled"
    return {"type": "local", "command": [launch.command, *launch.args]}


def _opencode_variant(text: str | None) -> tuple[str, Callable[[Launch], dict]]:
    """opencode 2 keeps servers under mcp.servers, 1.x under mcp: the config, or else the installed version, says which."""
    try:
        data = json.loads(_without_comments((text or "").lstrip(BOM)) or "{}")
        if isinstance(data.get("mcp"), dict) and isinstance(data["mcp"].get("servers"), dict):
            return "mcp.servers", _opencode_v2_entry
    except (ValueError, AttributeError):
        pass
    cli = shutil.which("opencode")
    if cli:
        try:
            out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=20).stdout
            if re.match(r"\s*v?([2-9]|\d{2,})\.", out):
                return "mcp.servers", _opencode_v2_entry
        except (OSError, subprocess.SubprocessError):
            pass
    return "mcp", _opencode_entry


def _openclaw_entry(launch: Launch) -> dict:
    # A first uvx download and long tool calls (installs, hand-offs) need more than its default timeouts.
    return {**_plain(launch), "requestTimeoutMs": 900_000, "connectionTimeoutMs": 60_000}


@dataclass(frozen=True)
class App:
    id: str
    name: str
    path: Callable[[], Path]  # its config file on this OS
    found: Callable[[Path], bool]  # is the app on this computer?
    reload: str  # what to do so the app loads the change
    key: str = "mcpServers"  # JSON: the object that holds the servers ("mcp.servers": nested)
    entry: Callable[[Launch], dict] = _plain
    kind: str = "json"  # "json", "toml" (Codex), or an app with its own `mcp add` CLI: "claude-code", "openclaw"
    variant: Callable[[str | None], tuple[str, Callable[[Launch], dict]]] | None = None  # format by version


# Where each app keeps its servers, and the format, are cited per app in docs/connect.md.
APPS: list[App] = [
    App(
        "claude-desktop",
        "Claude Desktop",
        _claude_desktop,
        _claude_desktop_found,
        "quit it completely (Cmd+Q on macOS, Quit from the tray icon on Windows and Linux) and open it again",
    ),
    App(
        "claude-code",
        "Claude Code",
        _claude_code,
        lambda path: path.is_file() or _home().joinpath(".claude").is_dir() or claude_cli() is not None,
        "start a new `claude` session",
        entry=_stdio,
        kind="claude-code",
    ),
    App("cursor", "Cursor", lambda: _home() / ".cursor" / "mcp.json", _has(".cursor"), "restart Cursor", entry=_stdio),
    App(
        "vscode",
        "VS Code",
        _copilot,
        _vscode_found,
        "VS Code 1.140+ (and Insiders) loads it by itself, as does GitHub Copilot CLI; allow Minion when asked",
        entry=_copilot_entry,
    ),
    App("devin", "Devin Desktop", _devin, _devin_found, "restart Devin Desktop, or start a new `devin` session"),
    App(
        "windsurf",
        "Windsurf",
        lambda: _home() / ".codeium" / "windsurf" / "mcp_config.json",
        _windsurf_found,
        "press Refresh in Cascade's MCP panel, or restart Windsurf",
    ),
    App(
        "gemini",
        "Gemini CLI",
        lambda: _env_dir("GEMINI_CLI_HOME", _home()) / ".gemini" / "settings.json",
        _or_command("gemini", _folder_exists),
        "start a new `gemini` session, or run /mcp reload",
    ),
    App(
        "codex",
        "Codex",
        _codex,
        _or_command("codex", _folder_exists),
        "start a new `codex` session; in the ChatGPT app or the IDE extension, restart it",
        kind="toml",
    ),
    App("lmstudio", "LM Studio", _lmstudio, _folder_exists, "it loads mcp.json as soon as the file is saved"),
    App("cline", "Cline", _cline, _cline_found, "it reloads its MCP settings by itself"),
    App(
        "kiro",
        "Kiro",
        lambda: _env_dir("KIRO_HOME", _home() / ".kiro") / "settings" / "mcp.json",
        lambda path: path.parent.parent.is_dir(),
        "it applies mcp.json changes when the file is saved",
    ),
    App("zed", "Zed", _zed, _folder_exists, "it reloads its settings by itself", key="context_servers"),
    App(
        "opencode",
        "opencode",
        _opencode,
        _or_command("opencode", _folder_exists),
        "start a new `opencode` session",
        key="mcp",
        entry=_opencode_entry,
        variant=_opencode_variant,
    ),
    App(
        "openclaw",
        "OpenClaw",
        lambda: _env_dir("OPENCLAW_HOME", _home() / ".openclaw") / "openclaw.json",
        _or_command("openclaw", _folder_exists),
        "it picks up new MCP servers on the next turn (or run `openclaw mcp reload`)",
        key="mcp.servers",
        entry=_openclaw_entry,
        kind="openclaw",
    ),
]
# Codex gives a server 10 s to start and a tool 60 s to finish: too little for a first uvx download, an image pull
# or a hand-off that waits for a person. Added when missing; values you set are kept.
CODEX_EXTRA = {"startup_timeout_sec": 60, "tool_timeout_sec": 900}

_ALIASES = {
    "code": "vscode",
    "insiders": "vscode",
    "vscodeinsiders": "vscode",
    "copilot": "vscode",
    "copilotcli": "vscode",
    "githubcopilot": "vscode",
    "geminicli": "gemini",
    "codexcli": "codex",
    "devindesktop": "devin",
}


def find_app(name: str) -> App:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    key = _ALIASES.get(key, key)
    for app in APPS:
        if key in (re.sub(r"[^a-z0-9]", "", app.id), re.sub(r"[^a-z0-9]", "", app.name.lower())):
            return app
    raise NotFound(f"unknown app {name!r}. Apps: {', '.join(a.id for a in APPS)}")


def detected() -> list[App]:
    return [app for app in APPS if app.found(app.path())]


# -- editing config files ------------------------------------------------------------
BOM = chr(0xFEFF)  # the byte-order mark some Windows editors add


class Unparseable(ValueError):
    """The file is not plain JSON/TOML, or not in a shape Minion can edit safely: it is left alone."""


def _unique(pairs: list) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"the key {k!r} appears twice")
        out[k] = v
    return out


def _load_json(text: str | None) -> dict:
    body = (text or "").lstrip(BOM)
    if not body.strip():
        return {}
    try:
        data = json.loads(body, object_pairs_hook=_unique)
    except ValueError as e:
        if re.search(r"^\s*(//|/\*)", body, re.M):
            raise Unparseable("it has comments") from e
        raise Unparseable(f"it isn't plain JSON ({e})") from e
    if not isinstance(data, dict):
        raise Unparseable("it isn't a JSON object")
    return data


def _dump_json(data: dict, like: str | None) -> str:
    """The whole file rewritten (the fallback): same indent, line endings and byte-order mark."""
    like = like or ""
    text = json.dumps(data, indent=_indent(like), ensure_ascii=False) + "\n"
    if "\r\n" in like:
        text = text.replace("\n", "\r\n")
    return (BOM if like.startswith(BOM) else "") + text


# Edits in place: the text is valid JSON (it was just parsed), so finding where each member starts and ends
# is simple. Only the lines of the "minion" entry change, and the result is parsed again to check it.
def _indent(text: str) -> str:
    m = re.search(r'^([ \t]+)"', text, re.M)
    return m.group(1) if m else "  "


def _ws(t: str, i: int) -> int:
    while i < len(t) and t[i] in " \t\r\n" + BOM:
        i += 1
    return i


def _string_end(t: str, i: int) -> int:
    i += 1
    while t[i] != '"':
        i += 2 if t[i] == "\\" else 1
    return i + 1


def _value_end(t: str, i: int) -> int:
    if t[i] == '"':
        return _string_end(t, i)
    if t[i] in "{[":
        close = "}" if t[i] == "{" else "]"
        i = _ws(t, i + 1)
        while t[i] != close:
            if close == "}":
                i = _ws(t, _ws(t, _string_end(t, i)) + 1)  # past the key and ':'
            i = _ws(t, _value_end(t, i))
            if t[i] == ",":
                i = _ws(t, i + 1)
        return i + 1
    return re.compile(r"[^\s,\]}]*").match(t, i).end()  # number, true, false, null


def _members(t: str, i: int) -> tuple[list[tuple[str, int, int, int]], int]:
    """The members of the object at t[i] as (key, key start, value start, value end), and its `}`."""
    out = []
    i = _ws(t, i + 1)
    while t[i] != "}":
        key_end = _string_end(t, i)
        start = _ws(t, _ws(t, key_end) + 1)
        end = _value_end(t, start)
        out.append((json.loads(t[i:key_end]), i, start, end))
        i = _ws(t, end)
        if t[i] == ",":
            i = _ws(t, i + 1)
    return out, i


def _pad(t: str, i: int) -> str | None:
    """The indentation before t[i] if it starts its line, else None."""
    pad = t[t.rfind("\n", 0, i) + 1 : i].replace(BOM, "")
    return pad if not pad.strip(" \t") else None


def _block(value: object, pad: str, unit: str, nl: str, depth: int) -> str:
    """JSON with one member per line for `depth` levels of objects, then inline (like ["mcp"])."""
    if depth <= 0 or not isinstance(value, dict) or not value:
        return json.dumps(value, ensure_ascii=False)
    rows = [
        f"{pad}{unit}{json.dumps(k, ensure_ascii=False)}: {_block(v, pad + unit, unit, nl, depth - 1)}"
        for k, v in value.items()
    ]
    return "{" + nl + ("," + nl).join(rows) + nl + pad + "}"


def _json_put(t: str, keys: list[str], value: object) -> str:
    """`t` with data[keys[0]][keys[1]]... set to `value`, changing only those lines."""
    nl, unit = ("\r\n" if "\r\n" in t else "\n"), _indent(t)
    inline = "\n" not in t.strip()  # a one-line file stays one line
    obj = _ws(t, 0)
    if obj >= len(t):  # an empty file
        for key in reversed(keys):
            value = {key: value}
        return _block(value, "", unit, nl, len(keys) + 1) + nl
    for n, key in enumerate(keys):
        members, close = _members(t, obj)
        found = next((m for m in members if m[0] == key), None)
        rest = keys[n + 1 :]
        if found and rest:
            obj = found[2]
            continue
        if found:  # replace the value
            pad = _pad(t, found[1])
            text = json.dumps(value, ensure_ascii=False) if inline or pad is None else _block(value, pad, unit, nl, 1)
            return t[: found[2]] + text + t[found[3] :]
        for k in reversed(rest):
            value = {k: value}
        member = json.dumps(key, ensure_ascii=False) + ": "
        pad = _pad(t, members[0][1]) if members else None
        if members and (inline or pad is None):  # members on one line: add one more
            return t[: members[-1][3]] + ", " + member + json.dumps(value, ensure_ascii=False) + t[members[-1][3] :]
        if members:
            return (
                t[: members[-1][3]]
                + ","
                + nl
                + pad
                + member
                + _block(value, pad, unit, nl, len(rest) + 1)
                + t[members[-1][3] :]
            )
        if inline:  # an empty object
            return t[:obj] + json.dumps({key: value}, ensure_ascii=False) + t[close + 1 :]
        line = t[t.rfind("\n", 0, obj) + 1 : obj]
        pad = line[: len(line) - len(line.lstrip(" \t" + BOM))].replace(BOM, "")
        return t[:obj] + _block({key: value}, pad, unit, nl, len(rest) + 2) + t[close + 1 :]
    raise ValueError("no keys")


def _json_drop(t: str, keys: list[str]) -> str:
    """`t` without data[keys[0]][keys[1]]... (an object it empties stays, as `{}`)."""
    obj = _ws(t, 0)
    for key in keys:
        members, close = _members(t, obj)
        i = next(i for i, m in enumerate(members) if m[0] == key)
        parent, obj = obj, members[i][2]
    obj = parent
    if len(members) == 1:
        return t[: obj + 1] + t[close:]
    if i > 0:  # from the end of the previous member: its comma goes too
        return t[: members[i - 1][3]] + t[members[i][3] :]
    return t[: members[0][1]] + t[members[1][1] :]


def _same(old: object, entry: dict) -> bool:
    return isinstance(old, dict) and all(old.get(k) == v for k, v in entry.items())


def _edited(text: str | None, expected: dict, edit: Callable[[str], str]) -> str:
    """The in-place edit if it gives exactly `expected`, else the whole file rewritten."""
    try:
        new = edit(text or "")
        if _load_json(new) == expected:
            return new
    except (ValueError, IndexError, StopIteration, Unparseable):
        pass
    return _dump_json(expected, text)


def _servers(data: dict, key: str) -> object:
    """data["mcp"]["servers"] for the key "mcp.servers" ({} if missing)."""
    obj: object = data
    for k in key.split("."):
        if not isinstance(obj, dict):
            raise Unparseable(f'its "{key}" is not an object')
        obj = obj.get(k, {})
    return obj


def json_set(text: str | None, key: str, name: str, entry: dict) -> tuple[str | None, bool]:
    """Add or update `key.name` (keeping fields the entry doesn't set, like "env"). The key may be a
    path ("mcp.servers"). Returns the new text (None if nothing changes) and whether an entry was there."""
    data = _load_json(text)
    servers = _servers(data, key)
    if not isinstance(servers, dict):
        raise Unparseable(f'its "{key}" is not an object')
    old = servers.get(name)
    if _same(old, entry):
        return None, True
    value = {**old, **entry} if isinstance(old, dict) else dict(entry)
    expected = copy.deepcopy(data)
    target = expected
    for k in key.split("."):
        target = target.setdefault(k, {})
    target[name] = value
    return _edited(text, expected, lambda t: _json_put(t, [*key.split("."), name], value)), old is not None


def json_remove(text: str | None, key: str, name: str) -> tuple[str | None, bool]:
    if text is None:
        return None, False
    data = _load_json(text)
    servers = _servers(data, key)
    if not isinstance(servers, dict) or name not in servers:
        return None, False
    expected = copy.deepcopy(data)
    target = expected
    for k in key.split("."):
        target = target[k]
    del target[name]
    return _edited(text, expected, lambda t: _json_drop(t, [*key.split("."), name])), True


_TABLE = re.compile(r"^[ \t]*\[")  # a [table] or [[array]] header


def _load_toml(text: str | None) -> dict:
    try:
        return tomllib.loads((text or "").lstrip(BOM))
    except tomllib.TOMLDecodeError as e:
        raise Unparseable(f"it isn't valid TOML ({e})") from e


def _toml_header(name: str, sub: bool = False) -> re.Pattern:
    """`[mcp_servers.NAME]`, or with `sub` its sub-tables such as `[mcp_servers.NAME.env]`."""
    q = re.escape(name)
    end = r"[ \t]*\." if sub else r"[ \t]*\][ \t]*(#.*)?$"
    return re.compile(rf"""^[ \t]*\[[ \t]*mcp_servers[ \t]*\.[ \t]*(?:{q}|"{q}"|'{q}'){end}""")


def _brackets(line: str) -> int:
    """How many `[` a TOML line leaves open (strings and comments skipped)."""
    depth, quote, i = 0, "", 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch in "[]":
            depth += 1 if ch == "[" else -1
        i += 1
    return depth


def _toml_set_lines(rows: list[str], start: int, end: int, lines: dict[str, str], nl: str) -> list[str]:
    """Replace (or add) `key = value` lines in the table body rows[start+1:end]."""
    body = rows[start + 1 : end]
    insert_at = 0
    for key, line in lines.items():
        i = next((i for i, r in enumerate(body) if re.match(rf"^[ \t]*{key}[ \t]*=", r)), None)
        if i is None:
            body.insert(insert_at, line + nl)
            insert_at += 1
            continue
        j, depth = i + 1, _brackets(body[i].split("=", 1)[1])
        while depth > 0 and j < len(body):
            depth += _brackets(body[j])
            j += 1
        body[i:j] = [line + nl]
        insert_at = i + 1
    return rows[: start + 1] + body + rows[end:]


def _check_toml(new: str, expected: dict) -> None:
    """The edited text must read back as exactly the expected config (an empty [mcp_servers] aside)."""
    try:
        parsed = _load_toml(new)
    except Unparseable:
        parsed = None
    for d in (expected, parsed or {}):
        if d.get("mcp_servers") == {}:
            del d["mcp_servers"]
    if parsed != expected:
        raise Unparseable("Minion couldn't edit it safely (an inline mcp_servers table, say)")


def _toml_lines(values: dict) -> dict[str, str]:
    return {k: f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in values.items()}  # JSON strings are TOML


def toml_set(
    text: str | None, name: str, command: str, args: list[str], extra: dict | None = None
) -> tuple[str | None, bool]:
    """Add or update `[mcp_servers.NAME]` by editing text (Python can read TOML but not write it). `extra` keys
    are added when missing and never overwritten. The result is parsed again and must equal the old config plus
    this change, or the file is left alone."""
    data = _load_toml(text)
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict) or not isinstance(servers.get(name, {}), dict):
        raise Unparseable('its "mcp_servers" is not a table of tables')
    old = servers.get(name)
    want = {"command": command, "args": list(args)}
    want.update({k: v for k, v in (extra or {}).items() if k not in (old or {})})
    if _same(old, want):
        return None, True
    text = text or ""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _toml_lines(want)
    if old is None:
        head = text if not text or text.endswith("\n") else text + nl
        head += nl if head.strip() else ""
        new = head + f"[mcp_servers.{name}]{nl}" + "".join(line + nl for line in lines.values())
    else:
        rows = text.splitlines(keepends=True)
        header = _toml_header(name)
        start = next((i for i, r in enumerate(rows) if header.match(r.rstrip("\r\n"))), None)
        if start is None:
            raise Unparseable(f"its {name} entry isn't a [mcp_servers.{name}] table")
        end = next((i for i in range(start + 1, len(rows)) if _TABLE.match(rows[i])), len(rows))
        new = "".join(_toml_set_lines(rows, start, end, lines, nl))
    expected = copy.deepcopy(data)
    expected.setdefault("mcp_servers", {}).setdefault(name, {}).update(want)
    _check_toml(new, expected)
    return new, old is not None


def toml_remove(text: str | None, name: str) -> tuple[str | None, bool]:
    if text is None:
        return None, False
    data = _load_toml(text)
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict) or name not in servers:
        return None, False
    rows = text.splitlines(keepends=True)
    header, sub = _toml_header(name), _toml_header(name, sub=True)
    start = next((i for i, r in enumerate(rows) if header.match(r.rstrip("\r\n"))), None)
    if start is None:
        raise Unparseable(f"its {name} entry isn't a [mcp_servers.{name}] table")
    end = start + 1
    while end < len(rows) and (not _TABLE.match(rows[end]) or sub.match(rows[end])):
        end += 1
    if end == len(rows) and start > 0 and not rows[start - 1].strip():
        start -= 1  # the blank line `connect` put before the table
    new = "".join(rows[:start] + rows[end:])
    expected = copy.deepcopy(data)
    del expected["mcp_servers"][name]
    _check_toml(new, expected)
    return new, True


def _read(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")  # bytes: keep \r\n as it is
    except FileNotFoundError:
        return None


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup, n = path.with_name(f"{path.name}.minion-{stamp}.bak"), 1
    while backup.exists():
        n += 1
        backup = path.with_name(f"{path.name}.minion-{stamp}-{n}.bak")
    shutil.copy2(path, backup)
    return backup


def _write(path: Path, text: str) -> Path | None:
    """Back up, then replace the file atomically. A symlinked config (dotfiles) is written where it points."""
    real = Path(os.path.realpath(path))
    real.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(real)
    tmp = real.with_name(f".{real.name}.minion-tmp")
    tmp.write_bytes(text.encode("utf-8"))
    if backup:
        shutil.copymode(real, tmp)
    os.replace(tmp, real)
    return backup


# -- planning and applying ----------------------------------------------------------
CHANGES = ("add", "update", "remove")


@dataclass
class Change:
    app: App
    path: Path
    action: str  # "add", "update", "remove", "none" (nothing to do), "manual" (paste a snippet) or "error"
    before: str | None = None
    after: str | None = None
    commands: list[list[str]] = field(default_factory=list)  # Claude Code: CLI calls instead of a file write
    note: str = ""
    snippet: str = ""
    backup: Path | None = None
    chosen: bool = False  # picked (or answered yes to) for this run
    done: bool = False

    def to_dict(self) -> dict:
        return {
            "app": self.app.id,
            "name": self.app.name,
            "config": str(self.path),
            "action": self.action,
            "chosen": self.chosen,
            "done": self.done,
            "backup": str(self.backup) if self.backup else None,
            "commands": self.commands,
            "note": self.note,
            "snippet": self.snippet,
        }


def snippet(app: App, launch: Launch) -> str:
    """What to paste by hand when Minion can't edit the file: a TOML table, or a member of the JSON object."""
    if app.kind == "toml":
        lines = _toml_lines({**_plain(launch), **CODEX_EXTRA})
        return f"[mcp_servers.{NAME}]\n" + "\n".join(lines.values())
    if app.kind == "openclaw":  # its config is JSON5: its CLI writes it
        return cmdline(openclaw_commands("openclaw", launch, remove=False, replace=False)[0])
    first, *rest = app.key.split(".")
    value: dict = {NAME: app.entry(launch)}
    for k in reversed(rest):
        value = {k: value}
    return f"{json.dumps(first)}: {_block(value, '', '  ', chr(10), 2)}"


def _without_comments(text: str) -> str:
    """JSON with comments and trailing commas (Zed, VS Code, Gemini) made plain: for reading only."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            if text[i] in "}]":
                k = len(out) - 1
                while k >= 0 and out[k].isspace():
                    k -= 1
                if k >= 0 and out[k] == ",":
                    del out[k]
            out.append(text[i])
            i += 1
    return "".join(out)


def _entry_in_jsonc(text: str | None, key: str) -> object:
    """The Minion entry in a file Minion can't edit (to tell whether someone already pasted it)."""
    try:
        data = json.loads(_without_comments((text or "").lstrip(BOM)) or "{}")
    except ValueError:
        return None
    servers = data.get(key) if isinstance(data, dict) else None
    return servers.get(NAME) if isinstance(servers, dict) else None


def claude_commands(cli: str, launch: Launch, remove: bool, replace: bool) -> list[list[str]]:
    rm = [cli, "mcp", "remove", "--scope", "user", NAME]
    if remove:
        return [rm]
    add = [cli, "mcp", "add", "--scope", "user", NAME, "--", launch.command, *launch.args]
    return [rm, add] if replace else [add]  # `claude mcp add` refuses to overwrite an entry


def openclaw_cli() -> str | None:
    return shutil.which("openclaw")


def openclaw_commands(cli: str, launch: Launch, remove: bool, replace: bool) -> list[list[str]]:
    rm = [cli, "mcp", "unset", NAME]
    if remove:
        return [rm]
    args = [a for arg in launch.args for a in ("--arg", arg)]
    # --no-probe: saving shouldn't wait for a first uvx download (`openclaw mcp doctor minion --probe` checks it)
    add = [cli, "mcp", "add", NAME, "--command", launch.command, *args, "--no-probe", "--connect-timeout", "60"]
    add += ["--timeout", "900"]
    return [rm, add] if replace else [add]


# Apps whose own CLI manages their MCP servers: (finds the CLI, builds its commands), looked up by name.
CLIS = {"claude-code": ("claude_cli", "claude_commands"), "openclaw": ("openclaw_cli", "openclaw_commands")}


def _app_cli(app: App) -> str | None:
    """The app's own CLI that manages its MCP servers, when it has one installed here."""
    found = CLIS.get(app.kind)
    return globals()[found[0]]() if found else None


def _cli_commands(app: App, cli: str, launch: Launch, remove: bool, replace: bool) -> list[list[str]]:
    return globals()[CLIS[app.kind][1]](cli, launch, remove, replace)


def plan(app: App, launch: Launch, remove: bool = False) -> Change:
    """What connecting (or removing) would change, without changing anything."""
    path = app.path()
    try:
        before = _read(path)
    except (OSError, UnicodeDecodeError) as e:
        return Change(app, path, "manual", note=f"Minion can't read it ({e})", snippet=snippet(app, launch))
    if app.variant is not None:  # the format depends on the app's version
        key, entry = app.variant(before)
        app = replace(app, key=key, entry=entry, variant=None)
    try:
        if app.kind == "toml" and remove:
            after, existed = toml_remove(before, NAME)
        elif app.kind == "toml":
            after, existed = toml_set(before, NAME, launch.command, launch.args, CODEX_EXTRA)
        elif remove:
            after, existed = json_remove(before, app.key, NAME)
        else:
            after, existed = json_set(before, app.key, NAME, app.entry(launch))
    except Unparseable as e:
        cli = _app_cli(app)
        if cli:  # its own CLI can still do it
            commands = _cli_commands(app, cli, launch, remove, replace=True)
            return Change(app, path, "remove" if remove else "update", before, commands=commands, note=str(e))
        if app.kind != "toml":  # JSON with comments: maybe the entry was pasted by hand already
            old = _entry_in_jsonc(before, app.key)
            if (old is None) if remove else _same(old, app.entry(launch)):
                return Change(app, path, "none", before)
        return Change(app, path, "manual", before, note=str(e), snippet=snippet(app, launch))
    action = "none" if after is None else "remove" if remove else "update" if existed else "add"
    change = Change(app, path, action, before, after)
    cli = _app_cli(app) if after is not None else None
    if cli:
        change.commands = _cli_commands(app, cli, launch, remove, replace=existed)
    if app.id == "vscode" and not remove:  # VS Code's install links and `code --add-mcp` write the older file
        for old in (_app_data(flavor) / "User" / "mcp.json" for flavor in ("Code", "Code - Insiders")):
            try:
                if _entry_in_jsonc(_read(old), "servers") is not None:
                    change.note = f"{pretty(old)} has a Minion entry too: delete one, or VS Code shows Minion twice"
            except (OSError, UnicodeDecodeError):
                pass
    return change


def _run_cli(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL, timeout=120)


def apply(change: Change) -> Change:
    """Make the planned change: back up the file, then write it (or run the app's CLI)."""
    if change.action not in CHANGES:
        return change
    try:
        if change.commands:
            change.backup = _backup(Path(os.path.realpath(change.path)))
            for cmd in change.commands:
                res = _run_cli(cmd)
                failed_rm = res.returncode != 0 and cmd[2] in ("remove", "unset") and len(change.commands) > 1
                if res.returncode != 0 and not failed_rm:  # removing first may find nothing to remove
                    lines = (res.stderr or res.stdout or f"exit code {res.returncode}").strip().splitlines()
                    raise MinionError(f"`{' '.join(cmd[1:3])}` failed: {lines[-1] if lines else ''}")
        else:
            change.backup = _write(change.path, change.after or "")
        change.done = True
    except (OSError, subprocess.SubprocessError, MinionError) as e:
        change.action, change.note = "error", str(e)
    return change


def diff(change: Change) -> str:
    before = (change.before or "").splitlines(keepends=True)
    after = (change.after or "").splitlines(keepends=True)
    for lines in (before, after):
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
    name = pretty(change.path)
    return "".join(difflib.unified_diff(before, after, name if change.before is not None else "/dev/null", name))


# -- talking to the person -------------------------------------------------------------
def interactive() -> bool:
    """Only ask questions when someone can see and answer them."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def ask(question: str, default: str, yes: bool = False) -> str:
    """Ask on a terminal. Otherwise (and with --yes) answer with the default and say so: never block."""
    if yes:
        return default
    if not interactive():
        print(f"{question}{default}  (no terminal to answer, so using the default; --yes skips this question)")
        return default
    try:
        answer = input(question).strip()
    except EOFError:
        print()
        return default
    return answer or default


def pretty(path: Path) -> str:
    home = str(_home())
    text = str(path)
    if home not in ("", os.sep) and text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text


def _paint(text: str, code: str) -> str:
    from .cli import c

    return c(text, code)


def _cli_name(change: Change) -> str:
    return Path(change.commands[0][0]).stem if change.commands else ""


def _describe(change: Change, remove: bool) -> str:
    where = pretty(change.path) + (f"  (with `{_cli_name(change)} mcp`)" if change.commands else "")
    status = {
        "none": "not connected" if remove else "already connected",
        "update": "starts Minion another way: will update it",
        "manual": f"{change.note}: you'll get a snippet to paste",
    }.get(change.action, "")
    if change.note and change.action not in ("manual",):
        status = f"{status}; {change.note}" if status else change.note
    return where + (_paint(f"  ({status})", "2") if status else "")


def _pick(changes: list[Change], pending: list[Change], verb: str, yes: bool) -> list[Change]:
    """One question for the whole list: Enter takes every app that needs something."""
    nums = [changes.index(c) + 1 for c in pending]
    if len(pending) == 1:
        question = f"{verb} {pending[0].app.name}? [Y/n]: "
    else:
        which = f"all {len(pending)} apps" if len(pending) == len(changes) else ", ".join(map(str, nums))
        question = f"{verb} {which}? [Y/n, or numbers like {nums[0]},{nums[1]}]: "
    for _ in range(3):
        answer = ask(question, "Y", yes).strip().lower()
        if answer in ("y", "yes", "a", "all"):
            return pending
        if answer in ("n", "no", "none", "q"):
            return []
        picked = [x for x in re.split(r"[\s,]+", answer) if x]
        if not all(x.isdigit() and 1 <= int(x) <= len(changes) for x in picked):
            print("Answer y, n, or numbers from the list.")
            continue
        return [c for c in pending if changes.index(c) + 1 in {int(x) for x in picked}]
    return []


def run(
    apps: list[App] | None = None,
    launch: Launch | None = None,
    *,
    remove: bool = False,
    dry_run: bool = False,
    yes: bool = False,
    each: bool = False,
    json_out: bool = False,
) -> list[Change]:
    """Connect (or with `remove`, disconnect) `apps`, by default the ones found on this computer.

    Without `yes` it asks first: which apps (or, with `each`, app by app). Without a terminal it never waits for
    an answer: it uses the default, which is every app listed."""
    launch = launch or launcher()
    say = (lambda *a, **k: None) if json_out else print
    changes = [plan(app, launch, remove) for app in (detected() if apps is None else apps)]
    verb = "Remove Minion from" if remove else "Connect Minion to"
    if not changes:
        say("No agent apps found on this computer.")
        say(f"Name one to set it up anyway (`minion connect cursor`; see `minion connect --list`), or see {DOCS}")
        if json_out:
            print("[]")
        return changes
    if not remove:
        say(f"Minion's MCP server: {launch}")
    say("Agent apps on this computer:" if apps is None else "Apps:")
    width, digits = max(len(c.app.name) for c in changes), len(str(len(changes)))
    for i, ch in enumerate(changes, 1):
        say(f"  {str(i).rjust(digits)}. {ch.app.name.ljust(width)}  {_describe(ch, remove)}")
    pending = [c for c in changes if c.action != "none"]
    chosen: list[Change] = []
    if not pending:
        say("Nothing to remove." if remove else "Every app listed is connected already.")
    elif each and not yes:
        chosen = [c for c in pending if ask(f"{verb} {c.app.name}? [Y/n]: ", "Y").lower() in ("y", "yes")]
    elif apps is None and not json_out:
        chosen = _pick(changes, pending, verb, yes)
    else:
        chosen = pending
    for ch in chosen:
        ch.chosen = True
        if not dry_run:
            apply(ch)
        elif ch.action in CHANGES:
            say(_paint(f"\n{ch.app.name}: would {ch.action} Minion in {pretty(ch.path)}", "1"))
            for cmd in ch.commands:
                say("  by running: " + cmdline(cmd))
            say(diff(ch).rstrip("\n"))
    if json_out:
        out = [{**ch.to_dict(), **({"diff": diff(ch)} if dry_run and ch.chosen else {})} for ch in changes]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif pending:
        _summary(chosen, remove, dry_run)
    return changes


def _summary(chosen: list[Change], remove: bool, dry_run: bool = False) -> None:
    from .cli import err, ok

    if not chosen:
        print("Nothing changed.")
        return
    print()
    for ch in chosen:
        if ch.done:
            what = {"add": "connected", "update": "updated", "remove": "removed"}[ch.action]
            how = f"with `{_cli_name(ch)} mcp`" if ch.commands else pretty(ch.path)
            extra = f"; backup: {ch.backup.name}" if ch.backup else ""
            ok(f"{ch.app.name}: {what} ({how}{extra})")
        elif ch.action == "error":
            err(f"{ch.app.name}: {ch.note}")
        elif ch.action == "manual":
            print(_paint("! ", "33") + f"{ch.app.name}: {ch.note}, so Minion leaves {pretty(ch.path)} alone.")
            if remove:
                print(f'  Please delete its "{NAME}" entry by hand.')
            elif ch.app.kind == "toml":
                print("  Please add this table to it by hand:")
            else:
                print(f'  Please add this inside its outer {{ }} by hand (if "{ch.app.key}" is there already,')
                print(f'  add just the "{NAME}" part to it):')
            if not remove:
                print("\n".join("    " + line for line in ch.snippet.splitlines()))
    done = [ch for ch in chosen if ch.done]
    if done and not remove:
        print("\nTo load Minion:")
        for ch in done:
            print(f"  • {ch.app.name}: {ch.app.reload}")
    if dry_run:
        print("\nThis was a dry run: nothing was changed.")


def _status(change: Change, found: bool) -> str:
    if change.action == "none":
        return "connected"
    if change.action == "update":
        return "connected (other command)"
    if change.action == "manual":
        return "can't edit: " + change.note
    if change.action == "error":
        return change.note
    return "not connected" if found else "not found"


def list_apps(launch: Launch, json_out: bool = False) -> int:
    rows = []
    for app in APPS:
        change = plan(app, launch)
        found = app.found(change.path)
        rows.append((app, change, found, _status(change, found)))
    if json_out:
        out = [{"app": a.id, "name": a.name, "found": f, "status": s, "config": str(ch.path)} for a, ch, f, s in rows]
        server = {"command": launch.command, "args": launch.args, "how": launch.how}
        print(json.dumps({"server": server, "apps": out}, indent=2))
        return 0
    print(f"Minion's MCP server: {launch}\n")
    table = [("APP", "NAME", "STATUS", "CONFIG")] + [(a.id, a.name, s, pretty(ch.path)) for a, ch, _f, s in rows]
    widths = [max(len(r[i]) for r in table) for i in range(3)]
    for i, row in enumerate(table):
        line = "  ".join(col.ljust(w) for col, w in zip(row[:3], widths, strict=True)) + "  " + row[3]
        print(_paint(line, "2") if i == 0 else line)
    print(f"\nConnect: minion connect [APP ...]   ·   Remove: minion connect --remove   ·   {DOCS}")
    return 0


def main(
    apps: list[str] | None = None,
    *,
    every: bool = False,
    list_only: bool = False,
    dry_run: bool = False,
    remove: bool = False,
    compact: bool = False,
    yes: bool = False,
    json_out: bool = False,
) -> int:
    """`minion connect`. With no APP it works on the apps found on this computer and asks which ones,
    unless --all or --yes is given."""
    chosen = [find_app(a) for a in apps] if apps else None
    launch = launcher(compact)
    if list_only:
        return list_apps(launch, json_out)
    changes = run(chosen, launch, remove=remove, dry_run=dry_run, yes=yes or every, json_out=json_out)
    return 1 if any(c.chosen and c.action in ("error", "manual") for c in changes) else 0
