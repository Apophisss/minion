"""`minion connect`: every app's config, merged without losing anything, idempotent and reversible.

Every test runs in a fake home directory: no real app config is read or written."""

import json
import os
import sys
import tomllib
from pathlib import Path

import pytest

from minion import cli, connect
from minion.connect import Launch
from minion.errors import NotFound

CMD = str(Path("/opt/minion/bin/minion").absolute())
LAUNCH = Launch(CMD, ["mcp"], "installed")
REAL_LAUNCHER = connect.launcher
ENV = (
    "XDG_CONFIG_HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "GEMINI_CLI_HOME",
    "KIRO_HOME",
    "CLINE_DIR",
    "CLINE_DATA_DIR",
    "CLINE_MCP_SETTINGS_PATH",
    "COPILOT_HOME",
    "UV",
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home with nothing on PATH (so no real `claude`, `codex`, ... is found) and no terminal."""
    h = tmp_path / "home"
    h.mkdir()
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(h))
    for var in ENV:
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "bin").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(connect, "interactive", lambda: False)
    monkeypatch.setattr(connect, "launcher", lambda compact=False: Launch(CMD, ["mcp", *(["--compact"] * compact)]))
    return h


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def seed(h: Path) -> dict[str, Path]:
    """An existing config for every app, each with something of the user's in it."""
    return {
        "claude-desktop": write(
            h / ".config/Claude/claude_desktop_config.json",
            '{\n  "globalShortcut": "Ctrl+Space",\n  "mcpServers": {\n    "fetch": {\n      "command": "uvx",\n'
            '      "args": ["mcp-server-fetch"]\n    }\n  }\n}\n',
        ),
        "claude-code": write(h / ".claude.json", '{\n  "numStartups": 3,\n  "projects": {\n    "/x": {}\n  }\n}\n'),
        "cursor": write(h / ".cursor/mcp.json", '{\n    "mcpServers": {}\n}\n'),
        "vscode": write(
            h / ".copilot/mcp-config.json",
            '{\n\t"mcpServers": {\n\t\t"github": {\n\t\t\t"type": "http",\n\t\t\t"url": "https://api.githubcopilot.com/mcp/"'
            "\n\t\t}\n\t}\n}",
        ),
        "devin": write(h / ".config/devin/mcp_config.json", '{"mcpServers": {}}'),
        "gemini": write(
            h / ".gemini/settings.json",
            '{\n  "ui": {"theme": "Dracula"},\n  "mcpServers": {"other": {"command": "npx", "args": ["-y", "x"]}}\n}\n',
        ),
        "codex": write(
            h / ".codex/config.toml",
            'model = "gpt-5-codex"\n\n[mcp_servers.context7]\ncommand = "npx"\nargs = ["-y", "@upstash/context7-mcp"]\n',
        ),
        "lmstudio": write(
            h / ".lmstudio/mcp.json", '{\n  "mcpServers": {\n    "hf": {"url": "https://hf.co/mcp"}\n  }\n}\n'
        ),
        "cline": write(h / ".cline/data/settings/cline_mcp_settings.json", '{\n  "mcpServers": {}\n}\n'),
        "kiro": write(h / ".kiro/settings/mcp.json", '{\n  "mcpServers": {}\n}\n'),
        "zed": write(h / ".config/zed/settings.json", '// Zed settings\n{\n  "ui_font_size": 16,\n}\n'),
    }


def snapshot(h: Path) -> dict[str, bytes]:
    return {str(p.relative_to(h)): p.read_bytes() for p in sorted(h.rglob("*")) if p.is_file()}


def entry(path: Path, key: str = "mcpServers") -> dict:
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text())["mcp_servers"]["minion"]
    return json.loads(path.read_text(encoding="utf-8-sig"))[key]["minion"]


# -- where configs live -------------------------------------------------------------
def paths() -> dict[str, Path]:
    return {app.id: app.path() for app in connect.APPS}


def test_paths_on_linux(home, monkeypatch):
    p = paths()
    assert p["claude-desktop"] == home / ".config/Claude/claude_desktop_config.json"
    assert p["claude-code"] == home / ".claude.json"
    assert p["cursor"] == home / ".cursor/mcp.json"
    assert p["vscode"] == home / ".copilot/mcp-config.json"
    assert p["devin"] == home / ".config/devin/mcp_config.json"
    assert p["windsurf"] == home / ".codeium/windsurf/mcp_config.json"
    assert p["gemini"] == home / ".gemini/settings.json"
    assert p["codex"] == home / ".codex/config.toml"
    assert p["lmstudio"] == home / ".lmstudio/mcp.json"
    assert p["cline"] == home / ".cline/data/settings/cline_mcp_settings.json"
    assert p["kiro"] == home / ".kiro/settings/mcp.json"
    assert p["zed"] == home / ".config/zed/settings.json"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    p = paths()
    assert p["claude-desktop"] == home / "xdg/Claude/claude_desktop_config.json"
    assert p["zed"] == home / "xdg/zed/settings.json"
    assert p["devin"] == home / "xdg/devin/mcp_config.json"


def test_paths_on_macos(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    support = home / "Library/Application Support"
    p = paths()
    assert p["claude-desktop"] == support / "Claude/claude_desktop_config.json"
    assert p["vscode"] == home / ".copilot/mcp-config.json"
    assert p["zed"] == home / ".config/zed/settings.json"  # Zed ignores XDG_CONFIG_HOME on macOS
    assert p["cursor"] == home / ".cursor/mcp.json"
    assert p["codex"] == home / ".codex/config.toml"


def test_paths_on_windows(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, local = home / "AppData/Roaming", home / "AppData/Local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    p = paths()
    assert p["claude-desktop"] == roaming / "Claude/claude_desktop_config.json"
    assert p["vscode"] == home / ".copilot/mcp-config.json"
    assert p["zed"] == roaming / "Zed/settings.json"
    assert p["devin"] == roaming / "devin/mcp_config.json"
    assert p["cursor"] == home / ".cursor/mcp.json"
    assert p["gemini"] == home / ".gemini/settings.json"
    assert p["codex"] == home / ".codex/config.toml"
    assert p["claude-code"] == home / ".claude.json"


def test_claude_desktop_msix_on_windows(home, monkeypatch):
    """The installer from claude.com is an MSIX package: Windows redirects its %APPDATA% into the package."""
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, local = home / "AppData/Roaming", home / "AppData/Local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    app = connect.find_app("claude-desktop")
    msix = local / "Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude"
    msix.mkdir(parents=True)
    assert app.path() == msix / "claude_desktop_config.json"  # the folder the app uses
    write(roaming / "Claude/claude_desktop_config.json", "{}")
    assert app.path() == roaming / "Claude/claude_desktop_config.json"  # the file Windows falls back to
    write(msix / "claude_desktop_config.json", "{}")
    assert app.path() == msix / "claude_desktop_config.json"  # the file Windows reads first
    assert app.found(app.path())


def test_env_overrides(home, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(home / "cx"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "cc"))
    monkeypatch.setenv("GEMINI_CLI_HOME", str(home / "gm"))
    monkeypatch.setenv("KIRO_HOME", str(home / "kr"))
    monkeypatch.setenv("CLINE_MCP_SETTINGS_PATH", str(home / "cl.json"))
    monkeypatch.setenv("COPILOT_HOME", str(home / "cp"))
    p = paths()
    assert p["codex"] == home / "cx/config.toml"
    assert p["claude-code"] == home / "cc/.claude.json"
    assert p["gemini"] == home / "gm/.gemini/settings.json"
    assert p["kiro"] == home / "kr/settings/mcp.json"
    assert p["cline"] == home / "cl.json"
    assert p["vscode"] == home / "cp/mcp-config.json"


def test_lmstudio_home(home):
    app = connect.find_app("lmstudio")
    assert app.path() == home / ".lmstudio/mcp.json"
    (home / ".cache/lm-studio").mkdir(parents=True)  # older installs
    assert app.path() == home / ".cache/lm-studio/mcp.json"
    write(home / ".lmstudio-home-pointer", str(home / "elsewhere") + "\n")
    assert app.path() == home / "elsewhere/mcp.json"


# -- detection ----------------------------------------------------------------------
def test_detects_only_the_apps_on_this_computer(home):
    assert connect.detected() == []
    (home / ".cursor").mkdir()
    (home / ".codex").mkdir()
    assert [a.id for a in connect.detected()] == ["cursor", "codex"]


def test_vscode_is_found_by_any_of_its_folders(home):
    (home / ".config/Code - Insiders/User").mkdir(parents=True)
    assert [a.id for a in connect.detected()] == ["vscode"]  # one file serves VS Code, Insiders and Copilot CLI


def test_vscode_warns_about_a_minion_entry_in_its_older_file(home):
    write(home / ".config/Code/User/mcp.json", '{"servers": {"minion": {"command": "uvx"}}}')  # an install link
    change = connect.plan(connect.find_app("vscode"), LAUNCH)
    assert change.action == "add" and "shows Minion twice" in change.note


def test_windsurf_is_left_to_devin(home):
    (home / ".codeium/windsurf").mkdir(parents=True)
    assert [a.id for a in connect.detected()] == ["windsurf"]
    (home / ".config/devin").mkdir(parents=True)  # Windsurf became Devin Desktop, which imports its config
    assert [a.id for a in connect.detected()] == ["devin"]


def test_detects_apps_by_their_command(home, tmp_path):
    exe = tmp_path / "bin" / "codex"  # (the fixture makes the platform Linux, where commands have no .exe)
    exe.write_text("")
    exe.chmod(0o755)
    assert [a.id for a in connect.detected()] == ["codex"]


def test_find_app_by_id_name_or_alias():
    assert connect.find_app("VS Code").id == "vscode"
    assert connect.find_app("code").id == "vscode"
    assert connect.find_app("Claude Desktop").id == "claude-desktop"
    assert connect.find_app("claude_code").id == "claude-code"
    assert connect.find_app("gemini-cli").id == "gemini"
    assert connect.find_app("devin-desktop").id == "devin"
    assert connect.find_app("copilot").id == connect.find_app("vscode-insiders").id == "vscode"
    with pytest.raises(NotFound, match="cursor"):
        connect.find_app("notepad")


# -- connecting -------------------------------------------------------------------------
def test_connect_merges_into_every_app(home):
    files = seed(home)
    before = snapshot(home)
    changes = {c.app.id: c for c in connect.run(launch=LAUNCH, yes=True)}
    assert {k for k, c in changes.items() if c.done} == set(files) - {"zed"}
    plain, stdio = {"command": CMD, "args": ["mcp"]}, {"type": "stdio", "command": CMD, "args": ["mcp"]}
    for app_id in ("claude-desktop", "devin", "gemini", "lmstudio", "cline", "kiro"):
        assert entry(files[app_id]) == plain, app_id
    for app_id in ("claude-code", "cursor"):
        assert entry(files[app_id]) == stdio, app_id
    assert entry(files["vscode"]) == {**stdio, "tools": ["*"]}
    assert entry(files["codex"]) == {**plain, "startup_timeout_sec": 60, "tool_timeout_sec": 900}
    # nothing of the user's is lost
    assert json.loads(files["claude-desktop"].read_text())["globalShortcut"] == "Ctrl+Space"
    assert json.loads(files["claude-desktop"].read_text())["mcpServers"]["fetch"]["args"] == ["mcp-server-fetch"]
    assert json.loads(files["claude-code"].read_text())["projects"] == {"/x": {}}
    assert json.loads(files["vscode"].read_text())["mcpServers"]["github"]["type"] == "http"
    assert json.loads(files["gemini"].read_text())["ui"] == {"theme": "Dracula"}
    codex = tomllib.loads(files["codex"].read_text())
    assert codex["model"] == "gpt-5-codex" and codex["mcp_servers"]["context7"]["command"] == "npx"
    # each change made a backup of the file as it was
    for app_id, change in changes.items():
        if change.done:
            assert change.backup.read_bytes() == before[str(files[app_id].relative_to(home))]
    assert (
        changes["zed"].action == "manual" and files["zed"].read_bytes() == before[str(files["zed"].relative_to(home))]
    )


def test_only_the_minion_lines_change(home):
    """In-place edits keep the file's own layout: indentation, tabs, one-liners, key order."""
    files = seed(home)
    connect.run(launch=LAUNCH, yes=True)
    assert files["claude-desktop"].read_text() == (
        '{\n  "globalShortcut": "Ctrl+Space",\n  "mcpServers": {\n    "fetch": {\n      "command": "uvx",\n'
        '      "args": ["mcp-server-fetch"]\n    },\n    "minion": {\n'
        f'      "command": {json.dumps(CMD)},\n      "args": ["mcp"]\n    }}\n  }}\n}}\n'
    )
    assert '\t\t"minion": {\n\t\t\t"type": "stdio",' in files["vscode"].read_text()
    minion = json.dumps({"command": CMD, "args": ["mcp"]})
    assert files["devin"].read_text() == '{"mcpServers": {"minion": ' + minion + "}}"  # one line stays one line


def test_running_twice_changes_nothing(home):
    seed(home)
    connect.run(launch=LAUNCH, yes=True)
    after_first = snapshot(home)
    changes = connect.run(launch=LAUNCH, yes=True)
    assert snapshot(home) == after_first  # no write and no new backup
    assert {c.action for c in changes} == {"none", "manual"}  # Zed still needs a hand


def test_remove_undoes_it(home):
    files = seed(home)
    before = snapshot(home)
    connect.run(launch=LAUNCH, yes=True)
    changes = connect.run(launch=LAUNCH, yes=True, remove=True)
    assert {c.app.id for c in changes if c.done} == set(files) - {"zed"}
    for app_id in set(files) - {"claude-code", "zed"}:
        rel = str(files[app_id].relative_to(home))
        assert files[app_id].read_bytes() == before[rel], app_id  # byte for byte
    # where Minion added "mcpServers", it stays, empty (as `claude mcp remove` leaves it)
    assert json.loads(files["claude-code"].read_text()) == {"numStartups": 3, "projects": {"/x": {}}, "mcpServers": {}}
    assert all(c.action == "none" for c in connect.run(launch=LAUNCH, yes=True, remove=True))


def test_an_existing_entry_is_updated_and_keeps_its_extras(home):
    path = write(
        home / ".cursor/mcp.json",
        '{"mcpServers": {"minion": {"command": "uvx", "args": ["minion-desktop", "mcp"], "env": {"A": "1"}}}}',
    )
    change = connect.run([connect.find_app("cursor")], LAUNCH)[0]
    assert change.action == "update" and change.done
    assert entry(path) == {"command": CMD, "args": ["mcp"], "env": {"A": "1"}, "type": "stdio"}


def test_compact(home):
    path = write(home / ".gemini/settings.json", "{}")
    connect.main(["gemini"], compact=True)
    assert entry(path)["args"] == ["mcp", "--compact"]


def test_an_app_named_explicitly_is_set_up_even_if_not_found(home):
    changes = connect.run([connect.find_app("kiro")], LAUNCH)
    assert changes[0].action == "add" and changes[0].backup is None  # nothing to back up
    assert entry(home / ".kiro/settings/mcp.json") == {"command": CMD, "args": ["mcp"]}


def test_dry_run_shows_the_diff_and_writes_nothing(home, capsys):
    seed(home)
    before = snapshot(home)
    connect.run(launch=LAUNCH, yes=True, dry_run=True)
    out = capsys.readouterr().out
    assert snapshot(home) == before
    assert '+    "minion": {' in out and "+[mcp_servers.minion]" in out and "dry run" in out
    assert '"context_servers": {' in out  # Zed's snippet


def test_empty_and_missing_files(home):
    write(home / ".cursor/mcp.json", "")
    connect.run([connect.find_app("cursor"), connect.find_app("codex")], LAUNCH)
    assert json.loads((home / ".cursor/mcp.json").read_text()) == {
        "mcpServers": {"minion": {"type": "stdio", "command": CMD, "args": ["mcp"]}}
    }
    assert (home / ".codex/config.toml").read_text() == (
        f'[mcp_servers.minion]\ncommand = {json.dumps(CMD)}\nargs = ["mcp"]\n'
        "startup_timeout_sec = 60\ntool_timeout_sec = 900\n"
    )


def test_line_endings_and_byte_order_mark_are_kept(home):
    path = write(
        home / ".cursor/mcp.json", connect.BOM + '{\r\n  "mcpServers": {\r\n    "a": {"url": "x"}\r\n  }\r\n}\r\n'
    )
    connect.run([connect.find_app("cursor")], LAUNCH)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\r\n") == raw.count(b"\n")
    assert entry(path)["command"] == CMD
    connect.run([connect.find_app("cursor")], LAUNCH, remove=True)
    assert path.read_bytes().decode() == connect.BOM + '{\r\n  "mcpServers": {\r\n    "a": {"url": "x"}\r\n  }\r\n}\r\n'


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlinked_config_stays_a_symlink(home, tmp_path):
    real = write(tmp_path / "dotfiles/mcp.json", '{"mcpServers": {}}')
    (home / ".cursor").mkdir()
    (home / ".cursor/mcp.json").symlink_to(real)
    connect.run([connect.find_app("cursor")], LAUNCH)
    assert (home / ".cursor/mcp.json").is_symlink()
    assert entry(real)["command"] == CMD


# -- files Minion can't edit ---------------------------------------------------------------
@pytest.mark.parametrize(
    "app_id,rel,text",
    [
        ("vscode", ".copilot/mcp-config.json", '{\n  // my servers\n  "mcpServers": {}\n}\n'),
        ("cursor", ".cursor/mcp.json", '{"mcpServers": {},}'),  # a trailing comma
        ("gemini", ".gemini/settings.json", '{"a": 1, "a": 2}'),  # a repeated key would lose a value
        ("lmstudio", ".lmstudio/mcp.json", '{"mcpServers": []}'),
        ("kiro", ".kiro/settings/mcp.json", "[1, 2]"),
        ("codex", ".codex/config.toml", "model = \n"),
        ("codex", ".codex/config.toml", 'mcp_servers = { other = { command = "x" } }\n'),  # inline: can't add
    ],
)
def test_files_minion_cant_parse_are_left_alone(home, capsys, app_id, rel, text):
    path = write(home / rel, text)
    changes = connect.run([connect.find_app(app_id)], LAUNCH)
    assert changes[0].action == "manual"
    assert path.read_text() == text and not list(path.parent.glob("*.bak"))
    out = capsys.readouterr().out
    assert "by hand" in out and json.dumps(CMD) in out  # the exact snippet to paste


def test_snippet_pasted_by_hand_counts_as_connected(home):
    path = write(home / ".config/zed/settings.json", '// mine\n{\n  "ui_font_size": 16,\n}\n')
    zed = connect.find_app("zed")
    assert connect.plan(zed, LAUNCH).action == "manual"
    snippet = connect.plan(zed, LAUNCH).snippet
    path.write_text(f'// mine\n{{\n  "ui_font_size": 16,\n  {snippet},  /* by hand */\n}}\n')
    assert connect.plan(zed, LAUNCH).action == "none"
    assert connect.plan(zed, LAUNCH, remove=True).action == "manual"  # it has to go by hand too


def test_main_exit_codes(home):
    write(home / ".cursor/mcp.json", "{}")
    assert connect.main(yes=True) == 0
    write(home / ".config/zed/settings.json", "// x\n{}")
    assert connect.main(yes=True) == 1  # Zed needs a hand


# -- TOML (Codex) ---------------------------------------------------------------------------
OLD = """\
# my Codex config
model = "o4"

[mcp_servers.minion]
command = "uvx"   # how it was
args = [
  "minion-desktop",
  "mcp",
]
startup_timeout_sec = 30

[mcp_servers.minion.env]
DOCKER_HOST = "unix:///var/run/docker.sock"

[profiles.fast]
model = "gpt-5-mini"
"""


def test_toml_update_in_place():
    new, existed = connect.toml_set(OLD, "minion", CMD, ["mcp"], {"tool_timeout_sec": 900})
    assert existed
    data = tomllib.loads(new)
    assert data["mcp_servers"]["minion"] == {
        "command": CMD,
        "args": ["mcp"],
        "startup_timeout_sec": 30,  # yours stays
        "tool_timeout_sec": 900,  # a missing one is added
        "env": {"DOCKER_HOST": "unix:///var/run/docker.sock"},
    }
    assert data["profiles"] == {"fast": {"model": "gpt-5-mini"}} and data["model"] == "o4"
    assert new.startswith("# my Codex config\n") and "startup_timeout_sec = 30\n" in new
    assert connect.toml_set(new, "minion", CMD, ["mcp"], {"tool_timeout_sec": 900}) == (None, True)


def test_toml_remove_takes_the_tables_out():
    new, existed = connect.toml_remove(OLD, "minion")
    assert existed and "minion" not in new
    assert tomllib.loads(new) == {"model": "o4", "profiles": {"fast": {"model": "gpt-5-mini"}}}
    assert connect.toml_remove(new, "minion") == (None, False)


def test_toml_add_then_remove_is_exact():
    for text in ("", 'model = "o4"\n', 'model = "o4"', "a = 1\r\n[b]\r\nc = 2\r\n"):
        new, _ = connect.toml_set(text, "minion", CMD, ["mcp"])
        assert tomllib.loads(new)["mcp_servers"]["minion"]["command"] == CMD
        if "\r\n" in text:
            assert new.count("\r\n") == new.count("\n")
        back, _ = connect.toml_remove(new, "minion")
        assert back == (text if text.endswith("\n") or not text else text + "\n")


def test_toml_windows_paths():
    path = "C:\\Users\\Zoë\\.local\\bin\\minion.exe"
    new, _ = connect.toml_set("", "minion", path, ["mcp"])
    assert tomllib.loads(new)["mcp_servers"]["minion"]["command"] == path


# -- Claude Code -----------------------------------------------------------------------------
@pytest.fixture
def claude(home, monkeypatch):
    """A fake `claude` CLI: records calls and edits ~/.claude.json like the real one."""
    calls = []

    def run_cli(cmd):
        calls.append(cmd[1:])
        path = home / ".claude.json"
        data = json.loads(path.read_text()) if path.exists() else {}
        servers = data.setdefault("mcpServers", {})
        if cmd[2] == "add":
            if cmd[5] in servers:
                return type("R", (), {"returncode": 1, "stdout": "", "stderr": "already exists"})
            servers[cmd[5]] = {"type": "stdio", "command": cmd[7], "args": cmd[8:], "env": {}}
        else:
            servers.pop(cmd[5])
        path.write_text(json.dumps(data, indent=2))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})

    monkeypatch.setattr(connect, "claude_cli", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(connect, "_run_cli", run_cli)
    write(home / ".claude.json", '{"numStartups": 2}')
    return calls


def test_claude_code_uses_its_cli(home, claude):
    app = [connect.find_app("claude-code")]
    change = connect.run(app, LAUNCH)[0]
    assert change.done and change.backup is not None
    assert claude == [["mcp", "add", "--scope", "user", "minion", "--", CMD, "mcp"]]
    assert connect.run(app, LAUNCH)[0].action == "none" and len(claude) == 1  # idempotent
    connect.run(app, Launch(CMD, ["mcp", "--compact"]))  # `add` won't overwrite: remove, then add
    assert claude[1:] == [
        ["mcp", "remove", "--scope", "user", "minion"],
        ["mcp", "add", "--scope", "user", "minion", "--", CMD, "mcp", "--compact"],
    ]
    connect.run(app, LAUNCH, remove=True)
    assert claude[-1] == ["mcp", "remove", "--scope", "user", "minion"]
    assert json.loads((home / ".claude.json").read_text()) == {"numStartups": 2, "mcpServers": {}}


def test_claude_code_cli_failure_is_reported(home, claude, monkeypatch, capsys):
    fail = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom\nreally broken"})
    monkeypatch.setattr(connect, "_run_cli", lambda cmd: fail)
    change = connect.run([connect.find_app("claude-code")], LAUNCH)[0]
    assert change.action == "error" and "really broken" in change.note
    assert "really broken" in capsys.readouterr().err


def test_claude_code_without_its_cli_edits_the_file(home):
    write(home / ".claude.json", '{\n  "numStartups": 2\n}\n')
    connect.run([connect.find_app("claude-code")], LAUNCH)
    data = json.loads((home / ".claude.json").read_text())
    assert data == {"numStartups": 2, "mcpServers": {"minion": {"type": "stdio", "command": CMD, "args": ["mcp"]}}}


# -- asking ---------------------------------------------------------------------------------
def test_no_terminal_uses_the_default_and_says_so(home, monkeypatch, capsys):
    seed(home)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("asked without a terminal"))
    changes = connect.run(launch=LAUNCH)
    assert all(c.done for c in changes if c.app.id != "zed")
    assert "no terminal to answer" in capsys.readouterr().out


@pytest.mark.parametrize(
    "answers,connected",
    [
        ([""], {"cursor", "codex"}),
        (["2"], {"codex"}),
        (["1, 2"], {"cursor", "codex"}),
        (["n"], set()),
        (["0", "-1", "3"], set()),
    ],  # not on the list: asked again, then nothing
)
def test_terminal_answers(home, monkeypatch, answers, connected):
    (home / ".cursor").mkdir()
    (home / ".codex").mkdir()
    replies = iter(answers)
    monkeypatch.setattr(connect, "interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda q: next(replies))
    assert {c.app.id for c in connect.run(launch=LAUNCH) if c.done} == connected


def test_asking_app_by_app(home, monkeypatch):
    (home / ".cursor").mkdir()
    (home / ".codex").mkdir()
    answers = iter(["y", "n"])
    monkeypatch.setattr(connect, "interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda q: next(answers))
    assert {c.app.id for c in connect.run(launch=LAUNCH, each=True) if c.done} == {"cursor"}


# -- the command line ----------------------------------------------------------------------
def test_cli(home, capsys):
    args = cli.build_parser().parse_args(["connect", "cursor", "vscode", "--dry-run", "--compact", "-y"])
    assert args.apps == ["cursor", "vscode"] and args.dry_run and args.compact and args.yes
    (home / ".cursor").mkdir()
    assert cli.main(["connect", "--all"]) == 0
    assert entry(home / ".cursor/mcp.json")["command"] == CMD
    capsys.readouterr()
    assert cli.main(["connect", "--list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    statuses = {a["app"]: a["status"] for a in listing["apps"]}
    assert statuses["cursor"] == "connected" and statuses["zed"] == "not found"
    assert cli.main(["connect", "nothing-like-this"]) == 2


def test_cli_json_output(home, capsys):
    (home / ".cursor").mkdir()
    assert cli.main(["connect", "--json", "--yes"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["app"] == "cursor" and out[0]["done"] and out[0]["action"] == "add"


# -- how apps start Minion ---------------------------------------------------------------------
def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    path.chmod(0o755)
    return path


EXE = ".exe" if os.name == "nt" else ""


@pytest.fixture
def real_launcher(home, monkeypatch, tmp_path):
    monkeypatch.setattr(connect, "launcher", REAL_LAUNCHER)  # not the `home` fixture's fake one
    monkeypatch.setattr(connect, "_source_spec", lambda: None)
    return tmp_path


def test_launcher_uses_the_minion_command_that_runs(real_launcher, monkeypatch):
    venv = real_launcher / "venv"
    script = executable(venv / "bin" / f"minion{EXE}")
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "argv", [str(script)])
    assert connect.launcher() == Launch(str(script), ["mcp"], "installed")
    assert connect.launcher(compact=True).args == ["mcp", "--compact"]


def test_launcher_finds_minion_next_to_python(real_launcher, monkeypatch):
    venv = real_launcher / "venv"
    script = executable(venv / "bin" / f"minion{EXE}")
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "argv", ["/usr/lib/python3/pytest"])
    monkeypatch.setattr(sys, "executable", str(venv / "bin" / f"python{EXE}"))
    assert connect.launcher().command == str(script)


def test_launcher_falls_back_to_python(real_launcher, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(real_launcher / "nowhere"))
    monkeypatch.setattr(sys, "argv", ["-c"])
    monkeypatch.setattr(sys, "executable", str(real_launcher / "nowhere/python"))
    assert connect.launcher() == Launch(str(real_launcher / "nowhere/python"), ["-m", "minion", "mcp"], "python")


def test_launcher_from_uvx_cache_uses_uvx(real_launcher, monkeypatch):
    cache = real_launcher / "home/.cache/uv/archive-v0/WY2atidSzoNiVxQU"
    executable(cache / "bin" / f"minion{EXE}")
    uvx = executable(real_launcher / "uv-bin" / f"uvx{EXE}")
    monkeypatch.setattr(sys, "prefix", str(cache))
    monkeypatch.setattr(sys, "argv", [str(cache / "bin" / f"minion{EXE}")])
    monkeypatch.setenv("UV", str(real_launcher / "uv-bin" / f"uv{EXE}"))  # uv tells its children where it is
    assert connect.launcher() == Launch(str(uvx), ["minion-desktop", "mcp"], "uvx")
    monkeypatch.setattr(connect, "_source_spec", lambda: "git+https://github.com/apophisss/minion@main")
    assert connect.launcher(compact=True).args == [
        "--from",
        "git+https://github.com/apophisss/minion@main",
        "minion",
        "mcp",
        "--compact",
    ]


def test_source_spec(monkeypatch, tmp_path):
    import importlib.metadata

    def fake(info):
        dist = type("D", (), {"read_text": lambda self, name: json.dumps(info) if info is not None else None})()
        monkeypatch.setattr(importlib.metadata, "distribution", lambda name: dist)

    fake({"url": "https://github.com/apophisss/minion", "vcs_info": {"vcs": "git", "requested_revision": "main"}})
    assert connect._source_spec() == "git+https://github.com/apophisss/minion@main"
    fake({"url": "https://github.com/apophisss/minion", "vcs_info": {"vcs": "git", "commit_id": "abc123"}})
    assert connect._source_spec() == "git+https://github.com/apophisss/minion@abc123"
    fake({"url": tmp_path.as_uri(), "dir_info": {}})
    assert connect._source_spec() == str(tmp_path)
    fake(None)  # installed from PyPI
    assert connect._source_spec() is None
