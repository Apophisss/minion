"""The agent daemon: a tiny JSON-lines RPC server on a UNIX socket inside the desktop.

Every request is one line: {"id": 1, "method": "act", "params": {...}}
Every response is one line: {"id": 1, "result": {...}} or {"id": 1, "error": {...}}
"""

from __future__ import annotations

import base64
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

from PIL import ImageDraw, ImageFont

from . import PROTOCOL, VERSION, a11y, catalog, docs
from . import ocr as ocr_mod
from .perceive import Perception, TargetError
from .recorder import Recorder
from .screen import Screen, describe_change, diff, draw_cursor, encode, fingerprint, fit, mime, settle, thumb
from .windows import WindowError, Windows
from .xinput import InputError, XInput, normalize_modifiers

PASSIVE = {"hello", "status", "frame", "record", "cursor"}
# What apps show while they work: "Loading…", "Generating report...", "Please wait", a progress bar.
BUSY_WORDS = re.compile(
    r"\b(loading|generating|processing|please wait|saving|uploading|downloading|searching|calculating|preparing|"
    r"connecting|signing in|logging in|exporting|importing|converting|rendering|working on it|in progress)\b",
    re.I,
)


BUSY_ROLES = {"status", "alert", "notification", "info bar", "static", "label", "paragraph", "section", "text", "panel"}


def busy_text(role: str, text: str) -> str | None:
    """The text, if it says the app is busy: short, a busy word, and an ellipsis ("Loading…") or a status role.
    Headings, links and buttons ("Uploading files" as a title) never count, nor a plain "Processing" or
    "In progress" (an order's status, a task list): those can stay for good."""
    t = " ".join((text or "").split())
    if role not in BUSY_ROLES or not t or len(t) > 80 or not BUSY_WORDS.search(t):
        return None
    if "..." in t or "…" in t or role in ("status", "alert", "notification"):
        return t
    return None


MAX_OUTPUT = 64 * 1024
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
DOMAIN_RE = re.compile(r"^(www\.)?[\w-]+(\.[\w-]+)*\.[a-zA-Z]{2,}(:\d+)?(/\S*)?$")


def run_captured(
    argv: list[str],
    cwd: str,
    timeout: float,
    stdin: bytes | None,
    out_limit: int = MAX_OUTPUT,
    err_limit: int = MAX_OUTPUT,
) -> dict:
    """Run a process and capture its output without being held hostage by children that keep
    stdout open (daemons, `xclip`, `(cd app && server &)`): we wait for the process itself, read
    what is already in the pipes for a moment, and stop. One thread, non-blocking pipes: nothing
    is left blocked on a pipe a background child still holds."""
    t0 = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    out_fd, err_fd = proc.stdout.fileno(), proc.stderr.fileno()
    # Only the start and the end of each stream are kept: a command that prints gigabytes (`find -L` in a
    # symlink loop, `yes`) must not take the desktop's memory with it.
    keep = {out_fd: out_limit // 2, err_fd: err_limit // 2}
    heads: dict[int, bytearray] = {out_fd: bytearray(), err_fd: bytearray()}
    tails: dict[int, bytearray] = {out_fd: bytearray(), err_fd: bytearray()}
    dropped: dict[int, int] = {out_fd: 0, err_fd: 0}
    sel = selectors.DefaultSelector()
    for fd in (out_fd, err_fd):
        os.set_blocking(fd, False)
        sel.register(fd, selectors.EVENT_READ)
    pending = memoryview(stdin or b"")
    if stdin is not None:
        if pending:
            os.set_blocking(proc.stdin.fileno(), False)
            sel.register(proc.stdin.fileno(), selectors.EVENT_WRITE)
        else:
            proc.stdin.close()
    deadline = t0 + timeout
    timed_out = False
    stop_at = None  # set once the process has ended: then only what is already in the pipes is read

    def kill() -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    while sel.get_map():
        now = time.monotonic()
        if stop_at is None:
            if proc.poll() is not None:
                stop_at = now + 0.3
            elif now >= deadline:
                timed_out = True
                kill()
                stop_at = time.monotonic() + 0.3
        if stop_at is not None and now >= stop_at:
            break
        for key, events in sel.select(timeout=0.05):
            fd = key.fd
            if events & selectors.EVENT_WRITE:
                try:
                    pending = pending[os.write(fd, pending[:65536]) :]
                except BlockingIOError:
                    continue
                except OSError:  # the process doesn't read its input (or has ended)
                    pending = pending[:0]
                if not pending:
                    sel.unregister(fd)
                    proc.stdin.close()
                continue
            try:
                data = os.read(fd, 65536)
            except BlockingIOError:
                continue
            except OSError:
                data = b""
            if data:
                head, tail = heads[fd], tails[fd]
                room = keep[fd] - len(head)
                if room > 0:
                    head += data[:room]
                    data = data[room:]
                tail += data
                if len(tail) > keep[fd]:
                    dropped[fd] += len(tail) - keep[fd]
                    del tail[: len(tail) - keep[fd]]
            else:
                sel.unregister(fd)
    sel.close()
    if proc.poll() is None and not timed_out:  # it closed its output but is still running
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            kill()
    for f in (proc.stdin, proc.stdout, proc.stderr):
        if f is not None:
            try:
                f.close()
            except OSError:
                pass

    def text(fd: int) -> str:
        middle = f"\n… [{dropped[fd]} bytes omitted] …\n".encode() if dropped[fd] else b""
        return (bytes(heads[fd]) + middle + bytes(tails[fd])).decode("utf-8", "replace")

    return {
        "code": proc.returncode,
        "timed_out": timed_out,
        "stdout": text(out_fd),
        "stderr": text(err_fd),
        "elapsed": round(time.monotonic() - t0, 3),
    }


class RpcError(Exception):
    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _trim(s: str, limit: int = MAX_OUTPUT) -> str:
    if len(s) <= limit:
        return s
    head = s[: limit // 2]
    tail = s[-limit // 2 :]
    return f"{head}\n… [{len(s) - limit} characters omitted] …\n{tail}"


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


# action name -> (canonical action, default params)
ACTIONS = {
    "click": ("click", {}),
    "left_click": ("click", {"button": "left"}),
    "right_click": ("click", {"button": "right"}),
    "middle_click": ("click", {"button": "middle"}),
    "double_click": ("click", {"count": 2}),
    "triple_click": ("click", {"count": 3}),
    "rclick": ("click", {"button": "right"}),
    "dclick": ("click", {"count": 2}),
    "tclick": ("click", {"count": 3}),
    "move": ("move", {}),
    "mouse_move": ("move", {}),
    "hover": ("move", {}),
    "drag": ("drag", {}),
    "left_click_drag": ("drag", {}),
    "mouse_down": ("mouse_down", {}),
    "left_mouse_down": ("mouse_down", {}),
    "mouse_up": ("mouse_up", {}),
    "left_mouse_up": ("mouse_up", {}),
    "scroll": ("scroll", {}),
    "type": ("type", {}),
    "paste": ("paste", {}),
    "fill": ("fill", {}),
    "select": ("select", {}),
    "choose": ("select", {}),
    "key": ("key", {}),
    "press": ("key", {}),
    "hotkey": ("key", {}),
    "hold_key": ("hold_key", {}),
    "wait": ("wait", {}),
    "sleep": ("wait", {}),
    "wait_for": ("wait_for", {}),
    "scroll_to": ("scroll_to", {}),
    "find": ("scroll_to", {}),
    "focus": ("focus", {}),
    "close": ("close", {}),
    "close_window": ("close", {}),
    "goto": ("goto", {}),
    "navigate": ("goto", {}),
    "copy": ("copy", {}),
    "open": ("open", {}),
    "menu": ("menu", {}),
    "path": ("path", {}),
    "file_path": ("path", {}),
}
# shorthand {"click": "@3"} -> which parameter receives the value
MAIN_PARAM = {
    "click": "target",
    "left_click": "target",
    "right_click": "target",
    "middle_click": "target",
    "double_click": "target",
    "triple_click": "target",
    "rclick": "target",
    "dclick": "target",
    "tclick": "target",
    "move": "target",
    "mouse_move": "target",
    "hover": "target",
    "type": "text",
    "paste": "text",
    "key": "keys",
    "press": "keys",
    "hotkey": "keys",
    "scroll": "direction",
    "wait": "seconds",
    "sleep": "seconds",
    "wait_for": "text",
    "scroll_to": "text",
    "find": "text",
    "focus": "window",
    "close": "window",
    "close_window": "window",
    "goto": "target",
    "navigate": "target",
    "copy": "target",
    "open": "target",
    "hold_key": "keys",
    "menu": "item",
    "path": "path",
    "file_path": "path",
}


# Runs a `script`: the GUI API preloaded, and errors reported as the lines of *your* script that failed
# (not the bootstrap's or the API's internals).
SCRIPT_BOOTSTRAP = """\
import sys, traceback
from minion_agent.client import *
__path = sys.argv[1]
try:
    exec(compile(open(__path, encoding="utf-8").read(), "script.py", "exec"))
except SystemExit:
    raise
except BaseException as __e:
    sys.stdout.flush()
    __lines = open(__path, encoding="utf-8").read().splitlines()
    __frames = [f for f in traceback.extract_tb(__e.__traceback__) if f.filename == "script.py"]
    print("Error in the script:", file=sys.stderr)
    for __f in __frames[-3:]:
        __src = __lines[__f.lineno - 1].strip() if 0 < __f.lineno <= len(__lines) else ""
        print(f"  line {__f.lineno}: {__src}", file=sys.stderr)
    print(f"{type(__e).__name__}: {__e}", file=sys.stderr)
    sys.exit(1)
"""


def split_words(text: str) -> list[str]:
    """Split like a shell (quotes group words) but keep backslashes, so `type C:\\Users\\agent` types a
    Windows path instead of `C:Usersagent`."""
    lex = shlex.shlex(text, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.escape = ""
    return list(lex)


def _unquote(text: str) -> str:
    """Strip one pair of matching outer quotes: "type 'hello world'" types hello world."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


# A Windows path, C:\\users\\agent\\note.txt or C:\\temp (no second ":" in it, which a row of
# "X:\\t5\\tY:\\t7" has): its backslashes are not escapes.
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^:\n\t]*")


def _escapes(text: str) -> str:
    """\\n is Return, \\t is Tab and \\\\ is a backslash, as in write() in scripts. A Windows path keeps its
    backslashes (C:\\users\\note.txt has no Return in it), apart from a \\n at its very end."""
    if WINDOWS_PATH.fullmatch(text) and "\\\\" not in text:  # (C:\\\\temp: the escape convention, as before)
        return text[:-2] + "\n" if text.endswith("\\n") else text
    return text.replace("\\\\", "\0").replace("\\n", "\n").replace("\\t", "\t").replace("\0", "\\")


_OOXML = {"docx": ("word/", "Word"), "xlsx": ("xl/", "Excel"), "pptx": ("ppt/", "PowerPoint")}
_ODF = {"odt": "text", "ods": "spreadsheet", "odp": "presentation"}


def _office_kind(path: str) -> str:
    """', Excel format' for a saved .xlsx that is one, and a warning when a document's content and name disagree
    (LibreOffice can keep its own format under a Microsoft name): so nobody spends a step on `file` to check."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext not in _OOXML and ext not in _ODF:
        return ""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            mime = z.read("mimetype").decode(errors="replace") if "mimetype" in names else ""
    except (OSError, zipfile.BadZipFile, KeyError):
        return ", not a valid document yet"
    if ext in _OOXML:
        folder, label = _OOXML[ext]
        if any(n.startswith(folder) for n in names):
            return f", {label} format"
        return (
            f", but it holds OpenDocument, not {label}" if "opendocument" in mime else f", but it isn't a {label} file"
        )
    return f", OpenDocument {_ODF[ext]}" if "opendocument" in mime else ""


CELL_REF = re.compile(r"(?:[A-Za-z_][\w ]*\.)?\$?[A-Za-z]{1,3}\$?[1-9]\d{0,6}(?::\$?[A-Za-z]{1,3}\$?[1-9]\d{0,6})?")


def _reads_as(shown: str, want: str) -> bool:
    """Whether text read off the screen (OCR: "1.5 Lines" may come back as "1.5 Lines" or "15 Lines") is the
    text that was asked for."""
    import difflib

    a, b = (" ".join(v.split()).casefold() for v in (shown, want))
    return b in a or a in b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def _first_word(rest: str) -> tuple[str, str]:
    """('"Customer name"', ' Ada') -> ('Customer name', 'Ada'): a target, then the verbatim rest."""
    rest = rest.lstrip()
    if rest[:1] in ("'", '"'):
        end = rest.find(rest[0], 1)
        if end > 0:
            return rest[1:end], rest[end + 1 :].lstrip()
    word, _, tail = rest.partition(" ")
    return word, tail.lstrip()


def parse_step(step) -> tuple[str, dict]:
    """Normalize one action from any of the accepted shapes into (action, params)."""
    if isinstance(step, str):
        m = re.match(r"\s*(\S+)(?:\s(.*))?$", step, re.S)
        if not m:
            raise RpcError("empty action")
        verb, rest = m.group(1).lower(), (m.group(2) or "")
        if verb in ("click?", "dclick?", "rclick?"):  # "click? 'Keep Current Format'": a dialog that may not come
            canon, params = parse_step(f"{verb[:-1]} {rest}")
            return canon, {**params, "optional": True}
        held = re.fullmatch(r"((?:(?:ctrl|shift|alt|super)\+)+)(click|dclick|rclick|tclick)", verb)
        if held:  # "ctrl+click @12": cells or files added to a selection, a link opened in a new tab
            canon, params = parse_step(f"{held.group(2)} {rest}")
            return canon, {**params, "modifiers": held.group(1).rstrip("+").split("+")}
        if verb not in ACTIONS:
            raise RpcError(
                f"unknown action {verb!r}; actions: {', '.join(sorted(set(a for a, _ in ACTIONS.values())))}"
            )
        canon = ACTIONS[verb][0]
        if canon in ("type", "paste"):  # the rest of the step, verbatim: spaces at either end are typed too
            quoted = rest.strip()
            text = quoted[1:-1] if len(quoted) >= 2 and quoted[0] == quoted[-1] and quoted[0] in "'\"" else rest
            return canon, {**ACTIONS[verb][1], "text": _escapes(text)}
        if canon == "wait_for":  # wait_for Saved · wait_for "Report ready" 60 · wait_for Loading --gone
            text, extra = rest.strip(), {}
            if text.endswith(" --gone"):
                text, extra["gone"] = text[: -len(" --gone")].rstrip(), True
            m = re.match(r"""^(["'])(.*)\1\s+(\d+(?:\.\d+)?)$""", text, re.S)
            if m:  # a timeout after a quoted text
                text, extra["timeout"] = m.group(1) + m.group(2) + m.group(1), float(m.group(3))
            return canon, {**ACTIONS[verb][1], "text": _unquote(text), **extra}
        if canon == "scroll_to":
            return canon, {"text": _unquote(rest.strip())}
        if canon == "fill":
            target, text = _first_word(rest)
            if not target:
                raise RpcError("fill needs a target and text: fill @3 'hello'")
            return canon, {**ACTIONS[verb][1], "target": target, "text": _escapes(_unquote(text))}
        if canon == "select":
            target, option = _first_word(rest)
            if not target or not option:
                raise RpcError("select needs a dropdown and an option: select @12 'Title'")
            return canon, {"target": target, "option": _unquote(option)}
        if canon == "menu":  # "menu File > Export > PDF": the rest is the menu path
            return canon, {"item": _unquote(rest.strip())}
        if canon == "path":  # "path ~/Documents/report.pdf [--overwrite]": a file dialog's path
            text, overwrite = rest.strip(), False
            if text.endswith(" --overwrite") or text.startswith("--overwrite "):
                text, overwrite = text.replace("--overwrite", "", 1).strip(), True
            return canon, {"path": _unquote(text), **({"overwrite": True} if overwrite else {})}
        args = split_words(rest)
        params: dict = {}
        if canon in ("click", "move", "copy"):
            if args:
                params["target"] = " ".join(args)
        elif canon in ("key", "hold_key"):
            params["keys"] = args[0] if args else ""
            if canon == "key" and len(args) == 2 and args[1].isdigit():  # "key Down 3": a repeat count
                params["repeat"] = int(args[1])
            elif canon == "key" and len(args) > 1:  # "key BackSpace BackSpace Return": a sequence
                params["keys"] = " ".join(args)
            if canon == "hold_key" and len(args) > 1:
                params["seconds"] = float(args[1])
        elif canon == "scroll":
            params["direction"] = args[0] if args else "down"
            if len(args) > 1:
                params["amount"] = int(args[1])
            if len(args) > 2:
                params["target"] = " ".join(args[2:])
        elif canon == "wait":
            params["seconds"] = float(args[0]) if args else 1.0
        elif canon == "drag":
            if len(args) != 2:
                raise RpcError("drag needs two targets: drag FROM TO")
            params["from"], params["to"] = args
        elif canon in ("focus", "open"):
            params["window" if canon == "focus" else "target"] = " ".join(args)
        elif canon == "close" and args:
            params["window"] = " ".join(args)
        elif canon == "goto" and args:
            params["target"] = args[0]
        verb_defaults = ACTIONS[verb][1]
        return canon, {**verb_defaults, **params}
    if not isinstance(step, dict):
        raise RpcError(f"an action must be an object or a string, got {type(step).__name__}")
    # Explicit nulls mean "use the default": some clients send every optional field as null.
    step = dict(step)
    if step.get("action") is not None:
        name = str(step.pop("action")).lower()
        step = {k: v for k, v in step.items() if v is not None}
    else:
        step.pop("action", None)
        keys = [k for k in step if k in ACTIONS and step[k] is not None] or [k for k in step if k in ACTIONS]
        if len(keys) != 1:
            raise RpcError(f"cannot tell which action this is: {json.dumps(step)[:120]}")
        name = keys[0]
        value = step.pop(name)
        step = {k: v for k, v in step.items() if v is not None}
        main = MAIN_PARAM.get(name)
        if main and value is not None and value is not True:
            step.setdefault(main, value)
        elif name in ("drag", "left_click_drag") and isinstance(value, (list, tuple)) and len(value) == 2:
            step.setdefault("from", value[0])
            step.setdefault("to", value[1])
        elif name == "fill" and isinstance(value, (list, tuple)) and len(value) == 2:
            step.setdefault("target", value[0])
            step.setdefault("text", value[1])
    if name not in ACTIONS:
        raise RpcError(f"unknown action {name!r}")
    canon, defaults = ACTIONS[name]
    params = {**defaults, **step}
    # Claude computer-use field names.
    if canon == "drag":
        if "start_coordinate" in params:
            params.setdefault("from", params.pop("start_coordinate"))
        if "coordinate" in params:
            params.setdefault("to", params.pop("coordinate"))
    if "coordinate" in params:
        params.setdefault("target", params.pop("coordinate"))
    if "scroll_direction" in params:
        params.setdefault("direction", params.pop("scroll_direction"))
    if "scroll_amount" in params:
        params.setdefault("amount", params.pop("scroll_amount"))
    if "duration" in params:
        params.setdefault("seconds", params.pop("duration"))
    if canon in ("key", "hold_key") and "keys" not in params and "text" in params:
        params["keys"] = params.pop("text")
    if canon in ("click", "scroll", "drag") and "text" in params and "modifiers" not in params:
        params["modifiers"] = params.pop("text")
    return canon, params


class Agent:
    def __init__(self, display: str, size: tuple[int, int], info: dict | None = None):
        self.display = display
        self.size = size
        self.info = info or {}
        self.apps = self.info.get("apps", [])
        self.screen = Screen(display)
        self.xi = XInput(display)
        self.windows = Windows(display)
        self.perception = Perception(self.screen, self.windows, size)
        self.perception.xi = self.xi  # for the LibreOffice coordinate nudge
        self.recorder = Recorder(enabled=os.environ.get("MINION_RECORD", "1") != "0")
        self.input_lock = threading.RLock()
        self._stuck_busy: dict = {}  # window id -> busy texts that stayed past the wait (not real work)
        self._covered = False  # the last act's click landed on a pop-up
        self.started = time.time()
        self.last_activity = time.time()
        self.last_view = 0.0
        self.inflight = 0  # non-passive calls running now (a long `run` is not "idle")
        self._inflight_lock = threading.Lock()
        self.home = os.path.expanduser("~")
        self._tipped: set[str] = set()  # apps whose tips this session has already shown
        self.handlers = {n[2:]: getattr(self, n) for n in dir(self) if n.startswith("m_")}

    # -- dispatch ------------------------------------------------------
    def call(self, method: str, params: dict | None):
        handler = self.handlers.get(method or "")
        if handler is None:
            raise RpcError(f"unknown method {method!r}", code=-32601)
        if method in PASSIVE:
            return handler(params or {})
        with self._inflight_lock:
            self.inflight += 1
        self.last_activity = time.time()
        try:
            return handler(params or {})
        finally:
            with self._inflight_lock:
                self.inflight -= 1
            self.last_activity = time.time()

    # -- info ----------------------------------------------------------
    def m_hello(self, p: dict) -> dict:
        return {
            "version": VERSION,
            "protocol": PROTOCOL,
            "display": self.display,
            "screen": list(self.size),
            "name": self.info.get("name", ""),
            "profile": self.info.get("profile", ""),
            "apps": [a.get("name") for a in self.apps],
            "features": {
                "a11y": a11y.AVAILABLE,
                "ocr": ocr_mod.available(),
                "clipboard": shutil.which("xclip") is not None,
            },
            "uptime": round(time.time() - self.started, 1),
            "idle": round(time.time() - self.last_activity, 1),
        }

    def m_status(self, p: dict) -> dict:
        mem = None
        for path in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
            try:
                with open(path) as f:
                    mem = int(f.read().strip())
                break
            except (OSError, ValueError):
                continue
        try:
            nwin = len(self.windows.list(with_states=False))
        except WindowError:
            nwin = None
        now = time.time()
        return {
            "uptime": round(now - self.started, 1),
            "idle": 0.0 if self.inflight else round(now - self.last_activity, 1),
            "viewed": round(now - (self.last_view or self.started), 1),
            "inflight": self.inflight,
            "memory": mem,
            "windows": nwin,
            "recording": self.recorder.info(),
        }

    # -- perception ----------------------------------------------------
    def _region(self, region) -> tuple[int, int, int, int] | None:
        if not region:
            return None
        if isinstance(region, str):
            region = [int(v) for v in re.split(r"[,\s]+", region.strip()) if v]
        if len(region) != 4:
            raise RpcError("region must be [x, y, width, height]")
        x, y, w, h = (int(round(float(v))) for v in region)
        sw, sh = self.size
        x, y = max(0, min(x, sw - 1)), max(0, min(y, sh - 1))
        w, h = max(1, min(w, sw - x)), max(1, min(h, sh - y))
        return x, y, w, h

    def m_screenshot(self, p: dict) -> dict:
        region = self._region(p.get("region"))
        img = self.screen.grab(region)
        fp = fingerprint(img)
        if p.get("since") and p["since"] == fp:
            return {"unchanged": True, "fingerprint": fp}
        ox, oy = (region[0], region[1]) if region else (0, 0)
        if p.get("marks"):
            self._draw_marks(img, (ox, oy))
        if p.get("cursor", True):
            try:
                cx, cy = self.xi.position()
                draw_cursor(img, cx, cy, offset=(ox, oy))
            except InputError:
                pass
        if p.get("grid"):
            self._draw_grid(img, (ox, oy), int(p.get("grid_step") or 100))
        scale = 1.0
        if p.get("width"):  # zoom: resize to an exact width, upscaling allowed (max 4x)
            tw = max(16, min(int(p["width"]), img.width * 4))
            th = max(1, round(img.height * tw / img.width))
            scale = tw / img.width
            img = img.resize((tw, th), resample=3)
        else:
            img, scale = fit(img, p.get("max_width"), p.get("max_height"), p.get("max_pixels"), p.get("scale"))
        fmt = (p.get("format") or "png").lower()
        data = encode(img, fmt, int(p.get("quality") or 80))
        return {
            "data": _b64(data),
            "format": fmt,
            "mime": mime(fmt),
            "width": img.width,
            "height": img.height,
            "scale": round(scale, 5),
            "region": list(region) if region else [0, 0, *self.size],
            "fingerprint": fp,
        }

    def _draw_marks(self, img, offset) -> None:
        seen = self.perception.see(ocr=False, register=True)
        d = ImageDraw.Draw(img)
        font = _font(11)
        ox, oy = offset
        for el in seen["elements"]:
            if el["role"] not in a11y.INTERACTIVE and el["role"] not in a11y.TEXT_INPUT:
                continue
            x, y, w, h = el["box"]
            x, y = x - ox, y - oy
            if x + w < 0 or y + h < 0 or x > img.width or y > img.height:
                continue
            d.rectangle([x, y, x + w, y + h], outline=(236, 72, 153), width=1)
            label = el["id"]
            tw = d.textlength(label, font=font)
            ly = y - 14 if y >= 14 else y  # above the element when there is room
            d.rectangle([x, ly, x + tw + 6, ly + 14], fill=(236, 72, 153))
            d.text((x + 3, ly + 1), label, fill=(255, 255, 255), font=font)

    def _draw_grid(self, img, offset, step: int) -> None:
        step = max(25, step)
        d = ImageDraw.Draw(img, "RGBA")
        font = _font(10)
        ox, oy = offset
        for gx in range((ox // step + 1) * step, ox + img.width, step):
            x = gx - ox
            d.line([(x, 0), (x, img.height)], fill=(255, 0, 0, 70))
            d.text((x + 2, 2), str(gx), fill=(220, 0, 0, 255), font=font)
        for gy in range((oy // step + 1) * step, oy + img.height, step):
            y = gy - oy
            d.line([(0, y), (img.width, y)], fill=(255, 0, 0, 70))
            d.text((2, y + 2), str(gy), fill=(220, 0, 0, 255), font=font)

    def m_see(self, p: dict) -> dict:
        ocr = p.get("ocr", "auto")
        if isinstance(ocr, str) and ocr.lower() in ("true", "yes", "1", "on"):
            ocr = True
        elif isinstance(ocr, str) and ocr.lower() in ("false", "no", "0", "off"):
            ocr = False
        try:
            full = bool(p.get("full_text"))
            res = self.perception.see(
                ocr=ocr,
                window=p.get("window"),
                max_elements=int(p.get("max_elements") or (600 if full else 250)),
                text_limit=4000 if full else 160,
                changes=bool(p.get("changes")),
            )
        except WindowError as e:
            raise RpcError(str(e)) from e
        if p.get("menus"):
            lines = self._menu_lines()
            res["menus"] = lines
            res["text"] += (
                "\n\nMenus (choose one with: menu File > Save As):\n" + "\n".join(lines)
                if lines
                else "\n\nThis window has no menu bar that accessibility can read (browsers hide theirs: use shortcuts)."
            )
        self.recorder.add("see", f"{len(res['elements'])} elements, {len(res['ocr'])} OCR lines")
        return res

    def _menu_lines(self) -> list[str]:
        try:
            _, aw = self._focused_a11y()
        except RpcError:
            return []
        return a11y.format_menus(a11y.menu_items(aw)) if aw is not None else []

    def m_read(self, p: dict) -> dict:
        """A document's text: docx, xlsx, pptx, odt/ods/odp, pdf, epub, html, images (OCR), doc/xls/ppt..."""
        try:
            text, kind = docs.read(
                str(p.get("path") or ""), max_chars=int(p.get("max_chars") or 200_000), details=bool(p.get("details"))
            )
        except docs.DocError as e:
            raise RpcError(str(e)) from e
        return {"text": text, "kind": kind}

    def m_convert(self, p: dict) -> dict:
        """Convert a document or image: {"path": "~/a.docx", "to": "pdf"} -> {"path": "/home/agent/a.pdf"}."""
        try:
            out = docs.convert(str(p.get("path") or ""), str(p.get("to") or ""), p.get("outdir"))
        except docs.DocError as e:
            raise RpcError(str(e)) from e
        except subprocess.TimeoutExpired as e:
            raise RpcError("the conversion took too long") from e
        self.recorder.add_macro("run", {"command": f"minion-convert {shlex.quote(str(p.get('path')))} {p.get('to')}"})
        return {"path": out}

    def m_cursor(self, p: dict) -> dict:
        x, y = self.xi.position()
        return {"x": x, "y": y}

    def m_find(self, p: dict) -> dict:
        text = p.get("text")
        if not text:
            raise RpcError("find needs text")
        found = self.perception.find_text(str(text), use_ocr=p.get("ocr", True))
        return {"matches": [{"score": s, "x": t.x, "y": t.y, "desc": t.desc} for s, t in found[:20]]}

    def m_windows(self, p: dict) -> dict:
        try:
            return {"windows": [w.to_dict() for w in self.windows.list()]}
        except WindowError as e:
            raise RpcError(str(e)) from e

    def m_window(self, p: dict) -> dict:
        action = (p.get("action") or "focus").lower()
        query = p.get("window")
        try:
            win = self.windows.find(query) if query is not None else self.windows.focused()
            if win is None:
                raise RpcError("no window is focused")
            with self.input_lock:
                if action in ("focus", "activate", "raise"):
                    self.windows.activate(win.id)
                elif action == "close":
                    said = self._close(win=win)
                    if said.startswith("asked"):
                        return {"ok": True, "window": win.to_dict(), "note": said}
                elif action == "maximize":
                    self.windows.maximize(win.id, True)
                elif action in ("restore", "unmaximize"):
                    self.windows.maximize(win.id, False)
                elif action == "minimize":
                    self.windows.minimize(win.id)
                elif action in ("move", "resize"):
                    self.windows.move_resize(
                        win.id,
                        int(p.get("x", win.x)),
                        int(p.get("y", win.y)),
                        int(p.get("w", p.get("width", win.w))),
                        int(p.get("h", p.get("height", win.h))),
                    )
                else:
                    raise RpcError(f"unknown window action {action!r}")
            time.sleep(0.2)
            self.recorder.add("window", f'{action} "{win.title}"', self.screen.grab())
            return {"ok": True, "window": win.to_dict()}
        except WindowError as e:
            raise RpcError(str(e)) from e

    # -- actions -------------------------------------------------------
    def _calc_ref(self, target) -> str | None:
        """A cell or range reference (B8, $C$2:$C$29, Sheet2.A1) as a target in LibreOffice Calc's window."""
        if not isinstance(target, str) or not CELL_REF.fullmatch(target.strip()):
            return None
        focused = self.windows.focused()
        if focused is None or "LibreOffice Calc" not in (focused.title or ""):
            return None
        return target.strip()

    def _goto_cell(self, ref: str) -> None:
        """Go to a cell, or select a range, by typing its reference into Calc's Name Box."""
        try:
            box = self.perception.resolve("Name Box")
        except (TargetError, RpcError) as e:
            raise RpcError(f"can't go to {ref}: Calc's Name Box isn't on screen (View > Formula Bar shows it)") from e
        self.xi.click(box.x, box.y)
        time.sleep(0.15)
        self.xi.key("ctrl+a")
        self.xi.type(ref)
        self.xi.key("Return")
        time.sleep(0.25)

    def _mods(self, p: dict) -> list[str]:
        try:
            return normalize_modifiers(p.get("modifiers"))
        except InputError as e:
            raise RpcError(str(e)) from e

    def _do(self, action: str, p: dict) -> str:
        r = self.perception.resolve
        if action in ("type", "paste", "key", "hold_key") and not self.windows.list(with_states=False):
            raise RpcError("no window is open, so keyboard input would go nowhere: open an app first (open firefox)")
        if action == "click":
            button = (p.get("button") or "left").lower()
            count = max(1, min(int(p.get("count") or 1), 3))
            mods = self._mods(p)
            if p.get("target") is None:
                self.xi.click(None, None, button, count, mods)
                x, y = self.xi.position()
                where = f"({x},{y})"
            elif (ref := self._calc_ref(p["target"])) is not None and count == 1 and button == "left" and not mods:
                self._goto_cell(ref)  # B8, C2:C29: go there (empty cells and ranges have no @id)
                return f"went to {ref} (in the Name Box)" if ":" not in ref else f"selected {ref} (in the Name Box)"
            else:
                try:
                    t = r(p["target"])
                except TargetError:
                    if p.get("optional"):
                        return f"nothing to click: {p['target']!r} didn't show up (skipped)"
                    raise
                covered = a11y.cover(t.element, t.x, t.y) if isinstance(t.element, a11y.Element) else ""
                if covered:  # a pop-up or a banner is on top: the click would go to it (an ad, "Subscribe")
                    self._covered = True
                    raise RpcError(
                        f"{t.desc} is covered by {covered}: close that first (to click there anyway, give the "
                        f"point: {t.x},{t.y})"
                    )
                self.xi.click(t.x, t.y, button, count, mods)
                where = t.desc
            kind = {1: "click", 2: "double-click", 3: "triple-click"}[count]
            if button != "left":
                kind = f"{button} {kind}"
            return f"{'+'.join(mods) + ' ' if mods else ''}{kind} {where}"
        if action == "move":
            t = r(p.get("target"))
            self.xi.move(t.x, t.y)
            return f"moved to {t.desc}"
        if action == "drag":
            a, b = r(p.get("from")), r(p.get("to"))
            source = (
                a.element
                if isinstance(a.element, a11y.Element)
                and a.element.node is not None
                and a.element.in_doc
                and a.element.role not in ("slider", "scroll bar", "spin button", "canvas", "image")
                else None
            )
            box = a11y.refresh(source) if source is not None else None
            self.xi.drag(a.x, a.y, b.x, b.y, self._mods(p), button=(p.get("button") or "left"))
            done = f"dragged {a.desc} → {b.desc}"
            if box is not None:
                time.sleep(0.3)
                if a11y.refresh(source) == box:  # (a moved card, a slider's knob: their box changes)
                    done += " (but it is still where it was: the drop may not have taken; look, then try again)"
            return done
        if action in ("mouse_down", "mouse_up"):
            if p.get("target") is not None:
                t = r(p["target"])
                self.xi.move(t.x, t.y)
            self.xi.button(action == "mouse_down", (p.get("button") or "left").lower())
            return action.replace("_", " ")
        if action == "scroll":
            direction = str(p.get("direction") or "down").lower()
            amount = max(1, min(int(p.get("amount") or 3), 50))
            x = y = None
            where = ""
            if p.get("target") is not None:
                t = r(p["target"])
                x, y, where = t.x, t.y, f" at {t.desc}"
            self.xi.scroll(direction, amount, x, y, self._mods(p))
            return f"scrolled {direction} ×{amount}{where}"
        if action == "type":
            text = p.get("text")
            if text is None or text == "":
                raise RpcError("type needs text")
            text = str(text)
            if len(text) > 20000:
                raise RpcError("text is too long to type (max 20000 characters); use paste or a file")
            fast = self._in_browser()
            if not text.isascii() or (not fast and len(text) > 200):
                # Characters outside ASCII (é, ש, 東, emoji) are typed through a remapped spare key, and many
                # apps (Firefox, LibreOffice) drop some of them: paste those lines instead, which is exact. Long
                # text in an app is pasted too (minutes of typing at a person's pace; an editor's auto-indent).
                self._type_via_clipboard(text, paste_all=not fast)
            else:
                # Only web pages take typing at full speed. Apps lose keys typed faster than a person: LibreOffice
                # reorders them while it switches modes ("Nmbusi"), and a calculator drops a key that follows an
                # operator or repeats the last one ("7006652" became 70652). A steadier hand costs a little time.
                self.xi.type(
                    text,
                    int(p.get("delay_ms") or (8 if fast else 30)),
                    key_pause=0.0 if fast else 0.08,
                    repeat_pause=0.0 if fast else 0.12,
                )
            return f"typed {len(text)} chars"
        if action == "paste":
            text = str(p.get("text") or "")
            focused = self.windows.focused()
            self._paste_keys(text, focused.app if focused is not None else "")
            return f"pasted {len(text)} chars"
        if action == "fill":
            text = str(p.get("text") if p.get("text") is not None else "")
            ref = self._calc_ref(p.get("target"))
            if ref is not None:  # a spreadsheet cell or range by its reference: B8, C2:C29
                self._goto_cell(ref)
                if text and not text.isascii():
                    self._type_via_clipboard(text)
                elif text:
                    self.xi.type(text)
                else:
                    self.xi.key("Delete")
                    return f"cleared {ref}"
                # Return enters it; Alt+Return enters it into every cell of a selected range.
                self.xi.key("alt+Return" if ":" in ref else "Return")
                return f"filled {ref} with {len(text)} chars" + (" (every cell of the range)" if ":" in ref else "")
            t = r(p.get("target"), prefer_input=True)
            el = t.element
            if isinstance(el, a11y.Element) and el.role in ("slider", "scroll bar", "level bar") and text.strip():
                return self._set_value(t, el, text.strip())
            if isinstance(el, a11y.Element) and el.role == "date editor" and text.strip():
                return self._fill_date(t, el, text.strip())
            if isinstance(el, a11y.Element) and not a11y.is_editable(el) and el.role != "panel":
                # (a named panel may hold an editor the app doesn't expose, e.g. LibreOffice's style box:
                # clicking it focuses that editor)
                inner = a11y.editable_descendant(el)
                if inner is None:
                    raise RpcError(
                        f"{t.desc} is not a text field, so fill would type into the wrong place. Use the "
                        "field's @id from `see` (or click it, then type)"
                    )
                box = a11y.refresh(inner)
                if box:
                    x, y, w, h = box
                    t = type(t)(x + w // 2, y + h // 2, f"{t.desc} → its {inner.role}", inner)
                el = inner
            # Native apps: set the text directly (instant, exact). Web pages: really type it, so the
            # page's own input handlers (React, Vue, autocomplete...) see every keystroke.
            native = isinstance(el, a11y.Element) and not el.in_doc
            if native and len(text) > 40 and a11y.set_text(el, text):
                return f"filled {t.desc} with {len(text)} chars"
            x, y = t.x, t.y
            if isinstance(el, a11y.Element) and el.role == "spin button" and el.w > 2 * el.h:
                # A spin box's middle is where its text meets its arrows (LibreOffice's margins: the click
                # missed the text): aim at the text part.
                box = a11y.refresh(el) or (el.x, el.y, el.w, el.h)
                if box[0] >= 0 and box[0] + box[2] <= self.size[0]:  # (only when the whole box is on screen)
                    x = box[0] + min(box[2] // 3, 30)
            self.xi.click(x, y)
            time.sleep(0.08)
            if isinstance(el, a11y.Element) and not el.in_doc and a11y.is_focused(el) is False:
                a11y.grab_focus(el)  # the click didn't give it the focus: typing must not go to the last field
                time.sleep(0.1)
            self.xi.key("ctrl+a")
            if text and not text.isascii():
                self._type_via_clipboard(text)  # (see type: remapped keys lose characters)
            elif text:
                self.xi.type(text)
            else:
                self.xi.key("BackSpace")
            if isinstance(el, a11y.Element) and el.role == "panel":
                self.xi.key("Return")  # a toolbar box (LibreOffice's style, font, size) applies on Return
                return f"filled {t.desc} with {len(text)} chars and pressed Return to apply it"
            done = f"filled {t.desc} with {len(text)} chars"
            if isinstance(el, a11y.Element) and text and "\n" not in text:

                def plain(v: str) -> str:
                    return " ".join(v.translate(a11y._INVISIBLE).split())

                now = None
                for _ in range(6):  # (a page's field reports its new text a moment later)
                    time.sleep(0.1)
                    now = a11y.field_text(el)
                    if now is None or plain(now) == plain(text):
                        break
                if now is not None and plain(now) != plain(text):
                    # The page reformatted it ("4242424242424242" → "4242 4242 4242 4242"), cut it to its
                    # maximum length, or an autocomplete took over: say what the field really holds.
                    done += f'; the field now shows "{now[:120]}"'
            return done
        if action == "select":
            option = str(p.get("option") or p.get("text") or p.get("value") or "")
            if not option:
                raise RpcError("select needs an option (its visible text)")
            t = r(p.get("target"))
            el = t.element
            if isinstance(el, a11y.Element) and not el.in_doc:
                # A native app's dropdown takes the choice through accessibility. A web page's doesn't count:
                # its value changes, but the page's "change" handlers never run (a shop's sort order stays put).
                try:
                    chosen = a11y.select_option(el, option)
                except ValueError as e:
                    raise RpcError(str(e)) from e
                if chosen is not None:
                    time.sleep(0.2)
                    now, _ = a11y.combo_value(el.node)
                    if now == chosen:
                        return f'selected "{chosen}" in {t.desc}'
                    if not now:  # (the app took the choice but doesn't tell accessibility its value)
                        return f'selected "{chosen}" in {t.desc}; its value can\'t be read back: look to confirm'
            if isinstance(el, a11y.Element) and el.in_doc and el.role in ("combo box", "list box"):
                options = a11y.options(el)  # (all of them: a look shows the first dozen)
                low = option.casefold().strip()
                if options and not any(o.casefold() == low or o.casefold().startswith(low) for o in options):
                    raise RpcError(f'no option "{option}" in {t.desc}; options: {" | ".join(options[:20])}')
            # The keyboard way: open it, type the option's text (type-ahead finds it), confirm. An autocomplete
            # field (a JS combo box) shows its suggestions as you type: click the one that matches.
            focused = self.windows.focused()  # (before the click: an opened list becomes the active window)
            aw = a11y.window_for(focused) if focused is not None and a11y.AVAILABLE else None
            self.xi.click(t.x, t.y)
            time.sleep(0.3)
            if aw is not None and isinstance(el, a11y.Element) and not el.in_doc and not a11y.has_entry(el):
                # A dialog's dropdown in LibreOffice or GTK opens its list in a window of its own, and says
                # nothing of its options or value until then: pick the option from that list. (Typing its name
                # instead only jumps by first letters: "Double" picked "Leading".)
                items: list = []
                end = time.monotonic() + 1.5
                while time.monotonic() < end:
                    items = [e for e in a11y.popup_menus(aw, screen=self.size) if e.role in a11y.PICKABLE]
                    if items:
                        break
                    time.sleep(0.15)
                if items:
                    pick = a11y.best_option(items, option)
                    if pick is None:
                        self.xi.key("Escape")
                        names = " | ".join(e.label() for e in items[:20])
                        raise RpcError(f'no option "{option}" in {t.desc}; options: {names}')
                    self.xi.click(*pick.center)
                    time.sleep(0.3)
                    shown = self.perception.shown_text(el)
                    if shown and not _reads_as(shown, pick.label()):
                        return f'clicked "{pick.label()}" in the list of {t.desc}, but it shows "{shown}": look'
                    return f'selected "{pick.label()}" from the list of {t.desc}'
            if isinstance(el, a11y.Element) and a11y.is_editable(el):
                self.xi.key("ctrl+a")
            self.xi.type(option)
            deadline = time.monotonic() + 2.5
            while aw is not None and time.monotonic() < deadline:
                time.sleep(0.35)
                hit = a11y.suggestion(aw, option, near=(t.x, t.y))
                if hit is not None:
                    x, y = hit.center
                    self.xi.click(x, y)
                    typed_in = isinstance(el, a11y.Element) and a11y.is_editable(el)
                    return f'selected "{hit.label()}" ' + (
                        f"from the suggestions of {t.desc}" if typed_in else f"in {t.desc}"
                    )
            self.xi.key("Return")
            if isinstance(el, a11y.Element) and el.node is not None and el.role in ("combo box", "list box"):
                time.sleep(0.2)
                now, _ = a11y.combo_value(el.node)
                if now and now.casefold() != option.casefold() and not now.casefold().startswith(option.casefold()):
                    raise RpcError(f'tried to select "{option}" in {t.desc}, but it shows "{now}"')
                if not now:  # (some apps' dropdowns don't tell accessibility their value)
                    return f'typed "{option}" into {t.desc} and pressed Return; its value can\'t be read back: look'
            return f'selected "{option}" in {t.desc}'
        if action == "key":
            keys = p.get("keys")
            if not keys:
                raise RpcError('key needs keys, e.g. "ctrl+s" or "Return"')
            if re.fullmatch(r"\s*alt\+f4\s*", str(keys), re.I):
                return self._close(None)  # the window manager's close: Windows programs (Wine) ignore a sent Alt+F4
            repeat = max(1, min(int(p.get("repeat") or 1), 100))
            sent = self.xi.key(str(keys), repeat)
            return f"pressed {sent}" + (f" ×{repeat}" if repeat > 1 else "")
        if action == "hold_key":
            keys = p.get("keys")
            seconds = max(0.0, min(float(p.get("seconds") or 1.0), 30.0))
            sent = self.xi.key_down(str(keys))
            try:
                time.sleep(seconds)
            finally:
                self.xi.key_up(str(keys))
            return f"held {sent} for {seconds:g}s"
        if action == "wait":
            seconds = max(0.0, min(float(p.get("seconds") if p.get("seconds") is not None else 1.0), 60.0))
            time.sleep(seconds)
            return f"waited {seconds:g}s"
        if action == "wait_for":
            text = p.get("text")
            if not text:
                raise RpcError("wait_for needs text")
            timeout = max(0.5, min(float(p.get("timeout") or 10.0), 120.0))
            gone = bool(p.get("gone"))
            ok, elapsed, where = self.perception.wait_for(str(text), timeout=timeout, gone=gone)
            what = f'"{text}" {"to disappear" if gone else "to appear"}'
            if not ok:
                raise RpcError(f"timed out after {timeout:g}s waiting for {what}")
            if gone:
                return f'"{text}" is gone (after {elapsed:.1f}s)'
            return f'"{text}" appeared after {elapsed:.1f}s' + (f": {where}" if where else "")
        if action == "close":
            return self._close(p.get("window") or p.get("target"))
        if action == "goto":  # a URL in the browser's current tab (open URL makes a new one)
            url = str(p.get("target") or p.get("text") or p.get("url") or "").strip()
            if not url:
                raise RpcError("goto needs a URL")
            focused = self.windows.focused()
            if focused is None or not self.BROWSER_APPS.search(focused.app or ""):
                raise RpcError("goto works in a browser window: open the URL instead (open example.com)")
            title = focused.title
            self.xi.key("ctrl+l")
            time.sleep(0.15)
            if url.isascii():
                self.xi.type(url)
            else:
                self._paste_keys(url, focused.app or "")  # (typing drops 東 and 都)
                time.sleep(0.2)
            self.xi.key("Return")
            end = time.monotonic() + 15.0  # the new page's title first, then until it has loaded
            while time.monotonic() < end:
                time.sleep(0.25)
                now = self.windows.focused()
                if now is not None and now.title != title:
                    break
            self._wait_page_loaded(timeout=max(1.0, end - time.monotonic()), grace=0.6)
            return f"went to {url}"
        if action == "copy":
            # An element's whole text onto the clipboard (to paste it elsewhere: it needn't pass through you).
            t = r(p.get("target"))
            el = t.element
            text = a11y.full_text(el) if isinstance(el, a11y.Element) else str(getattr(el, "text", "") or "")
            if not text.strip():
                raise RpcError(f"{t.desc} has no text to copy")
            self._clip_set(text)
            return f"copied {len(text)} characters of {t.desc} to the clipboard"
        if action == "scroll_to":
            text = str(p.get("text") or "").strip()
            if not text:
                raise RpcError("scroll_to needs the text to look for")
            return self._scroll_to(text, max(1.0, min(float(p.get("timeout") or 20.0), 120.0)))
        if action == "focus":
            win = self.windows.find(p.get("window"))
            self.windows.activate(win.id)
            return f'focused "{win.title}"'
        if action == "open":
            res = self._open(  # (no look here: the act's own reply shows what changed)
                p.get("target"), wait=float(p.get("wait") or 12.0), install=p.get("install", True), look=False
            )
            if res.get("error"):
                raise RpcError(res["error"])
            w = res.get("window")
            done = f"opened {res['command']}" + (f' → "{w["title"]}"' if w else "")
            if res.get("installed"):
                done = f"installed {res['installed']}, then {done}"
            return done + (f". Tips: {res['tips']}" if res.get("tips") else "")
        if action == "menu":
            return self._menu(p.get("item") or p.get("path") or p.get("text"))
        if action == "path":
            return self._file_dialog(str(p.get("path") or p.get("text") or ""), bool(p.get("overwrite")))
        raise RpcError(f"unknown action {action!r}")

    # -- menus and file dialogs ---------------------------------------
    def _focused_a11y(self):
        focused = self.windows.focused()
        if focused is None:
            raise RpcError("no window is focused: open an app first")
        aw = a11y.window_for(focused) if a11y.AVAILABLE else None
        return focused, aw

    def _menu(self, item) -> str:
        """Choose a menu command by its path ("File > Export > PDF"), as a person would, in one step."""
        if isinstance(item, (list, tuple)):
            parts = [str(s).strip() for s in item if str(s).strip()]
        else:
            parts = [s.strip() for s in re.split(r"\s*(?:>|→|›)\s*", str(item or "")) if s.strip()]
        if not parts:
            raise RpcError("menu needs a menu path, e.g. menu File > Save As (see --menus lists them)")
        focused, aw = self._focused_a11y()
        if aw is None:
            raise RpcError(f'"{focused.title}" shows no menus to accessibility: use its keyboard shortcuts or click it')
        try:
            nodes = a11y.find_menu_path(aw, parts, check_enabled=False)
        except ValueError as e:
            raise RpcError(str(e)) from e
        label = " > ".join(parts)
        dialog = a11y.opens_dialog(nodes[-1])
        try:
            before = {w.id for w in self.windows.list(with_states=False)} if dialog else set()
        except WindowError:
            dialog = False
        # Some apps (LibreOffice) update whether a command is available only when its menu opens: a command
        # that reads as greyed out is checked again with its menus open.
        stale = not a11y.enabled(nodes[-1])
        if not stale and a11y.press_menu(nodes):
            return f"chose {label}" + self._dialog_note(dialog, before)
        # This app needs its menus opened: click through them like a person.
        for node in nodes:
            box = None
            for _ in range(12):
                box = a11y.menu_box(node)
                if box:
                    break
                time.sleep(0.15)
            if box is None:
                self.xi.key("Escape")
                raise RpcError(f"could not open the menus to reach {label}: click them, or use the app's shortcut")
            if node is nodes[-1] and not a11y.enabled(node):
                for _ in nodes:
                    self.xi.key("Escape")
                raise RpcError(f'"{label}" is greyed out right now (disabled), even with its menu open')
            x, y, w, h = box
            self.xi.click(x + w // 2, y + h // 2)
            time.sleep(0.3)
        return f"chose {label} (clicked through the menus)" + self._dialog_note(dialog, before)

    def _dialog_note(self, dialog: bool, before: set) -> str:
        """A command whose label ends in "…" opens a dialog: wait for it, and say so if it doesn't come."""
        if not dialog or self._wait_new_window(before, timeout=8.0):
            return ""
        return " (its dialog hasn't opened yet: look again in a moment)"

    def _wait_new_window(self, before: set, timeout: float = 4.0) -> bool:
        """Wait for a window that wasn't open before (the dialog a "Chart…" command opens takes a moment)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            time.sleep(0.15)
            try:
                if {w.id for w in self.windows.list(with_states=False)} - before:
                    return True
            except WindowError:
                return False
        return False

    PATH_LABEL = re.compile(r"^(file ?name|name|location|save as|file|path|object name|folder( name)?)\b", re.I)
    FILE_DIALOG = re.compile(
        r"open|save|export|import|select|choose|browse|file|folder|location|upload|attach|insert", re.I
    )

    def _path_field(self):
        """The text box of the focused file dialog that takes a file name or path, or None."""
        focused, aw = self._focused_a11y()
        if aw is None:
            return None, focused
        snap = a11y.snapshot(aw, max_elements=400, budget=2.0, screen=self.size)
        fields = [el for el in snap.elements if el.role in a11y.TEXT_INPUT and el.role != "terminal"]
        named = [el for el in fields if self.PATH_LABEL.match((el.name or "").strip())]
        if named:
            return next((el for el in named if "focused" in el.states), named[0]), focused
        if self.FILE_DIALOG.search(focused.title or ""):
            return next((el for el in fields if "focused" in el.states), None), focused
        return None, focused

    def _await_dialog(self, timeout: float = 5.0) -> None:
        """Give a file dialog that is still opening (ctrl+s was pressed just now) time to take the focus, so the
        path goes into the dialog and not into the app's own window."""
        deadline, first = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            try:
                focused = self.windows.focused()
            except WindowError:
                focused = None
            if focused is not None:
                first = first or focused.id
                aw = a11y.window_for(focused) if a11y.AVAILABLE else None
                if aw is None:  # (a Windows program: no accessibility to tell a dialog by, but its title says)
                    if focused.id != first or self.FILE_DIALOG.search(focused.title or ""):
                        return
                elif aw.get("role") != "frame" or focused.id != first:  # a dialog, or the focus moved on
                    return
            time.sleep(0.2)

    def _file_dialog(self, path: str, overwrite: bool = False) -> str:
        """Type a full path into the open file dialog (Open, Save As, Export, Upload, ...) and confirm."""
        if not path.strip():
            raise RpcError("path needs a file path, e.g. path ~/Documents/report.pdf")
        windows_path = re.match(r"^[A-Za-z]:[\\/]", path.strip()) is not None  # C:\users\agent\x.txt
        full = path.strip() if windows_path else os.path.normpath(os.path.expanduser(path.strip()))
        if not windows_path and not os.path.isabs(full):
            full = os.path.join(self.home, full)
        self._await_dialog()
        field, focused = self._path_field()
        wine = focused is not None and self._is_wine(focused)
        if field is None and wine and self.FILE_DIALOG.search(focused.title):
            return self._wine_file_dialog(focused, full, overwrite)
        if windows_path and not wine:
            raise RpcError(
                f"{full} is a Windows path, and this is a Linux program: use a Linux path such as ~/Documents/x "
                "(in Wine, C:\\users\\agent is the desktop's home ~)"
            )
        if field is None:  # GTK's Open dialog has no path box until ctrl+L asks for one
            self.xi.key("ctrl+l")
            time.sleep(0.5)
            field, focused = self._path_field()
        if field is None:
            raise RpcError(
                "no file dialog is open: open one first (ctrl+o to open, ctrl+shift+s to save as), then use path"
            )
        typed = full
        if self._is_wine(focused):
            typed = "Z:" + full.replace("/", "\\")  # a Windows program (Wine) sees the Linux root as Z:
        self.xi.click(field.center[0], field.center[1])
        time.sleep(0.1)
        self.xi.key("ctrl+a")
        self.xi.type(typed)
        time.sleep(0.15)
        self.xi.key("Delete")  # drop a selected auto-completion suffix, so Return takes exactly this path
        self.xi.key("Return")
        if not self._focus_leaves(focused.id, 8.0):  # (inserting a big image can keep the dialog up for seconds)
            raise RpcError(
                f"entered {full}, but the file dialog is still open: if that is a folder it opened it; "
                "otherwise check its file type list or see what it says"
            )
        done = self._confirm_replace(overwrite)
        problem = self._dialog_error()
        if problem:
            raise RpcError(f"the file dialog refused {full}: {problem}")
        return f"entered {full} in the file dialog" + done

    def _wine_file_dialog(self, focused, full: str, overwrite: bool) -> str:
        """A Windows program's Open/Save dialog (Wine: no accessibility): its "File name" box takes a full
        path. Alt+N goes to that box in Windows' common dialogs; Wine reads the Linux root as drive Z:."""
        typed = full if re.match(r"^[A-Za-z]:[\\/]", full) else "Z:" + full.replace("/", "\\")
        self.xi.key("alt+n")
        time.sleep(0.15)
        self.xi.key("ctrl+a")
        self.xi.type(typed)
        time.sleep(0.15)
        self.xi.key("Return")
        if not self._focus_leaves(focused.id, 6.0):
            raise RpcError(
                f"typed {typed} into the Windows file dialog, but it is still open: if that is a folder it opened "
                "it; otherwise look at what the dialog says"
            )
        time.sleep(0.3)
        try:
            now = self.windows.focused()
        except WindowError:
            now = None
        done = ""
        if now is not None and self._is_wine(now) and re.search(r"save as|confirm|replace|exist", now.title, re.I):
            # "x already exists. Do you want to replace it?": Yes is Alt+Y, No is Alt+N
            if not overwrite:
                self.xi.key("alt+n")
                raise RpcError(f"{full} already exists: use overwrite=true (path ... --overwrite) to replace it")
            self.xi.key("alt+y")
            done = " (replaced the existing file)"
        return f"entered {full} in the Windows file dialog" + done

    def _focus_leaves(self, wid: str, timeout: float) -> bool:
        """Wait until window `wid` is no longer focused (closed, or a confirmation came up over it)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.2)
            try:
                now = self.windows.focused()
            except WindowError:
                continue
            if now is None or now.id != wid:
                time.sleep(0.3)  # let the next window draw and fill its accessibility tree
                return True
        return False

    def _dialog_error(self) -> str:
        """The message of an error box the app just showed (and closes it), or ""."""
        try:
            focused, aw = self._focused_a11y()
        except RpcError:
            return ""
        if aw is None:
            return ""
        snap = a11y.snapshot(aw, max_elements=60, budget=1.5, screen=self.size)
        is_alert = any(el.role == "alert" for el in snap.elements) or re.search(r"error|warning", focused.title, re.I)
        said = [el.name or el.text for el in snap.elements if el.role in ("label", "static", "text") and el.name]
        if not is_alert or not said:
            return ""
        ok = next((el for el in snap.elements if el.role in ("push button", "button")), None)
        if ok is not None:
            self.xi.click(*ok.center)
        else:
            self.xi.key("Escape")
        return " ".join(said)[:300]

    @staticmethod
    def _is_wine(win) -> bool:
        """Is this window a Windows program running in Wine? (Its process is Wine's loader, named after the .exe.)"""
        try:
            with open(f"/proc/{win.pid}/cmdline", "rb") as f:
                cmdline = f.read().decode("utf-8", "replace")
            exe = os.path.basename(os.readlink(f"/proc/{win.pid}/exe"))
        except OSError:
            return False
        return bool(re.search(r"\.exe\b", cmdline, re.I) or exe.startswith("wine"))

    def _confirm_replace(self, overwrite: bool) -> str:
        """Answer "a file named x already exists, replace it?" only when the caller said so."""
        try:
            focused, aw = self._focused_a11y()
        except RpcError:
            return ""
        if aw is None or aw.get("role") not in ("alert", "dialog", "file chooser"):
            return ""  # back in the app's own window (whose status bar may well say "Overwrite"): no question asked
        snap = a11y.snapshot(aw, max_elements=120, budget=1.5, screen=self.size)
        said = " ".join(f"{el.name} {el.text}" for el in snap.elements)
        if not re.search(r"already exists|replace it\b|overwrite it\b", said, re.I):
            return ""
        buttons = {(el.name or "").strip().lower(): el for el in snap.elements if el.role in ("push button", "button")}
        answer = next((buttons[n] for n in ("replace", "overwrite", "yes", "ok") if n in buttons), None)
        cancel = next((buttons[n] for n in ("cancel", "no") if n in buttons), None)
        if overwrite and answer is not None:
            self.xi.click(*answer.center)
            self._focus_leaves(focused.id, 3.0)
            return " and replaced the existing file"
        if cancel is not None:
            self.xi.click(*cancel.center)
        else:
            self.xi.key("Escape")
        raise RpcError("that file already exists: nothing was replaced. Use path with overwrite to replace it")

    def _portable(self, params: dict) -> dict:
        """Step parameters with @ids replaced by what they pointed at (a label or x,y), so a
        recorded macro still works in another session."""
        out = dict(params)
        for key in ("target", "from", "to"):
            v = out.get(key)
            if isinstance(v, str) and re.fullmatch(r"\s*@\d+\s*", v):
                el = self.perception.registry.get(int(v.strip()[1:]))
                if el is None:
                    continue
                # A control's name ("Save", "File name:") is stable; its content (a document's text, a
                # cell's value) changes, so elements without a name are recorded by position.
                label = getattr(el, "name", "") if hasattr(el, "label") else getattr(el, "text", "")
                if label and len(label) <= 80:
                    out[key] = label
                else:
                    cx, cy = el.center
                    out[key] = f"{cx},{cy}"
        return out

    def m_act(self, p: dict) -> dict:
        steps = p.get("actions")
        if steps is None:
            raise RpcError('act needs `actions`: a list like [{"action": "click", "target": "@3"}]')
        if not isinstance(steps, list):
            steps = [steps]
        if not steps:
            raise RpcError("act needs at least one action")
        parsed = []
        for s in steps:
            try:
                parsed.append(parse_step(s))
            except (RpcError, ValueError) as e:
                raise RpcError(f"invalid action {json.dumps(s)[:100]}: {e}") from e
        t0 = time.monotonic()
        results = []
        error = None
        self._covered = False
        will_wait = (
            p.get("settle", True) is not False
            and p.get("wait_busy", True) is not False
            and any(a in ("click", "double_click", "key", "type", "fill", "select", "menu") for a, _ in parsed)
        )
        with self.input_lock:
            files_before = self._files_state()
            known_busy = self._known_busy() if will_wait else None  # (a look costs time: only if it will be used)
            before_frame = self.screen.grab()
            before = thumb(before_frame)
            try:
                wins_before = {w.id: w for w in self.windows.list(with_states=False)}
            except WindowError:
                wins_before = {}
            focused_app = next((w.app for w in wins_before.values() if w.focused), None)
            status_before = self._status_bar() if "libreoffice" in (focused_app or "").lower() else None
            if focused_app and focused_app != getattr(self, "_macro_app", None):
                # A replay must type into the same app: record the switch (apps, not titles: "Untitled 2")
                self.recorder.add_macro("focus", {"window": focused_app})
                self._macro_app = focused_app
            for i, (action, params) in enumerate(parsed):
                if error is not None:
                    results.append(
                        {
                            "action": action,
                            "ok": False,
                            "skipped": True,
                            "detail": "Not executed: an earlier action failed.",
                        }
                    )
                    continue
                try:
                    portable = self._portable(params)  # before the action: @ids describe the old screen
                    detail = self._do(action, params)
                    results.append({"action": action, "ok": True, "detail": detail})
                    self.recorder.add_macro(action, portable)
                    if i < len(parsed) - 1:
                        # Let the app process the event before the next one, like a person would. Typing that
                        # a busy app is still drawing would otherwise be overtaken by the next click (and land
                        # in the next field), and a click that moves the focus must have moved it before typing.
                        nxt = parsed[i + 1][0]
                        if nxt == "wait_for" and action in ("click", "double_click", "key", "type", "fill", "select"):
                            # A link or Return may have started loading another page: its text, not the old
                            # page's, is what the wait is for.
                            self._wait_page_loaded(timeout=8.0, grace=0.6)
                        elif action in ("type", "paste", "fill") and nxt not in ("wait", "wait_for"):
                            settle(self.screen, timeout=1.5, quiet=0.25, min_wait=0.1)
                        elif action == "click" and nxt in ("type", "paste", "key"):
                            settle(self.screen, timeout=1.0, quiet=0.15)
                        else:
                            time.sleep(0.2 if action in ("open", "focus") else 0.06)
                except (RpcError, TargetError, InputError, WindowError, ValueError, TypeError) as e:
                    error = str(e)
                    results.append({"action": action, "ok": False, "detail": error})
            if p.get("settle", True) is not False:
                settled, _, frame = settle(self.screen, timeout=float(p.get("settle_timeout") or 2.5))
                if any(a in ("click", "double_click", "key", "fill", "type") for a, _ in parsed[: len(results)]):
                    if self._wait_page_loaded(timeout=8.0):  # a click or Return may have started a navigation
                        settled, _, frame = settle(self.screen, timeout=1.5)
            else:
                settled, frame = False, self.screen.grab()
            busy_note = None
            if will_wait:
                # Work the action started ("Generating…", a spinner's text, a progress bar): wait it out, so the
                # reply shows the result instead of the busy screen.
                busy_note = self._wait_busy(known_busy, float(p.get("busy_timeout") or 20.0))
                if busy_note:
                    settled, _, frame = settle(self.screen, timeout=1.5)
            frac, bbox = diff(before, thumb(frame))
            change = describe_change(frac, bbox)
            try:
                wins_after = self.windows.list(with_states=False)
            except WindowError:
                wins_after = []
            acted = [  # (a busy app can take in a burst of typing and only repaint after the screen looked settled)
                a
                for a, _ in parsed[: len(results)]
                if a in ("click", "double_click", "key", "fill", "select", "type", "paste", "menu", "path")
            ]
            if (
                acted
                and p.get("settle", True) is not False
                and not change.get("changed")
                and {w.id for w in wins_after} == set(wins_before)
            ):
                # Dialogs often appear a moment after the key or click (ctrl+s, "Save changes?"), and an app that
                # is still busy (starting up) can take in typing and only show it seconds later: keep looking for
                # a while before reporting that nothing happened.
                typed = sum(len(str(q.get("text") or "")) for a, q in parsed[: len(results)] if a in ("type", "paste"))
                end = time.monotonic() + 1.5 + min(3.0, typed / 30)
                while time.monotonic() < end:
                    time.sleep(0.3)
                    if diff(before, thumb(self.screen.grab()))[0]:
                        break
                settled, _, frame = settle(self.screen, timeout=1.5)
                frac, bbox = diff(before, thumb(frame))
                change = describe_change(frac, bbox)
                try:
                    wins_after = self.windows.list(with_states=False)
                except WindowError:
                    pass
        after_ids = {w.id for w in wins_after}
        for w in wins_after:
            if w.focused or w.id not in wins_before:
                self.windows.refine(w)
        opened = [w.to_dict() for w in wins_after if w.id not in wins_before]
        closed = [w.to_dict() for wid, w in wins_before.items() if wid not in after_ids]
        focused = next((w for w in wins_after if w.focused), None)
        dialog = self._page_dialog(focused) if change.get("changed") else None
        files = self._files_changed(files_before, self._files_state())
        if busy_note:
            files = [busy_note, *files]
        summary = self._summary(results, change, opened, closed, focused, wins_before, dialog, files)
        self.recorder.add(
            "act", " · ".join(r["detail"] for r in results if not r.get("skipped")), frame, ok=error is None
        )
        out = {
            "ok": error is None,
            "error": error,
            "steps": results,
            "summary": summary,
            "settled": settled,
            "elapsed": round(time.monotonic() - t0, 3),
            "change": change,
            "focused": focused.to_dict() if focused else None,
            "opened": opened,
            "closed": closed,
        }
        observe = set(str(p.get("observe") or "auto").replace(",", "+").split("+"))
        if "auto" in observe:
            # What changed on screen comes along when the action took you somewhere: a new page or window, a
            # dialog, or work it waited for. That's what the next look would be for.
            observe.discard("auto")
            prev = next((w for w in wins_before.values() if w.focused), None)
            moved = focused is not None and (prev is None or prev.id != focused.id or prev.title != focused.title)
            # A click, a key or a picked option that changed the screen (a wizard's next step, a form's result, a
            # console's output) is also worth showing: the next thing an agent does is look at what it did.
            committed = any(
                a in ("click", "double_click", "key", "select", "menu", "path", "close", "scroll_to", "fill", "drag")
                or a in ("move", "goto")
                or (a == "type" and "\n" in str(q.get("text") or ""))
                for a, q in parsed[: len(results)]
            )
            if self._covered:  # a pop-up took a click: show it, with its buttons, to close it
                observe.add("changes")
            if error is None and (
                opened or closed or dialog or busy_note or moved or (committed and change.get("changed"))
            ):
                observe.add("changes")
            if not observe:
                observe.add("summary")
        if p.get("screenshot"):
            observe.add("screenshot")
        if p.get("see"):
            observe.add("see")
        if "screenshot" in observe:
            img = frame.copy()
            try:
                cx, cy = self.xi.position()
                draw_cursor(img, cx, cy)
            except InputError:
                pass
            img, scale = fit(img, p.get("max_width"), p.get("max_height"))
            fmt = (p.get("format") or "png").lower()
            out["screenshot"] = {
                "data": _b64(encode(img, fmt)),
                "format": fmt,
                "mime": mime(fmt),
                "width": img.width,
                "height": img.height,
                "scale": round(scale, 5),
            }
        if "crop" in observe and change.get("changed"):
            out["crop"] = self._crop(frame, change["region"])
        if "see" in observe or "changes" in observe:
            out["see"] = self.perception.see(ocr=p.get("ocr", "auto"), changes="see" not in observe)
        elif status_before is not None and error is None:
            # LibreOffice's status bar says what a click did when the screen barely shows it: a shape selected
            # or its text being edited, the selected object's position and size, the slide or page.
            now = [t for t in self._status_bar() or [] if t not in status_before]
            if now:
                out["summary"] += "\n→ status bar: " + " · ".join(now[:5])
        return out

    def _status_bar(self) -> list[str] | None:
        """The texts of the focused LibreOffice window's status bar, or None."""
        try:
            focused = self.windows.focused()
            aw = a11y.window_for(focused) if focused is not None and a11y.AVAILABLE else None
        except Exception:
            return None
        return a11y.status_bar_texts(aw) if aw is not None else None

    def _crop(self, frame, region) -> dict:
        """Just the part of the screen that changed (with some context): far fewer image tokens."""
        x, y, w, h = region
        sw, sh = self.size
        pad = 24
        w2, h2 = max(w + 2 * pad, 320), max(h + 2 * pad, 200)
        x0 = max(0, min(sw - w2, x - (w2 - w) // 2))
        y0 = max(0, min(sh - h2, y - (h2 - h) // 2))
        box = (x0, y0, min(sw, x0 + w2), min(sh, y0 + h2))
        img = frame.crop(box)
        try:
            cx, cy = self.xi.position()
            draw_cursor(img, cx, cy, offset=(box[0], box[1]))
        except InputError:
            pass
        return {
            "data": _b64(encode(img, "png")),
            "format": "png",
            "mime": "image/png",
            "width": img.width,
            "height": img.height,
            "region": [box[0], box[1], box[2] - box[0], box[3] - box[1]],
        }

    def _busy_now(self) -> set[str]:
        """Busy texts in the focused window right now (a quick look at what is on screen)."""
        try:
            focused = self.windows.focused()
        except WindowError:
            return set()
        aw = a11y.window_for(focused) if focused is not None and a11y.AVAILABLE else None
        if aw is None:
            return set()
        snap = a11y.snapshot(aw, max_elements=400, budget=0.6)
        return {t for e in snap.elements if (t := busy_text(e.role, e.name or e.text))}

    def _known_busy(self) -> set[str] | None:
        """The busy texts already on screen before an action (a page that always says "Loading more…" is not
        busy because of it): from the last look at this window, else a quick look now."""
        try:
            focused = self.windows.focused()
        except WindowError:
            return None
        if focused is None:
            return None
        stuck = self._stuck_busy.get(focused.id, set())  # texts that never went away: not a sign of work
        view = self.perception.last_views.get(focused.id)
        if view is not None:
            return stuck | {t for (key, *_rest) in view["items"].values() if (t := busy_text(key[0], key[1] or key[2]))}
        return stuck | self._busy_now()

    def _wait_busy(self, known: set[str] | None, timeout: float) -> str | None:
        """If the action made the app say it is busy, wait (up to `timeout`) until it stops saying so."""
        busy = self._busy_now() - (known or set())
        if not busy:
            return None
        t0 = time.monotonic()
        what = sorted(busy, key=len)[0]
        while time.monotonic() - t0 < timeout:
            time.sleep(0.5)
            if not (self._busy_now() & busy):
                return f'waited {time.monotonic() - t0:.1f}s while it showed "{what}"'
        try:
            focused = self.windows.focused()
            if focused is not None:
                self._stuck_busy.setdefault(focused.id, set()).update(busy)
        except WindowError:
            pass
        return f'it still shows "{what}" after {timeout:g}s (still working? wait_for the result, or look)'

    DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y", "%d.%m.%Y")

    def _fill_date(self, t, el, text: str) -> str:
        """fill on a date field (Firefox's mm/dd/yyyy editor): any clear date, typed part by part in the field's
        own order, so "2027-03-15" doesn't become 12/09/0007."""
        import datetime as dt

        day = None
        for fmt in self.DATE_FORMATS:
            try:
                day = dt.datetime.strptime(text.replace(",", ""), fmt).date()
                break
            except ValueError:
                continue
        if day is None:
            raise RpcError(f'{t.desc} is a date field: give a date like 2027-03-15 (got "{text}")')
        parts = a11y.segments(el)
        values = {"month": f"{day.month:02d}", "day": f"{day.day:02d}", "year": f"{day.year:04d}"}
        typed = 0
        for part in parts:
            key = next((k for k in values if k in part.name.casefold()), None)
            if key is None:
                continue
            x, y = part.center
            self.xi.click(x, y)
            time.sleep(0.05)
            self.xi.type(values[key])
            typed += 1
        if typed < 3:
            raise RpcError(f"{t.desc}: couldn't find its month, day and year parts; click it and type the digits")
        time.sleep(0.15)
        return f"filled {t.desc} with {day.isoformat()}"

    def _set_value(self, t, el, text: str) -> str:
        """fill on a slider: set its value (accessibility first, then the arrow keys, as a person would)."""
        try:
            want = float(text.rstrip("%"))
        except ValueError:
            raise RpcError(f"{t.desc} is a slider: fill it with a number, e.g. fill {t.desc.split()[0]} 70") from None
        now, limits = a11y.set_value(el, want)
        if now is not None and abs(now - want) < 1e-6:
            return f"set {t.desc} to {now:g}"
        if limits is None or now is None:
            raise RpcError(f"{t.desc} doesn't say its value: click a spot on it, or use the arrow keys")
        lo, hi, step = limits
        if not lo <= want <= hi:
            raise RpcError(f"{t.desc} goes from {lo:g} to {hi:g}: {want:g} is out of range")
        a11y.grab_focus(el)
        time.sleep(0.1)
        now = a11y.value_of(el) if a11y.value_of(el) is not None else now  # (the set may have moved it after all)
        presses = round(abs(want - now) / step)
        if presses:
            self.xi.key("Right" if want > now else "Left", min(presses, 500))
        time.sleep(0.15)
        got = a11y.value_of(el)
        return f"set {t.desc} to {got:g}" if got is not None else f"moved {t.desc} {presses} steps toward {want:g}"

    def _close(self, which=None, win=None) -> str:
        """Close a window like its title bar's X button: the app may ask first ("Save changes?")."""
        if win is None:
            win = self.windows.find(str(which)) if which else self.windows.focused()
        if win is None:
            raise RpcError("no window is focused: name the window to close")
        self.windows.close(win.id)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            time.sleep(0.2)
            try:
                if all(w.id != win.id for w in self.windows.list(with_states=False)):
                    return f'closed "{win.title}"'
            except WindowError:
                continue
        return f'asked "{win.title}" to close; it is still open (look: it may be asking something, e.g. to save)'

    def _scroll_to(self, query: str, timeout: float) -> str:
        """Bring text into view wherever it is in the focused window: further down a long page, or not
        loaded yet (a feed that loads more as you scroll: scroll to its end until the text shows up)."""
        deadline = time.monotonic() + timeout
        focused = self.windows.focused()
        aw = a11y.window_for(focused) if focused is not None and a11y.AVAILABLE else None
        if aw is None:
            raise RpcError("scroll_to needs a window whose text accessibility can read (a web page, most apps)")
        loads, stale = 0, 0
        while True:
            found, last, count = a11y.search(aw, query, budget=min(3.0, max(0.5, deadline - time.monotonic())))
            if found is not None:
                a11y.scroll_into_view(found)
                time.sleep(0.35)
                x, y, w, h = a11y.refresh(found) or (found.x, found.y, found.w, found.h)
                cx, cy = x + w // 2, y + h // 2
                shown = " ".join(f"{found.name} {found.text}".split()) or found.value
                more = f" (after loading more {loads} time{'s' if loads != 1 else ''})" if loads else ""
                return f'scrolled to "{query}"{more}: {found.role} "{shown[:300]}" ({cx},{cy})'
            if last is None or stale >= 2 or time.monotonic() >= deadline:
                why = f"after loading more {loads} times" if loads else "on this page"
                raise RpcError(f'"{query}" is not in the focused window ({why}); check the spelling, or look')
            # Not there (yet): scroll to the page's end, which makes a feed load more, then look again once
            # the page has grown (a feed fetches the next entries first).
            _, before = a11y.page_state(aw, limit=8000)
            a11y.scroll_into_view(last)
            loads += 1
            grew, until = False, min(deadline, time.monotonic() + 3.0)
            while time.monotonic() < until:
                time.sleep(0.4)
                _, now = a11y.page_state(aw, limit=8000)
                if now > before:
                    grew = True
                    time.sleep(0.3)  # (the rest of the batch)
                    break
            stale = 0 if grew else stale + 1

    def _in_browser(self) -> bool:
        try:
            focused = self.windows.focused()
        except WindowError:
            return False
        return focused is not None and bool(self.BROWSER_APPS.search(focused.app or ""))

    def _page_dialog(self, focused) -> str | None:
        """A web page's alert/confirm/prompt in the focused browser window: the window list doesn't show it."""
        if focused is None or not a11y.AVAILABLE or not self.BROWSER_APPS.search(focused.app or ""):
            return None
        try:
            aw = a11y.window_for(focused)
            return a11y.page_dialog(aw) if aw else None
        except Exception:
            return None

    def _files_state(self, limit: int = 4000) -> dict:
        """The files in the home folder, two folders deep (hidden ones skipped): what an action saves or
        downloads shows up here, and the reply can say where it went."""
        state: dict[str, tuple[int, int]] = {}
        budget = limit

        def scan(folder: str, depth: int) -> None:
            nonlocal budget
            try:
                with os.scandir(folder) as entries:
                    for e in entries:
                        budget -= 1
                        if budget <= 0:
                            return
                        if e.name.startswith("."):
                            continue
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if depth < 2:
                                    scan(e.path, depth + 1)
                            elif e.is_file(follow_symlinks=False):
                                st = e.stat(follow_symlinks=False)
                                state[e.path] = (st.st_mtime_ns, st.st_size)
                        except OSError:
                            continue
            except OSError:
                return

        scan(self.home, 0)
        if budget <= 0:
            state["\0partial"] = (0, 0)  # (a scan that stopped early can't tell what was deleted)
        return state

    def _files_changed(self, before: dict, after: dict) -> list[str]:
        def short(path: str) -> str:  # ~/Downloads/x.csv (with / on every system)
            inside = path.startswith(os.path.join(self.home, ""))
            return ("~" + path[len(self.home) :] if inside else path).replace(os.sep, "/")

        def size(n: int) -> str:
            return f"{n} bytes" if n < 1024 else f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"

        notes = []
        for path, (_, n) in sorted(after.items(), key=lambda kv: -kv[1][0]):
            if path == "\0partial":
                continue
            if path.endswith((".part", ".crdownload", ".tmp")) or os.path.basename(path).startswith(".~lock."):
                if path not in before and path.endswith((".part", ".crdownload")):
                    notes.append(f"downloading {short(path.rsplit('.', 1)[0])} (not finished yet)")
                continue
            if path + ".part" in after or path + ".crdownload" in after:
                continue  # the browser's placeholder for a download in progress
            kind = _office_kind(path)
            if path not in before:
                notes.append(f"new file {short(path)} ({size(n)}{kind})")
            elif before[path] != after[path]:
                notes.append(f"saved {short(path)} ({size(n)}{kind})")
        if "\0partial" not in before and "\0partial" not in after:
            notes += [f"deleted {short(path)}" for path in before if path not in after]
        if len(notes) > 4:
            notes = notes[:4] + [f"{len(notes) - 4} more files changed"]
        return notes

    def _summary(self, results, change, opened, closed, focused, wins_before, dialog=None, files=()) -> str:
        parts = [
            ("✓ " if r["ok"] else ("· " if r.get("skipped") else "✗ ")) + r["detail"]
            for r in results
            if not r.get("skipped")
        ]
        skipped = sum(1 for r in results if r.get("skipped"))
        if skipped:
            parts.append(f"{skipped} later action{'s' if skipped > 1 else ''} not executed")
        tail = []
        waits_only = all(r.get("action") in ("wait", "wait_for") for r in results)
        if change.get("changed"):
            x, y, w, h = change["region"]
            pct = change["fraction"] * 100
            amount = f"{pct:.0f}%" if pct >= 1 else "<1%"
            tail.append(f"screen changed {amount} (region {x},{y} {w}x{h})")
        elif not waits_only:  # after a wait, "no visible change" reads like a failure
            tail.append("no visible change")
        if dialog:
            tail.append(f'the page opened a dialog: "{dialog}" (answer it: see lists its field and buttons)')
        tail.extend(files)
        for w in opened[:3]:
            tail.append(f'opened "{w["title"]}"')
        for w in closed[:3]:
            tail.append(f'closed "{w["title"]}"')
        if focused is not None:
            prev = next((w for w in wins_before.values() if w.focused), None)
            if prev is None or prev.id != focused.id or prev.title != focused.title:
                tail.append(f'focused "{focused.title}"')
        return "\n".join(parts) + ("\n→ " + " · ".join(tail) if tail else "")

    # -- apps, shell, clipboard ---------------------------------------
    def _browser(self) -> str:
        env = os.environ.get("MINION_BROWSER")
        if env:
            return env
        for b in ("firefox-esr", "firefox", "chromium", "chromium-browser", "google-chrome"):
            if shutil.which(b):
                return b
        return "xdg-open"

    def _resolve_open(self, target: str) -> tuple[str, str]:
        t = target.strip()
        low = t.lower()
        for app in self.apps:
            if low in (str(app.get("name", "")).lower(), str(app.get("id", "")).lower()):
                return app["command"], "app"
        first, _, rest = t.partition(" ")
        for app in self.apps if rest.strip() else []:  # "notepad C:\users\agent\notes.txt", "editor ~/a.txt"
            if first.lower() in (str(app.get("name", "")).lower(), str(app.get("id", "")).lower()):
                arg = _unquote(rest.strip())
                if re.match(r"^[A-Za-z]:[\\/]", arg):  # a Windows path stays as it is, backslashes too
                    return f"{app['command']} {shlex.quote(arg)}", "app"
                if os.path.exists(os.path.expanduser(arg)):  # one file, spaces and all
                    return f"{app['command']} {shlex.quote(os.path.expanduser(arg))}", "app"
                try:  # several arguments (two files, a flag and a URL): each stays a word
                    words = [os.path.expanduser(w) for w in shlex.split(rest)]
                except ValueError:
                    words = rest.split()
                return f"{app['command']} {shlex.join(words)}", "app"
        if (
            URL_RE.match(t)
            or low.startswith(("about:", "file:", "data:"))
            or (DOMAIN_RE.match(t) and not os.path.exists(os.path.expanduser(t)))
        ):
            url = t if ("://" in t or ":" in t.split("/")[0]) else "https://" + t
            return f"{self._browser()} {shlex.quote(url)}", "url"
        path = os.path.expanduser(t)
        if os.path.exists(path):
            return self._file_opener(path), "file"
        try:
            first = os.path.expanduser(shlex.split(t)[0]) if t else ""
        except ValueError:
            first = ""
        if first and os.path.isfile(first) and os.access(first, os.X_OK):
            return t, "command"  # a program by its path, with arguments: ~/apps/postman/Postman --no-sandbox
        if t.startswith(("~", "/", "./", "../")) and " " not in t.split("/")[0]:
            raise RpcError(f"no such file in the desktop: {t} (list the folder with run('ls'))")
        return t, "command"

    def _from_catalog(self, target: str, install: bool) -> tuple[str, str, dict]:
        """`open NAME` for apps that aren't on this desktop's profile: web apps open in the browser, apps
        install themselves the first time (Debian packages, .debs, AppImages, GitHub releases), and apps
        that don't exist on Linux come back with alternatives. Returns (command, kind, notes)."""
        app, rest = catalog.lookup(target)
        if app is None:
            word = target.split()[0] if target.split() else ""
            if word and "/" not in word and not shutil.which(word) and install and catalog.apt_package(word):
                try:
                    secs, _ = catalog.install([word])
                except catalog.InstallError as e:
                    raise RpcError(f"{word} is not installed and {e}") from e
                return target, "command", {"installed": f"{word} ({secs:.0f}s)"}
            return target, "command", {}
        name = app.get("name", app["id"])
        notes: dict = {"app": app["id"]}
        if app["id"] not in self._tipped and catalog.tips(app):
            self._tipped.add(app["id"])
            notes["tips"] = catalog.tips(app)
        if app.get("unavailable"):
            raise RpcError(catalog.unavailable_message(app))
        if app.get("url"):
            return f"{self._browser()} {shlex.quote(app['url'])}", "url", notes
        if not catalog.installed(app):
            if not install:
                raise RpcError(f"{name} is not installed here; open it with install allowed (the default) to add it")
            try:
                secs, _ = catalog.install_app(app)
            except catalog.InstallError as e:
                raise RpcError(f"{name} is not installed and {e}") from e
            notes["installed"] = f"{name} ({secs:.0f}s)"
        return app["command"] + (f" {rest}" if rest else ""), "app", notes

    OFFICE_EXT = {
        ".docx",
        ".doc",
        ".odt",
        ".rtf",
        ".xlsx",
        ".xls",
        ".ods",
        ".csv",
        ".tsv",
        ".pptx",
        ".ppt",
        ".odp",
        ".odg",
    }
    WEB_EXT = {".pdf", ".html", ".htm", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
    WINE_EXT = {".exe", ".msi", ".bat", ".cmd", ".lnk"}
    TEXT_EXT = {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".ts",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sh",
        ".css",
        ".xml",
        ".log",
        ".ini",
        ".cfg",
    }

    def _file_opener(self, path: str) -> str:
        """Pick the app for a file by extension (deterministic), falling back to xdg-open."""
        ext = os.path.splitext(path)[1].lower()
        q = shlex.quote(path)
        if ext in self.OFFICE_EXT and shutil.which("libreoffice"):
            return f"libreoffice {q}"
        if ext in self.WINE_EXT and shutil.which("wine"):  # Windows programs (the `windows` profile)
            return f"wine start /unix {q}"  # .msi included: start hands it to msiexec
        if ext in self.WEB_EXT and self._browser() != "xdg-open":
            return f"{self._browser()} {q}"
        if ext in self.TEXT_EXT:
            for editor in ("mousepad", "geany", "gedit"):
                if shutil.which(editor):
                    return f"{editor} {q}"
        if os.path.isdir(path):
            for fm in ("pcmanfm", "thunar", "nautilus"):
                if shutil.which(fm):
                    return f"{fm} {q}"
        return f"xdg-open {q}"

    def _open(self, target, wait: float = 12.0, install: bool = True, look: bool = True) -> dict:
        if not target:
            raise RpcError("open needs a target: an app name, a URL, a file path or a command")
        cmd, kind = self._resolve_open(str(target))
        extra: dict = {}
        if kind == "command":
            cmd, kind, extra = self._from_catalog(str(target).strip(), install)
        if kind == "url" and cmd.startswith("xdg-open ") and install:  # no browser here (the base profile)
            browser = catalog.find("firefox")
            if browser is not None and not catalog.installed(browser):
                try:
                    secs, _ = catalog.install_app(browser)
                except catalog.InstallError as e:
                    raise RpcError(f"this desktop has no web browser and {e}") from e
                extra["installed"] = f"{browser.get('name', 'Firefox')} ({secs:.0f}s)"
                cmd = self._browser() + cmd[len("xdg-open") :]
        try:
            before = {w.id: w for w in self.windows.list(with_states=False)}
        except WindowError:
            before = {}
        prev_focus = next((w for w in before.values() if w.focused), None)
        log_path = os.path.join(os.environ.get("MINION_RUNTIME_DIR", "/tmp"), f"open-{time.time_ns() // 1000000}.log")
        with open(log_path, "ab") as log:
            proc = subprocess.Popen(
                ["bash", "-lc", cmd],
                cwd=self.home,
                env=catalog.launch_env(),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        t0 = time.monotonic()
        found = None
        while time.monotonic() - t0 < wait:
            time.sleep(0.25)
            try:
                now = self.windows.list(with_states=False)
            except WindowError:
                continue
            new = [w for w in now if w.id not in before]
            if new:
                found = next((w for w in new if w.focused), new[-1])
                break
            focus = next((w for w in now if w.focused), None)
            if kind == "url" and focus and prev_focus and focus.id == prev_focus.id and focus.title != prev_focus.title:
                found = focus
                break
            if proc.poll() is not None and proc.returncode != 0 and kind != "url":
                break
        if found is not None:
            found = self._until_ready(found, before, deadline=t0 + wait + 6)
            self.windows.refine(found)
            settle(self.screen, timeout=4.0, quiet=0.5)
            if kind == "url" or self.BROWSER_APPS.search(found.app or ""):
                if self._wait_page_loaded(timeout=10.0, require_page=kind == "url"):
                    settle(self.screen, timeout=2.0, quiet=0.4)
            elif re.search(r"libreoffice|soffice", found.app or "", re.I) and a11y.AVAILABLE:
                # The window shows before its document can take keystrokes: wait for the document.
                end = time.monotonic() + 8.0
                while time.monotonic() < end:
                    aw = a11y.window_for(found)
                    if aw is not None and a11y.has_document(aw):
                        break
                    time.sleep(0.25)
                time.sleep(0.3)
            try:  # the title changes as the page or document loads
                found = next((w for w in self.windows.list(with_states=False) if w.id == found.id), found)
            except WindowError:
                pass
        code = proc.poll()
        res = {
            "command": cmd,
            "kind": kind,
            "pid": proc.pid,
            "window": found.to_dict() if found else None,
            "elapsed": round(time.monotonic() - t0, 2),
            **extra,
        }
        try:
            also = [
                w for w in self.windows.list(with_states=False) if w.id not in before and found and w.id != found.id
            ]
            if also:
                res["also"] = [w.title for w in also if not self._splash(w)]
        except WindowError:
            pass
        problem = self._error_box(found) if found is not None and kind != "url" else None
        if problem:  # the app opened, but only to say it couldn't open the file: that is not a success
            res["error"] = f"it opened, but shows an error: {problem}"
        elif found is not None and a11y.AVAILABLE and look:
            try:  # a web page, or a question it opened on (a CSV's Text Import): what is on it comes along
                aw = a11y.window_for(self.windows.focused() or found)
                if kind == "url" or (aw is not None and aw.get("role") in ("dialog", "alert", "file chooser")):
                    res["look"] = self.perception.see()["text"]
            except (WindowError, RpcError, TargetError):
                pass
        if found is None and code not in (None, 0):
            try:
                with open(log_path, "rb") as f:
                    tail = f.read()[-400:].decode("utf-8", "replace").strip().splitlines()[-1:]
            except OSError:
                tail = []
            if code == 127:
                apps = ", ".join(str(a.get("id") or a.get("name", "")).lower() for a in self.apps)
                res["error"] = (
                    f"{target!r} is not an app, URL or file here, and no such command exists. "
                    f"Apps: {apps}. URLs need a dot (example.com) or a scheme (https://). Other programs install "
                    "with run('minion-install NAME') (a Debian package, or a .deb/.AppImage URL)."
                )
            else:
                res["error"] = f"exited with code {code}" + (f": {tail[0]}" if tail else "")
        return res

    BROWSER_APPS = re.compile(r"firefox|chromium|chrome|navigator|brave|vivaldi|opera|epiphany", re.I)
    FAILURE = re.compile(
        r"fail|error|could not|couldn't|cannot|can't|no such|not found|does(?:n't| not) exist|unable|denied", re.I
    )

    def _error_box(self, win) -> str | None:
        """What an error box says, if `win` is one ("GIMP Message": Opening '/x.png' failed: No such file)."""
        if not a11y.AVAILABLE:
            return None
        try:
            focused = self.windows.focused() or win
        except WindowError:
            focused = win
        aw = a11y.window_for(focused)
        if aw is None:
            return None
        snap = a11y.snapshot(aw, max_elements=60, budget=1.0, screen=self.size)
        # A message box (a dialog or an alert): a document titled "Problem set 3" or a page about errors is not one.
        if aw.get("role") not in ("alert", "dialog") and not any(el.role == "alert" for el in snap.elements):
            return None
        said = " ".join(
            el.name or el.text for el in snap.elements if el.role in ("label", "static", "text", "paragraph")
        ).strip()
        if not self.FAILURE.search(said):
            return None
        return f'"{focused.title}": {" ".join(said.split())[:300]}'

    def _wait_page_loaded(self, timeout: float = 10.0, require_page: bool = False, grace: float = 0.15) -> bool:
        """In a browser, wait while the page loads and its accessibility tree fills in. With require_page
        (a fresh `open`), also wait for the page to exist. True if it had to wait."""
        try:
            focused = self.windows.focused()
        except WindowError:
            return False
        if focused is None or not self.BROWSER_APPS.search(focused.app or "") or not a11y.AVAILABLE:
            return False
        deadline = time.monotonic() + timeout
        waited, last = False, -1
        time.sleep(0.15)  # a navigation starts a moment after the click
        if grace > 0.15:  # (before a wait_for: don't let the old page's text answer it)
            until = time.monotonic() + grace - 0.15
            while time.monotonic() < until:
                aw = a11y.find_window(title=None, pid=focused.pid)
                if aw and a11y.page_state(aw)[0]:
                    break
                time.sleep(0.1)
        while time.monotonic() < deadline:
            aw = a11y.find_window(title=None, pid=focused.pid)  # the title changes as pages load
            busy, size = a11y.page_state(aw) if aw else (None, 0)
            if busy is None and not (require_page and size == 0):
                return waited  # no web page here
            if busy or (busy is None and require_page):
                waited, last = True, -1
                time.sleep(0.25)
                continue
            if not (waited or require_page) or size == last:
                return waited  # loaded, and the tree stopped growing
            last = size
            time.sleep(0.3)
        return waited

    @staticmethod
    def _splash(w) -> bool:
        """A splash screen (LibreOffice's logo window, "GIMP Startup", "Loading…") is not the app's window yet."""
        if w.title in ("LibreOffice", "") and w.w <= 800 and w.h <= 400:
            return True
        return bool(re.search(r"\b(startup|starting|loading|splash)\b", w.title, re.I)) and w.w <= 900 and w.h <= 600

    def _until_ready(self, found, before: dict, deadline: float):
        """Apps often map a window before they are ready (a splash, a generic title that changes when
        the document loads). Wait until the new windows and their titles stop changing for a moment."""
        stable_since = time.monotonic()
        last = None
        while time.monotonic() < deadline:
            try:
                now = [w for w in self.windows.list(with_states=False) if w.id not in before]
            except WindowError:
                break
            sig = tuple((w.id, w.title) for w in now)
            if sig != last:
                last = sig
                stable_since = time.monotonic()
                real = [w for w in now if not self._splash(w)]
                if real:
                    found = next((w for w in real if w.focused), real[-1])
            elif time.monotonic() - stable_since >= 0.8 and not (now and all(self._splash(w) for w in now)):
                break
            time.sleep(0.15)
        return found

    def m_open(self, p: dict) -> dict:
        with self.input_lock:
            res = self._open(
                p.get("target"),
                wait=float(p.get("wait") or 12.0),
                install=p.get("install", True),
                look=p.get("look", True) is not False,
            )
        if "error" not in res:
            self.recorder.add_macro("open", {"target": p.get("target")})
        detail = res["command"] + (f" (installed {res['installed']} first)" if res.get("installed") else "")
        self.recorder.add("open", detail, self.screen.grab(), ok="error" not in res)
        return res

    def m_run(self, p: dict) -> dict:
        command = p.get("command")
        if not command:
            raise RpcError("run needs a command")
        if isinstance(command, list):
            command = shlex.join(str(c) for c in command)
        cwd = os.path.expanduser(p.get("cwd") or self.home)
        if p.get("background"):
            log_path = os.path.join(os.environ.get("MINION_RUNTIME_DIR", "/tmp"), f"bg-{time.time_ns() // 1000000}.log")
            with open(log_path, "ab") as log:
                proc = subprocess.Popen(
                    ["bash", "-lc", command],
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            self.recorder.add("run", f"{command} (background)")
            return {"pid": proc.pid, "background": True, "log": log_path}
        timeout = max(1.0, min(float(p.get("timeout") or 60.0), 3600.0))
        stdin = p.get("input")
        res = run_captured(["bash", "-lc", command], cwd, timeout, stdin.encode() if stdin is not None else None)
        self.recorder.add("run", f"$ {command[:200]} → exit {res['code']}")
        if p.get("record", True):  # housekeeping (a folder made for a copy) is not part of the macro
            self.recorder.add_macro("run", {"command": command, "input": stdin})
        return res

    def m_script(self, p: dict) -> dict:
        """Run a Python program inside the desktop with the minion_agent.client API preloaded.
        Loops and retries happen here, not in the model's context: only what it prints returns."""
        code = p.get("code")
        if not code or not str(code).strip():
            raise RpcError("script needs Python code")
        timeout = max(1.0, min(float(p.get("timeout") or 120.0), 1800.0))
        folder = os.path.join(os.environ.get("MINION_RUNTIME_DIR", "/tmp/minion"), "scripts")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"script-{int(time.time() * 1000)}.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(code))
        res = run_captured(
            [sys.executable, "-u", "-c", SCRIPT_BOOTSTRAP, path],
            self.home,
            timeout,
            None,
            out_limit=32 * 1024,
            err_limit=16 * 1024,
        )
        self.recorder.add("script", f"{len(str(code).splitlines())} lines → exit {res['code']}")
        return res

    def _type_via_clipboard(self, text: str, paste_all: bool = False) -> None:
        """Type ASCII lines with xdotool and paste the others (apps lose keymap-remapped characters such
        as ü, 你 or emoji), or paste every line (paste_all). Tab and Return stay key presses, so a spreadsheet
        row still moves from cell to cell. The clipboard is restored."""
        try:
            saved = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=3)
            previous = saved.stdout if saved.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            previous = None
        focused = self.windows.focused()
        app = focused.app if focused is not None else ""
        for token in re.split(r"(\n|\t)", text.replace("\r\n", "\n")):
            if token in ("\n", "\t"):
                self.xi.type(token)
                time.sleep(0.05)
            elif token.isascii() and not (paste_all and len(token) > 3):
                self.xi.type(token)
            elif token:
                self._paste_keys(token, app)
                time.sleep(0.25)
        if previous is not None:
            subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=previous, timeout=5)

    def _paste_keys(self, text: str, app: str) -> None:
        """Put text on the clipboard and press the app's paste shortcut."""
        if re.fullmatch(r"(u?xterm|u?rxvt.*)", app, re.I):  # xterm has no paste shortcut for CLIPBOARD
            self._clip_set(text, primary=True)
            time.sleep(0.05)
            self.xi.key("shift+Insert")
            return
        self._clip_set(text)
        time.sleep(0.05)
        term = re.search(r"term|konsole|kitty|alacritty|tilix|terminator", app, re.I)
        self.xi.key("ctrl+shift+v" if term else "ctrl+v")

    def _clip_set(self, text: str, primary: bool = False) -> None:
        if not shutil.which("xclip"):
            raise RpcError("xclip is not installed in this desktop")
        for selection in ("clipboard", "primary") if primary else ("clipboard",):
            subprocess.run(
                ["xclip", "-selection", selection, "-i"],
                input=text.encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )

    def m_clipboard(self, p: dict) -> dict:
        if "text" in p and p["text"] is not None:
            self._clip_set(str(p["text"]))
            return {"ok": True, "length": len(str(p["text"]))}
        if not shutil.which("xclip"):
            raise RpcError("xclip is not installed in this desktop")
        try:
            out = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=3)
        except subprocess.TimeoutExpired:
            return {"text": ""}
        limit = max(1000, min(int(p.get("limit") or MAX_OUTPUT), 50_000_000))  # the live view copies it whole
        return {"text": _trim(out.stdout.decode("utf-8", "replace"), limit) if out.returncode == 0 else ""}

    # -- files ---------------------------------------------------------
    def m_ls(self, p: dict) -> dict:
        """A folder's entries, folders first, then files by name (the live view's Files panel)."""
        shown = str(p.get("path") or "~")
        path = os.path.realpath(os.path.expanduser(shown))
        if not os.path.isdir(path):
            raise RpcError(f"no such folder in the desktop: {shown}")
        entries = []
        try:
            with os.scandir(path) as it:
                for e in it:
                    if e.name.startswith(".") and not p.get("hidden"):
                        continue
                    try:
                        folder, st = e.is_dir(), e.stat()
                    except OSError:  # a broken link
                        continue
                    size = None if folder else st.st_size
                    entries.append({"name": e.name, "dir": folder, "size": size, "modified": round(st.st_mtime, 3)})
        except PermissionError:
            raise RpcError(f"{shown} can't be read here (permission denied)") from None
        entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
        limit = max(1, min(int(p.get("limit") or 1000), 10_000))
        return {"path": path, "home": self.home, "entries": entries[:limit], "total": len(entries)}

    # -- live view -----------------------------------------------------
    def m_frame(self, p: dict) -> dict:
        self.last_view = time.time()
        since = p.get("since")
        wait = max(0.0, min(float(p.get("wait") or 0) / 1000.0, 10.0))
        t0 = time.monotonic()
        while True:
            img = self.screen.grab()
            fp = fingerprint(img)
            try:
                cur = self.xi.position()
            except InputError:
                cur = (0, 0)
            key = f"{fp}:{cur[0]},{cur[1]}"
            if key != since or time.monotonic() - t0 >= wait:
                break
            time.sleep(0.1)
        if key == since:
            return {"unchanged": True, "key": key}
        draw_cursor(img, cur[0], cur[1])
        img, scale = fit(img, p.get("max_width") or 1600)
        data = encode(img, "jpeg", int(p.get("quality") or 72))
        return {
            "key": key,
            "data": _b64(data),
            "mime": "image/jpeg",
            "width": img.width,
            "height": img.height,
            "scale": round(scale, 5),
            "screen": list(self.size),
        }

    def m_input(self, p: dict) -> dict:
        """Raw input from a human in the live view (no settling, no element targets)."""
        kind = p.get("type")
        self.last_activity = time.time()
        with self.input_lock:
            if kind in ("move", "down", "up", "click", "scroll"):
                x, y = int(p.get("x", 0)), int(p.get("y", 0))
                sw, sh = self.size
                x, y = max(0, min(x, sw - 1)), max(0, min(y, sh - 1))
                if kind == "move":
                    self.xi.move(x, y)
                elif kind == "click":
                    self.xi.click(x, y, p.get("button") or "left", int(p.get("count") or 1))
                elif kind in ("down", "up"):
                    self.xi.move(x, y)
                    self.xi.button(kind == "down", p.get("button") or "left")
                else:
                    self.xi.scroll(p.get("direction") or "down", int(p.get("amount") or 1), x, y)
            elif kind == "key":
                self.xi.key(str(p.get("keys")))
            elif kind == "type":
                self.xi.type(str(p.get("text") or ""), 4)
            else:
                raise RpcError(f"unknown input type {kind!r}")
        return {"ok": True}

    # -- recording -----------------------------------------------------
    def m_record(self, p: dict) -> dict:
        action = (p.get("action") or "info").lower()
        if action == "info":
            return self.recorder.info()
        if action in ("on", "start"):
            self.recorder.enabled = True
            return self.recorder.info()
        if action in ("off", "stop"):
            self.recorder.enabled = False
            return self.recorder.info()
        if action == "clear":
            self.recorder.clear()
            return self.recorder.info()
        if action == "html":
            title = p.get("title") or f"Minion · {self.info.get('name') or 'desktop'}"
            return {"html": self.recorder.export_html(title)}
        if action == "script":
            return {"script": self.recorder.export_script(p.get("title") or f"Minion · {self.info.get('name') or ''}")}
        if action == "gif":
            try:
                data = self.recorder.export_gif(
                    width=int(p.get("width") or 720), frame_ms=int(p.get("frame_ms") or 900)
                )
            except ValueError as e:
                raise RpcError(str(e)) from e
            return {"data": _b64(data), "mime": "image/gif"}
        raise RpcError(f"unknown record action {action!r}")


# ---------------------------------------------------------------------------
def _handle(agent: Agent, conn: socket.socket, pool: ThreadPoolExecutor) -> None:
    wlock = threading.Lock()

    def respond(msg: dict) -> None:
        data = (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        with wlock:
            try:
                conn.sendall(data)
            except OSError:
                pass

    def run_one(req: dict) -> None:
        rid = req.get("id")
        try:
            result = agent.call(req.get("method"), req.get("params"))
            respond({"id": rid, "result": result})
        except RpcError as e:
            respond({"id": rid, "error": {"code": e.code, "message": str(e)}})
        except (TargetError, InputError, WindowError) as e:
            respond({"id": rid, "error": {"code": -32000, "message": str(e)}})
        except Exception as e:  # report, never crash the daemon
            respond({"id": rid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})

    try:
        with conn, conn.makefile("rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except json.JSONDecodeError:
                    respond({"id": None, "error": {"code": -32700, "message": "invalid JSON"}})
                    continue
                pool.submit(run_one, req)
    except OSError:
        pass


def serve(agent: Agent, path: str, ready: threading.Event | None = None) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o600)
    srv.listen(32)
    if ready is not None:
        ready.set()
    pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="rpc")
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            break
        threading.Thread(target=_handle, args=(agent, conn, pool), daemon=True).start()
