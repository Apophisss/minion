"""Gemini computer use on a Minion desktop.

``ComputerUse`` gives you the ``computer_use`` tool entry and turns Gemini's predefined UI function
calls into function results that carry a fresh screenshot. With the Interactions API (the default):

    from google import genai
    from minion import Desktop
    from minion.integrations.gemini import ComputerUse

    client = genai.Client()
    desk = Desktop.create("office")
    cu = ComputerUse(desk)                   # environment="desktop"; "browser" adds navigate/go_back/go_forward
    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        input=[{"type": "text", "text": "Write a haiku in Writer."}, cu.screenshot_input()],
        tools=[cu.tool()],
    )
    while results := cu.run(interaction):    # [] once the model stops calling computer functions
        interaction = client.interactions.create(
            model="gemini-3.8-flash", previous_interaction_id=interaction.id, input=results, tools=[cu.tool()]
        )
    print(interaction.output_text)

``api="generate_content"`` speaks ``models.generate_content`` instead: ``tool()`` returns
``{"computer_use": {"environment": "ENVIRONMENT_DESKTOP"}}`` and ``run(response)`` returns
``function_response`` parts for the next user turn.

Coordinates arrive on Gemini's normalized 0-999 grid and become desktop pixels
(``int(x / 1000 * width)``), so screenshots can be downscaled freely. Two function sets are executed:

- Gemini 3.5 and later (the current docs): click, double_click, triple_click, middle_click,
  right_click, mouse_down, mouse_up, move, type, drag_and_drop, wait, press_key, key_down, key_up,
  hotkey, take_screenshot, scroll, and in the browser environment go_back, navigate, go_forward.
- The earlier set, still emitted by ``gemini-3-flash-preview`` (and by the retired
  ``gemini-2.5-computer-use-preview-10-2025``), as handled by Google's reference implementation:
  open_web_browser, click_at, hover_at, type_text_at, scroll_document, scroll_at, wait_5_seconds,
  go_back, go_forward, search, navigate, key_combination, drag_and_drop.

Browser-only functions use the desktop's browser: ``navigate`` focuses it and types the URL into the
address bar (ctrl+l), or opens the URL with ``desk.open`` when no browser window exists;
``go_back``/``go_forward`` press alt+Left/alt+Right. A ``safety_decision`` that requires
confirmation is never acknowledged silently: ``run()`` raises ``SafetyCheckRequired`` unless a
person approved it (``confirm=`` or ``acknowledge=``). Calls to your own functions are skipped, so
answer those yourself alongside ``run()``'s results.

Plain dicts and the ``google-genai`` SDK's objects are both accepted; this module does not import the
SDK. Checked against https://ai.google.dev/gemini-api/docs/computer-use (Interactions API),
https://ai.google.dev/gemini-api/docs/generate-content/computer-use and
https://github.com/google/computer-use-preview (October 2026).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from ..desktop import Desktop
from ..errors import MinionError

APIS = ("interactions", "generate_content")
ENVIRONMENTS = ("desktop", "browser")  # "mobile" (Android) does not apply to a Linux desktop
FUNCTIONS = (
    "click",
    "double_click",
    "triple_click",
    "middle_click",
    "right_click",
    "mouse_down",
    "mouse_up",
    "move",
    "type",
    "drag_and_drop",
    "wait",
    "press_key",
    "key_down",
    "key_up",
    "hotkey",
    "take_screenshot",
    "scroll",
    "go_back",
    "navigate",
    "go_forward",
)
LEGACY_FUNCTIONS = (
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "key_combination",
    "drag_and_drop",
)
MOBILE_FUNCTIONS = ("open_app", "list_apps", "long_press")  # answered with an error here
HALT = "Not executed: an earlier computer action in this turn failed."
CLICKS = {
    "click": ("left", 1),
    "click_at": ("left", 1),
    "double_click": ("left", 2),
    "triple_click": ("left", 3),
    "middle_click": ("middle", 1),
    "right_click": ("right", 1),
}
# Key names Gemini emits (Playwright-style "Control", "ArrowLeft", "PageDown", and the names in the
# reference implementation's key map) -> xdotool names. Others pass through; the desktop normalizes them.
KEYS = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "controlormeta": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "meta": "super",
    "command": "super",
    "cmd": "super",
    "super": "super",
    "win": "super",
    "windows": "super",
    "enter": "Return",
    "return": "Return",
    "escape": "Escape",
    "esc": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "arrowup": "Up",
    "arrowdown": "Down",
    "arrowleft": "Left",
    "arrowright": "Right",
    "semicolon": "semicolon",
    "equals": "equal",
    "multiply": "KP_Multiply",
    "add": "KP_Add",
    "separator": "KP_Separator",
    "subtract": "KP_Subtract",
    "decimal": "KP_Decimal",
    "divide": "KP_Divide",
}
MODIFIERS = ("ctrl", "shift", "alt", "super")
BROWSER_APPS = re.compile(r"firefox|chrom|brave|vivaldi|opera|epiphany|falkon|qutebrowser|librewolf|msedge", re.I)
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_FKEY = re.compile(r"^f([1-9]|1[0-9]|2[0-4])$")
_PLAYWRIGHT_CODE = re.compile(r"^(?:key|digit)([a-z0-9])$")  # "KeyA" -> a, "Digit1" -> 1


class ComputerError(MinionError):
    """A call the model can correct (bad coordinate, unknown key...): reported in the function result."""


class SafetyCheckRequired(MinionError):
    """Gemini marked calls with ``safety_decision.decision == "require_confirmation"``. ``checks`` lists
    them as plain dicts ({"call_id", "function", "explanation"}). Show them to the user and, if they
    agree, call ``run(source, acknowledge=err.checks)``; the results then carry
    ``safety_acknowledgement``."""

    def __init__(self, checks: list[dict], declined: bool = False):
        self.checks = checks
        self.declined = declined
        detail = "; ".join(f"{c['function']}: {c.get('explanation') or 'needs confirmation'}" for c in checks)
        state = "was declined" if declined else "needs a person's confirmation"
        super().__init__(f"Gemini's safety service {state} before these actions can run: {detail}")


@dataclass
class Call:
    """One predefined computer-use function call, from either API."""

    name: str
    args: dict
    id: str | None
    api: str  # the shape to answer in: "interactions" or "generate_content"


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def xdotool_key(name) -> str:
    """One Gemini key name (``"Control"``, ``"enter"``, ``"ArrowLeft"``, ``"a"``) as an xdotool key."""
    key = str(name)
    if key == " ":
        return "space"
    low = key.strip().lower()
    if low in KEYS:
        return KEYS[low]
    if _FKEY.match(low):
        return low.upper()
    code = _PLAYWRIGHT_CODE.match(low)
    if code:
        return code.group(1)
    return key.strip() or key


def split_keys(keys) -> list[str]:
    """``"control+shift+t"`` (or a list) as key names; a "+" that follows another "+" is the plus key."""
    if not isinstance(keys, str):
        return [str(k) for k in keys or []]
    parts: list[str] = []
    buf = ""
    for ch in keys:
        if ch == "+" and buf.strip():
            parts.append(buf.strip())
            buf = ""
        elif ch == "+":
            parts.append("+")
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _approved(checks: list[dict], acknowledge) -> bool:
    if acknowledge is True:
        return True
    if not acknowledge:
        return False
    approved = list(acknowledge)
    return all(c in approved or c.get("call_id") in approved for c in checks)


class ComputerUse:
    """Executes Gemini computer-use function calls against a desktop.

    ``environment`` is "desktop" or "browser"; ``api`` is "interactions" or "generate_content";
    ``exclude`` lists predefined functions to leave out of the tool (your own functions may then use
    those names; ``run()`` skips them); ``confirm(checks) -> bool`` is asked about safety decisions
    that require confirmation; ``url`` decides the "url" in each result (default: in the browser
    environment, the address bar as read by ``desk.see()``; ``False`` for none; or a callable);
    ``search_url`` is where ``search`` and ``open_web_browser`` go; ``scroll_unit`` is how many pixels
    one wheel click scrolls; ``max_long_edge`` / ``max_pixels`` downscale screenshots.
    """

    def __init__(
        self,
        desktop: Desktop,
        *,
        environment: str = "desktop",
        api: str = "interactions",
        exclude=(),
        confirm=None,
        url=None,
        search_url: str = "https://www.google.com",
        scroll_unit: float = 100,
        max_long_edge: int | None = None,
        max_pixels: int | None = None,
    ):
        if environment not in ENVIRONMENTS:
            raise MinionError(f"unknown environment {environment!r} (use 'desktop' or 'browser')")
        if api not in APIS:
            raise MinionError(f"unknown api {api!r} (use 'interactions' or 'generate_content')")
        self.desktop = desktop
        self.environment = environment
        self.api = api
        self.exclude = tuple(exclude)
        self.confirm = confirm
        self.url = url
        self.search_url = search_url
        self.scroll_unit = scroll_unit
        self.held: list[str] = []  # modifiers held down by key_down, applied to later clicks and keys
        w, h = desktop.size
        self.screen = (w, h)
        scale = 1.0
        if max_long_edge:
            scale = min(scale, max_long_edge / max(w, h))
        if max_pixels:
            scale = min(scale, (max_pixels / (w * h)) ** 0.5)
        self.scale = scale

    # -- tool definition ----------------------------------------------
    def tool(self, **options) -> dict:
        """The ``tools`` entry. Extra options pass through, e.g. ``enable_prompt_injection_detection=True``
        or ``disabled_safety_policies=["data_modification"]``."""
        config: dict = {"environment": self.environment}
        if self.exclude:
            config["excluded_predefined_functions"] = list(self.exclude)
        config.update(options)
        policies = config.get("disabled_safety_policies")
        if self.api == "interactions":
            if policies:
                config["disabled_safety_policies"] = [str(p).lower() for p in policies]
            return {"type": "computer_use", **config}
        config["environment"] = "ENVIRONMENT_" + str(config["environment"]).upper()
        if policies:
            config["disabled_safety_policies"] = [str(p).upper() for p in policies]
        return {"computer_use": config}

    # -- coordinates and screenshots ------------------------------------
    def to_screen(self, x, y, field: str = "x/y") -> list[int]:
        """A point on Gemini's normalized 0-999 grid as desktop pixels."""
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            raise ComputerError(f"{field} must be numbers on the 0-999 grid, got {x!r}, {y!r}") from None
        if not (0 <= fx <= 1000 and 0 <= fy <= 1000):
            raise ComputerError(f"({fx:g}, {fy:g}) is outside the 0-999 coordinate grid")
        w, h = self.screen
        return [min(w - 1, int(fx / 1000 * w)), min(h - 1, int(fy / 1000 * h))]

    def screenshot_b64(self) -> tuple[str, str]:
        shot = self.desktop.screenshot(scale=self.scale if self.scale < 1 else None)
        return shot.base64(), shot.mime

    def screenshot_input(self) -> dict:
        """The current screen for a request's input: an Interactions ``image`` content block, or a
        generateContent ``inline_data`` part."""
        data, mime = self.screenshot_b64()
        if self.api == "interactions":
            return {"type": "image", "data": data, "mime_type": mime}
        return {"inline_data": {"mime_type": mime, "data": data}}

    def current_url(self) -> str | None:
        """The "url" reported with results (None leaves it out)."""
        if self.url is False:
            return None
        if callable(self.url):
            return str(self.url() or "")
        if self.environment != "browser":
            return None
        try:
            seen = self.desktop.see(ocr=False)
        except MinionError:
            return ""
        for el in _get(seen, "elements") or []:
            if el.get("role") == "address bar":
                return el.get("value") or el.get("text") or ""
        return ""

    # -- execution -----------------------------------------------------
    def _act(self, steps: list[dict]) -> None:
        res = self.desktop.act(steps, check=False)
        if not res.ok:
            raise ComputerError(res.error or res.summary)

    def _mods(self, step: dict) -> dict:
        if self.held:
            step["modifiers"] = "+".join(self.held)
        return step

    def combo(self, keys) -> str:
        """Key names as one xdotool combo, including any modifiers held by ``key_down``."""
        names = [*self.held, *(xdotool_key(k) for k in split_keys(keys))]
        if len(names) == len(self.held) or not all(names):
            raise ComputerError("no key given")
        if len(names) > 1:  # ctrl+A means ctrl+a, not ctrl+shift+a
            names = [n.lower() if len(n) == 1 and n.isalpha() else n for n in names]
        return "+".join(dict.fromkeys(names))

    def _number(self, args: dict, key: str, default, low: float, high: float) -> float:
        value = args.get(key, default)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ComputerError(f"{key} must be a number, got {value!r}") from None
        if not (low <= number <= high):
            raise ComputerError(f"{key} must be between {low:g} and {high:g}, got {number:g}")
        return number

    def _scroll(self, args: dict, default_magnitude: int) -> None:
        direction = str(args.get("direction") or "").lower()
        if direction not in ("up", "down", "left", "right"):
            raise ComputerError(f"direction must be up, down, left or right, got {args.get('direction')!r}")
        # Gemini 3.5+ sends magnitude_in_pixels (docs: 0-999, default 300); the earlier scroll_at sent
        # magnitude (default 800). Both are read on the normalized grid along the scroll axis, as the
        # reference implementation does: the model never learns the real screen size.
        key = "magnitude_in_pixels" if "magnitude_in_pixels" in args else "magnitude"
        magnitude = self._number(args, key, default_magnitude, 0, 1000)
        length = self.screen[1] if direction in ("up", "down") else self.screen[0]
        clicks = max(1, min(50, int(magnitude / 1000 * length / self.scroll_unit + 0.5)))
        target = self.to_screen(args.get("x"), args.get("y"))
        self._act([self._mods({"action": "scroll", "direction": direction, "amount": clicks, "target": target})])

    def _browser(self) -> list[dict] | None:
        """Steps that put a browser window in front ([] if one is focused), or None if none is open."""
        try:
            windows = self.desktop.windows()
        except MinionError:
            windows = []
        browsers = [w for w in windows if BROWSER_APPS.search(str(w.get("app") or ""))]
        if not browsers:
            return None
        if any(w.get("focused") for w in browsers):
            return []
        return [{"action": "focus", "window": browsers[-1]["id"]}]

    def _open(self, url: str) -> None:
        res = self.desktop.open(url if _SCHEME.match(url) else "https://" + url)
        if isinstance(res, dict) and res.get("error"):
            raise ComputerError(f"could not open {url}: {res['error']}")

    def navigate(self, url) -> None:
        url = str(url or "").strip()
        if not url:
            raise ComputerError("navigate needs a url")
        focus = self._browser()
        if focus is None:  # no browser yet: launch one on the URL
            self._open(url)
            return
        self._act(
            [
                *focus,
                {"action": "key", "keys": "ctrl+l"},
                {"action": "type", "text": url},
                {"action": "key", "keys": "Return"},
            ]
        )

    def _history(self, keys: str) -> None:
        focus = self._browser()
        if focus is None:
            raise ComputerError("no browser window is open")
        self._act([*focus, {"action": "key", "keys": keys}])

    def do(self, name: str, args: dict | None = None) -> None:
        """Execute one predefined function; raises ComputerError (or MinionError) on failure."""
        a = dict(args or {})
        if name == "take_screenshot":
            return  # every result carries a fresh screenshot anyway
        if name in CLICKS:
            button, count = CLICKS[name]
            target = self.to_screen(a.get("x"), a.get("y"))
            self._act([self._mods({"action": "click", "target": target, "button": button, "count": count})])
        elif name in ("move", "hover_at"):
            self._act([{"action": "move", "target": self.to_screen(a.get("x"), a.get("y"))}])
        elif name in ("mouse_down", "mouse_up"):
            # Held modifiers cannot be applied here: Minion's mouse_down/mouse_up take none.
            self._act([{"action": name, "target": self.to_screen(a.get("x"), a.get("y"))}])
        elif name in ("type", "type_text_at"):
            self._type(name, a)
        elif name == "drag_and_drop":
            # The docs name the points start_x/start_y/end_x/end_y; the reference implementation (and
            # the earlier set) use x/y/destination_x/destination_y. Both are accepted.
            start = self.to_screen(a.get("start_x", a.get("x")), a.get("start_y", a.get("y")), "start_x/start_y")
            end = self.to_screen(
                a.get("end_x", a.get("destination_x")), a.get("end_y", a.get("destination_y")), "end_x/end_y"
            )
            self._act([self._mods({"action": "drag", "from": start, "to": end})])
        elif name in ("wait", "wait_5_seconds"):
            time.sleep(5 if name == "wait_5_seconds" else self._number(a, "seconds", 1, 0, 60))
        elif name == "press_key":
            self._act([{"action": "key", "keys": self.combo([a.get("key") or ""])}])
        elif name in ("hotkey", "key_combination"):
            self._act([{"action": "key", "keys": self.combo(a.get("keys") or "")}])
        elif name in ("key_down", "key_up"):
            self._hold(name, a.get("key"))
        elif name in ("scroll", "scroll_at"):
            self._scroll(a, 300 if name == "scroll" else 800)
        elif name == "scroll_document":
            self._scroll_document(a)
        elif name in ("go_back", "go_forward"):
            self._history("alt+Left" if name == "go_back" else "alt+Right")
        elif name == "navigate":
            self.navigate(a.get("url"))
        elif name == "search":
            self.navigate(self.search_url)
        elif name == "open_web_browser":
            focus = self._browser()
            if focus is None:
                self._open(self.search_url)
            elif focus:
                self._act(focus)
        elif name in MOBILE_FUNCTIONS:
            raise ComputerError(f"{name} belongs to the mobile environment; this is a Linux desktop")
        else:
            raise ComputerError(f"unknown computer use function {name!r}")

    def _type(self, name: str, a: dict) -> None:
        steps = []
        if a.get("x") is not None and a.get("y") is not None:
            steps.append({"action": "click", "target": self.to_screen(a["x"], a["y"]), "button": "left", "count": 1})
        if name == "type_text_at" and a.get("clear_before_typing", True):
            # The earlier type_text_at cleared the field first (default true): select all, then Delete.
            steps += [{"action": "key", "keys": "ctrl+a"}, {"action": "key", "keys": "Delete"}]
        # The current `type` does not clear: the reference implementation only types. (The docs' sample
        # handler clears with Meta+A, which is macOS-only and would wipe whole documents on a desktop.)
        text = a.get("text")
        if text:
            steps.append({"action": "type", "text": str(text)})
        # press_enter defaults to false for `type` (docs) and, following the reference handler, for
        # type_text_at too (its declaration once described Enter as automatic; unconfirmed).
        if a.get("press_enter"):
            steps.append({"action": "key", "keys": "Return"})
        if not steps:
            raise ComputerError("type needs text")
        self._act(steps)

    def _hold(self, name: str, key) -> None:
        # Minion presses keys as whole combos (xdotool key --clearmodifiers), so a held modifier is
        # tracked here and added to later clicks, drags, scrolls and keys until key_up. Other keys are
        # pressed once on key_down (nothing stays physically held, so nothing can get stuck).
        if not key:
            raise ComputerError(f"{name} needs a key")
        k = xdotool_key(key)
        if k in MODIFIERS:
            if name == "key_down" and k not in self.held:
                self.held.append(k)
            elif name == "key_up" and k in self.held:
                self.held.remove(k)
        elif name == "key_down":
            self._act([{"action": "key", "keys": self.combo([key])}])

    def _scroll_document(self, a: dict) -> None:
        direction = str(a.get("direction") or "").lower()
        if direction in ("up", "down"):  # like the reference implementation: Page Up / Page Down
            self._act([{"action": "key", "keys": "Page_Up" if direction == "up" else "Page_Down"}])
        elif direction in ("left", "right"):  # half a screen sideways, at the center
            w, h = self.screen
            clicks = max(1, min(50, int(w / 2 / self.scroll_unit + 0.5)))
            self._act([{"action": "scroll", "direction": direction, "amount": clicks, "target": [w // 2, h // 2]}])
        else:
            raise ComputerError(f"direction must be up, down, left or right, got {a.get('direction')!r}")

    # -- function calls -> results --------------------------------------
    def _items(self, source) -> list:
        if source is None:
            return []
        steps = _get(source, "steps")
        if steps is not None:  # an Interaction
            return list(steps)
        candidates = _get(source, "candidates")
        if candidates is not None:  # a GenerateContentResponse
            source = candidates[0] if candidates else None
        content = _get(source, "content")
        if content is not None and not isinstance(content, (str, list)):  # a Candidate
            source = content
        parts = _get(source, "parts")
        if parts is not None:  # a Content
            return list(parts)
        if isinstance(source, (list, tuple)):  # steps, parts or FunctionCalls (not a whole history)
            return list(source)
        return [source]

    def calls(self, source) -> list[Call]:
        """The predefined computer-use calls in an Interaction (or its ``steps``), a generateContent
        response, Candidate or Content (or a list of parts). Your own functions are left out."""
        items = self._items(source)
        answered = {_get(i, "call_id") for i in items if _get(i, "type") == "function_result"}
        known = set(FUNCTIONS) | set(LEGACY_FUNCTIONS) | set(MOBILE_FUNCTIONS)
        out = []
        for item in items:
            if _get(item, "type") == "function_call":  # Interactions step
                call = Call(_get(item, "name"), dict(_get(item, "arguments") or {}), _get(item, "id"), "interactions")
                if call.id is not None and call.id in answered:
                    continue
            else:  # generateContent part ({"function_call": ...} or REST's {"functionCall": ...}) or a FunctionCall
                fc = _get(item, "function_call") or _get(item, "functionCall")
                if fc is None and _get(item, "args") is not None and _get(item, "name"):
                    fc = item
                if fc is None:
                    continue
                call = Call(_get(fc, "name"), dict(_get(fc, "args") or {}), _get(fc, "id"), "generate_content")
            if call.name in known and call.name not in self.exclude:
                out.append(call)
        return out

    @staticmethod
    def _decision(call: Call) -> tuple[str, str]:
        safety = call.args.get("safety_decision")
        if not safety:
            return "", ""
        return str(_get(safety, "decision") or "").lower(), str(_get(safety, "explanation") or "")

    def safety_checks(self, source) -> list[dict]:
        """The calls whose ``safety_decision`` requires a person's confirmation, as plain dicts."""
        return self._checks(self.calls(source))

    def _checks(self, calls: list[Call]) -> list[dict]:
        checks = []
        for call in calls:
            decision, explanation = self._decision(call)
            if decision == "require_confirmation":
                checks.append({"call_id": call.id, "function": call.name, "explanation": explanation})
        return checks

    def result(self, call: Call, state: tuple, error: str | None = None, extra: dict | None = None) -> dict:
        """The answer to one call: a ``function_result`` step (Interactions) or a ``function_response``
        part (generateContent), with the screenshot and a JSON payload ("url", "error", ...)."""
        data, mime, url = state
        payload: dict = {}
        if url is not None:
            payload["url"] = url
        if error:
            payload["error"] = error
        payload.update(extra or {})
        if call.api == "interactions":
            out = {
                "type": "function_result",
                "name": call.name,
                "call_id": call.id,
                "result": [
                    {"type": "text", "text": json.dumps(payload)},
                    {"type": "image", "data": data, "mime_type": mime},
                ],
            }
            if error:
                out["is_error"] = True
            return out
        response = {
            "name": call.name,
            "response": payload,
            "parts": [{"inline_data": {"mime_type": mime, "data": data}}],
        }
        if call.id:
            response = {"id": call.id, **response}
        return {"function_response": response}

    def run(self, source, *, acknowledge=False) -> list[dict]:
        """Run every predefined computer-use call in ``source``, in order, and return one result per
        call (each with a screenshot taken after it). ``[]`` means there was nothing to run.

        A call whose ``safety_decision`` requires confirmation runs only when acknowledged: by
        ``acknowledge=True``, by ``acknowledge=`` the checks a person approved, or by the ``confirm``
        callable; otherwise ``SafetyCheckRequired`` is raised before anything runs. A call with any
        other safety decision ("blocked") is not run. After a failure, later calls are answered with
        an error and not run.
        """
        calls = self.calls(source)
        if not calls:
            return []
        checks = self._checks(calls)
        if checks and not _approved(checks, acknowledge):
            if self.confirm is None or not self.confirm(checks):
                raise SafetyCheckRequired(checks, declined=self.confirm is not None)
        results = []
        failed = False
        state = None
        for call in calls:
            decision, explanation = self._decision(call)
            extra = None
            error = None
            if failed:
                error = HALT
            elif decision in ("", "regular", "allowed", "allow", "require_confirmation"):
                if decision == "require_confirmation":
                    extra = {"safety_acknowledgement": True}
                try:
                    self.do(call.name, call.args)
                except (ComputerError, MinionError) as e:
                    error = str(e)
                state = None  # the screen may have changed
            else:
                error = f"Not executed: blocked by Gemini's safety decision {decision!r}. {explanation}".strip()
            if error:
                failed = True
            if state is None:
                state = (*self.screenshot_b64(), self.current_url())
            results.append(self.result(call, state, error, extra))
        return results
