"""Apps by name: find them, install them the first time, and launch them.

`open gimp` on a desktop without GIMP installs it (Debian package, a .deb, an AppImage or an archive,
from a stable "latest" URL or the newest GitHub release) and then starts it. Web apps open in the
browser, and apps that don't exist on Linux come back with alternatives. Any other name that is a
Debian package works too. The list of apps is catalog_data.py.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

try:
    from .catalog_data import APPS
except ImportError:  # pragma: no cover - a desktop image from before the catalog
    APPS: list[dict] = []

INSTALL_TIMEOUT = 600.0  # seconds: big apps (LibreOffice, Blender) take a few minutes on a slow link
JAVA_ATK = "/usr/share/java/java-atk-wrapper.jar"


class InstallError(Exception):
    """An app could not be installed; the message says why and what to try."""


def _key(name: str) -> str:
    """ "VS Code", "vs-code" and "vscode" are the same app."""
    return re.sub(r"[^a-z0-9+#]+", "", name.lower())


_index: dict[str, dict] = {}


def find(name: str) -> dict | None:
    """The catalog entry for an app id, name or alias, or None."""
    if not _index:
        for app in APPS:
            for n in (app["id"], app.get("name", ""), *app.get("aliases", ())):
                if n:
                    _index.setdefault(_key(n), app)
    return _index.get(_key(name)) if name else None


def lookup(target: str) -> tuple[dict | None, str]:
    """(entry, the rest of the command) for `open TARGET`: "gimp ~/a.png" -> (GIMP, "~/a.png")."""
    app = find(target)
    if app:
        return app, ""
    words = target.split()
    for n in range(len(words) - 1, 0, -1):  # the longest leading name: "google chrome https://x" -> Chrome
        app = find(" ".join(words[:n]))
        if app:
            return app, " ".join(words[n:])
    return None, target


def arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("aarch64", "arm64") else "amd64"


def executable(app: dict) -> str:
    return os.path.expanduser(shlex.split(app["command"])[0])


def installed(app: dict) -> bool:
    exe = executable(app)
    return os.path.exists(exe) if "/" in exe else shutil.which(exe) is not None


def tips(app: dict) -> str:
    return app.get("tips", "")


def describe(app: dict) -> str:
    return f"{app.get('name', app['id'])} (open {app['id']})"


def alternatives(app: dict) -> str:
    alts = [find(a) for a in app.get("alternatives", ())]
    return ", ".join(describe(a) for a in alts if a)


def unavailable_message(app: dict) -> str:
    alts = alternatives(app)
    return app["unavailable"] + (f" Alternatives here: {alts}." if alts else "")


def _latest_asset(spec: dict) -> str:
    pattern = spec.get(arch())
    if not pattern:
        raise InstallError(f"no build for this computer's CPU ({arch()})")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{spec['repo']}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "minion-install"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            assets = json.load(r).get("assets", [])
    except OSError as e:
        raise InstallError(f"could not look up the newest release of {spec['repo']} ({e})") from e
    for asset in assets:
        if re.search(pattern, asset.get("name", "")):
            return asset["browser_download_url"]
    raise InstallError(f"the newest release of {spec['repo']} has no download for {arch()}")


def sources(app: dict) -> list[str]:
    """The arguments for minion-install: Debian package names, or one download URL for this CPU."""
    if app.get("apt"):
        return list(app["apt"])
    if app.get("deb"):
        url = app["deb"].get(arch())
        if not url:
            raise InstallError(f"{app.get('name', app['id'])} has no build for this computer's CPU ({arch()})")
        return [url]
    if app.get("github"):
        return [_latest_asset(app["github"])]
    raise InstallError(f"{app.get('name', app['id'])} cannot be installed here")


def install_name(app: dict) -> str:
    """What minion-install should call a download: the command an AppImage becomes ("obsidian"), or
    the ~/apps folder an archive is unpacked to (as the app's command expects)."""
    exe = shlex.split(app["command"])[0]
    if "/" not in exe:
        return exe
    m = re.match(r"(?:~|\$HOME)/apps/([^/]+)/", exe)
    return m.group(1) if m else app["id"]


def install_app(app: dict, timeout: float = INSTALL_TIMEOUT) -> tuple[float, str]:
    """Install a catalog app; returns (seconds, log path)."""
    targets = sources(app)
    if not app.get("apt"):
        targets = ["--name", install_name(app), *targets]
    took = install(targets, timeout)
    configure(app)
    return took


def configure(app: dict) -> None:
    """Write an app's settings files (e.g. no welcome dialog at every start) unless the user has their own."""
    for path, text in (app.get("files") or {}).items():
        target = Path(os.path.expanduser(path))
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        except OSError:
            pass


def _runtime() -> Path:
    return Path(os.environ.get("MINION_RUNTIME_DIR", "/tmp/minion"))


def install(targets: list[str], timeout: float = INSTALL_TIMEOUT) -> tuple[float, str]:
    """Run minion-install for `targets`; returns (seconds, log path). Raises InstallError with the log's tail."""
    if os.environ.get("MINION_AUTO_INSTALL", "1") == "0":
        raise InstallError("installing apps is turned off in this desktop (MINION_AUTO_INSTALL=0)")
    log_path = _runtime() / f"install-{time.time_ns() // 1_000_000}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with open(log_path, "ab") as log:
        try:
            res = subprocess.run(
                ["python3", "-m", "minion_agent.install", *targets],
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise InstallError(f"installing took longer than {timeout:.0f}s (log: {log_path})") from e
    if res.returncode != 0:
        tail = log_path.read_text(errors="replace").strip().splitlines()[-3:]
        hint = " ".join(tail)
        if re.search(
            r"Temporary failure resolving|Could not resolve|Network is unreachable|Name or service not known", hint
        ):
            hint = "this desktop has no internet access (was it created with --offline?)"
        raise InstallError(f"installing failed: {hint[-300:]} (log: {log_path})")
    return time.monotonic() - t0, str(log_path)


def _apt_lists_ready() -> None:
    """Debian package lists are left out of the images to keep them small: fetch them once per desktop."""
    stamp = _runtime() / "apt-lists"
    if stamp.exists():
        return
    res = subprocess.run(
        ["sudo", "-n", "apt-get", "update", "-qq"], capture_output=True, timeout=180, stdin=subprocess.DEVNULL
    )
    if res.returncode == 0:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()


def apt_package(name: str) -> bool:
    """Is `name` a Debian package that can be installed here?"""
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]{1,60}", name) or os.environ.get("MINION_AUTO_INSTALL", "1") == "0":
        return False
    try:
        _apt_lists_ready()
        res = subprocess.run(["apt-cache", "policy", name], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    m = re.search(r"Candidate:\s*(\S+)", res.stdout)
    return bool(m and m.group(1) != "(none)")


def launch_env() -> dict:
    """The environment for apps: Java apps expose their UI to the accessibility tree when the ATK
    wrapper is installed (libatk-wrapper-java-jni)."""
    env = dict(os.environ)
    if os.path.exists(JAVA_ATK) and "AtkWrapper" not in env.get("JAVA_TOOL_OPTIONS", ""):
        flag = "-Djavax.accessibility.assistive_technologies=org.GNOME.Accessibility.AtkWrapper"
        env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") + " " + flag).strip()
    return env
