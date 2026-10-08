"""X11 desktop backend: screenshots + input injection via xdotool.

Implements the 17 member tools of Claude's ``computer_toolset_20260801``
(screenshot, zoom, left_click, right_click, middle_click, double_click,
triple_click, left_click_drag, mouse_move, left_mouse_down, left_mouse_up,
cursor_position, scroll, type, key, hold_key, wait) with the parameter names
the toolset uses, so a ``tool_use`` block's ``name`` + ``input`` can be passed
straight to :meth:`Computer.run`.

Coordinates are in "model space": the pixel space of the screenshots this
backend returns. With the default 1280x800 display the scale is 1.0 and model
space == screen space. If the display is larger than the configured image
limits, screenshots are downscaled and incoming coordinates are scaled back up.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import re
import shlex
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

DISPLAY = os.environ.get("DISPLAY", ":1")
TYPING_DELAY_MS = int(os.environ.get("TYPING_DELAY_MS", "12"))
TYPING_CHUNK_CHARS = 50
# Claude image limits for models that support computer_toolset_20260801:
# <= 2576 px long edge and <= 4784 visual tokens (ceil(w/28) * ceil(h/28)).
# Requests carrying > 20 images are held to <= 2000 px per side, so default to 2000.
SCREENSHOT_MAX_LONG_EDGE = int(os.environ.get("SCREENSHOT_MAX_LONG_EDGE", "2000"))
SCREENSHOT_MAX_VISUAL_TOKENS = int(os.environ.get("SCREENSHOT_MAX_VISUAL_TOKENS", "4784"))
SCREENSHOT_CURSOR = os.environ.get("SCREENSHOT_CURSOR", "1") not in ("0", "false", "no")
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/tmp/desktop-api/screens")

MEMBERS = (
    "screenshot",
    "zoom",
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "left_click_drag",
    "mouse_move",
    "left_mouse_down",
    "left_mouse_up",
    "cursor_position",
    "scroll",
    "type",
    "key",
    "hold_key",
    "wait",
)

# Legacy computer_20251124 action aliases that map onto toolset members.
_ALIASES = {"left_mouse_click": "left_click", "mouse_down": "left_mouse_down", "mouse_up": "left_mouse_up"}

_CLICK_ARGS = {
    "left_click": ["click", "1"],
    "right_click": ["click", "3"],
    "middle_click": ["click", "2"],
    "double_click": ["click", "--repeat", "2", "--delay", "10", "1"],
    "triple_click": ["click", "--repeat", "3", "--delay", "10", "1"],
}
_SCROLL_BUTTON = {"up": "4", "down": "5", "left": "6", "right": "7"}

# Friendly / browser-style key names -> X keysym names understood by xdotool.
_KEY_ALIASES = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "backspace": "BackSpace",
    "del": "Delete",
    "delete": "Delete",
    "ins": "Insert",
    "insert": "Insert",
    "tab": "Tab",
    "space": "space",
    "spacebar": "space",
    "pageup": "Page_Up",
    "page_up": "Page_Up",
    "pgup": "Page_Up",
    "pagedown": "Page_Down",
    "page_down": "Page_Down",
    "pgdn": "Page_Down",
    "home": "Home",
    "end": "End",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "arrowup": "Up",
    "arrowdown": "Down",
    "arrowleft": "Left",
    "arrowright": "Right",
    "ctrl": "ctrl",
    "control": "ctrl",
    "control_l": "Control_L",
    "control_r": "Control_R",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "super": "super",
    "win": "super",
    "windows": "super",
    "meta": "super",
    "cmd": "super",
    "command": "super",
    "capslock": "Caps_Lock",
    "printscreen": "Print",
    "minus": "minus",
    "plus": "plus",
}
_MODIFIERS = {"ctrl", "alt", "shift", "super"}


class ActionError(Exception):
    """An anticipated failure; the message is safe to show to the model."""


@dataclass
class ActionResult:
    output: str | None = None
    image: bytes | None = None  # encoded image bytes (PNG unless image_format says otherwise)
    image_format: str = "png"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        import base64

        d: dict[str, Any] = {"ok": True, "output": self.output}
        if self.image is not None:
            d["image"] = {
                "media_type": f"image/{self.image_format}",
                "data": base64.b64encode(self.image).decode(),
            }
        if self.meta:
            d["meta"] = self.meta
        return d


def _normalize_combo(combo: str) -> str:
    """'Ctrl+Shift+t' -> 'ctrl+shift+t', 'Enter' -> 'Return', 'cmd+c' -> 'super+c'."""
    parts = [p for p in combo.strip().split("+")]
    out = []
    for p in parts:
        if p == "":  # "ctrl++" -> plus key
            out.append("plus")
            continue
        alias = _KEY_ALIASES.get(p.lower())
        if alias:
            out.append(alias)
        elif len(p) == 1:
            out.append(p)  # single character keysym, keep case
        elif re.fullmatch(r"[Ff]\d{1,2}", p):
            out.append(p.upper())
        else:
            out.append(p)  # assume a valid X keysym name (e.g. "KP_Enter", "XF86AudioMute")
    return "+".join(out)


def _normalize_keys(text: str) -> list[str]:
    """A key spec may contain several space-separated combos: 'ctrl+a Delete'."""
    if not isinstance(text, str) or not text.strip():
        raise ActionError("'text' must be a non-empty key or key combination, e.g. 'Return' or 'ctrl+s'")
    return [_normalize_combo(c) for c in text.split()]


def _modifier_keys(text: Any) -> list[str]:
    """Modifier string for click/scroll ('shift', 'ctrl+shift') -> ['shift'] / ['ctrl','shift']."""
    if text in (None, ""):
        return []
    if not isinstance(text, str):
        raise ActionError("'text' (modifier keys) must be a string such as 'shift' or 'ctrl+shift'")
    mods = [_KEY_ALIASES.get(m.strip().lower(), m.strip()) for m in text.split("+") if m.strip()]
    for m in mods:
        if m not in _MODIFIERS:
            raise ActionError(f"Unsupported modifier {m!r}; use shift, ctrl, alt or super")
    return mods


def fit_scale(width: int, height: int, max_long_edge: int, max_tokens: int) -> float:
    """Largest scale <= 1 so the image fits the long-edge and visual-token budgets."""
    s = min(1.0, max_long_edge / max(width, height))
    while s > 0.05 and math.ceil(width * s / 28) * math.ceil(height * s / 28) > max_tokens:
        s *= 0.99
    return s


class Computer:
    def __init__(self, display: str = DISPLAY) -> None:
        self.display = display
        self.env = {**os.environ, "DISPLAY": display}
        self.width = 0
        self.height = 0
        self.scale = 1.0  # model px per screen px
        self._lock = asyncio.Lock()
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # ------------------------------------------------------------------ setup
    async def init(self, retries: int = 60) -> None:
        last: Exception | None = None
        for _ in range(retries):
            try:
                out = await self._run("xdotool", "getdisplaygeometry", timeout=5)
                w, h = (int(v) for v in out.split()[:2])
                self.width, self.height = w, h
                self.scale = fit_scale(w, h, SCREENSHOT_MAX_LONG_EDGE, SCREENSHOT_MAX_VISUAL_TOKENS)
                return
            except Exception as e:  # X not up yet
                last = e
                await asyncio.sleep(0.5)
        raise RuntimeError(f"X display {self.display} not reachable: {last}")

    @property
    def model_size(self) -> tuple[int, int]:
        return round(self.width * self.scale), round(self.height * self.scale)

    def info(self) -> dict[str, Any]:
        mw, mh = self.model_size
        return {
            "display": self.display,
            "screen": {"width": self.width, "height": self.height},
            "model_space": {"width": mw, "height": mh, "scale": round(self.scale, 6)},
        }

    # ---------------------------------------------------------------- helpers
    async def _run(self, *args: str, timeout: float = 30.0, check: bool = True) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            start_new_session=True,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ActionError(f"{args[0]} timed out after {timeout:.0f}s")
        if check and proc.returncode != 0:
            msg = err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
            raise ActionError(f"{shlex.join(args)} failed (exit {proc.returncode}): {msg[:500]}")
        return out.decode(errors="replace")

    async def xdotool(self, *args: str, timeout: float = 30.0) -> str:
        return await self._run("xdotool", *args, timeout=timeout)

    def _to_screen(self, coord: Any, name: str = "coordinate") -> tuple[int, int]:
        if not isinstance(coord, (list, tuple)) or len(coord) != 2:
            raise ActionError(f"'{name}' must be [x, y]")
        try:
            x, y = float(coord[0]), float(coord[1])
        except (TypeError, ValueError):
            raise ActionError(f"'{name}' must contain two numbers")
        mw, mh = self.model_size
        if not (0 <= x < mw and 0 <= y < mh):
            raise ActionError(f"{name} {[coord[0], coord[1]]} is outside the screen ({mw}x{mh})")
        sx = min(self.width - 1, round(x / self.scale))
        sy = min(self.height - 1, round(y / self.scale))
        return sx, sy

    def _to_model(self, x: int, y: int) -> tuple[int, int]:
        return round(x * self.scale), round(y * self.scale)

    # ------------------------------------------------------------ screenshots
    async def capture_png(self) -> bytes:
        """Full-resolution PNG of the display (with the mouse pointer if enabled)."""
        path = os.path.join(SCREENSHOT_DIR, f"shot-{uuid.uuid4().hex}.png")
        try:
            if shutil.which("scrot"):
                args = ["scrot", "--overwrite", "--silent"]
                if SCREENSHOT_CURSOR:
                    args.append("--pointer")
                await self._run(*args, path, timeout=15)
                with open(path, "rb") as f:
                    return f.read()
            # Fallback: Pillow's XCB grabber (no cursor).
            from PIL import ImageGrab

            img = await asyncio.to_thread(ImageGrab.grab, xdisplay=self.display)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    @staticmethod
    def _encode(img: Image.Image, fmt: str = "png", quality: int = 80) -> bytes:
        buf = io.BytesIO()
        if fmt == "jpeg":
            img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
        else:
            img.save(buf, "PNG", compress_level=6)
        return buf.getvalue()

    async def screenshot(
        self, scale: float | None = None, fmt: str = "png", quality: int = 80
    ) -> tuple[bytes, int, int]:
        """Screenshot in model space (scale=None) or at an explicit scale factor.

        Returns (bytes, width, height).
        """
        raw = await self.capture_png()
        target = self.scale if scale is None else max(0.05, min(4.0, float(scale)))
        if abs(target - 1.0) < 1e-6 and fmt == "png":
            return raw, self.width, self.height

        def work() -> tuple[bytes, int, int]:
            img = Image.open(io.BytesIO(raw))
            if abs(target - 1.0) >= 1e-6:
                size = (max(1, round(img.width * target)), max(1, round(img.height * target)))
                img = img.resize(size, Image.Resampling.LANCZOS)
            return self._encode(img, fmt, quality), img.width, img.height

        return await asyncio.to_thread(work)

    async def zoom_png(self, region: Any) -> bytes:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ActionError("'region' must be [x0, y0, x1, y1]")
        x0, y0 = self._to_screen(region[:2], "region top-left")
        mw, mh = self.model_size
        x1m, y1m = min(float(region[2]), mw), min(float(region[3]), mh)
        x1, y1 = round(x1m / self.scale), round(y1m / self.scale)
        if x1 <= x0 or y1 <= y0:
            raise ActionError("'region' must have x1 > x0 and y1 > y0")
        raw = await self.capture_png()
        box_w, box_h = mw, mh  # "your usual screenshot dimensions"

        def work() -> bytes:
            img = Image.open(io.BytesIO(raw)).crop((x0, y0, x1, y1))
            f = min(box_w / img.width, box_h / img.height)
            size = (max(1, round(img.width * f)), max(1, round(img.height * f)))
            return self._encode(img.resize(size, Image.Resampling.LANCZOS))

        return await asyncio.to_thread(work)

    # ----------------------------------------------------------------- actions
    async def run(self, action: str, params: dict[str, Any] | None = None) -> ActionResult:
        """Execute one toolset member. Serialized: one action at a time."""
        params = dict(params or {})
        params.pop("action", None)  # tolerate legacy {"action": ...} inputs
        action = _ALIASES.get(action, action)
        if action not in MEMBERS:
            raise ActionError(f"Unknown action {action!r}. Supported: {', '.join(MEMBERS)}")
        async with self._lock:
            return await getattr(self, f"_do_{action}")(params)

    async def _do_screenshot(self, p: dict[str, Any]) -> ActionResult:
        data, w, h = await self.screenshot()
        return ActionResult(image=data, meta={"width": w, "height": h})

    async def _do_zoom(self, p: dict[str, Any]) -> ActionResult:
        return ActionResult(image=await self.zoom_png(p.get("region")))

    async def _click(self, p: dict[str, Any], click_args: list[str]) -> ActionResult:
        mods = _modifier_keys(p.get("text"))
        args: list[str] = []
        if p.get("coordinate") is not None:
            x, y = self._to_screen(p["coordinate"])
            args += ["mousemove", "--sync", str(x), str(y)]
        if mods:
            args = ["keydown", "+".join(mods)] + args
        args += click_args
        if mods:
            args += ["keyup", "+".join(mods)]
        try:
            await self.xdotool(*args)
        except ActionError:
            if mods:
                await self._run("xdotool", "keyup", "+".join(mods), check=False)
            raise
        return ActionResult(output="OK")

    async def _do_left_click(self, p):
        return await self._click(p, _CLICK_ARGS["left_click"])

    async def _do_right_click(self, p):
        return await self._click(p, _CLICK_ARGS["right_click"])

    async def _do_middle_click(self, p):
        return await self._click(p, _CLICK_ARGS["middle_click"])

    async def _do_double_click(self, p):
        return await self._click(p, _CLICK_ARGS["double_click"])

    async def _do_triple_click(self, p):
        return await self._click(p, _CLICK_ARGS["triple_click"])

    async def _do_left_click_drag(self, p: dict[str, Any]) -> ActionResult:
        sx, sy = self._to_screen(p.get("start_coordinate"), "start_coordinate")
        ex, ey = self._to_screen(p.get("coordinate"), "coordinate")
        mods = _modifier_keys(p.get("text"))
        mx, my = (sx + ex) // 2, (sy + ey) // 2
        args = ["mousemove", "--sync", str(sx), str(sy), "mousedown", "1", "sleep", "0.05",
                "mousemove", str(mx), str(my), "sleep", "0.05",
                "mousemove", str(ex), str(ey), "sleep", "0.05", "mouseup", "1"]
        if mods:
            args = ["keydown", "+".join(mods)] + args + ["keyup", "+".join(mods)]
        try:
            await self.xdotool(*args)
        except ActionError:
            await self._run("xdotool", "mouseup", "1", check=False)
            if mods:
                await self._run("xdotool", "keyup", "+".join(mods), check=False)
            raise
        return ActionResult(output="OK")

    async def _do_mouse_move(self, p: dict[str, Any]) -> ActionResult:
        x, y = self._to_screen(p.get("coordinate"))
        await self.xdotool("mousemove", "--sync", str(x), str(y))
        return ActionResult(output="OK")

    async def _do_left_mouse_down(self, p):
        await self.xdotool("mousedown", "1")
        return ActionResult(output="OK")

    async def _do_left_mouse_up(self, p):
        await self.xdotool("mouseup", "1")
        return ActionResult(output="OK")

    async def _do_cursor_position(self, p: dict[str, Any]) -> ActionResult:
        out = await self.xdotool("getmouselocation", "--shell")
        vals = dict(line.split("=", 1) for line in out.split() if "=" in line)
        x, y = self._to_model(int(vals["X"]), int(vals["Y"]))
        return ActionResult(output=f"X={x}, Y={y}", meta={"x": x, "y": y})

    async def _do_scroll(self, p: dict[str, Any]) -> ActionResult:
        direction = p.get("scroll_direction")
        if direction not in _SCROLL_BUTTON:
            raise ActionError("'scroll_direction' must be one of up, down, left, right")
        try:
            amount = int(p.get("scroll_amount", 3))
        except (TypeError, ValueError):
            raise ActionError("'scroll_amount' must be an integer")
        if not 0 < amount <= 100:
            raise ActionError("'scroll_amount' must be between 1 and 100")
        mods = _modifier_keys(p.get("text"))
        args: list[str] = []
        if p.get("coordinate") is not None:
            x, y = self._to_screen(p["coordinate"])
            args += ["mousemove", "--sync", str(x), str(y)]
        if mods:
            args += ["keydown", "+".join(mods)]
        args += ["click", "--repeat", str(amount), "--delay", "30", _SCROLL_BUTTON[direction]]
        if mods:
            args += ["keyup", "+".join(mods)]
        try:
            await self.xdotool(*args)
        except ActionError:
            if mods:
                await self._run("xdotool", "keyup", "+".join(mods), check=False)
            raise
        return ActionResult(output="OK")

    async def _do_type(self, p: dict[str, Any]) -> ActionResult:
        text = p.get("text")
        if not isinstance(text, str) or text == "":
            raise ActionError("'text' must be a non-empty string")
        for i in range(0, len(text), TYPING_CHUNK_CHARS):
            chunk = text[i : i + TYPING_CHUNK_CHARS]
            await self.xdotool(
                "type", "--delay", str(TYPING_DELAY_MS), "--", chunk,
                timeout=30 + len(chunk) * TYPING_DELAY_MS / 1000 * 4,
            )
        return ActionResult(output="OK")

    async def _do_key(self, p: dict[str, Any]) -> ActionResult:
        keys = _normalize_keys(p.get("text"))
        try:
            repeat = int(p.get("repeat", 1))
        except (TypeError, ValueError):
            raise ActionError("'repeat' must be an integer between 1 and 100")
        if not 1 <= repeat <= 100:
            raise ActionError("'repeat' must be between 1 and 100")
        args = ["key", "--delay", "20"]
        if repeat > 1:
            args += ["--repeat", str(repeat), "--repeat-delay", "40"]
        await self.xdotool(*args, "--", *keys, timeout=30 + repeat * 0.2)
        return ActionResult(output="OK")

    async def _do_hold_key(self, p: dict[str, Any]) -> ActionResult:
        keys = _normalize_keys(p.get("text"))
        duration = _duration(p.get("duration"))
        await self.xdotool("keydown", *keys)
        try:
            await asyncio.sleep(duration)
        finally:
            await self._run("xdotool", "keyup", *reversed(keys), check=False)
        return ActionResult(output="OK")

    async def _do_wait(self, p: dict[str, Any]) -> ActionResult:
        await asyncio.sleep(_duration(p.get("duration")))
        return ActionResult(output="OK")


def _duration(v: Any) -> float:
    try:
        d = float(v)
    except (TypeError, ValueError):
        raise ActionError("'duration' must be a number of seconds")
    if not 0 <= d <= 300:
        raise ActionError("'duration' must be between 0 and 300 seconds")
    return d


HALT_TEXT = "Not executed: an earlier computer action in this turn failed."


async def run_batch(computer: Computer, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run toolset actions in order and stop at the first failure (toolset batch semantics)."""
    results: list[dict[str, Any]] = []
    failed = False
    for item in items:
        if failed:
            results.append({"ok": False, "is_error": True, "error": HALT_TEXT})
            continue
        try:
            res = await computer.run(item.get("action", ""), item.get("params") or {})
            results.append(res.to_json())
        except ActionError as e:
            failed = True
            results.append({"ok": False, "is_error": True, "error": str(e)})
    return results


def tempdir() -> str:
    d = os.path.join(tempfile.gettempdir(), "desktop-api")
    os.makedirs(d, exist_ok=True)
    return d
