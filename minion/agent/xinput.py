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
    "cmd": "super",
    "command": "super",
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
        return out.stdout

    # -- pointer -------------------------------------------------------
    def position(self) -> tuple[int, int]:
        out = self._xdo("getmouselocation", "--shell")
        vals = dict(line.split("=", 1) for line in out.split() if "=" in line)
        return int(vals.get("X", 0)), int(vals.get("Y", 0))

    def move(self, x: int, y: int) -> None:
        self._xdo("mousemove", "--sync", str(int(x)), str(int(y)))

    def click(
        self, x: int | None, y: int | None, button: str = "left", count: int = 1, modifiers: list[str] | None = None
    ) -> None:
        b = BUTTONS.get(button)
        if b is None:
            raise InputError(f"unknown mouse button {button!r}")
        args: list[str] = []
        if x is not None and y is not None:
            args += ["mousemove", "--sync", str(int(x)), str(int(y))]
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
            self._xdo("mousemove", "--sync", str(int(x1)), str(int(y1)))
            self._xdo("mousedown", b)
            time.sleep(0.05)
            for i in range(1, steps + 1):
                xi = round(x1 + (x2 - x1) * i / steps)
                yi = round(y1 + (y2 - y1) * i / steps)
                self._xdo("mousemove", "--sync", str(xi), str(yi))
                time.sleep(0.012)
            time.sleep(0.05)
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
            args += ["mousemove", "--sync", str(int(x)), str(int(y))]
        for m in modifiers or []:
            args += ["keydown", m]
        args += ["click", "--repeat", str(amount), "--delay", "25", str(b)]
        for m in reversed(modifiers or []):
            args += ["keyup", m]
        self._xdo(*args)

    # -- keyboard ------------------------------------------------------
    def key(self, combo: str, repeat: int = 1) -> str:
        keys = normalize_combo(combo)
        self._xdo("key", "--clearmodifiers", "--repeat", str(max(1, int(repeat))), "--delay", "40", "--", keys)
        return keys

    def key_down(self, combo: str) -> str:
        keys = normalize_combo(combo)
        self._xdo("keydown", "--", keys)
        return keys

    def key_up(self, combo: str) -> str:
        keys = normalize_combo(combo)
        self._xdo("keyup", "--", keys)
        return keys

    def type(self, text: str, delay_ms: int = 8) -> None:
        if not text:
            return
        # Newlines and tabs become real Return/Tab key presses (xdotool would send
        # Linefeed, which many toolkits ignore). Long runs are chunked to keep argv small;
        # xdotool handles any unicode character by remapping a spare keycode.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for token in re.split(r"(\n|\t)", text):
            if token == "\n":
                self._xdo("key", "--clearmodifiers", "Return")
            elif token == "\t":
                self._xdo("key", "--clearmodifiers", "Tab")
            elif token:
                for i in range(0, len(token), 200):
                    part = token[i : i + 200]
                    timeout = 30 + len(part) * (delay_ms + 30) / 1000
                    self._xdo("type", "--clearmodifiers", "--delay", str(int(delay_ms)), "--", part, timeout=timeout)
