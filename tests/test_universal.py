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
    app = {"id": "postman", "command": f"{exe} --flag"}
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
