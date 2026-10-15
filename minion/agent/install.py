"""minion-install: get any Linux software into this desktop with one command.

minion-install gimp inkscape                       # Debian packages (apt)
minion-install https://example.com/tool.deb        # a .deb from the web
minion-install https://example.com/App.AppImage    # an AppImage (runs without FUSE)
minion-install https://example.com/tool.tar.gz     # an archive: unpacked to ~/apps/<name>
minion-install pip:yt-dlp                          # a Python CLI or library in its own virtualenv (importable)
minion-install npm:prettier                        # a Node.js CLI (installs Node if needed)
minion-install --name obsidian https://…/App.AppImage   # choose the command (or ~/apps folder) name
"""

from __future__ import annotations

import http.client
import os
import re
import shlex
import stat
import subprocess
import sys
import time
import urllib.error
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


def download(url: str, folder: Path, attempts: int = 4) -> Path:
    """Download into `folder`, named as the server names it: "latest" URLs often redirect to the real
    file name, or give it in Content-Disposition. Big downloads get cut off now and then: they are
    resumed where they stopped (or restarted) up to `attempts` times."""
    print(f"downloading {url}", flush=True)
    dest, final = None, url
    for attempt in range(1, attempts + 1):
        have = dest.stat().st_size if dest is not None and dest.exists() else 0
        headers = {"User-Agent": "minion-install", **({"Range": f"bytes={have}-"} if have else {})}
        try:
            with urllib.request.urlopen(urllib.request.Request(final, headers=headers), timeout=300) as r:
                if dest is None:
                    disposition = r.headers.get("Content-Disposition") or ""
                    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition, re.I)
                    name = urllib.parse.unquote(m.group(1)) if m else ""
                    name = Path(name).name or Path(urllib.parse.urlparse(r.geturl()).path).name
                    name = name or Path(urllib.parse.urlparse(url).path).name or "download"
                    dest, final = folder / name, r.geturl()
                resume = have and r.status == 206
                with open(dest, "ab" if resume else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            return dest
        except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as e:
            reason = getattr(e, "reason", e)
            if attempt == attempts or "Name or service not known" in str(reason) or "resolv" in str(reason):
                raise
            print(f"download interrupted ({reason}); trying again ({attempt}/{attempts - 1})", flush=True)
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


MAGIC = [  # what a download really is, when its name doesn't say
    (b"!<arch>\ndebian-binary", ".deb"),
    (b"\x1f\x8b", ".tar.gz"),
    (b"\xfd7zXZ\x00", ".tar.xz"),
    (b"BZh", ".tar.bz2"),
    (b"PK\x03\x04", ".zip"),
]
KNOWN = (".deb", ".appimage", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".zip", ".exe", ".msi")
GUI_LIBS = ["libgtk-3-0t64", "libnss3", "libasound2t64"]  # what AppImages and Electron apps expect of the system


def sniff(path: Path) -> Path:
    """Give an extension-less download the extension of what it is (by its first bytes)."""
    if path.name.lower().endswith(KNOWN):
        return path
    with open(path, "rb") as f:
        head = f.read(64)
    ext = next((e for magic, e in MAGIC if head.startswith(magic)), "")
    if not ext and head.startswith(b"\x7fELF") and head[8:11] == b"AI\x02":
        ext = ".AppImage"
    if not ext:
        return path
    new = path.with_name(path.name + ext)
    path.replace(new)
    return new


def gui_libs() -> None:
    """Install the GUI libraries self-contained apps take from the system, if any are missing."""
    missing = [
        p for p in GUI_LIBS if subprocess.call(["dpkg", "-s", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ]
    if missing:
        install_apt(missing)


def wrapper(name: str, command: str) -> Path:
    ensure_bin()
    path = BIN / name
    path.write_text(f'#!/bin/sh\nexec {command} "$@"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def install_apt(packages: list[str]) -> int:
    """apt-get, quietly: its progress goes to a log; only what went wrong (and a last line) is printed."""
    quoted = " ".join(shlex.quote(p) for p in packages)
    log = Path(os.environ.get("MINION_RUNTIME_DIR", "/tmp")) / "minion-install-apt.log"
    t0 = time.monotonic()
    code = sh(
        f"(sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q {quoted}) "
        f"> {shlex.quote(str(log))} 2>&1"
    )
    if code != 0:
        tail = log.read_text(errors="replace").strip().splitlines()[-8:] if log.exists() else []
        print("\n".join(tail))
    else:
        print(f"installed {' '.join(packages)} ({time.monotonic() - t0:.0f}s)")
    return code


def install_url(url: str, as_name: str = "") -> int:
    """Install a download: a .deb, an AppImage (a command named `as_name`, or after the file), or an
    archive (unpacked to ~/apps/`as_name`, or the file's name)."""
    downloads = HOME / "Downloads"
    downloads.mkdir(exist_ok=True)
    dest = sniff(download(url, downloads))
    name = dest.name
    low = name.lower()
    if low.endswith(".deb"):
        lists = Path("/var/lib/apt/lists")  # (left out of the images): its dependencies need them
        update = "" if any(lists.glob("*_Packages*")) else "sudo apt-get update -qq && "
        return sh(f"{update}sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(str(dest))}")
    if low.endswith(".appimage"):
        apps = HOME / "Applications"
        apps.mkdir(exist_ok=True)
        target = apps / name
        dest.replace(target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        gui_libs()
        cmd_name = as_name or re.sub(r"[-_.]?(x86_64|amd64|aarch64|arm64)?\.appimage$", "", low, flags=re.I) or "app"
        w = wrapper(cmd_name, f"env APPIMAGE_EXTRACT_AND_RUN=1 {shlex.quote(str(target))}")
        print(f"installed: {w} (run it with `{cmd_name}` or `open {cmd_name}`)")
        return 0
    if re.search(r"\.(tar\.gz|tgz|tar\.xz|tar\.bz2|zip)$", low):
        stem = as_name or re.sub(r"\.(tar\.gz|tgz|tar\.xz|tar\.bz2|zip)$", "", name)
        target = HOME / "apps" / stem
        target.mkdir(parents=True, exist_ok=True)
        if low.endswith(".zip"):
            code = sh(f"cd {shlex.quote(str(target))} && python3 -m zipfile -e {shlex.quote(str(dest))} .")
        else:
            code = sh(f"tar -xf {shlex.quote(str(dest))} -C {shlex.quote(str(target))}")
        if code == 0:
            gui_libs()
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
        # A library (openpyxl, python-docx, pandas) is for `import` in the desktop's own python3: point its user
        # site-packages at the virtualenv's (a .pth file), so it imports without touching the system's Python.
        site = subprocess.run(
            ["python3", "-c", "import site; print(site.getusersitepackages())"], capture_output=True, text=True
        ).stdout.strip()
        found = sorted(venv.glob("lib/python3*/site-packages"))
        if site and found:
            Path(site).mkdir(parents=True, exist_ok=True)
            # (appended to sys.path, so the system's own packages keep their place before the virtualenv's)
            (Path(site) / f"minion-{venv.name}.pth").write_text(f"import sys; sys.path.append({str(found[-1])!r})\n")
            print(f"importable from python3: {pkg}")
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
    as_name = ""
    if args[0] == "--name" and len(args) > 2:
        as_name, args = args[1], args[2:]
    for a in args:
        if a.startswith(("http://", "https://")):
            code |= install_url(a, as_name)
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
