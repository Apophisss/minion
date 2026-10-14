"""Top-level window listing and management (EWMH, via wmctrl/xdotool/xprop)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field


@dataclass
class Window:
    id: str            # hex X window id, e.g. "0x01a00003"
    title: str
    app: str           # WM_CLASS class, e.g. "firefox-esr"
    pid: int
    x: int
    y: int
    w: int
    h: int
    focused: bool = False
    states: list[str] = field(default_factory=list)

    @property
    def minimized(self) -> bool:
        return "minimized" in self.states

    def to_dict(self) -> dict:
        d = asdict(self)
        d["minimized"] = self.minimized
        return d


class WindowError(Exception):
    pass


class Windows:
    def __init__(self, display: str, env: dict | None = None):
        self.env = dict(env or os.environ)
        self.env["DISPLAY"] = display

    def _run(self, *cmd: str, check: bool = True) -> str:
        try:
            out = subprocess.run(list(cmd), env=self.env, capture_output=True, text=True, timeout=10)
        except FileNotFoundError as e:
            raise WindowError(f"{cmd[0]} is not installed") from e
        except subprocess.TimeoutExpired as e:
            raise WindowError(f"{cmd[0]} timed out") from e
        if check and out.returncode != 0:
            raise WindowError((out.stderr or out.stdout).strip() or f"{cmd[0]} failed")
        return out.stdout

    def active_id(self) -> str | None:
        try:
            out = self._run("xdotool", "getactivewindow", check=False).strip()
        except WindowError:
            return None
        if not out.isdigit():
            return None
        return f"0x{int(out):08x}"

    def refine(self, win: Window) -> Window:
        """Exact on-screen frame geometry and EWMH states (wmctrl's geometry is WM-dependent)."""
        try:
            info = self._run("xwininfo", "-id", win.id, check=False)
            props = self._run("xprop", "-id", win.id, "_NET_WM_STATE", "_NET_FRAME_EXTENTS", check=False)
        except WindowError:
            return win
        ax = re.search(r"Absolute upper-left X:\s+(-?\d+)", info)
        ay = re.search(r"Absolute upper-left Y:\s+(-?\d+)", info)
        aw = re.search(r"Width:\s+(\d+)", info)
        ah = re.search(r"Height:\s+(\d+)", info)
        left = right = top = bottom = 0
        m = re.search(r"_NET_FRAME_EXTENTS\(CARDINAL\) = (\d+), (\d+), (\d+), (\d+)", props)
        if m:
            left, right, top, bottom = (int(v) for v in m.groups())
        if ax and ay and aw and ah:
            win.x = int(ax.group(1)) - left
            win.y = int(ay.group(1)) - top
            win.w = int(aw.group(1)) + left + right
            win.h = int(ah.group(1)) + top + bottom
        states = []
        for s in re.findall(r"_NET_WM_STATE_([A-Z_]+)", props):
            s = s.lower()
            if s == "hidden":
                s = "minimized"
            elif s in ("maximized_vert", "maximized_horz"):
                s = "maximized"
            elif s == "focused":
                continue
            if s not in states:
                states.append(s)
        win.states = states
        return win

    def list(self, with_states: bool = True) -> list[Window]:
        out = self._run("wmctrl", "-lpGx", check=False)
        active = self.active_id()
        wins: list[Window] = []
        for line in out.splitlines():
            parts = line.split(None, 8)
            if len(parts) < 8:
                continue
            wid, desk, pid, x, y, w, h, wmclass = parts[:8]
            rest = parts[8] if len(parts) > 8 else ""
            # rest = "<host> <title>"; host may be "N/A"
            title = rest.split(" ", 1)[1] if " " in rest else ""
            if desk == "-1":
                continue  # sticky panels / docks
            try:
                wid_norm = f"0x{int(wid, 16):08x}"
            except ValueError:
                continue
            app = wmclass.split(".")[-1] if "." in wmclass else wmclass
            win = Window(
                id=wid_norm, title=title.strip(), app=app, pid=int(pid) if pid.isdigit() else 0,
                x=int(x), y=int(y), w=int(w), h=int(h), focused=(wid_norm == active),
            )
            if with_states:
                self.refine(win)
            wins.append(win)
        return wins

    def focused(self) -> Window | None:
        for w in self.list(with_states=False):
            if w.focused:
                return self.refine(w)
        return None

    def find(self, query: str) -> Window:
        """Find a window by id ("0x..."), index ("1") or title/app substring."""
        wins = self.list(with_states=False)
        q = str(query).strip()
        if q.startswith("0x"):
            try:
                qn = f"0x{int(q, 16):08x}"
            except ValueError:
                qn = q
            for w in wins:
                if w.id == qn:
                    return w
        if q.isdigit() and 1 <= int(q) <= len(wins):
            return wins[int(q) - 1]
        low = q.lower()
        for w in wins:
            if w.title.lower() == low:
                return w
        for w in wins:
            if low in w.title.lower() or low == w.app.lower():
                return w
        raise WindowError(f"no window matches {query!r}")

    def activate(self, wid: str) -> None:
        self._run("wmctrl", "-i", "-a", wid)

    def close(self, wid: str) -> None:
        self._run("wmctrl", "-i", "-c", wid)

    def maximize(self, wid: str, on: bool = True) -> None:
        self._run("wmctrl", "-i", "-r", wid, "-b",
                  ("add" if on else "remove") + ",maximized_vert,maximized_horz")

    def minimize(self, wid: str) -> None:
        self._run("xdotool", "windowminimize", str(int(wid, 16)))

    def move_resize(self, wid: str, x: int, y: int, w: int, h: int) -> None:
        self.maximize(wid, on=False)
        self._run("wmctrl", "-i", "-r", wid, "-e", f"0,{int(x)},{int(y)},{int(w)},{int(h)}")
