"""The Python SDK: `Desktop` gives an agent (or you) a whole Linux computer.

from minion import Desktop

desk = Desktop.create("browser")          # pulls/builds the image on first use
desk.open("news.ycombinator.com")
print(desk.see())                          # the page as compact text with @ids
desk.click("@12")                          # click by reference, text or [x, y]
desk.screenshot().save("page.png")
desk.remove()
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, profiles
from .backends import Backend, CreateOptions, DesktopInfo, get_backend
from .channel import Channel, ConnectionLost
from .errors import AgentError, MinionError, NotFound

SIZE_RE = re.compile(r"^\s*(\d{3,4})\s*[x×]\s*(\d{3,4})\s*$")


def _backend(backend) -> Backend:
    """A backend object as is (anything with the Backend methods), or one looked up by name."""
    return backend if backend is not None and not isinstance(backend, str) else get_backend(backend)


def _desk_path(path: str) -> str:
    """A desktop path for use inside double quotes in bash: ~ becomes $HOME, specials are escaped."""
    path = str(path)
    home = ""
    if path == "~" or path.startswith("~/"):
        home, path = "$HOME", path[1:]
    return home + re.sub(r'(["\\$`])', r"\\\1", path)


def normalize_size(size: str | tuple | None) -> str:
    if size is None or size == "":
        return config.DEFAULT_SIZE
    if isinstance(size, (tuple, list)):
        w, h = size
    else:
        m = SIZE_RE.match(str(size))
        if not m:
            raise MinionError(f"invalid size {size!r}: use WIDTHxHEIGHT, e.g. 1280x800")
        w, h = m.groups()
    w, h = int(w), int(h)
    if not (640 <= w <= 3840 and 480 <= h <= 2160):
        raise MinionError(f"size {w}x{h} out of range (640x480 to 3840x2160)")
    return f"{w}x{h}"


INSTALL_TIME = 660.0  # seconds an `open` may spend installing a missing app (big apps, slow links)


# ---------------------------------------------------------------------------
# results
@dataclass
class Screenshot:
    data: bytes
    width: int
    height: int
    format: str = "png"
    scale: float = 1.0
    region: tuple = (0, 0, 0, 0)

    @property
    def mime(self) -> str:
        return {"jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp"}.get(self.format, "image/png")

    def save(self, path: str | os.PathLike) -> Path:
        p = Path(path)
        p.write_bytes(self.data)
        return p

    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Map a point in this image to desktop coordinates (handles scaling and regions)."""
        rx, ry = self.region[0], self.region[1]
        return round(rx + x / (self.scale or 1)), round(ry + y / (self.scale or 1))

    def _repr_png_(self):  # Jupyter
        return self.data if self.format == "png" else None


@dataclass
class Observation:
    text: str
    elements: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    focused: dict | None = None
    ocr: list = field(default_factory=list)
    screen: tuple = (0, 0)
    changes: dict | None = None  # counts when this was a "changes" look

    def __str__(self) -> str:
        return self.text

    def find(self, query: str) -> list[dict]:
        q = query.casefold()
        return [e for e in self.elements + self.ocr if q in (e.get("name") or e.get("text") or "").casefold()]


@dataclass
class ActResult:
    ok: bool
    summary: str
    steps: list = field(default_factory=list)
    change: dict = field(default_factory=dict)
    focused: dict | None = None
    opened: list = field(default_factory=list)
    closed: list = field(default_factory=list)
    error: str | None = None
    screenshot: Screenshot | None = None
    observation: Observation | None = None
    crop: Screenshot | None = None
    elapsed: float = 0.0

    def __str__(self) -> str:
        return self.summary

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class RunResult:
    code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    elapsed: float = 0.0
    pid: int | None = None
    log: str | None = None  # background jobs: the file in the desktop that collects their output

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out

    def __str__(self) -> str:
        return self.stdout

    def check(self) -> RunResult:
        if not self.ok:
            what = "timed out" if self.timed_out else f"exited with code {self.code}"
            raise MinionError(f"command {what}: {self.stderr.strip()[-500:] or self.stdout.strip()[-500:]}")
        return self


def _screenshot(d: dict) -> Screenshot:
    return Screenshot(
        base64.b64decode(d["data"]),
        d["width"],
        d["height"],
        d.get("format", "png"),
        d.get("scale", 1.0),
        tuple(d.get("region") or (0, 0, d["width"], d["height"])),
    )


def _observation(d: dict) -> Observation:
    return Observation(
        text=d.get("text", ""),
        elements=d.get("elements", []),
        windows=d.get("windows", []),
        focused=d.get("focused"),
        ocr=d.get("ocr", []),
        screen=tuple(d.get("screen") or (0, 0)),
        changes=d.get("changes"),
    )


# ---------------------------------------------------------------------------
class Desktop:
    """A handle to one desktop. Cheap to create; the connection opens lazily."""

    def __init__(self, name: str, backend: Backend | str | None = None, *, _owned: bool = False):
        self.name = name
        self.backend = _backend(backend)
        self._channel: Channel | None = None
        self._lock = threading.Lock()
        self._owned = _owned
        self._info: DesktopInfo | None = None

    # -- construction --------------------------------------------------
    @classmethod
    def create(
        cls,
        profile: str = config.DEFAULT_PROFILE,
        name: str | None = None,
        size: str | tuple | None = None,
        *,
        backend: Backend | str | None = None,
        memory: str = "",
        cpus: str = "",
        network: bool = True,
        mounts: list[str] | None = None,
        env: dict | None = None,
        ports: list | None = None,
        progress=None,
        keep: bool = True,
    ) -> Desktop:
        """Create and start a desktop. `keep=False` removes it when used as a context manager."""
        be = _backend(backend)
        prof = profiles.get(profile)
        name = name or cls._free_name(be, prof.name)
        opts = CreateOptions(
            size=normalize_size(size or prof.merged("size") or None),
            memory=memory,
            cpus=cpus,
            network=network,
            mounts=list(mounts or []),
            env=dict(env or {}),
            ports=[str(p) for p in (ports or [])],
        )
        info = be.create(name, prof, opts, progress=progress)
        desk = cls(name, be, _owned=not keep)
        desk._info = info
        config.update_state(current=name)
        return desk

    @classmethod
    def create_many(
        cls,
        profile: str = config.DEFAULT_PROFILE,
        count: int = 2,
        *,
        names: list[str] | None = None,
        progress=None,
        **kw,
    ) -> list[Desktop]:
        """Create several desktops in parallel (one per worker/sub-agent)."""
        from concurrent.futures import ThreadPoolExecutor

        be = kw.pop("backend", None)
        be = _backend(be)
        prof = profiles.get(profile)
        be.prepare(prof, progress)  # pull/build the image once, not once per desktop
        if names is None:
            taken = {d.name for d in be.list()}
            names, n = [], 1
            while len(names) < count:
                if f"{profile}-{n}" not in taken:
                    names.append(f"{profile}-{n}")
                n += 1
        with ThreadPoolExecutor(max_workers=min(len(names), 8)) as pool:
            futures = [pool.submit(cls.create, profile, name=n, backend=be, progress=progress, **kw) for n in names]
            return [f.result() for f in futures]

    @staticmethod
    def _free_name(be: Backend, profile: str) -> str:
        taken = {d.name for d in be.list()}
        n = 1
        while f"{profile}-{n}" in taken:
            n += 1
        return f"{profile}-{n}"

    @classmethod
    def attach(cls, name: str | None = None, backend: Backend | str | None = None) -> Desktop:
        """Connect to an existing desktop (default: the current/most recent one)."""
        be = _backend(backend)
        if name:
            info = be.get(name)
            desk = cls(name, be)
            desk._info = info
            return desk
        desks = be.list()
        if not desks:
            raise NotFound("no desktops yet — create one with `minion up browser` (or Desktop.create())")
        current = config.load_state().get("current")
        for d in desks:
            if d.name == current:
                return cls(d.name, be)
        running = [d for d in desks if d.state in ("running", "paused")]
        if len(running or desks) == 1:
            return cls((running or desks)[0].name, be)
        # Several desktops and none chosen: guessing could act on another agent's desktop.
        names = ", ".join(d.name for d in (running or desks))
        raise MinionError(
            f"several desktops exist ({names}) and none is selected: pass -d NAME (CLI) or desktop=NAME "
            "(tools), or run `minion use NAME`"
        )

    @classmethod
    def list(cls, backend: Backend | str | None = None, stats: bool = False) -> list[DesktopInfo]:
        be = _backend(backend)
        return be.list(stats=stats)

    def __enter__(self) -> Desktop:
        return self

    def __exit__(self, *exc) -> None:
        if self._owned:
            try:
                self.remove()
            except MinionError:
                pass
        else:
            self.close()

    def __repr__(self) -> str:
        return f"Desktop({self.name!r}, backend={self.backend.name!r})"

    # -- transport -----------------------------------------------------
    def close(self) -> None:
        with self._lock:
            if self._channel is not None:
                self._channel.close()
                self._channel = None

    def info(self, refresh: bool = True) -> DesktopInfo:
        if refresh or self._info is None:
            self._info = self.backend.get(self.name)
        return self._info

    def _wake(self) -> bool:
        """Thaw or start the desktop if it is frozen or stopped. True if it changed anything."""
        info = self.info()
        if info.state == "paused":
            self.backend.thaw(self.name)
            return True
        if info.state in ("stopped", "created"):
            self.backend.start(self.name)
            return True
        return False

    def _call_once(self, method: str, params: dict | None, timeout: float, wake: bool = True):
        if wake:
            self.backend.ensure_awake(self.name)
        with self._lock:
            if self._channel is None:
                self._channel = self.backend.channel(self.name)
            ch = self._channel
        return ch.call(method, params, timeout=timeout)

    def call(self, method: str, params: dict | None = None, timeout: float = 120.0, *, wake: bool = True):
        """Raw RPC to the in-desktop agent (see minion/agent/server.py for methods).

        A frozen or stopped desktop is woken up transparently, unless wake=False (then the call
        fails instead, which is what housekeeping like the idle reaper wants)."""
        try:
            return self._call_once(method, params, timeout, wake)
        except AgentError as e:
            if wake and e.code == -32001 and self.info().state == "paused":  # frozen while the call was queued
                self.close()
                self.backend.thaw(self.name)
                raise AgentError(f"{e} — the desktop had been frozen; it is awake now, retry the call") from e
            if e.code == -32601:
                raise AgentError(
                    f"{e} — this desktop runs an older Minion agent; restart it to update: "
                    f"minion stop {self.name} && minion start {self.name}",
                    e.code,
                ) from e
            raise
        except ConnectionLost:
            self.close()
            if not wake:
                raise
            woke = self._wake()
            # Retry only if the desktop was asleep (the call never ran) or the call is
            # read-only; never replay actions that may already have happened.
            if not woke and method in ("act", "run", "open", "input", "window", "clipboard"):
                raise
            return self._call_once(method, params, timeout)

    # -- perception ----------------------------------------------------
    def hello(self) -> dict:
        return self.call("hello", timeout=30)

    @property
    def size(self) -> tuple[int, int]:
        w, h = self.hello()["screen"]
        return int(w), int(h)

    def screenshot(
        self,
        path: str | os.PathLike | None = None,
        *,
        region=None,
        max_width: int | None = None,
        max_height: int | None = None,
        scale: float | None = None,
        width: int | None = None,
        format: str = "png",
        quality: int = 80,
        cursor: bool = True,
        marks: bool = False,
        grid: bool = False,
    ) -> Screenshot:
        params = {
            "region": list(region) if region else None,
            "max_width": max_width,
            "max_height": max_height,
            "scale": scale,
            "width": width,
            "format": format,
            "quality": quality,
            "cursor": cursor,
            "marks": marks,
            "grid": grid,
        }
        shot = _screenshot(self.call("screenshot", {k: v for k, v in params.items() if v is not None}))
        if path:
            shot.save(path)
        return shot

    def zoom(self, region, width: int = 1024, **kw) -> Screenshot:
        """A region at higher magnification (region = [x, y, w, h])."""
        return self.screenshot(region=region, width=width, **kw)

    def see(
        self,
        ocr: bool | str = "auto",
        window: str | None = None,
        max_elements: int | None = None,
        full_text: bool = False,
        changes: bool = False,
        menus: bool = False,
    ) -> Observation:
        """The screen as text. `changes=True` returns only what changed since the previous look
        (ids are stable across looks); `full_text=True` keeps paragraphs whole (for reading);
        `menus=True` adds the focused app's menu commands and their shortcuts."""
        params = {
            "ocr": ocr,
            "window": window,
            "max_elements": max_elements,
            "full_text": full_text,
            "changes": changes,
            "menus": menus,
        }
        return _observation(self.call("see", params, timeout=90))

    def menus(self) -> list[str]:
        """The focused app's menu commands with their shortcuts, one line per menu."""
        return self.call("see", {"menus": True, "max_elements": 1}, timeout=90).get("menus", [])

    def cursor(self) -> tuple[int, int]:
        pos = self.call("cursor", timeout=30)
        return int(pos["x"]), int(pos["y"])

    def find(self, text: str, ocr: bool = True) -> list[dict]:
        return self.call("find", {"text": text, "ocr": ocr}, timeout=90)["matches"]

    # -- actions -------------------------------------------------------
    def act(
        self,
        *actions,
        observe: str = "summary",
        screenshot: bool = False,
        see: bool = False,
        settle: bool = True,
        settle_timeout: float = 2.5,
        check: bool = True,
        **kw,
    ) -> ActResult:
        """Run one or more actions in order (stops at the first failure), then wait for the
        screen to settle. Actions: dicts ({"click": "@3"}, {"action": "type", "text": "hi"})
        or strings ("click @3", "type 'hello'", "key ctrl+s")."""
        flat: list = []
        for a in actions:
            flat.extend(a if isinstance(a, list) else [a])
        params = {
            "actions": flat,
            "observe": observe,
            "screenshot": screenshot,
            "see": see,
            "settle": settle,
            "settle_timeout": settle_timeout,
            **kw,
        }
        opens = any("open" in (a if isinstance(a, str) else json.dumps(a)) for a in flat)
        res = self.call("act", params, timeout=300 + (INSTALL_TIME if opens else 0))  # `open` may install the app
        out = ActResult(
            ok=res["ok"],
            summary=res["summary"],
            steps=res["steps"],
            change=res.get("change", {}),
            focused=res.get("focused"),
            opened=res.get("opened", []),
            closed=res.get("closed", []),
            error=res.get("error"),
            elapsed=res.get("elapsed", 0.0),
        )
        if res.get("screenshot"):
            out.screenshot = _screenshot(res["screenshot"])
        if res.get("crop"):
            out.crop = _screenshot(res["crop"])
        if res.get("see"):
            out.observation = _observation(res["see"])
        if check and not out.ok:
            raise AgentError(out.error or out.summary)
        return out

    def click(
        self, target=None, *, button: str = "left", count: int = 1, modifiers: str | None = None, **kw
    ) -> ActResult:
        return self.act(
            {"action": "click", "target": target, "button": button, "count": count, "modifiers": modifiers}, **kw
        )

    def double_click(self, target=None, **kw) -> ActResult:
        return self.click(target, count=2, **kw)

    def right_click(self, target=None, **kw) -> ActResult:
        return self.click(target, button="right", **kw)

    def move(self, target, **kw) -> ActResult:
        return self.act({"action": "move", "target": target}, **kw)

    def drag(self, start, end, **kw) -> ActResult:
        return self.act({"action": "drag", "from": start, "to": end}, **kw)

    def type(self, text: str, **kw) -> ActResult:
        return self.act({"action": "type", "text": text}, **kw)

    def paste(self, text: str, **kw) -> ActResult:
        return self.act({"action": "paste", "text": text}, **kw)

    def fill(self, target, text: str, **kw) -> ActResult:
        return self.act({"action": "fill", "target": target, "text": text}, **kw)

    def select(self, target, option: str, **kw) -> ActResult:
        """Pick an option of a dropdown (a <select>, a combo box) by its visible text."""
        return self.act({"action": "select", "target": target, "option": option}, **kw)

    def menu(self, item: str, **kw) -> ActResult:
        """Choose a menu command by its path: desk.menu("File > Export as PDF")."""
        return self.act({"action": "menu", "item": item}, **kw)

    def path(self, file_path: str, overwrite: bool = False, **kw) -> ActResult:
        """Type a full path into the open file dialog (Open, Save As, Export, Upload...) and confirm it.
        An existing file is only replaced with overwrite=True."""
        return self.act({"action": "path", "path": file_path, "overwrite": overwrite}, **kw)

    def key(self, keys: str, repeat: int = 1, **kw) -> ActResult:
        return self.act({"action": "key", "keys": keys, "repeat": repeat}, **kw)

    def scroll(self, direction: str = "down", amount: int = 3, target=None, **kw) -> ActResult:
        return self.act({"action": "scroll", "direction": direction, "amount": amount, "target": target}, **kw)

    def wait(self, seconds: float = 1.0) -> None:
        time.sleep(seconds)

    def wait_for(self, text: str, timeout: float = 10.0, gone: bool = False) -> ActResult:
        return self.act({"action": "wait_for", "text": text, "timeout": timeout, "gone": gone}, settle=False)

    # -- apps, shell, files --------------------------------------------
    def open(self, target: str, wait: float = 12.0, install: bool = True) -> dict:
        """Launch an app ("writer", "gimp", "vscode", "figma"), a URL, a file in the desktop, or a shell
        command. Apps that aren't installed are installed first (install=False to fail instead)."""
        params = {"target": target, "wait": wait, "install": install}
        return self.call("open", params, timeout=wait + 60 + (INSTALL_TIME if install else 0))

    def run(
        self,
        command: str | list,
        timeout: float = 60.0,
        *,
        background: bool = False,
        cwd: str | None = None,
        input: str | None = None,
        record: bool = True,
    ) -> RunResult:
        res = self.call(
            "run",
            {
                "command": command,
                "timeout": timeout,
                "background": background,
                "cwd": cwd,
                "input": input,
                "record": record,
            },
            timeout=timeout + 30,
        )
        if background:
            return RunResult(code=None, pid=res.get("pid"), log=res.get("log"))
        return RunResult(res["code"], res["stdout"], res["stderr"], res["timed_out"], res.get("elapsed", 0.0))

    def script(self, code: str, timeout: float = 120.0) -> RunResult:
        """Run Python inside the desktop with the GUI API preloaded (see minion/agent/client.py):
        loops and retries without a round trip per step. Returns what it printed."""
        res = self.call("script", {"code": code, "timeout": timeout}, timeout=timeout + 30)
        return RunResult(res["code"], res["stdout"], res["stderr"], res["timed_out"], res.get("elapsed", 0.0))

    def upload(self, src: str | os.PathLike, dst: str = "~/") -> str:
        self._wake()
        folder = dst if dst.endswith("/") else (os.path.dirname(dst) or "~")
        if folder not in ("~", "~/", "/", "/tmp", "/tmp/"):  # make sure the destination folder exists
            self.run(f'mkdir -p -- "{_desk_path(folder)}"', timeout=15, record=False)
        self.backend.copy_in(self.name, str(src), dst)
        return dst

    def download(self, src: str, dst: str | os.PathLike = ".") -> Path:
        self._wake()
        p = Path(dst)
        into = p.is_dir()  # an existing folder receives the item; otherwise `dst` becomes it
        try:
            self.backend.copy_out(self.name, src, str(dst))
        except MinionError as e:
            if re.search(r"could not find|no such file|not found", str(e), re.I):
                raise NotFound(f"no such file in the desktop: {src}") from None
            raise
        return p / Path(src.rstrip("/")).name if into else p

    def write_text(self, path: str, text: str) -> None:
        """Write a UTF-8 text file in the desktop (as the desktop's user), creating missing folders."""
        target = _desk_path(path)
        res = self.run(f'mkdir -p -- "$(dirname -- "{target}")" && cat > "{target}"', timeout=60, input=text)
        if not res.ok:
            raise MinionError(f"could not write {path}: {(res.stderr or res.stdout).strip()[-300:]}")

    def read(self, path: str, max_chars: int = 200_000) -> str:
        """Any file's text: text files as they are, and documents converted inside the desktop: docx, xlsx
        (values and formulas), pptx, odt/ods/odp, pdf, epub, html, images (OCR), doc/xls/ppt, ..."""
        try:
            return self.call("read", {"path": path, "max_chars": max_chars}, timeout=900)["text"]
        except MinionError as e:
            if "unknown method" not in str(e):  # (a desktop made by an older Minion reads text files only)
                raise
            return self.read_text(path)

    def convert(self, path: str, to: str, outdir: str | None = None) -> str:
        """Convert a document or image in the desktop ("pdf", "docx", "xlsx", "csv", "pptx", "png", "md", ...).
        Returns the new file's path (next to the original unless outdir is given)."""
        return self.call("convert", {"path": path, "to": to, "outdir": outdir}, timeout=900)["path"]

    def read_text(self, path: str) -> str:
        """A text file from the desktop. Folders and binary files are errors (download those instead)."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self.backend.copy_out(self.name, path, tmp)
            except MinionError as e:
                if re.search(r"could not find|no such file|not found", str(e), re.I):
                    raise NotFound(f"no such file in the desktop: {path}") from None
                raise
            local = Path(tmp) / Path(path).name
            if local.is_dir():
                raise MinionError(f"{path} is a folder: list it with run('ls -la {path}')")
            data = local.read_bytes()
        if b"\x00" in data[:8192]:
            raise MinionError(f"{path} is a binary file ({len(data):,} bytes): download it instead of reading it")
        return data.decode("utf-8", errors="replace")

    @property
    def clipboard(self) -> str:
        return self.call("clipboard", {})["text"]

    @clipboard.setter
    def clipboard(self, text: str) -> None:
        self.call("clipboard", {"text": text})

    def windows(self) -> list[dict]:
        return self.call("windows")["windows"]

    def window(self, action: str = "focus", window: str | None = None, **geometry) -> dict:
        return self.call("window", {"action": action, "window": window, **geometry})

    # -- lifecycle -----------------------------------------------------
    def freeze(self) -> None:
        """Pause every process (0% CPU). Any later call thaws it automatically."""
        self.close()
        self.backend.freeze(self.name)

    def thaw(self) -> None:
        self.backend.thaw(self.name)

    def stop(self) -> None:
        self.close()
        self.backend.stop(self.name)

    def start(self) -> None:
        self.backend.start(self.name)

    def remove(self) -> None:
        self.close()
        self.backend.remove(self.name)
        if config.load_state().get("current") == self.name:
            config.update_state(current=None)

    def snapshot(self, tag: str | None = None) -> str:
        tag = tag or time.strftime("%Y%m%d-%H%M%S")
        self.close()
        return self.backend.snapshot(self.name, tag).tag

    def restore(self, tag: str) -> None:
        self.close()
        self._info = self.backend.restore(self.name, tag)

    def fork(self, name: str | None = None, progress=None) -> Desktop:
        """Clone this desktop's disk state into a new desktop (apps restart fresh)."""
        self.close()
        name = name or self._free_name(self.backend, f"{self.name}-fork")
        info = self.backend.fork(self.name, name, progress=progress)
        d = Desktop(name, self.backend)
        d._info = info
        return d

    def recording(self, format: str = "html", path: str | os.PathLike | None = None):
        """The flight recorder: every action with a thumbnail, as HTML (str) or GIF (bytes), or the
        actions as a replayable Python script (format="script"; run it with `script()`)."""
        if format == "script":
            code = self.call("record", {"action": "script", "title": f"Minion · {self.name}"})["script"]
            if path:
                Path(path).write_bytes(code.encode("utf-8"))
            return code
        if format == "gif":
            data = base64.b64decode(self.call("record", {"action": "gif"}, timeout=120)["data"])
            if path:
                Path(path).write_bytes(data)
            return data
        html = self.call("record", {"action": "html", "title": f"Minion · {self.name}"}, timeout=120)["html"]
        if path:
            Path(path).write_text(html, encoding="utf-8")
        return html

    def status(self) -> dict:
        return self.call("status")

    def logs(self, tail: int = 200) -> str:
        return self.backend.logs(self.name, tail)

    def to_dict(self) -> dict:
        return self.info().to_dict()

    def __str__(self) -> str:
        return self.name

    def _json(self) -> str:
        return json.dumps(self.to_dict())
