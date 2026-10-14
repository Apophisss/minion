"""minion-install: get any Linux software into this desktop with one command.

minion-install gimp inkscape                       # Debian packages (apt)
minion-install https://example.com/tool.deb        # a .deb from the web
minion-install https://example.com/App.AppImage    # an AppImage (runs without FUSE)
minion-install https://example.com/tool.tar.gz     # an archive: unpacked to ~/apps/<name>
minion-install pip:yt-dlp                          # a Python CLI in its own virtualenv
minion-install npm:prettier                        # a Node.js CLI (installs Node if needed)
"""

from __future__ import annotations

import os
import re
import shlex
import stat
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
BIN = HOME / ".local" / "bin"


def sh(cmd: str) -> int:
    print(f"$ {cmd}", flush=True)
    return subprocess.call(["bash", "-lc", cmd])


def ensure_bin() -> None:
    BIN.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path) -> Path:
    print(f"downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "minion-install"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest


def wrapper(name: str, command: str) -> Path:
    ensure_bin()
    path = BIN / name
    path.write_text(f'#!/bin/sh\nexec {command} "$@"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def install_apt(packages: list[str]) -> int:
    quoted = " ".join(shlex.quote(p) for p in packages)
    return sh(f"sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {quoted}")


def install_url(url: str) -> int:
    name = Path(urllib.parse.urlparse(url).path).name or "download"
    downloads = HOME / "Downloads"
    downloads.mkdir(exist_ok=True)
    dest = download(url, downloads / name)
    low = name.lower()
    if low.endswith(".deb"):
        return sh(f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(str(dest))}")
    if low.endswith(".appimage"):
        apps = HOME / "Applications"
        apps.mkdir(exist_ok=True)
        target = apps / name
        dest.replace(target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        cmd_name = re.sub(r"[-_.]?(x86_64|amd64|aarch64|arm64)?\.appimage$", "", low, flags=re.I) or "app"
        w = wrapper(cmd_name, f"env APPIMAGE_EXTRACT_AND_RUN=1 {shlex.quote(str(target))}")
        print(f"installed: {w} (run it with `{cmd_name}` or `open {cmd_name}`)")
        return 0
    if re.search(r"\.(tar\.gz|tgz|tar\.xz|tar\.bz2|zip)$", low):
        stem = re.sub(r"\.(tar\.gz|tgz|tar\.xz|tar\.bz2|zip)$", "", name)
        target = HOME / "apps" / stem
        target.mkdir(parents=True, exist_ok=True)
        if low.endswith(".zip"):
            code = sh(f"cd {shlex.quote(str(target))} && python3 -m zipfile -e {shlex.quote(str(dest))} .")
        else:
            code = sh(f"tar -xf {shlex.quote(str(dest))} -C {shlex.quote(str(target))}")
        if code == 0:
            found = [p for p in target.rglob("*") if p.is_file() and os.access(p, os.X_OK)][:10]
            print(f"unpacked to {target}")
            for p in found:
                print(f"  executable: {p}")
        return code
    if low.endswith((".exe", ".msi")):
        print("Windows program: use the `windows` profile (Wine) and run: wine " + str(dest))
        return 0
    print(f"downloaded to {dest} (unknown type: install it manually)")
    return 0


def install_pip(pkg: str) -> int:
    if subprocess.call(["python3", "-c", "import ensurepip"], stderr=subprocess.DEVNULL) != 0:
        if install_apt(["python3-venv"]) != 0:  # Debian splits venv support into its own package
            return 1
    venv = HOME / ".local" / "venvs" / re.sub(r"[^A-Za-z0-9_.-]", "_", pkg)
    code = sh(
        f"python3 -m venv {shlex.quote(str(venv))} && {shlex.quote(str(venv))}/bin/pip install -q {shlex.quote(pkg)}"
    )
    if code == 0:
        ensure_bin()
        for exe in (venv / "bin").iterdir():
            if exe.name in ("python", "python3", "pip", "pip3") or exe.name.lower().startswith(
                ("activate", "python3.", "pip3.")
            ):
                continue  # the venv's own tools (and Activate.ps1), not the package's commands
            link = BIN / exe.name
            if not link.exists():
                link.symlink_to(exe)
                print(f"installed: {link}")
    return code


def install_npm(pkg: str) -> int:
    if subprocess.call(["bash", "-lc", "command -v npm >/dev/null"]) != 0:
        if install_apt(["nodejs", "npm"]) != 0:
            return 1
    return sh(f"sudo npm install -g {shlex.quote(pkg)}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    apt: list[str] = []
    code = 0
    for a in args:
        if a.startswith(("http://", "https://")):
            code |= install_url(a)
        elif a.startswith("pip:"):
            code |= install_pip(a[4:])
        elif a.startswith("npm:"):
            code |= install_npm(a[4:])
        else:
            apt.append(a)
    if apt:
        code |= install_apt(apt)
    return code


if __name__ == "__main__":
    sys.exit(main())
