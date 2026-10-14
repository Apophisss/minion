"""`minion doctor`: check the setup and say exactly how to fix what's missing."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys

from . import __version__, config, profiles
from .backends import get_backend


def _check(results: list, ok: bool, what: str, fix: str = "", level: str = "error") -> None:
    results.append({"ok": ok, "check": what, "fix": "" if ok else fix, "level": "ok" if ok else level})


def run_checks(json_out: bool = False) -> int:
    results: list[dict] = []
    _check(results, sys.version_info >= (3, 11), f"Python {platform.python_version()}",
           "Minion needs Python 3.11 or newer.")
    backend = get_backend()
    ok, detail = backend.available()
    _check(results, ok, f"backend: {backend.name} ({detail})",
           "Start Docker Desktop / the Docker daemon, or install Docker: https://docs.docker.com/get-docker/ "
           "(Linux without Docker: MINION_BACKEND=local)." if backend.name == "docker" else detail)
    if backend.name == "docker" and ok:
        have = []
        for name in profiles.names():
            p = profiles.get(name)
            if backend.image_labels(p.image) is not None:
                have.append(name)
        _check(results, bool(have), f"images ready: {', '.join(have) or 'none yet'}",
               "Images download on first use; prepare ahead with `minion pull browser office`.", level="info")
    if backend.name == "local":
        from .backends.local import missing_tools

        missing = missing_tools()
        _check(results, not missing, "local desktop tools (Xvfb, xdotool, wmctrl, jwm, Pillow)",
               "Install: sudo apt-get install -y " + " ".join(missing))
    _check(results, shutil.which("uvx") is not None or shutil.which("pipx") is not None,
           "uvx/pipx available (for `uvx minion-desktop mcp` in MCP configs)",
           "Optional: install uv (https://docs.astral.sh/uv/) to run Minion without installing it.", level="info")
    if json_out:
        print(json.dumps({"version": __version__, "backend": backend.name, "checks": results}, indent=2))
    else:
        print(f"minion {__version__} · {platform.system()} {platform.machine()} · config: {config.config_dir()}")
        tty = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        paint = (lambda t, code: f"\033[{code}m{t}\033[0m") if tty else (lambda t, code: t)
        for r in results:
            mark = paint("✓", 32) if r["ok"] else (paint("•", 33) if r["level"] == "info" else paint("✗", 31))
            print(f" {mark} {r['check']}")
            if r["fix"]:
                print(f"     → {r['fix']}")
    return 0 if all(r["ok"] or r["level"] == "info" for r in results) else 1


def _which_python_with(modules: list[str]) -> str | None:
    """A python3 on this host that can import all `modules` (the local backend needs one)."""
    candidates = [sys.executable, shutil.which("python3"), "/usr/bin/python3"]
    for py in dict.fromkeys(c for c in candidates if c and os.path.exists(c)):
        code = "; ".join(f"import {m}" for m in modules)
        try:
            if subprocess.run([py, "-c", code], capture_output=True, timeout=20).returncode == 0:
                return py
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None
