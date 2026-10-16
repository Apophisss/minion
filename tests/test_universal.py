"""Working with any app: menus, file dialogs, typed targets, and opening (and installing) apps by name."""

import io
import json

import pytest

from minion.agent import a11y, catalog
from minion.agent.perceive import role_query
from minion.agent.server import parse_step


@pytest.mark.parametrize(
    "binding,expected",
    [
        ("s;<Alt>f:s;<Primary>s", "ctrl+s"),  # GTK: mnemonic; keyboard path; accelerator
        ("a;<Alt>f:a;<Shift><Control>s", "ctrl+shift+s"),
        ("x;<Alt>e:x;", ""),  # no accelerator, only a mnemonic path
        ("Ctrl+Shift+S", "ctrl+shift+s"),  # Qt and LibreOffice
        ("F11", "F11"),
        ("Alt+Shift+F8", "alt+shift+F8"),
        ("", ""),
    ],
)
def test_shortcuts_are_normalized(binding, expected):
    assert a11y._shortcut(binding) == expected


def test_menu_listing_counts_greyed_out_commands():
    items = [
        (0, "File", "", True, True),
        (1, "New", "", True, True),
        (2, "Text Document", "ctrl+n", True, False),
        (1, "Save As...", "ctrl+shift+s", True, False),
        (1, "Reload", "", False, False),
        (0, "Edit", "", True, True),
        (1, "Undo", "ctrl+z", False, False),
    ]
    assert a11y.format_menus(items) == [
        "File: New ▸ · Save As... (ctrl+shift+s) (+1 greyed out)",
        "File > New: Text Document (ctrl+n)",
    ]
    assert a11y.menu_name("Save _As…") == a11y.menu_name("save as...") == "save as"


def test_menu_and_path_steps():
    assert parse_step("menu File > Export As > Export as PDF...") == (
        "menu",
        {"item": "File > Export As > Export as PDF..."},
    )
    assert parse_step({"menu": "Edit > Find"}) == ("menu", {"item": "Edit > Find"})
    assert parse_step("path ~/My Documents/report.pdf") == ("path", {"path": "~/My Documents/report.pdf"})
    assert parse_step("path ~/a.pdf --overwrite") == ("path", {"path": "~/a.pdf", "overwrite": True})
    assert parse_step({"path": "/tmp/x.txt"}) == ("path", {"path": "/tmp/x.txt"})


@pytest.mark.parametrize(
    "query,expected",
    [
        ("button:Save", ("button", "Save")),
        ('button "Save As…"', ("button", "Save As…")),
        ("link 'Docs'", ("link", "Docs")),
        ("field: Email address", ("field", "Email address")),
        ("textbox:Search", ("field", "Search")),
        ("combo box:Font", ("dropdown", "Font")),
        ("tab:Settings", ("tab", "Settings")),
        ("Total: 5", ("", "Total: 5")),  # ordinary text with a colon is not a kind
        ("Note: save first", ("", "Note: save first")),
        ("Save", ("", "Save")),
    ],
)
def test_typed_targets(query, expected):
    assert role_query(query) == expected


FAKE_APPS = [
    {"id": "gimp", "name": "GIMP", "aliases": ["gimp-3"], "apt": ["gimp"], "command": "gimp", "tips": "ctrl+shift+e"},
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "aliases": ["code", "vs code"],
        "deb": {"amd64": "https://example.com/code_amd64.deb"},
        "command": "code --no-sandbox",
    },
    {
        "id": "obsidian",
        "name": "Obsidian",
        "aliases": [],
        "github": {"repo": "o/releases", "amd64": r"_amd64\.deb$", "arm64": r"arm64\.AppImage$"},
        "command": "obsidian --no-sandbox",
    },
    {"id": "figma", "name": "Figma", "aliases": [], "url": "https://www.figma.com/files"},
    {
        "id": "photoshop",
        "name": "Adobe Photoshop",
        "aliases": [],
        "unavailable": "Photoshop does not run on Linux.",
        "alternatives": ["gimp", "figma"],
    },
]


@pytest.fixture
def fake_catalog(monkeypatch):
    monkeypatch.setattr(catalog, "APPS", FAKE_APPS)
    monkeypatch.setattr(catalog, "_index", {})
    monkeypatch.setattr(catalog, "arch", lambda: "amd64")


def test_catalog_lookup_by_id_name_alias_and_with_arguments(fake_catalog):
    assert catalog.find("VS Code")["id"] == catalog.find("vs-code")["id"] == catalog.find("code")["id"] == "vscode"
    assert catalog.find("Visual Studio Code")["id"] == "vscode"
    app, rest = catalog.lookup("gimp ~/Pictures/cat.png")
    assert app["id"] == "gimp" and rest == "~/Pictures/cat.png"
    assert catalog.lookup("ls -la") == (None, "ls -la")
    assert catalog.unavailable_message(catalog.find("photoshop")) == (
        "Photoshop does not run on Linux. Alternatives here: GIMP (open gimp), Figma (open figma)."
    )


def test_catalog_sources_per_method(fake_catalog, monkeypatch):
    assert catalog.sources(catalog.find("gimp")) == ["gimp"]
    assert catalog.sources(catalog.find("vscode")) == ["https://example.com/code_amd64.deb"]
    release = {
        "assets": [
            {"name": "obsidian_1.9_amd64.deb", "browser_download_url": "https://dl/obsidian_1.9_amd64.deb"},
            {"name": "Obsidian-1.9-arm64.AppImage", "browser_download_url": "https://dl/arm.AppImage"},
        ]
    }
    monkeypatch.setattr(
        catalog.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(json.dumps(release).encode())
    )
    assert catalog.sources(catalog.find("obsidian")) == ["https://dl/obsidian_1.9_amd64.deb"]
    monkeypatch.setattr(catalog, "arch", lambda: "arm64")
    with pytest.raises(catalog.InstallError, match="arm64"):
        catalog.sources(catalog.find("vscode"))  # no arm64 build listed
    with pytest.raises(catalog.InstallError, match="cannot be installed"):
        catalog.sources(catalog.find("figma"))


def test_installed_checks_the_command(fake_catalog, monkeypatch, tmp_path):
    monkeypatch.setattr(catalog.shutil, "which", lambda name: "/usr/bin/gimp" if name == "gimp" else None)
    assert catalog.installed(catalog.find("gimp")) and not catalog.installed(catalog.find("vscode"))
    exe = tmp_path / "Postman"
    app = {"id": "postman", "command": f"{exe.as_posix()} --flag"}  # (commands are POSIX shell words)
    assert not catalog.installed(app)
    exe.write_text("")
    assert catalog.installed(app)


def test_installing_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("MINION_AUTO_INSTALL", "0")
    with pytest.raises(catalog.InstallError, match="turned off"):
        catalog.install(["gimp"])
    assert not catalog.apt_package("gimp")


def test_java_apps_get_the_accessibility_bridge(monkeypatch):
    monkeypatch.delenv("JAVA_TOOL_OPTIONS", raising=False)
    monkeypatch.setattr(catalog.os.path, "exists", lambda p: p == catalog.JAVA_ATK)
    assert "AtkWrapper" in catalog.launch_env()["JAVA_TOOL_OPTIONS"]
    monkeypatch.setattr(catalog.os.path, "exists", lambda p: False)
    assert "JAVA_TOOL_OPTIONS" not in catalog.launch_env()


def test_cli_maps_this_machines_home_to_the_desktops(monkeypatch):
    from minion import cli

    monkeypatch.setattr(cli.os.path, "expanduser", lambda p: "/Users/ada" if p == "~" else p)
    assert cli.desktop_path("/Users/ada/Documents/x.pdf") == "~/Documents/x.pdf"  # the shell expanded ~
    assert cli.desktop_path("/Users/adam/x.pdf") == "/Users/adam/x.pdf"
    assert cli.desktop_path("/tmp/x.pdf") == "/tmp/x.pdf"
    assert cli.desktop_path("~/x.pdf") == "~/x.pdf"


def test_downloads_are_named_and_typed_like_what_they_are(tmp_path, monkeypatch):
    from minion.agent import install

    class Response(io.BytesIO):
        def __init__(self, data, final, headers):
            super().__init__(data)
            self.final, self.headers = final, headers

        def geturl(self):
            return self.final

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    responses = {
        "https://x/latest/stable": Response(b"!<arch>\ndebian-binary...", "https://cdn/code_1.99_amd64.deb", {}),
        "https://x/dl?platform=linux": Response(b"\x1f\x8b...", "https://x/dl?platform=linux", {}),
        "https://x/get": Response(
            b"zip", "https://x/get", {"Content-Disposition": 'attachment; filename="App-1.2.zip"'}
        ),
    }
    monkeypatch.setattr(install.urllib.request, "urlopen", lambda req, timeout: responses[req.full_url])
    assert install.download("https://x/latest/stable", tmp_path).name == "code_1.99_amd64.deb"  # the redirect's name
    assert install.download("https://x/get", tmp_path).name == "App-1.2.zip"  # Content-Disposition
    plain = install.download("https://x/dl?platform=linux", tmp_path)
    assert plain.name == "dl" and install.sniff(plain).name == "dl.tar.gz"  # no name at all: by its first bytes
    image = tmp_path / "Obsidian"
    image.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\x00" * 60)
    assert install.sniff(image).name == "Obsidian.AppImage"
    other = tmp_path / "notes"
    other.write_bytes(b"just text")
    assert install.sniff(other) == other


def test_catalog_downloads_get_the_name_their_command_expects():
    assert catalog.install_name({"id": "obsidian", "command": "obsidian --no-sandbox"}) == "obsidian"
    assert (
        catalog.install_name({"id": "postman", "command": "~/apps/postman/Postman/Postman --no-sandbox"}) == "postman"
    )
    assert catalog.install_name({"id": "x", "command": "/opt/x/bin/x"}) == "x"


class _Win:
    def __init__(self, wid):
        self.id = wid


class _Windows:
    """Window lists over time: the dialog shows up on the third look."""

    def __init__(self):
        self.calls = 0

    def list(self, with_states=True):
        self.calls += 1
        return [_Win("calc")] + ([_Win("chart wizard")] if self.calls >= 3 else [])


def test_menu_waits_for_the_dialog_an_ellipsis_command_opens(monkeypatch):
    from minion.agent.server import Agent

    agent = object.__new__(Agent)
    agent.windows = _Windows()
    agent._focused_a11y = lambda: (None, {"node": "calc"})
    monkeypatch.setattr(a11y, "find_menu_path", lambda window, parts, check_enabled=True: ["Insert", "Chart..."])
    monkeypatch.setattr(a11y, "opens_dialog", lambda node: node.endswith("..."))
    monkeypatch.setattr(a11y, "press_menu", lambda nodes: True)
    monkeypatch.setattr(a11y, "enabled", lambda node: True)
    assert agent._menu("Insert > Chart") == "chose Insert > Chart"
    assert agent.windows.calls == 3  # it looked until the dialog was there

    agent.windows = _Windows()
    monkeypatch.setattr(a11y, "find_menu_path", lambda window, parts, check_enabled=True: ["Edit", "Undo"])
    assert agent._menu("Edit > Undo") == "chose Edit > Undo"
    assert agent.windows.calls == 0  # a plain command doesn't wait


class _Focus:
    """The focused window over time: the app, the app again, then the Save dialog."""

    def __init__(self, ids):
        self.ids, self.calls = list(ids), 0

    def focused(self):
        self.calls += 1
        wid = self.ids[min(self.calls, len(self.ids)) - 1]
        if wid is None:
            return None
        w = _Win(wid)
        w.title, w.pid, w.x, w.y, w.w, w.h = wid, 1, 0, 0, 100, 100
        return w


def test_path_waits_for_the_file_dialog_to_take_the_focus(monkeypatch):
    from minion.agent import server
    from minion.agent.server import Agent

    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(a11y, "AVAILABLE", True)
    monkeypatch.setattr(a11y, "window_for", lambda w: {"role": "frame" if w.title == "calc" else "file chooser"})
    agent = object.__new__(Agent)
    agent.windows = _Focus(["calc", None, "calc", "save"])  # ctrl+s was pressed a moment ago
    agent._await_dialog()
    assert agent.windows.calls == 4  # it waited for the dialog

    agent.windows = _Focus(["save"])
    agent._await_dialog()
    assert agent.windows.calls == 1  # a dialog has the focus already
