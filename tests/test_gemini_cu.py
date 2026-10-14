import base64
import json
from types import SimpleNamespace as NS

import pytest

import minion.integrations.gemini as gemini
from minion.desktop import ActResult, Observation, Screenshot
from minion.errors import MinionError
from minion.integrations.gemini import (
    HALT,
    ComputerError,
    ComputerUse,
    SafetyCheckRequired,
    split_keys,
    xdotool_key,
)

B64 = base64.b64encode(b"PNG").decode()
FIREFOX = {"id": "0x1", "title": "Example — Mozilla Firefox", "app": "firefox-esr", "focused": True}
WRITER = {"id": "0x2", "title": "Untitled 1 - LibreOffice Writer", "app": "libreoffice", "focused": True}


class FakeDesktop:
    """Records act() batches, opens and screenshots; `fail(step)` returning a message fails that step."""

    def __init__(self, w=1280, h=800, windows=(), url="https://example.com/", fail=None):
        self.size = (w, h)
        self.acts = []
        self.shots = []
        self.opened = []
        self.sees = 0
        self._windows = [dict(win) for win in windows]
        self.url = url
        self.fail = fail
        self.open_error = None

    def screenshot(self, **kw):
        self.shots.append(kw)
        return Screenshot(b"PNG", 10, 10, "png")

    def act(self, *actions, check=True, **kw):
        steps = [s for a in actions for s in (a if isinstance(a, list) else [a])]
        self.acts.append(steps)
        for s in steps:
            why = self.fail(s) if self.fail else None
            if why:
                return ActResult(False, f"✗ {why}", error=why)
        return ActResult(True, "✓ done")

    def windows(self):
        return self._windows

    def open(self, target, wait=12.0):
        self.opened.append(target)
        res = {"command": f"firefox-esr {target}", "kind": "url", "window": None}
        if self.open_error:
            res["error"] = self.open_error
        return res

    def see(self, ocr="auto", **kw):
        self.sees += 1
        return Observation("page", elements=[{"id": "@1", "role": "address bar", "name": "Address", "value": self.url}])


def fc(name, i="fc_1", **args):
    """An Interactions API function_call step."""
    return {"type": "function_call", "id": i, "name": name, "arguments": args}


def interaction(*steps):
    return {"id": "int_1", "status": "requires_action", "steps": list(steps)}


def last(d):
    return d.acts[-1]


# -- tool entries ---------------------------------------------------------------------------
def test_tool_entries_for_both_apis():
    d = FakeDesktop()
    assert ComputerUse(d).tool() == {"type": "computer_use", "environment": "desktop"}
    cu = ComputerUse(d, environment="browser", exclude=["go_back"])
    assert cu.tool(enable_prompt_injection_detection=True, disabled_safety_policies=["DATA_MODIFICATION"]) == {
        "type": "computer_use",
        "environment": "browser",
        "excluded_predefined_functions": ["go_back"],
        "enable_prompt_injection_detection": True,
        "disabled_safety_policies": ["data_modification"],
    }
    gc = ComputerUse(d, api="generate_content", environment="browser")
    assert gc.tool() == {"computer_use": {"environment": "ENVIRONMENT_BROWSER"}}
    assert gc.tool(disabled_safety_policies=["financial_transactions"]) == {
        "computer_use": {"environment": "ENVIRONMENT_BROWSER", "disabled_safety_policies": ["FINANCIAL_TRANSACTIONS"]}
    }
    with pytest.raises(MinionError):
        ComputerUse(d, environment="mobile")
    with pytest.raises(MinionError):
        ComputerUse(d, api="chat")


# -- coordinates ------------------------------------------------------------------------------
def test_normalized_coordinates_map_to_desktop_pixels():
    cu = ComputerUse(FakeDesktop(1280, 800))
    assert cu.to_screen(500, 500) == [640, 400]
    assert cu.to_screen(0, 0) == [0, 0]
    assert cu.to_screen(999, 999) == [1278, 799]
    assert cu.to_screen(1000, 1000) == [1279, 799]  # clamped to the last pixel
    assert ComputerUse(FakeDesktop(1920, 1080)).to_screen(250, 750) == [480, 810]
    for bad in ((-1, 5), (1001, 0), (5, 1200)):
        with pytest.raises(ComputerError, match="0-999 coordinate grid"):
            cu.to_screen(*bad)
    with pytest.raises(ComputerError, match="must be numbers"):
        cu.to_screen("left", None)
    small = ComputerUse(FakeDesktop(1280, 800), max_long_edge=640)  # screenshots shrink, the grid does not
    assert small.to_screen(500, 500) == [640, 400]
    small.screenshot_input()
    assert small.desktop.shots[-1] == {"scale": 0.5}


# -- every function ---------------------------------------------------------------------------
def test_clicks_pointer_and_drag_functions():
    d = FakeDesktop()
    cu = ComputerUse(d)
    expected = {
        "click": ("left", 1),
        "click_at": ("left", 1),
        "double_click": ("left", 2),
        "triple_click": ("left", 3),
        "middle_click": ("middle", 1),
        "right_click": ("right", 1),
    }
    for name, (button, count) in expected.items():
        cu.do(name, {"x": 500, "y": 250, "intent": "press it"})
        assert last(d) == [{"action": "click", "target": [640, 200], "button": button, "count": count}]
    for name in ("move", "hover_at"):
        cu.do(name, {"x": 100, "y": 100})
        assert last(d) == [{"action": "move", "target": [128, 80]}]
    cu.do("mouse_down", {"x": 100, "y": 100})
    assert last(d) == [{"action": "mouse_down", "target": [128, 80]}]
    cu.do("mouse_up", {"x": 200, "y": 100})
    assert last(d) == [{"action": "mouse_up", "target": [256, 80]}]
    cu.do("drag_and_drop", {"start_x": 0, "start_y": 0, "end_x": 500, "end_y": 500})
    assert last(d) == [{"action": "drag", "from": [0, 0], "to": [640, 400]}]
    cu.do("drag_and_drop", {"x": 0, "y": 0, "destination_x": 500, "destination_y": 500})  # earlier names
    assert last(d) == [{"action": "drag", "from": [0, 0], "to": [640, 400]}]
    with pytest.raises(ComputerError, match="end_x/end_y"):
        cu.do("drag_and_drop", {"start_x": 0, "start_y": 0})
    count = len(d.acts)
    cu.do("take_screenshot", {"intent": "look"})
    assert len(d.acts) == count  # take_screenshot does not act


def test_typing_functions():
    d = FakeDesktop()
    cu = ComputerUse(d)
    cu.do("type", {"text": "otters", "intent": "name the deck"})
    assert last(d) == [{"action": "type", "text": "otters"}]
    cu.do("type", {"text": "otters", "press_enter": True})
    assert last(d) == [{"action": "type", "text": "otters"}, {"action": "key", "keys": "Return"}]
    cu.do("type", {"text": "a", "x": 500, "y": 500})  # the docs' handler clicks first when given a point
    assert last(d)[0] == {"action": "click", "target": [640, 400], "button": "left", "count": 1}
    cu.do("type", {"text": "", "press_enter": True})
    assert last(d) == [{"action": "key", "keys": "Return"}]
    with pytest.raises(ComputerError, match="type needs text"):
        cu.do("type", {"text": ""})
    cu.do("type_text_at", {"x": 500, "y": 500, "text": "hello"})  # earlier set: clears the field first
    assert last(d) == [
        {"action": "click", "target": [640, 400], "button": "left", "count": 1},
        {"action": "key", "keys": "ctrl+a"},
        {"action": "key", "keys": "Delete"},
        {"action": "type", "text": "hello"},
    ]
    cu.do("type_text_at", {"x": 500, "y": 500, "text": "hi", "press_enter": True, "clear_before_typing": False})
    assert [s["action"] for s in last(d)] == ["click", "type", "key"] and last(d)[-1]["keys"] == "Return"


def test_key_functions_map_names_to_xdotool():
    d = FakeDesktop()
    cu = ComputerUse(d)

    def pressed(name, **args):
        cu.do(name, args)
        return last(d)[0]["keys"]

    assert pressed("press_key", key="Enter") == "Return"
    assert pressed("press_key", key="a") == "a"
    assert pressed("press_key", key="A") == "A"  # alone, a capital stays a capital
    assert pressed("hotkey", keys=["Control", "A"]) == "ctrl+a"
    assert pressed("hotkey", keys=["ctrl", "shift", "T"]) == "ctrl+shift+t"
    assert pressed("hotkey", keys=["Meta", "ArrowLeft"]) == "super+Left"
    assert pressed("key_combination", keys="control+c") == "ctrl+c"
    assert pressed("key_combination", keys="Control++") == "ctrl++"  # the plus key
    assert split_keys("alt+F4") == ["alt", "F4"] and split_keys("+") == ["+"] and split_keys(["a", "b"]) == ["a", "b"]
    assert [xdotool_key(k) for k in ("multiply", "PageDown", "pageup", "Backspace", "F5", "KeyA", "Digit1", " ")] == [
        "KP_Multiply",
        "Page_Down",
        "Page_Up",
        "BackSpace",
        "F5",
        "a",
        "1",
        "space",
    ]
    with pytest.raises(ComputerError, match="no key given"):
        cu.do("press_key", {"key": ""})
    with pytest.raises(ComputerError, match="no key given"):
        cu.do("hotkey", {"keys": []})


def test_key_down_holds_modifiers_for_later_actions():
    d = FakeDesktop()
    cu = ComputerUse(d)
    cu.do("key_down", {"key": "Shift"})
    assert d.acts == [] and cu.held == ["shift"]
    cu.do("click", {"x": 500, "y": 500})
    assert last(d)[0]["modifiers"] == "shift"
    cu.do("press_key", {"key": "Tab"})
    assert last(d) == [{"action": "key", "keys": "shift+Tab"}]
    cu.do("key_down", {"key": "Control"})
    cu.do("drag_and_drop", {"start_x": 1, "start_y": 1, "end_x": 2, "end_y": 2})
    assert last(d)[0]["modifiers"] == "shift+ctrl"
    cu.do("scroll", {"x": 1, "y": 1, "direction": "down"})
    assert last(d)[0]["modifiers"] == "shift+ctrl"
    cu.do("hotkey", {"keys": ["Control", "c"]})
    assert last(d) == [{"action": "key", "keys": "shift+ctrl+c"}]  # no doubled ctrl
    cu.do("key_up", {"key": "Shift"})
    cu.do("key_up", {"key": "ctrl"})
    assert cu.held == []
    cu.do("click", {"x": 1, "y": 1})
    assert "modifiers" not in last(d)[0]
    count = len(d.acts)
    cu.do("key_down", {"key": "a"})  # not a modifier: pressed once, nothing stays held
    assert last(d) == [{"action": "key", "keys": "a"}] and cu.held == []
    cu.do("key_up", {"key": "a"})
    assert len(d.acts) == count + 1
    with pytest.raises(ComputerError, match="needs a key"):
        cu.do("key_down", {})


def test_scroll_functions_turn_magnitudes_into_wheel_clicks():
    d = FakeDesktop(1280, 800)
    cu = ComputerUse(d)

    def scroll(name, **args):
        cu.do(name, {"x": 500, "y": 500, **args})
        return last(d)[0]

    # magnitude_in_pixels is on the 0-999 grid along the scroll axis: 300 -> 240 px -> 2 clicks of 100 px
    assert scroll("scroll", direction="down") == {
        "action": "scroll",
        "direction": "down",
        "amount": 2,
        "target": [640, 400],
    }
    assert scroll("scroll", direction="up", magnitude_in_pixels=999)["amount"] == 8
    assert scroll("scroll", direction="left", magnitude_in_pixels=500)["amount"] == 6  # 640 px wide
    assert scroll("scroll_at", direction="down")["amount"] == 6  # earlier default magnitude 800 -> 640 px
    assert scroll("scroll_at", direction="right", magnitude=100)["amount"] == 1
    assert ComputerUse(d, scroll_unit=40).to_screen(0, 0) == [0, 0]
    fine = ComputerUse(d, scroll_unit=40)
    fine.do("scroll", {"x": 1, "y": 1, "direction": "down"})
    assert last(d)[0]["amount"] == 6  # 240 px / 40
    with pytest.raises(ComputerError, match="direction must be"):
        scroll("scroll", direction="sideways")
    with pytest.raises(ComputerError, match="between 0 and 1000"):
        scroll("scroll", direction="down", magnitude_in_pixels=5000)
    cu.do("scroll_document", {"direction": "down"})
    assert last(d) == [{"action": "key", "keys": "Page_Down"}]
    cu.do("scroll_document", {"direction": "up"})
    assert last(d) == [{"action": "key", "keys": "Page_Up"}]
    cu.do("scroll_document", {"direction": "right"})
    assert last(d) == [{"action": "scroll", "direction": "right", "amount": 6, "target": [640, 400]}]
    with pytest.raises(ComputerError, match="direction must be"):
        cu.do("scroll_document", {})


def test_wait_functions(monkeypatch):
    slept = []
    monkeypatch.setattr(gemini.time, "sleep", slept.append)
    d = FakeDesktop()
    cu = ComputerUse(d)
    cu.do("wait", {})
    cu.do("wait", {"seconds": 3})
    cu.do("wait_5_seconds", {})
    assert slept == [1.0, 3.0, 5]
    with pytest.raises(ComputerError, match="between 0 and 60"):
        cu.do("wait", {"seconds": 61})
    assert d.acts == []


def test_browser_functions_use_the_desktops_browser():
    d = FakeDesktop(windows=[FIREFOX])
    cu = ComputerUse(d, environment="browser")
    cu.do("navigate", {"url": "example.com/docs"})
    assert last(d) == [
        {"action": "key", "keys": "ctrl+l"},
        {"action": "type", "text": "example.com/docs"},
        {"action": "key", "keys": "Return"},
    ]
    cu.do("go_back", {})
    assert last(d) == [{"action": "key", "keys": "alt+Left"}]
    cu.do("go_forward", {})
    assert last(d) == [{"action": "key", "keys": "alt+Right"}]
    cu.do("search", {})
    assert last(d)[1] == {"action": "type", "text": "https://www.google.com"}
    count = len(d.acts)
    cu.do("open_web_browser", {})  # already focused: nothing to do
    assert len(d.acts) == count and d.opened == []
    with pytest.raises(ComputerError, match="navigate needs a url"):
        cu.do("navigate", {"url": " "})

    behind = FakeDesktop(windows=[WRITER, {**FIREFOX, "focused": False}])
    cu = ComputerUse(behind, environment="browser", search_url="https://duckduckgo.com")
    cu.do("go_back", {})
    assert last(behind) == [{"action": "focus", "window": "0x1"}, {"action": "key", "keys": "alt+Left"}]
    cu.do("navigate", {"url": "https://example.org"})
    assert last(behind)[0] == {"action": "focus", "window": "0x1"} and last(behind)[1]["keys"] == "ctrl+l"
    cu.do("open_web_browser", {})
    assert last(behind) == [{"action": "focus", "window": "0x1"}]

    none = FakeDesktop(windows=[WRITER])
    cu = ComputerUse(none, environment="browser", search_url="https://duckduckgo.com")
    cu.do("navigate", {"url": "example.com"})
    cu.do("navigate", {"url": "http://localhost:8000/app"})
    cu.do("search", {})
    cu.do("open_web_browser", {})
    assert none.opened == [
        "https://example.com",
        "http://localhost:8000/app",
        "https://duckduckgo.com",
        "https://duckduckgo.com",
    ]
    assert none.acts == []
    with pytest.raises(ComputerError, match="no browser window is open"):
        cu.do("go_back", {})
    none.open_error = "exited with code 1"
    with pytest.raises(ComputerError, match="could not open"):
        cu.do("navigate", {"url": "example.com"})


def test_mobile_and_unknown_functions_are_errors():
    cu = ComputerUse(FakeDesktop())
    with pytest.raises(ComputerError, match="mobile environment"):
        cu.do("open_app", {"app_name": "Chrome"})
    with pytest.raises(ComputerError, match="unknown computer use function"):
        cu.do("teleport", {})


# -- run(): Interactions API ------------------------------------------------------------------
def test_run_answers_interactions_function_calls_with_screenshots():
    d = FakeDesktop()
    cu = ComputerUse(d)
    source = interaction(
        {"type": "thought", "signature": "abc"},
        fc("click", "fc_1", x=500, y=500, intent="Open the menu"),
        fc("lookup_weather", "fc_2", city="Paris"),  # your own function: left for you
        {"type": "model_output", "content": [{"type": "text", "text": "Clicking."}]},
    )
    results = cu.run(source)
    assert d.acts == [[{"action": "click", "target": [640, 400], "button": "left", "count": 1}]]
    assert results == [
        {
            "type": "function_result",
            "name": "click",
            "call_id": "fc_1",
            "result": [{"type": "text", "text": "{}"}, {"type": "image", "data": B64, "mime_type": "image/png"}],
        }
    ]
    assert cu.run(source["steps"])[0]["call_id"] == "fc_1"  # a list of steps works too
    sdk = NS(id="int_2", steps=[NS(type="function_call", id="fc_9", name="type", arguments={"text": "hi"})])
    assert cu.run(sdk)[0]["call_id"] == "fc_9"
    answered = [fc("click", "fc_1", x=1, y=1), {"type": "function_result", "call_id": "fc_1", "result": "done"}]
    assert cu.run(answered) == []
    shots = len(d.shots)
    assert cu.run(interaction({"type": "model_output", "content": []})) == [] and cu.run(None) == []
    assert len(d.shots) == shots


def test_results_carry_the_url_in_the_browser_environment():
    d = FakeDesktop(windows=[FIREFOX], url="https://example.com/a")
    results = ComputerUse(d, environment="browser").run(interaction(fc("go_back")))
    assert json.loads(results[0]["result"][0]["text"]) == {"url": "https://example.com/a"}
    assert d.sees == 1
    assert (
        ComputerUse(d, environment="browser", url=False).run(interaction(fc("go_back")))[0]["result"][0]["text"] == "{}"
    )
    custom = ComputerUse(d, url=lambda: "https://intranet/")  # any environment, your own lookup
    assert json.loads(custom.run(interaction(fc("take_screenshot")))[0]["result"][0]["text"]) == {
        "url": "https://intranet/"
    }
    assert d.sees == 1


def test_excluded_functions_are_left_for_your_own_handler():
    d = FakeDesktop(windows=[FIREFOX])
    cu = ComputerUse(d, environment="browser", exclude=["navigate"])
    assert cu.run(interaction(fc("navigate", url="https://example.com"))) == []
    assert d.acts == [] and cu.tool()["excluded_predefined_functions"] == ["navigate"]


# -- run(): generateContent ------------------------------------------------------------------
def test_run_answers_generate_content_calls_with_function_response_parts():
    d = FakeDesktop()
    cu = ComputerUse(d, api="generate_content")
    response = NS(
        candidates=[
            NS(
                content=NS(
                    role="model",
                    parts=[
                        NS(text="I'll click.", function_call=None),
                        NS(text=None, function_call=NS(name="click", args={"x": 500, "y": 500}, id="abc")),
                    ],
                )
            )
        ]
    )
    assert cu.run(response) == [
        {
            "function_response": {
                "id": "abc",
                "name": "click",
                "response": {},
                "parts": [{"inline_data": {"mime_type": "image/png", "data": B64}}],
            }
        }
    ]
    rest = {
        "candidates": [
            {"content": {"role": "model", "parts": [{"functionCall": {"name": "type", "args": {"text": "hi"}}}]}}
        ]
    }
    out = cu.run(rest)
    assert out[0]["function_response"]["name"] == "type" and "id" not in out[0]["function_response"]
    assert last(d) == [{"action": "type", "text": "hi"}]
    parts = [{"function_call": {"name": "press_key", "args": {"key": "Enter"}}}]
    assert cu.run(parts)[0]["function_response"]["name"] == "press_key"
    assert cu.run(response.candidates[0])[0]["function_response"]["id"] == "abc"  # a Candidate
    assert cu.run(response.candidates[0].content)[0]["function_response"]["id"] == "abc"  # a Content
    assert cu.screenshot_input() == {"inline_data": {"mime_type": "image/png", "data": B64}}
    assert ComputerUse(d).screenshot_input() == {"type": "image", "data": B64, "mime_type": "image/png"}


# -- errors ----------------------------------------------------------------------------------
def test_failures_are_reported_and_later_calls_are_not_run():
    d = FakeDesktop()
    cu = ComputerUse(d)
    results = cu.run(interaction(fc("click", "fc_1", x=2000, y=5), fc("type", "fc_2", text="never")))
    assert d.acts == []
    first, second = results
    assert first["is_error"] and "0-999 coordinate grid" in json.loads(first["result"][0]["text"])["error"]
    assert first["result"][1]["type"] == "image"
    assert second["is_error"] and json.loads(second["result"][0]["text"]) == {"error": HALT}
    assert len(d.shots) == 1  # the halted call reuses the screenshot taken after the failure

    broken = FakeDesktop(fail=lambda s: "xdotool click failed" if s["action"] == "click" else None)
    results = ComputerUse(broken).run(interaction(fc("click", x=1, y=1)))
    assert json.loads(results[0]["result"][0]["text"]) == {"error": "xdotool click failed"}

    gc = ComputerUse(FakeDesktop(), api="generate_content").run([{"function_call": {"name": "open_app", "args": {}}}])
    response = gc[0]["function_response"]
    assert "mobile environment" in response["response"]["error"] and "is_error" not in response


# -- safety decisions --------------------------------------------------------------------------
CONFIRM = {"decision": "require_confirmation", "explanation": "Must check check-box"}


def test_safety_decisions_need_a_persons_confirmation():
    d = FakeDesktop()
    cu = ComputerUse(d)
    source = interaction(fc("click", "fc_1", x=60, y=100, safety_decision=CONFIRM))
    check = {"call_id": "fc_1", "function": "click", "explanation": "Must check check-box"}
    assert cu.safety_checks(source) == [check]
    with pytest.raises(SafetyCheckRequired) as err:
        cu.run(source)
    assert err.value.checks == [check] and not err.value.declined
    assert d.acts == [] and d.shots == []
    results = cu.run(source, acknowledge=err.value.checks)
    assert json.loads(results[0]["result"][0]["text"]) == {"safety_acknowledgement": True}
    assert len(d.acts) == 1
    assert "safety_acknowledgement" in cu.run(source, acknowledge=True)[0]["result"][0]["text"]
    asked = []
    approve = ComputerUse(d, confirm=lambda checks: asked.append(checks) or True)
    assert approve.run(source) and asked == [[check]]
    with pytest.raises(SafetyCheckRequired) as declined:
        ComputerUse(d, confirm=lambda checks: False).run(source)
    assert declined.value.declined
    gc = ComputerUse(d, api="generate_content")
    part = {"function_call": {"name": "click", "args": {"x": 1, "y": 1, "safety_decision": CONFIRM}}}
    assert gc.run([part], acknowledge=True)[0]["function_response"]["response"] == {"safety_acknowledgement": True}


def test_blocked_and_regular_safety_decisions():
    d = FakeDesktop()
    cu = ComputerUse(d)
    blocked = {"decision": "blocked", "explanation": "Payment pages are off limits."}
    results = cu.run(interaction(fc("click", "fc_1", x=1, y=1, safety_decision=blocked), fc("type", "fc_2", text="x")))
    assert d.acts == []
    assert results[0]["is_error"] and "Payment pages" in json.loads(results[0]["result"][0]["text"])["error"]
    assert json.loads(results[1]["result"][0]["text"])["error"] == HALT
    regular = {"decision": "regular", "explanation": ""}
    assert "is_error" not in cu.run(interaction(fc("click", x=1, y=1, safety_decision=regular)))[0]
    assert len(d.acts) == 1
