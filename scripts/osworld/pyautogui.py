"""The parts of pyautogui that OSWorld's setup and post-steps use, done with xdotool (Minion desktops have no pyautogui)."""

import subprocess
import time

FAILSAFE = False
_KEYS = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "win": "super",
    "command": "super",
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "pgup": "Prior",
    "pgdn": "Next",
    "insert": "Insert",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}


def _k(key):
    return _KEYS.get(str(key).lower(), str(key))


def _x(*args):
    subprocess.run(["xdotool", *map(str, args)])


def hotkey(*keys, **_):
    _x("key", "+".join(_k(k) for k in keys))


def press(keys, presses=1, interval=0.0, **_):
    for key in keys if isinstance(keys, (list, tuple)) else [keys]:
        for _n in range(presses):
            _x("key", _k(key))
            time.sleep(interval)


def keyDown(key, **_):
    _x("keydown", _k(key))


def keyUp(key, **_):
    _x("keyup", _k(key))


def typewrite(text, interval=0.0, **_):
    if isinstance(text, (list, tuple)):
        press(list(text), interval=interval)
    else:
        _x("type", "--delay", max(12, int(interval * 1000)), text)


write = typewrite


def moveTo(x=None, y=None, duration=0, **_):
    if x is not None:
        _x("mousemove", int(x), int(y))


def click(x=None, y=None, clicks=1, button="left", **_):
    moveTo(x, y)
    _x("click", "--repeat", clicks, {"left": 1, "middle": 2, "right": 3}[button])


def doubleClick(x=None, y=None, **_):
    click(x, y, clicks=2)


def rightClick(x=None, y=None, **_):
    click(x, y, button="right")


def scroll(clicks, x=None, y=None, **_):
    moveTo(x, y)
    _x("click", "--repeat", abs(int(clicks)), 4 if clicks > 0 else 5)


def size():
    return 1280, 800


def position():
    return 0, 0
