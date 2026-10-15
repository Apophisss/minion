"""Schema checks for the app catalog data (offline and fast: no network, no Docker)."""

import re

import pytest

from minion.agent.catalog_data import APPS

METHODS = ("apt", "deb", "github", "url", "unavailable")
INSTALL_METHODS = ("apt", "deb", "github")
ARCHES = {"amd64", "arm64"}
KEYS = {"id", "name", "aliases", "command", "tips", "size_mb", "alternatives", *METHODS}
ID_RE = re.compile(r"^[a-z0-9-]+$")
DEBIAN_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IDS = {app["id"] for app in APPS}


def method(app: dict) -> str:
    return next(m for m in METHODS if m in app)


def test_ids_are_unique_and_well_formed():
    ids = [app["id"] for app in APPS]
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)
    assert all(ID_RE.match(i) for i in ids), [i for i in ids if not ID_RE.match(i)]


def test_aliases_are_lowercase_unique_and_never_an_id():
    seen: dict[str, str] = {}
    for app in APPS:
        assert isinstance(app["aliases"], list), app["id"]
        for alias in app["aliases"]:
            assert isinstance(alias, str) and alias, app["id"]
            assert alias == alias.lower() == alias.strip(), (app["id"], alias)
            assert alias not in IDS, f"alias {alias!r} of {app['id']} is also an id"
            assert alias not in seen, f"alias {alias!r} used by {seen.get(alias)} and {app['id']}"
            seen[alias] = app["id"]


@pytest.mark.parametrize("app", APPS, ids=lambda a: a["id"])
def test_entry_shape(app):
    assert set(app) <= KEYS, f"unknown keys: {set(app) - KEYS}"
    assert isinstance(app["name"], str) and app["name"].strip()
    assert [m for m in METHODS if m in app] == [method(app)], "exactly one of apt/deb/github/url/unavailable"
    if method(app) in INSTALL_METHODS:
        assert isinstance(app.get("command"), str) and app["command"].strip(), "install entries need a command"
    else:
        assert "command" not in app and "size_mb" not in app
    if "size_mb" in app:
        assert type(app["size_mb"]) is int and app["size_mb"] > 0
    if "tips" in app:
        assert isinstance(app["tips"], str) and app["tips"].strip()
        assert len(app["tips"]) <= 300, f"tips are {len(app['tips'])} characters"


def test_apt_packages():
    for app in (a for a in APPS if "apt" in a):
        assert isinstance(app["apt"], list) and app["apt"], app["id"]
        assert all(DEBIAN_PACKAGE_RE.match(p) for p in app["apt"]), app["id"]


def test_deb_urls_per_architecture():
    for app in (a for a in APPS if "deb" in a):
        deb = app["deb"]
        assert isinstance(deb, dict) and deb and set(deb) <= ARCHES, app["id"]
        assert all(isinstance(u, str) and u.startswith("https://") for u in deb.values()), app["id"]


def test_github_entries():
    for app in (a for a in APPS if "github" in a):
        gh = app["github"]
        assert set(gh) <= {"repo", *ARCHES}, app["id"]
        assert GITHUB_REPO_RE.match(gh.get("repo", "")), app["id"]
        arches = set(gh) & ARCHES
        assert arches, f"{app['id']}: no architecture"
        for arch in arches:
            re.compile(gh[arch])  # raises if the pattern is invalid


def test_web_apps_use_https():
    for app in (a for a in APPS if "url" in a):
        assert app["url"].startswith("https://"), app["id"]


def test_unavailable_entries_point_to_real_alternatives():
    for app in APPS:
        alternatives = app.get("alternatives", [])
        if "unavailable" in app:
            assert isinstance(app["unavailable"], str) and app["unavailable"].strip(), app["id"]
            assert alternatives, f"{app['id']}: suggest at least one alternative"
        for alt in alternatives:
            assert alt in IDS, f"{app['id']}: unknown alternative {alt!r}"
            assert alt != app["id"]
            assert "unavailable" not in next(a for a in APPS if a["id"] == alt), f"{app['id']}: {alt} is unavailable"


def test_unpacked_archives_run_from_their_own_folder():
    # A .tar.gz is unpacked to ~/apps/<id>, so its command is the path of the program in there.
    for app in APPS:
        command = app.get("command", "")
        sources = [*app.get("deb", {}).values(), *(v for k, v in app.get("github", {}).items() if k != "repo")]
        if command.startswith(("~/apps/", "$HOME/apps/")) or any(re.search(r"tar\W*gz", s) for s in sources):
            assert command.startswith(f"~/apps/{app['id']}/"), app["id"]


def test_the_apps_page_is_up_to_date():
    """docs/apps.md is generated from the catalog: regenerate it with scripts/gen_apps_doc.py."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "gen_apps_doc.py"
    spec = importlib.util.spec_from_file_location("gen_apps_doc", script)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert gen.DOC.read_text() == gen.render(), "run: python scripts/gen_apps_doc.py"
