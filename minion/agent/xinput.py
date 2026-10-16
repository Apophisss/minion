"""Mouse and keyboard input through xdotool.

Key names follow xdotool/X keysym syntax ("ctrl+s", "Return", "alt+Tab"), which is
also what Claude's computer-use tool emits. Friendly aliases such as "enter",
"esc", "cmd+c" or "PageDown" are normalized.
"""

from __future__ import annotations

import os
import re
import subprocess
import time

BUTTONS = {"left": 1, "middle": 2, "right": 3}
SCROLL_BUTTONS = {"up": 4, "down": 5, "left": 6, "right": 7}

MODIFIERS = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "super": "super",
    "cmd": "ctrl",  # macOS habits (cmd+c, cmd+l): on these Linux desktops that is ctrl
    "command": "ctrl",
    "win": "super",
    "windows": "super",
    "meta": "super",
    "mod4": "super",
}

NAMED_KEYS = {
    "enter": "Return",
    "return": "Return",
    "ret": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "backspace": "BackSpace",
    "bs": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "ins": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "page_up": "Page_Up",
    "pgup": "Page_Up",
    "prior": "Page_Up",
    "pagedown": "Page_Down",
    "page_down": "Page_Down",
    "pgdn": "Page_Down",
    "next": "Page_Down",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "arrowup": "Up",
    "arrowdown": "Down",
    "arrowleft": "Left",
    "arrowright": "Right",
    "space": "space",
    "spacebar": "space",
    "menu": "Menu",
    "apps": "Menu",
    "contextmenu": "Menu",
    "print": "Print",
    "printscreen": "Print",
    "prtsc": "Print",
    "pause": "Pause",
    "break": "Pause",
    "capslock": "Caps_Lock",
    "caps_lock": "Caps_Lock",
    "numlock": "Num_Lock",
    "num_lock": "Num_Lock",
    "scrolllock": "Scroll_Lock",
    "scroll_lock": "Scroll_Lock",
    "plus": "plus",
    "minus": "minus",
    "equal": "equal",
    "equals": "equal",
    "comma": "comma",
    "period": "period",
    "dot": "period",
    "slash": "slash",
    "backslash": "backslash",
    "semicolon": "semicolon",
    "colon": "colon",
    "apostrophe": "apostrophe",
    "quote": "apostrophe",
    "grave": "grave",
    "backtick": "grave",
    "bracketleft": "bracketleft",
    "bracketright": "bracketright",
    "volumeup": "XF86AudioRaiseVolume",
    "volumedown": "XF86AudioLowerVolume",
    "mute": "XF86AudioMute",
}

CHAR_KEYS = {
    "+": "plus",
    "-": "minus",
    "=": "equal",
    ",": "comma",
    ".": "period",
    "/": "slash",
    "\\": "backslash",
    ";": "semicolon",
    ":": "colon",
    "'": "apostrophe",
    '"': "quotedbl",
    "`": "grave",
    "[": "bracketleft",
    "]": "bracketright",
    "{": "braceleft",
    "}": "braceright",
    "(": "parenleft",
    ")": "parenright",
    "<": "less",
    ">": "greater",
    "?": "question",
    "!": "exclam",
    "@": "at",
    "#": "numbersign",
    "$": "dollar",
    "%": "percent",
    "^": "asciicircum",
    "&": "ampersand",
    "*": "asterisk",
    "_": "underscore",
    "|": "bar",
    "~": "asciitilde",
    " ": "space",
}


class InputError(Exception):
    pass


def split_combo(combo: str) -> list[str]:
    """Split "ctrl+shift++" into ["ctrl", "shift", "+"]."""
    combo = combo.strip()
    if not combo:
        raise InputError("empty key")
    if combo == "+":
        return ["+"]
    parts: list[str] = []
    buf = ""
    i = 0
    while i < len(combo):
        ch = combo[i]
        if ch == "+" and buf:
            parts.append(buf)
            buf = ""
        elif ch == "+" and not buf:
            # a literal plus key, e.g. the last "+" of "ctrl++"
            buf = "+"
            parts.append(buf)
            buf = ""
        else:
            buf += ch
        i += 1
    if buf:
        parts.append(buf)
    return [p.strip() if p.strip() else p for p in parts]


def normalize_key(name: str, with_modifiers: bool = False) -> str:
    if name in CHAR_KEYS and len(name) == 1:
        return CHAR_KEYS[name]
    low = name.lower()
    if low in MODIFIERS:
        return MODIFIERS[low]
    if low in NAMED_KEYS:
        return NAMED_KEYS[low]
    if len(low) >= 2 and low[0] == "f" and low[1:].isdigit():
        return "F" + low[1:]
    if low.startswith("kp_") or low.startswith("xf86"):
        return name
    if len(name) == 1:
        # ctrl+A means ctrl+a (not ctrl+shift+a); a lone "A" stays a capital A.
        return name.lower() if with_modifiers and name.isalpha() else name
    return name  # assume a valid X keysym name such as "Return" or "ISO_Left_Tab"


def normalize_combo(combo: str) -> str:
    parts = split_combo(combo)
    has_mod = len(parts) > 1
    keys = [normalize_key(p, with_modifiers=has_mod) for p in parts]
    return "+".join(keys)


def normalize_modifiers(text: str | None) -> list[str]:
    if not text:
        return []
    mods = []
    for part in split_combo(text):
        low = part.lower()
        if low not in MODIFIERS:
            raise InputError(f"not a modifier key: {part!r} (use shift, ctrl, alt or super)")
        mods.append(MODIFIERS[low])
    return mods


class XInput:
    """Thin wrapper around xdotool bound to one X display."""

    def __init__(self, display: str, env: dict | None = None):
        self.display = display
        self.env = dict(env or os.environ)
        self.env["DISPLAY"] = display

    def _xdo(self, *args: str, timeout: float = 30.0) -> str:
        try:
            out = subprocess.run(["xdotool", *args], env=self.env, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as e:  # pragma: no cover - environment problem
            raise InputError("xdotool is not installed in this desktop") from e
        except subprocess.TimeoutExpired as e:
            raise InputError(f"xdotool timed out: {' '.join(args[:3])}") from e
        if out.returncode != 0:
            msg = (out.stderr or out.stdout).strip() or f"exit code {out.returncode}"
            raise InputError(f"xdotool {args[0]} failed: {msg}")
        if args[0] in ("key", "keydown", "keyup") and "No such key name" in out.stderr:
            bad = re.search(r"No such key name '([^']*)'", out.stderr)
            raise InputError(
                f"unknown key {bad.group(1) if bad else ''!r}: use names like Return, Tab, Escape, BackSpace, "
                "Delete, Home, End, Page_Up, Left, F5, or a single character (combos: ctrl+s)"
            )
        return out.stdout

    # -- pointer -------------------------------------------------------
    def position(self) -> tuple[int, int]:
        out = self._xdo("getmouselocation", "--shell")
        vals = dict(line.split("=", 1) for line in out.split() if "=" in line)
        return int(vals.get("X", 0)), int(vals.get("Y", 0))

    def _move_args(self, x: int, y: int) -> list[str]:
        """xdotool arguments that put the pointer at (x, y) and wait until it is there. None when it is
        there already: --sync would then wait ~15 s for a move that never happens."""
        x, y = max(0, int(x)), max(0, int(y))  # (xdotool reads "-26" as an option: never pass a negative point)
        try:
            if self.position() == (x, y):
                return []
        except InputError:
            return ["mousemove", str(x), str(y)]
        return ["mousemove", "--sync", str(x), str(y)]

    def move(self, x: int, y: int) -> None:
        args = self._move_args(x, y)
        if args:
            self._xdo(*args)

    def click(
        self, x: int | None, y: int | None, button: str = "left", count: int = 1, modifiers: list[str] | None = None
    ) -> None:
        b = BUTTONS.get(button)
        if b is None:
            raise InputError(f"unknown mouse button {button!r}")
        args: list[str] = []
        if x is not None and y is not None:
            args += self._move_args(x, y)
        for m in modifiers or []:
            args += ["keydown", m]
        args += ["click", "--repeat", str(max(1, int(count))), "--delay", "70", str(b)]
        for m in reversed(modifiers or []):
            args += ["keyup", m]
        self._xdo(*args)

    def button(self, down: bool, button: str = "left") -> None:
        b = BUTTONS.get(button)
        if b is None:
            raise InputError(f"unknown mouse button {button!r}")
        self._xdo("mousedown" if down else "mouseup", str(b))

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        modifiers: list[str] | None = None,
        steps: int = 12,
        button: str = "left",
    ) -> None:
        b = str(BUTTONS.get(button, 1))
        for m in modifiers or []:
            self._xdo("keydown", m)
        try:
            # Hover first: a browser starts a drag only from an element the pointer has been seen over.
            self.move(x1 + 3, y1)
            time.sleep(0.08)
            self.move(x1, y1)
            time.sleep(0.15)
            self._xdo("mousedown", b)
            time.sleep(0.12)
            last = (int(x1), int(y1))

            def to(px: float, py: float, pause: float) -> None:
                nonlocal last
                point = (max(0, round(px)), max(0, round(py)))
                if point != last:  # short drags repeat points, and --sync waits for a real move
                    self._xdo("mousemove", "--sync", str(point[0]), str(point[1]))
                    last = point
                time.sleep(pause)

            # Start slowly: toolkits wait for the pointer to pass a threshold, and a web page's drag-and-drop
            # only begins with the dragstart that follows; a fast first move loses the whole drag.
            dist = max(1.0, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
            for k in (3, 6, 10):
                if k < dist:
                    to(x1 + (x2 - x1) * k / dist, y1 + (y2 - y1) * k / dist, 0.04)
            time.sleep(0.08)
            for i in range(1, steps + 1):
                to(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps, 0.02)
            if dist >= 20:  # (a long drag: onto a drop target, which needs its dragover events before the drop)
                for ox in (2, -2, 0):
                    to(x2 + ox, y2, 0.05)
                time.sleep(0.1)
            self._xdo("mouseup", b)
        finally:
            for m in reversed(modifiers or []):
                self._xdo("keyup", m)

    def scroll(
        self,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
        modifiers: list[str] | None = None,
    ) -> None:
        b = SCROLL_BUTTONS.get(direction)
        if b is None:
            raise InputError(f"scroll direction must be up, down, left or right (got {direction!r})")
        amount = max(1, int(amount))
        args: list[str] = []
        if x is not None and y is not None:
            args += self._move_args(x, y)
        for m in modifiers or []:
            args += ["keydown", m]
        args += ["click", "--repeat", str(amount), "--delay", "25", str(b)]
        for m in reversed(modifiers or []):
            args += ["keyup", m]
        self._xdo(*args)

    # -- keyboard ------------------------------------------------------
    def key(self, combo: str, repeat: int = 1) -> str:
        """Press one combo ("ctrl+s") or a space-separated sequence ("BackSpace BackSpace Return")."""
        keys = [normalize_combo(c) for c in combo.split()] or [normalize_combo(combo)]
        self._xdo("key", "--clearmodifiers", "--repeat", str(max(1, int(repeat))), "--delay", "40", "--", *keys)
        return " ".join(keys)

    def key_down(self, combo: str) -> str:
        keys = normalize_combo(combo)
        self._xdo("keydown", "--", keys)
        return keys

    def key_up(self, combo: str) -> str:
        keys = normalize_combo(combo)
        self._xdo("keyup", "--", keys)
        return keys

    def type(self, text: str, delay_ms: int = 8, key_pause: float = 0.0, repeat_pause: float = 0.0) -> None:
        """Type text. key_pause waits after each Tab and Return; repeat_pause between two equal characters
        ("00", "ll"), which some apps take for one held key and drop (a calculator turns 7006652 into 70652)."""
        if not text:
            return
        # Newlines and tabs become real Return/Tab key presses (xdotool would send
        # Linefeed, which many toolkits ignore). Long runs are chunked to keep argv small;
        # xdotool handles any unicode character by remapping a spare keycode.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for token in re.split(r"(\n|\t)", text):
            if token == "\n":
                self._xdo("key", "--clearmodifiers", "Return")
                time.sleep(key_pause)
            elif token == "\t":
                self._xdo("key", "--clearmodifiers", "Tab")
                time.sleep(key_pause)
            elif token:
                runs = [token]
                if repeat_pause:
                    # Split between equal neighbours ("7006652" -> "70", "06", "652") and after operators ("12*",
                    # "2="): an app that works on a key (a calculator on "*") drops the keys that follow too soon.
                    runs, rest = [], token
                    while rest:
                        cut = next(
                            (
                                k
                                for k in range(1, len(rest))
                                if (rest[k] == rest[k - 1] and rest[k].isdigit()) or rest[k - 1] in "+-*/=%^"
                            ),
                            len(rest),
                        )
                        runs.append(rest[:cut])
                        rest = rest[cut:]
                for n, run in enumerate(runs):
                    if n:
                        time.sleep(repeat_pause)
                    for i in range(0, len(run), 200):
                        part = run[i : i + 200]
                        timeout = 30 + len(part) * (delay_ms + 30) / 1000
                        self._xdo(
                            "type", "--clearmodifiers", "--delay", str(int(delay_ms)), "--", part, timeout=timeout
                        )
