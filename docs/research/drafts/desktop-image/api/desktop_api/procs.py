"""Shell commands, app launching and window listing for the desktop user."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from typing import Any

from .computer import ActionError

DISPLAY = os.environ.get("DISPLAY", ":1")
HOME = os.path.expanduser("~")
LOG_DIR = os.environ.get("APP_LOG_DIR", "/tmp/desktop-api/apps")
MAX_OUTPUT = int(os.environ.get("BASH_MAX_OUTPUT", str(64 * 1024)))
DEFAULT_BROWSER = os.environ.get("DEFAULT_BROWSER", "chromium")

# Logical app names -> argv. Chromium flags (--no-sandbox etc.) live in /etc/chromium.d/.
APPS: dict[str, list[str]] = {
    "chromium": ["chromium"],
    "firefox": ["firefox-esr"],
    "terminal": ["xfce4-terminal"],
    "xterm": ["xterm"],
    "editor": ["mousepad"],
    "mousepad": ["mousepad"],
    "files": ["pcmanfm"],
    "libreoffice": ["libreoffice"],
    "writer": ["libreoffice", "--writer"],
    "calc": ["libreoffice", "--calc"],
    "impress": ["libreoffice", "--impress"],
}
_APP_ALIASES = {"chrome": "chromium", "google-chrome": "chromium", "firefox-esr": "firefox",
                "text-editor": "editor", "gedit": "editor", "file-manager": "files"}


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {**os.environ, "DISPLAY": DISPLAY, "HOME": HOME}
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def _truncate(b: bytes) -> tuple[str, bool]:
    if len(b) <= MAX_OUTPUT:
        return b.decode(errors="replace"), False
    head = b[: MAX_OUTPUT // 2].decode(errors="replace")
    tail = b[-MAX_OUTPUT // 2 :].decode(errors="replace")
    return f"{head}\n... [{len(b) - MAX_OUTPUT} bytes truncated] ...\n{tail}", True


async def run_bash(
    cmd: str,
    timeout: float = 60.0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    background: bool = False,
) -> dict[str, Any]:
    """Run `bash -c cmd` as the desktop user with DISPLAY set."""
    if not cmd or not cmd.strip():
        raise ActionError("'cmd' must be a non-empty string")
    cwd = cwd or HOME
    if background:
        os.makedirs(LOG_DIR, exist_ok=True)
        log = os.path.join(LOG_DIR, f"bash-{uuid.uuid4().hex[:8]}.log")
        with open(log, "ab") as fh:
            p = subprocess.Popen(["/bin/bash", "-c", cmd], cwd=cwd, env=_env(env), stdin=subprocess.DEVNULL,
                                 stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        return {"pid": p.pid, "log": log, "background": True}

    timeout = max(1.0, min(float(timeout), 3600.0))
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-c", cmd, cwd=cwd, env=_env(env),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # own process group so a timeout kills the whole tree
    )
    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = await proc.communicate()
    stdout, t1 = _truncate(out)
    stderr, t2 = _truncate(err)
    return {
        "exit_code": None if timed_out else proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "truncated": t1 or t2,
        "duration_s": round(time.monotonic() - t0, 3),
    }


async def list_windows() -> list[dict[str, Any]]:
    """Top-level managed windows via wmctrl -lpx."""
    proc = await asyncio.create_subprocess_exec(
        "wmctrl", "-lpx", env=_env(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await proc.communicate()
    windows = []
    for line in out.decode(errors="replace").splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        wid, desktop, pid, wm_class, _host = parts[:5]
        windows.append({
            "id": wid, "desktop": int(desktop), "pid": int(pid), "wm_class": wm_class,
            "title": parts[5] if len(parts) > 5 else "",
        })
    return windows


async def _wmctrl(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec("wmctrl", *args, env=_env(),
                                                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()


def resolve_app(app: str, args: list[str] | None = None) -> list[str]:
    name = _APP_ALIASES.get(app.strip().lower(), app.strip().lower())
    if name == "browser":
        candidates = [DEFAULT_BROWSER, "chromium", "firefox"]
        name = next((c for c in candidates if c in APPS and shutil.which(APPS[c][0])), DEFAULT_BROWSER)
    if name in APPS:
        argv = list(APPS[name])
        if not shutil.which(argv[0]):
            if name == "terminal" and shutil.which("xterm"):
                argv = ["xterm"]
            else:
                raise ActionError(f"App {app!r} ({argv[0]}) is not installed in this image")
    else:
        argv = shlex.split(app)
        if not argv or not shutil.which(argv[0]):
            known = ", ".join(sorted(k for k, v in APPS.items() if shutil.which(v[0])))
            raise ActionError(f"Unknown app {app!r}. Known apps: {known}, or any executable on PATH")
    return argv + [str(a) for a in (args or [])]


async def launch(
    argv: list[str], wait: bool = True, timeout: float = 20.0, maximize: bool = True
) -> dict[str, Any]:
    """Start a GUI program detached; optionally wait for a new window and maximize it."""
    os.makedirs(LOG_DIR, exist_ok=True)
    before = {w["id"] for w in await list_windows()}
    log = os.path.join(LOG_DIR, f"{os.path.basename(argv[0])}-{uuid.uuid4().hex[:8]}.log")
    with open(log, "ab") as fh:
        p = subprocess.Popen(argv, cwd=HOME, env=_env(), stdin=subprocess.DEVNULL, stdout=fh,
                             stderr=subprocess.STDOUT, start_new_session=True)
    result: dict[str, Any] = {"pid": p.pid, "argv": argv, "log": log, "window": None}
    if not wait:
        return result
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        await asyncio.sleep(0.4)
        new = [w for w in await list_windows() if w["id"] not in before]
        if new:
            # Prefer a window owned by the launched pid, else the newest one.
            win = next((w for w in new if w["pid"] == p.pid), new[-1])
            if maximize:
                await _wmctrl("-i", "-r", win["id"], "-b", "add,maximized_vert,maximized_horz")
            await _wmctrl("-i", "-a", win["id"])
            result["window"] = win
            return result
        if p.poll() is not None:
            # Process exited without a new window: typical when a running browser
            # receives the URL in a new tab of its existing window.
            result["exit_code"] = p.returncode
            result["note"] = "process exited without opening a new window (e.g. URL handed to a running instance)"
            return result
    result["note"] = f"no new window within {timeout:.0f}s (app may still be starting)"
    return result


async def open_target(
    url: str | None = None,
    app: str | None = None,
    args: list[str] | None = None,
    browser: str | None = None,
    wait: bool = True,
    timeout: float = 20.0,
    maximize: bool = True,
) -> dict[str, Any]:
    if bool(url) == bool(app):
        raise ActionError("Provide exactly one of 'url' or 'app'")
    if url:
        if "://" not in url and not url.startswith(("about:", "file:", "chrome:")):
            url = "https://" + url
        argv = resolve_app(browser or "browser", list(args or []) + [url])
    else:
        argv = resolve_app(app or "", args)
    return await launch(argv, wait=wait, timeout=timeout, maximize=maximize)
