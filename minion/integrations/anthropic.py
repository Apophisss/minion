"""Claude computer use on a Minion desktop.

With the Anthropic SDK's tool runner (``pip install "minion-desktop[anthropic]"``):

    import anthropic
    from minion import Desktop
    from minion.integrations.anthropic import MinionComputer, allow_all

    desk = Desktop.create("office")
    with MinionComputer(desk, confirm=allow_all) as computer:   # the desktop is the sandbox
        runner = anthropic.Anthropic().beta.messages.tool_runner(
            model="claude-opus-5-5", max_tokens=4096, tools=[computer],
            messages=[{"role": "user", "content": "Make a 3-slide deck about otters in Impress."}],
        )
        for message in runner:
            print(message)

Without the SDK helpers (raw HTTP, other SDKs, your own loop), ``ComputerUse`` gives you the
``tools`` entry and turns Claude's ``tool_use`` blocks into ``tool_result`` blocks:

    cu = ComputerUse(desk)
    tools = [cu.tool()]                         # {"type": "computer_toolset_20260801"}
    ...
    user_turn = {"role": "user", "content": cu.run(response.content)}

Both speak the current ``computer_toolset_20260801`` (all 17 members, including ``zoom``)
and the earlier ``computer_20251124`` / ``computer_20250124`` tools (``input.action``).
"""

from __future__ import annotations

import time

from ..desktop import Desktop
from ..errors import MinionError

TOOLSET = "computer_toolset_20260801"
LEGACY = ("computer_20251124", "computer_20250124")
BETA_HEADERS = {"computer_20251124": "computer-use-2025-11-24", "computer_20250124": "computer-use-2025-01-24"}
HALT = "Not executed: an earlier computer action in this turn failed."
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
# Image limits: every model that speaks the toolset accepts 2576 px / ~3.75 MP; older ones 1568 px / 1.15 MP.
LIMITS = {"toolset": (2576, 3_750_000), "legacy": (1568, 1_150_000)}


class ComputerError(MinionError):
    """A call Claude can correct (bad coordinate, unknown key...): reported as is_error."""


def allow_all(_context) -> bool:
    """A `confirm` callable that approves every action. Fine for a disposable Minion desktop
    that holds no credentials; gate actions yourself for anything that matters."""
    return True


def _get(block, key, default=None):
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


class ComputerUse:
    """Executes Claude computer-use calls against a desktop, handling screenshot scaling."""

    def __init__(
        self,
        desktop: Desktop,
        *,
        version: str = TOOLSET,
        zoom: bool = True,
        max_long_edge: int | None = None,
        max_pixels: int | None = None,
        report_changes: bool = True,
    ):
        self.desktop = desktop
        self.version = version
        self.zoom = zoom
        self.report_changes = report_changes
        edge, pixels = LIMITS["toolset" if version == TOOLSET else "legacy"]
        edge, pixels = max_long_edge or edge, max_pixels or pixels
        w, h = desktop.size
        self.screen = (w, h)
        self.scale = min(1.0, edge / max(w, h), (pixels / (w * h)) ** 0.5)
        self.shot = (round(w * self.scale), round(h * self.scale))

    # -- tool definition ----------------------------------------------
    def tool(self) -> dict:
        """The `tools` entry for this version (send the beta header for the legacy versions)."""
        if self.version == TOOLSET:
            entry: dict = {"type": TOOLSET}
            if not self.zoom:
                entry["configs"] = {"zoom": {"enabled": False}}
            return entry
        if self.version in LEGACY:
            entry = {
                "type": self.version,
                "name": "computer",
                "display_width_px": self.shot[0],
                "display_height_px": self.shot[1],
            }
            if self.version == "computer_20251124" and self.zoom:
                entry["enable_zoom"] = True
            return entry
        raise MinionError(f"unknown computer tool version {self.version!r}")

    @property
    def beta_header(self) -> str | None:
        return BETA_HEADERS.get(self.version)

    # -- coordinates ---------------------------------------------------
    def to_screen(self, point, field: str = "coordinate") -> list[int]:
        try:
            x, y = (float(v) for v in point)
        except (TypeError, ValueError):
            raise ComputerError(f"{field} must be [x, y], got {point!r}") from None
        w, h = self.shot
        if not (0 <= x < w and 0 <= y < h):
            raise ComputerError(f"[{x:g}, {y:g}] is outside the {w}x{h} screenshot")
        sw, sh = self.screen
        return [min(sw - 1, int(x / self.scale)), min(sh - 1, int(y / self.scale))]

    def to_shot(self, x: int, y: int) -> tuple[int, int]:
        return round(x * self.scale), round(y * self.scale)

    # -- execution -----------------------------------------------------
    def screenshot_b64(self) -> tuple[str, str]:
        shot = self.desktop.screenshot(scale=self.scale if self.scale < 1 else None)
        return shot.base64(), shot.mime

    def zoom_b64(self, region) -> tuple[str, str]:
        try:
            x0, y0, x1, y1 = (float(v) for v in region)
        except (TypeError, ValueError):
            raise ComputerError(f"region must be [x0, y0, x1, y1], got {region!r}") from None
        if x1 <= x0 or y1 <= y0:
            raise ComputerError("region must have x1 > x0 and y1 > y0")
        sx0, sy0 = self.to_screen([x0, y0], "region")
        sx1, sy1 = self.to_screen([min(x1, self.shot[0] - 0.01), min(y1, self.shot[1] - 0.01)], "region")
        rw, rh = max(1, sx1 - sx0), max(1, sy1 - sy0)
        factor = min(self.shot[0] / rw, self.shot[1] / rh)
        shot = self.desktop.screenshot(region=[sx0, sy0, rw, rh], width=max(16, round(rw * factor)))
        return shot.base64(), shot.mime

    def _act(self, step: dict) -> str:
        res = self.desktop.act(step, check=False)
        if not res.ok:
            raise ComputerError(res.error or res.summary)
        if not self.report_changes:
            return ""
        return res.summary.split("→", 1)[-1].strip()

    def do(self, member: str, inp: dict) -> str | tuple | None:
        """Run one member. Returns a line of text, ('image', b64, mime), ('cursor', x, y) or None."""
        mods = (
            inp.get("text")
            if member
            in (
                "left_click",
                "right_click",
                "middle_click",
                "double_click",
                "triple_click",
                "left_click_drag",
                "scroll",
            )
            else None
        )
        if member == "screenshot":
            return ("image", *self.screenshot_b64())
        if member == "zoom":
            return ("image", *self.zoom_b64(inp.get("region")))
        if member in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
            coord = inp.get("coordinate")
            step = {
                "action": "click",
                "target": self.to_screen(coord) if coord is not None else None,
                "button": {"right_click": "right", "middle_click": "middle"}.get(member, "left"),
                "count": {"double_click": 2, "triple_click": 3}.get(member, 1),
                "modifiers": mods,
            }
            return self._act(step)
        if member == "left_click_drag":
            return self._act(
                {
                    "action": "drag",
                    "from": self.to_screen(inp.get("start_coordinate"), "start_coordinate"),
                    "to": self.to_screen(inp.get("coordinate")),
                    "modifiers": mods,
                }
            )
        if member == "mouse_move":
            return self._act({"action": "move", "target": self.to_screen(inp.get("coordinate"))})
        if member in ("left_mouse_down", "left_mouse_up"):
            return self._act({"action": "mouse_down" if member == "left_mouse_down" else "mouse_up"})
        if member == "cursor_position":
            x, y = self.desktop.cursor()
            sx, sy = self.to_shot(x, y)
            return ("cursor", sx, sy)
        if member == "scroll":
            direction = inp.get("scroll_direction") or "down"
            amount = int(inp.get("scroll_amount") or 3)
            if not (1 <= amount <= 50):
                raise ComputerError("scroll_amount must be between 1 and 50")
            coord = inp.get("coordinate")
            return self._act(
                {
                    "action": "scroll",
                    "direction": direction,
                    "amount": amount,
                    "target": self.to_screen(coord) if coord is not None else None,
                    "modifiers": mods,
                }
            )
        if member == "type":
            if not inp.get("text"):
                raise ComputerError("type needs text")
            return self._act({"action": "type", "text": inp["text"]})
        if member == "key":
            repeat = int(inp.get("repeat") or 1)
            if not (1 <= repeat <= 100):
                raise ComputerError("repeat must be between 1 and 100")
            return self._act({"action": "key", "keys": inp.get("text") or "", "repeat": repeat})
        if member == "hold_key":
            duration = float(inp.get("duration") or 1)
            if not (0 < duration <= 30):
                raise ComputerError("duration must be between 0 and 30 seconds for this desktop")
            return self._act({"action": "hold_key", "keys": inp.get("text") or "", "seconds": duration})
        if member == "wait":
            duration = float(inp.get("duration") or 1)
            if not (0 <= duration <= 300):
                raise ComputerError("duration must be between 0 and 300 seconds")
            time.sleep(duration)
            return None
        raise ComputerError(f"unknown computer action {member!r}")

    def execute(self, member: str, inp: dict) -> list[dict]:
        """Run one member and return tool_result content blocks."""
        out = self.do(member, inp or {})
        if isinstance(out, tuple) and out[0] == "image":
            return [{"type": "image", "source": {"type": "base64", "media_type": out[2], "data": out[1]}}]
        if isinstance(out, tuple) and out[0] == "cursor":
            return [{"type": "text", "text": f"X={out[1]},Y={out[2]}"}]
        return [{"type": "text", "text": f"OK{(' — ' + out) if out else ''}"}]

    # -- tool_use blocks -----------------------------------------------
    def member_of(self, block) -> tuple[str, dict] | None:
        """(member, input) if this block is a computer call, else None."""
        if _get(block, "type") != "tool_use":
            return None
        inp = dict(_get(block, "input") or {})
        if _get(block, "toolset_name") == "computer":
            return _get(block, "name"), inp
        if _get(block, "name") == "computer" and "action" in inp:
            return inp.pop("action"), inp
        return None

    def run(self, content) -> list[dict]:
        """tool_result blocks for every computer call in an assistant message's content, run in order.

        After a failure the remaining computer calls are answered without running (as the API requires).
        """
        results = []
        failed = False
        for block in content or []:
            call = self.member_of(block)
            if call is None:
                continue
            member, inp = call
            result = {"type": "tool_result", "tool_use_id": _get(block, "id")}
            if _get(block, "toolset_name") == "computer":
                result["toolset_name"] = "computer"
            if failed:
                result.update(is_error=True, content=HALT)
            else:
                try:
                    result["content"] = self.execute(member, inp)
                except (ComputerError, MinionError) as e:
                    failed = True
                    result.update(is_error=True, content=str(e))
            results.append(result)
        return results


# -- Anthropic SDK driver -----------------------------------------------------------
try:  # optional dependency
    from anthropic.tools import ToolError as _SdkToolError
    from anthropic.tools.computer import (
        BetaAbstractComputerToolset20260801 as _SdkToolset,
    )
    from anthropic.tools.computer import (
        BetaComputerCursorPositionResult as _SdkCursor,
    )
    from anthropic.tools.computer import (
        BetaScreenshotResult as _SdkScreenshot,
    )
except ImportError:  # pragma: no cover - exercised only without the SDK
    _SdkToolset = None


if _SdkToolset is not None:

    class MinionComputer(_SdkToolset):
        """A ready-made computer toolset driver for the Anthropic SDK, backed by a Minion desktop."""

        def __init__(
            self,
            desktop: Desktop,
            *,
            confirm=None,
            configs=None,
            tool_configs=None,
            max_long_edge: int | None = None,
            max_pixels: int | None = None,
            remove_on_close: bool = False,
        ):
            super().__init__(configs=configs, confirm=confirm, tool_configs=tool_configs)
            self.cu = ComputerUse(desktop, max_long_edge=max_long_edge, max_pixels=max_pixels)
            self.desktop = desktop
            self.remove_on_close = remove_on_close

        def _do(self, member: str, inp):
            try:
                return self.cu.do(
                    member, inp.model_dump(exclude_none=True) if hasattr(inp, "model_dump") else dict(inp)
                )
            except (ComputerError, MinionError) as e:
                raise _SdkToolError(str(e)) from e

        def _image(self, member: str, inp):
            _, data, mime = self._do(member, inp)
            return _SdkScreenshot(data=data, media_type=mime)

        def screenshot(self, context, input):
            return self._image("screenshot", input)

        def zoom(self, context, input):
            return self._image("zoom", input)

        def cursor_position(self, context, input):
            _, x, y = self._do("cursor_position", input)
            return _SdkCursor(x=x, y=y)

        def left_click(self, context, input):
            return self._do("left_click", input) or None

        def right_click(self, context, input):
            return self._do("right_click", input) or None

        def middle_click(self, context, input):
            return self._do("middle_click", input) or None

        def double_click(self, context, input):
            return self._do("double_click", input) or None

        def triple_click(self, context, input):
            return self._do("triple_click", input) or None

        def left_click_drag(self, context, input):
            return self._do("left_click_drag", input) or None

        def mouse_move(self, context, input):
            return self._do("mouse_move", input) or None

        def left_mouse_down(self, context, input):
            return self._do("left_mouse_down", input) or None

        def left_mouse_up(self, context, input):
            return self._do("left_mouse_up", input) or None

        def scroll(self, context, input):
            return self._do("scroll", input) or None

        def type(self, context, input):
            return self._do("type", input) or None

        def key(self, context, input):
            return self._do("key", input) or None

        def hold_key(self, context, input):
            return self._do("hold_key", input) or None

        def wait(self, context, input):
            return self._do("wait", input) or None

        def close(self) -> None:
            super().close()
            if self.remove_on_close:
                self.desktop.remove()
            else:
                self.desktop.close()

else:

    class MinionComputer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError('MinionComputer needs the Anthropic SDK: pip install "minion-desktop[anthropic]"')
