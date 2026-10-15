"""Drive this desktop from Python running *inside* it.

This is what the `script` tool runs: an agent sends a short program instead of dozens of
tool calls, and only what the program prints goes back to the model.

    from minion_agent.client import *
    launch("calc")
    for value in [3.5, 2.25, 4]:
        write(f"{value}\\n")              # one cell per line
    write("=SUM(A1:A3)\\n")
    print(cells())                          # {"A1": "3.5", "A2": "2.25", "A3": "4", "A4": "9.75"}

Names avoid shadowing Python builtins: use `write` (not type) and `launch` (not open).
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import threading
import time

__all__ = [
    "see",
    "look",
    "elements",
    "find",
    "cells",
    "formulas",
    "act",
    "click",
    "double_click",
    "right_click",
    "move",
    "drag",
    "write",
    "paste",
    "key",
    "hold_key",
    "scroll",
    "fill",
    "select",
    "menu",
    "menus",
    "path",
    "read",
    "convert",
    "wait",
    "wait_for",
    "launch",
    "run",
    "screenshot",
    "windows",
    "focus",
    "clipboard",
    "MinionScriptError",
]


class MinionScriptError(Exception):
    pass


class _Conn:
    def __init__(self) -> None:
        path = os.environ.get("MINION_SOCKET") or os.path.join(
            os.environ.get("MINION_RUNTIME_DIR", "/tmp/minion"), "agent.sock"
        )
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.file = self.sock.makefile("rb")
        self.ids = itertools.count(1)
        self.lock = threading.Lock()

    def call(self, method: str, params: dict | None = None):
        with self.lock:
            rid = next(self.ids)
            self.sock.sendall((json.dumps({"id": rid, "method": method, "params": params or {}}) + "\n").encode())
            while True:
                line = self.file.readline()
                if not line:
                    raise MinionScriptError("the desktop agent closed the connection")
                msg = json.loads(line)
                if msg.get("id") == rid:
                    break
        if msg.get("error"):
            raise MinionScriptError(msg["error"].get("message", "error"))
        return msg.get("result")


_conn: _Conn | None = None


def _call(method: str, params: dict | None = None):
    global _conn
    if _conn is None:
        _conn = _Conn()
    return _conn.call(method, params)


# -- looking --------------------------------------------------------------------
def look(ocr="auto", window: str | None = None, full_text: bool = False, changes: bool = False) -> dict:
    """The full `see` result: text, elements, windows, focused, ocr."""
    return _call("see", {"ocr": ocr, "window": window, "full_text": full_text, "changes": changes})


def see(ocr="auto", window: str | None = None, full_text: bool = False, changes: bool = False) -> str:
    """The screen as text (windows + UI elements with @ids)."""
    return look(ocr, window, full_text, changes)["text"]


def elements(role: str | None = None, name: str | None = None) -> list[dict]:
    """UI elements of the focused window, optionally filtered by role and (substring of) name."""
    out = look()["elements"]
    if role:
        out = [e for e in out if e["role"] == role]
    if name:
        out = [e for e in out if name.casefold() in (e.get("name") or e.get("text") or "").casefold()]
    return out


def find(text: str) -> list[dict]:
    return _call("find", {"text": text})["matches"]


def formulas() -> dict[str, str]:
    """Formulas of the visible spreadsheet cells: {"B7": "=SUM(B2:B6)", ...}. A cell whose formula
    failed reads "#ERROR" in cells()."""
    return {
        e["name"]: e["value"] for e in look()["elements"] if e["role"] == "cell" and e.get("value", "").startswith("=")
    }


def cells() -> dict[str, str]:
    """Visible spreadsheet cells: {"A1": "Item", "B1": "Price", ...}. Right after typing, a sheet can
    take a moment to report its cells, so an empty result is retried briefly."""
    for attempt in range(4):
        found = {e["name"]: e.get("text", "") for e in look()["elements"] if e["role"] == "cell"}
        if found or attempt == 3:
            return found
        time.sleep(0.4)
    return {}


# -- acting -----------------------------------------------------------------------
def act(*actions, check: bool = True) -> str:
    """Run actions ({"click": "@3"} or "click @3" strings) and return the summary."""
    res = _call("act", {"actions": list(actions)})
    if check and not res["ok"]:
        raise MinionScriptError(res.get("error") or res["summary"])
    return res["summary"]


def click(target=None, button: str = "left", count: int = 1, modifiers: str | None = None) -> str:
    return act({"action": "click", "target": target, "button": button, "count": count, "modifiers": modifiers})


def double_click(target=None) -> str:
    return click(target, count=2)


def right_click(target=None) -> str:
    return click(target, button="right")


def move(target) -> str:
    return act({"action": "move", "target": target})


def drag(start, end) -> str:
    return act({"action": "drag", "from": start, "to": end})


def write(text: str) -> str:
    """Type text (\\n presses Return, \\t presses Tab)."""
    return act({"action": "type", "text": text})


def paste(text: str) -> str:
    return act({"action": "paste", "text": text})


def key(keys: str, repeat: int = 1) -> str:
    return act({"action": "key", "keys": keys, "repeat": repeat})


def hold_key(keys: str, seconds: float = 1.0) -> str:
    return act({"action": "hold_key", "keys": keys, "seconds": seconds})


def scroll(direction: str = "down", amount: int = 3, target=None) -> str:
    return act({"action": "scroll", "direction": direction, "amount": amount, "target": target})


def fill(target, text: str) -> str:
    return act({"action": "fill", "target": target, "text": text})


def select(target, option: str) -> str:
    """Pick an option of a dropdown (<select>, combo box) by its visible text."""
    return act({"action": "select", "target": target, "option": option})


def menu(item: str) -> str:
    """Choose a menu command by its path: menu("File > Export as PDF")."""
    return act({"action": "menu", "item": item})


def menus() -> list[str]:
    """The focused app's menu commands with their shortcuts, one line per menu."""
    return _call("see", {"menus": True}).get("menus", [])


def path(file_path: str, overwrite: bool = False) -> str:
    """Type a full path into the open file dialog (Open, Save As, Export...) and confirm it."""
    return act({"action": "path", "path": file_path, "overwrite": overwrite})


def read(file_path: str) -> str:
    """A document's text: docx, xlsx, pptx, odt/ods/odp, pdf, epub, html, images (OCR), ..."""
    return _call("read", {"path": file_path})["text"]


def convert(file_path: str, to: str, outdir: str | None = None) -> str:
    """Convert a document or image ("pdf", "docx", "xlsx", "csv", "png", "md", ...); returns the new path."""
    return _call("convert", {"path": file_path, "to": to, "outdir": outdir})["path"]


def wait(seconds: float) -> None:
    time.sleep(seconds)


def wait_for(text: str, timeout: float = 10.0, gone: bool = False) -> bool:
    """True when the text appeared (or disappeared with gone=True) before the timeout."""
    res = _call(
        "act", {"actions": [{"action": "wait_for", "text": text, "timeout": timeout, "gone": gone}], "settle": False}
    )
    return bool(res["ok"])


# -- apps, shell, misc ------------------------------------------------------------
def launch(target: str, wait: float = 12.0, install: bool = True) -> dict:
    """Open an app ("writer", "gimp", "vscode": installed first if needed), a URL, a file or a command,
    and wait for its window."""
    return _call("open", {"target": target, "wait": wait, "install": install})


def run(command: str, timeout: float = 60.0, input: str | None = None) -> dict:
    """Run a shell command (with optional stdin text); returns {"code", "stdout", "stderr", ...}."""
    return _call("run", {"command": command, "timeout": timeout, "input": input})


def screenshot(path: str = "/tmp/screenshot.png", region=None, marks: bool = False) -> str:
    """Save a screenshot inside the desktop and return its path."""
    import base64

    res = _call("screenshot", {"region": region, "marks": marks})
    with open(path, "wb") as f:  # noqa: PTH123 - builtin open is intact here
        f.write(base64.b64decode(res["data"]))
    return path


def windows() -> list[dict]:
    return _call("windows")["windows"]


def focus(window: str) -> dict:
    return _call("window", {"action": "focus", "window": window})


def clipboard(text: str | None = None) -> str:
    """Read the clipboard, or set it when text is given."""
    if text is not None:
        _call("clipboard", {"text": text})
        return text
    return _call("clipboard", {})["text"]
