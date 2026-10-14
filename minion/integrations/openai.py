"""OpenAI computer use on a Minion desktop.

``ComputerUse`` gives you the ``tools`` entry for the Responses API and turns the model's
``computer_call`` items into ``computer_call_output`` items (a screenshot as a data URL):

    from openai import OpenAI
    from minion import Desktop
    from minion.integrations.openai import ComputerUse

    client = OpenAI()
    desk = Desktop.create("browser")
    cu = ComputerUse(desk)                       # cu.tool() == {"type": "computer"}
    response = client.responses.create(model="gpt-6.1-sol", input="Open example.com", **cu.params())
    while items := cu.run(response.output):      # [] once the model stops using the computer
        response = client.responses.create(
            model="gpt-6.1-sol", previous_response_id=response.id, input=items, **cu.params()
        )
    print(response.output_text)

Both generations of the tool are supported:

- ``computer`` (GA, the default): ``{"type": "computer"}`` and an ordered ``actions`` list on every
  ``computer_call``. Screenshots go back with ``detail: "original"``, as the guide recommends.
- ``computer_use_preview`` (``version=PREVIEW``): one ``action`` per call; the display size and the
  environment are part of the tool, and requests need ``truncation="auto"`` (``params()`` adds it).

Actions: ``click`` (left, right, wheel, back, forward), ``double_click``, ``drag`` (a path),
``move``, ``scroll`` (``scroll_x``/``scroll_y`` pixels become wheel clicks), ``keypress``
(``["CTRL", "C"]`` -> ``ctrl+c``), ``type``, ``wait`` and ``screenshot``, plus held modifier ``keys``
on mouse actions. The actions of one call run as a single Minion ``act`` batch that stops at the
first failure. ``pending_safety_checks`` are never acknowledged silently: ``run()`` raises
``SafetyCheckRequired`` unless a person approved them (``confirm=`` or ``acknowledge=``).

Plain dicts and the ``openai`` SDK's objects are both accepted; this module does not import the SDK.
Checked against https://developers.openai.com/api/docs/guides/tools-computer-use, the integration
recipes (.../guides/tools-computer-use-integration) and the Responses API reference (October 2026).
"""

from __future__ import annotations

import re

from ..desktop import Desktop
from ..errors import MinionError

TOOL = "computer"
PREVIEW = "computer_use_preview"
VERSIONS = (TOOL, PREVIEW)
ENVIRONMENTS = ("windows", "mac", "linux", "ubuntu", "browser")  # the preview tool's `environment` values
ACTIONS = ("click", "double_click", "drag", "keypress", "move", "screenshot", "scroll", "type", "wait")
HALT = "Not executed: an earlier computer action in this turn failed."

# Key names the model emits (upper case: ["CTRL", "C"]) -> xdotool names. The first block is the
# table in OpenAI's xdotool action handler (tools-computer-use-integration#implement-action-handlers);
# the second adds a few common names that table leaves out.
KEYS = {
    "ENTER": "Return",
    "RETURN": "Return",
    "ESC": "Escape",
    "ESCAPE": "Escape",
    "TAB": "Tab",
    "SPACE": "space",
    "BACKSPACE": "BackSpace",
    "DELETE": "Delete",
    "DEL": "Delete",
    "HOME": "Home",
    "END": "End",
    "PAGEUP": "Page_Up",
    "PAGEDOWN": "Page_Down",
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "ARROWUP": "Up",
    "ARROWDOWN": "Down",
    "ARROWLEFT": "Left",
    "ARROWRIGHT": "Right",
    "CTRL": "ctrl",
    "CONTROL": "ctrl",
    "SHIFT": "shift",
    "OPTION": "alt",
    "ALT": "alt",
    "META": "super",
    "CMD": "super",
    "COMMAND": "super",
    # not in OpenAI's table
    "SUPER": "super",
    "WIN": "super",
    "INSERT": "Insert",
    "CAPSLOCK": "Caps_Lock",
    "PRINTSCREEN": "Print",
    " ": "space",
}
MODIFIERS = ("ctrl", "shift", "alt", "super")
BUTTONS = {"left": "left", "right": "right", "wheel": "middle"}
# "back" and "forward" are X buttons 8 and 9, which Minion's `act` does not click. Browsers and file
# managers bind them to these shortcuts, sent after moving the pointer to the click point.
HISTORY_KEYS = {"back": "alt+Left", "forward": "alt+Right"}
_FKEY = re.compile(r"^[Ff]([1-9]|1[0-9]|2[0-4])$")
_UNSET = object()


class ComputerError(MinionError):
    """An action the model can correct (bad coordinate, unknown key...)."""


class SafetyCheckRequired(MinionError):
    """OpenAI attached ``pending_safety_checks`` to a computer call; a person must acknowledge them
    before its actions run. ``checks`` holds them as plain dicts ({"id", "code", "message"}). Show them
    to the user and, if they agree, call ``run(output, acknowledge=err.checks)``."""

    def __init__(self, checks: list[dict], declined: bool = False):
        self.checks = checks
        self.declined = declined
        detail = "; ".join(f"{c.get('code') or 'safety check'}: {c.get('message') or c.get('id')}" for c in checks)
        state = "were declined" if declined else "need a person's acknowledgement"
        super().__init__(f"OpenAI safety checks {state} before these actions can run: {detail}")


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def xdotool_key(name) -> str:
    """One key name from a keypress (``"CTRL"``, ``"ENTER"``, ``"ARROWLEFT"``, ``"C"``) as an xdotool key."""
    key = str(name)
    mapped = KEYS.get(key.upper())
    if mapped:
        return mapped
    if _FKEY.match(key):
        return key.upper()
    if len(key) == 1 and key.isalpha():
        return key.lower()  # "C" names the C key: ["CTRL", "C"] is ctrl+c, not ctrl+shift+c
    return key  # X keysyms ("Print") and symbols ("+") as is; the desktop normalizes those


def _check(check) -> dict:
    """A pending safety check (dict or SDK object) as a plain dict, ready to send back."""
    out = {"id": _get(check, "id")}
    for key in ("code", "message"):
        if _get(check, key) is not None:
            out[key] = _get(check, key)
    return out


def _approved(checks: list[dict], acknowledge) -> bool:
    if acknowledge is True:
        return True
    if not acknowledge:
        return False
    ids = {a if isinstance(a, str) else _get(a, "id") for a in acknowledge}
    return all(c["id"] in ids for c in checks)


def _xy(point) -> tuple:
    if isinstance(point, (list, tuple)):
        return (point[0], point[1]) if len(point) >= 2 else (None, None)
    return _get(point, "x"), _get(point, "y")


class ComputerUse:
    """Executes OpenAI computer-use calls against a desktop, handling screenshot scaling.

    ``max_long_edge`` / ``max_pixels`` downscale screenshots (coordinates are mapped back);
    ``wait`` is how long a ``wait`` action sleeps (the API gives no duration; OpenAI's examples use
    2 s); ``scroll_unit`` is how many pixels one wheel click scrolls (OpenAI's xdotool example uses
    100); ``confirm(checks) -> bool`` is asked about ``pending_safety_checks``; ``report_errors``
    appends a short message describing failed actions to ``run()``'s items, because a
    ``computer_call_output`` itself can only carry a screenshot.
    """

    def __init__(
        self,
        desktop: Desktop,
        *,
        version: str = TOOL,
        environment: str = "linux",
        detail=_UNSET,
        max_long_edge: int | None = None,
        max_pixels: int | None = None,
        wait: float = 2.0,
        scroll_unit: float = 100,
        confirm=None,
        report_errors: bool = True,
    ):
        if version not in VERSIONS:
            raise MinionError(f"unknown computer tool version {version!r} (use {TOOL!r} or {PREVIEW!r})")
        if environment not in ENVIRONMENTS:
            raise MinionError(f"unknown environment {environment!r} (one of: {', '.join(ENVIRONMENTS)})")
        self.desktop = desktop
        self.version = version
        self.environment = environment
        # The GA guide asks for detail "original"; the preview's examples never set it, so leave it out there.
        self.detail = ("original" if version == TOOL else None) if detail is _UNSET else detail
        self.wait = wait
        self.scroll_unit = scroll_unit
        self.confirm = confirm
        self.report_errors = report_errors
        self.errors: list[str] = []  # what went wrong in the last run()
        w, h = desktop.size
        self.screen = (w, h)
        scale = 1.0
        if max_long_edge:
            scale = min(scale, max_long_edge / max(w, h))
        if max_pixels:
            scale = min(scale, (max_pixels / (w * h)) ** 0.5)
        self.scale = scale
        self.shot = (round(w * scale), round(h * scale))

    # -- tool definition ----------------------------------------------
    def tool(self) -> dict:
        """The ``tools`` entry: ``{"type": "computer"}``, or the preview tool with this display's size."""
        if self.version == TOOL:
            return {"type": TOOL}
        return {
            "type": PREVIEW,
            "display_width": self.shot[0],
            "display_height": self.shot[1],
            "environment": self.environment,
        }

    def params(self) -> dict:
        """Keyword arguments for ``client.responses.create``: the tool, plus the ``truncation="auto"``
        the preview tool requires."""
        params: dict = {"tools": [self.tool()]}
        if self.version == PREVIEW:
            params["truncation"] = "auto"
        return params

    # -- coordinates ---------------------------------------------------
    def to_screen(self, x, y, field: str = "x/y") -> list[int]:
        """A point in the screenshot as desktop pixels."""
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            raise ComputerError(f"{field} must be numbers, got {x!r}, {y!r}") from None
        w, h = self.shot
        if not (0 <= fx < w and 0 <= fy < h):
            raise ComputerError(f"({fx:g}, {fy:g}) is outside the {w}x{h} screenshot")
        sw, sh = self.screen
        return [min(sw - 1, int(fx / self.scale)), min(sh - 1, int(fy / self.scale))]

    def wheel_clicks(self, pixels) -> int:
        """A scroll distance in screenshot pixels as mouse-wheel clicks (1 to 50)."""
        return max(1, min(50, int(abs(pixels) / self.scale / self.scroll_unit + 0.5)))

    # -- actions -> Minion steps ----------------------------------------
    def combo(self, keys) -> str:
        """A keypress's ``keys`` as one xdotool combo: ``["CTRL", "SHIFT", "T"]`` -> ``ctrl+shift+t``."""
        if isinstance(keys, str):
            keys = [keys]
        names = [xdotool_key(k) for k in keys or []]
        if not names or not all(names):
            raise ComputerError('keypress needs keys, e.g. ["CTRL", "C"]')
        return "+".join(names)

    def modifiers(self, keys) -> str | None:
        """The ``keys`` held during a mouse action as Minion modifiers (``"ctrl+shift"``)."""
        if not keys:
            return None
        mods = []
        for key in [keys] if isinstance(keys, str) else keys:
            name = xdotool_key(key)
            if name not in MODIFIERS:
                raise ComputerError(f"cannot hold {key!r} during a mouse action; use SHIFT, CTRL, ALT or META")
            if name not in mods:
                mods.append(name)
        return "+".join(mods)

    def steps(self, action) -> list[dict]:
        """The Minion ``act`` steps for one action (``[]`` for ``screenshot``)."""
        kind = _get(action, "type")
        if kind == "screenshot":
            return []  # the screen is captured after every call anyway
        if kind == "wait":
            return [{"action": "wait", "seconds": self.wait}]
        if kind == "type":
            text = _get(action, "text")
            return [{"action": "type", "text": str(text)}] if text else []
        if kind == "keypress":
            return [{"action": "key", "keys": self.combo(_get(action, "keys"))}]
        if kind == "drag":
            return self._drag(_get(action, "path"), self.modifiers(_get(action, "keys")))
        if kind not in ("click", "double_click", "move", "scroll"):
            raise ComputerError(f"unknown computer action {kind!r}")
        target = self.to_screen(_get(action, "x"), _get(action, "y"))
        if kind == "move":
            return [{"action": "move", "target": target}]  # held keys change nothing for a plain move
        mods = self.modifiers(_get(action, "keys"))
        if kind == "scroll":
            return self._scroll(target, _get(action, "scroll_x"), _get(action, "scroll_y"), mods)
        button = "left" if kind == "double_click" else str(_get(action, "button") or "left").lower()
        if button in HISTORY_KEYS:
            return [{"action": "move", "target": target}, {"action": "key", "keys": HISTORY_KEYS[button]}]
        if button not in BUTTONS:
            raise ComputerError(f"unknown mouse button {button!r} (left, right, wheel, back or forward)")
        step = {
            "action": "click",
            "target": target,
            "button": BUTTONS[button],
            "count": 2 if kind == "double_click" else 1,
        }
        if mods:
            step["modifiers"] = mods
        return [step]

    def _scroll(self, target, scroll_x, scroll_y, mods) -> list[dict]:
        steps = []
        for delta, negative, positive in ((scroll_y, "up", "down"), (scroll_x, "left", "right")):
            try:
                pixels = float(delta or 0)
            except (TypeError, ValueError):
                raise ComputerError(f"scroll_x and scroll_y must be numbers, got {delta!r}") from None
            if pixels:
                step = {
                    "action": "scroll",
                    "direction": negative if pixels < 0 else positive,
                    "amount": self.wheel_clicks(pixels),
                    "target": target,
                }
                if mods:
                    step["modifiers"] = mods
                steps.append(step)
        return steps or [{"action": "move", "target": target}]  # a zero scroll still moves the pointer there

    def _drag(self, path, mods) -> list[dict]:
        points = [self.to_screen(*_xy(p), field="drag path") for p in path or []]
        if len(points) < 2:
            raise ComputerError("drag needs a path of at least two points")
        if len(points) == 2 or mods:
            # Minion's drag holds modifiers and moves in small steps, but only from one point to another,
            # so a modifier drag along a longer path goes straight from its first point to its last.
            step = {"action": "drag", "from": points[0], "to": points[-1]}
            if mods:
                step["modifiers"] = mods
            return [step]
        moves = [{"action": "move", "target": p} for p in points[1:-1]]
        return [{"action": "mouse_down", "target": points[0]}, *moves, {"action": "mouse_up", "target": points[-1]}]

    # -- execution -----------------------------------------------------
    @staticmethod
    def actions_of(call) -> list:
        """A computer_call's actions: the GA ``actions`` list, or the preview's single ``action``."""
        actions = _get(call, "actions")
        if actions:
            return list(actions)
        action = _get(call, "action")
        return [action] if action is not None else []

    def execute(self, actions) -> str | None:
        """Run actions in order as one ``act`` batch. Returns None, or what went wrong (the failing
        action and all later ones did not run)."""
        actions = list(actions or [])
        steps: list[dict] = []
        owner: list[int] = []
        problem = None
        for i, action in enumerate(actions):
            try:
                more = self.steps(action)
            except ComputerError as e:
                problem = (i, str(e))
                break
            steps += more
            owner += [i] * len(more)
        if steps:
            res = self.desktop.act(steps, check=False)
            if not res.ok:
                bad = next((k for k, s in enumerate(res.steps or []) if not s.get("ok") and not s.get("skipped")), None)
                problem = (owner[bad] if bad is not None and bad < len(owner) else None, res.error or res.summary)
        if problem is None:
            return None
        i, why = problem
        why = str(why).rstrip(". ")
        if i is None:
            return f"A computer action failed: {why}."
        later = len(actions) - i - 1
        tail = f" The {later} action(s) after it were not executed." if later else ""
        return f"Action {i + 1} of {len(actions)} ({_get(actions[i], 'type')}) failed: {why}.{tail}"

    def screenshot_b64(self) -> tuple[str, str]:
        shot = self.desktop.screenshot(scale=self.scale if self.scale < 1 else None)
        return shot.base64(), shot.mime

    def output(self, call_id: str, acknowledged: list[dict] | None = None) -> dict:
        """A ``computer_call_output`` item with a fresh screenshot as a data URL."""
        data, mime = self.screenshot_b64()
        screenshot = {"type": "computer_screenshot", "image_url": f"data:{mime};base64,{data}"}
        if self.detail:
            screenshot["detail"] = self.detail
        item = {"type": "computer_call_output", "call_id": call_id, "output": screenshot}
        if acknowledged:
            item["acknowledged_safety_checks"] = acknowledged
        return item

    # -- response items ------------------------------------------------
    @staticmethod
    def computer_calls(output) -> list:
        """The ``computer_call`` items of a response's ``output`` (dicts or SDK objects)."""
        return [item for item in output or [] if _get(item, "type") == "computer_call"]

    def pending_safety_checks(self, output) -> list[dict]:
        """Every pending safety check on the computer calls in ``output``, as plain dicts."""
        return [_check(c) for call in self.computer_calls(output) for c in _get(call, "pending_safety_checks") or []]

    def run(self, output, *, acknowledge=False) -> list[dict]:
        """Run every ``computer_call`` in a response's ``output``, in order, and return the input items
        for the next request: one ``computer_call_output`` per call, plus (with ``report_errors``) a
        short message when an action failed. ``[]`` means the model made no computer call.

        Calls with ``pending_safety_checks`` run only when they are acknowledged: by
        ``acknowledge=True``, by ``acknowledge=`` the checks (or their ids) a person approved, or by the
        ``confirm`` callable. Otherwise ``SafetyCheckRequired`` is raised before anything runs.
        After a failure, later calls are not executed but still answered with a screenshot.
        """
        calls = self.computer_calls(output)
        self.errors = []
        if not calls:
            return []
        for call in calls:
            status = _get(call, "status")
            if status in ("in_progress", "incomplete"):
                raise MinionError(f"computer_call {_get(call, 'call_id')} is {status}; partial calls must not run")
        acknowledged = self._acknowledge(calls, acknowledge)
        items = []
        for call in calls:
            call_id = _get(call, "call_id")
            if self.errors:
                self.errors.append(f"Call {call_id}: {HALT}")
            else:
                error = self.execute(self.actions_of(call))
                if error:
                    self.errors.append(error)
            items.append(self.output(call_id, acknowledged.get(call_id)))
        if self.errors and self.report_errors:
            report = "\n".join(f"- {e}" for e in self.errors)
            items.append(
                {
                    "role": "user",
                    "content": f"Computer tool report (from the harness, not the user):\n{report}\n"
                    "The screenshot shows the screen as it is now.",
                }
            )
        return items

    def _acknowledge(self, calls, acknowledge) -> dict[str, list[dict]]:
        pending = {}
        for call in calls:
            checks = [_check(c) for c in _get(call, "pending_safety_checks") or []]
            if checks:
                pending[_get(call, "call_id")] = checks
        if not pending:
            return {}
        checks = [c for group in pending.values() for c in group]
        if _approved(checks, acknowledge):
            return pending
        if self.confirm is not None and self.confirm(checks):
            return pending
        raise SafetyCheckRequired(checks, declined=self.confirm is not None)
