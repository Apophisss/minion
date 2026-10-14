import base64
from types import SimpleNamespace as NS

import pytest

from minion.desktop import ActResult, Screenshot
from minion.errors import MinionError
from minion.integrations.openai import (
    HALT,
    PREVIEW,
    ComputerError,
    ComputerUse,
    SafetyCheckRequired,
    xdotool_key,
)

PNG_URL = "data:image/png;base64," + base64.b64encode(b"PNG").decode()


class FakeDesktop:
    """Records act() batches; `fail(step)` returning a message makes that step fail like the agent does."""

    def __init__(self, w=1280, h=800, fail=None):
        self.size = (w, h)
        self.acts = []
        self.shots = []
        self.fail = fail

    def screenshot(self, **kw):
        self.shots.append(kw)
        return Screenshot(b"PNG", 10, 10, "png")

    def act(self, *actions, check=True, **kw):
        steps = [s for a in actions for s in (a if isinstance(a, list) else [a])]
        self.acts.append(steps)
        results, error = [], None
        for s in steps:
            if error:
                results.append({"action": s["action"], "ok": False, "skipped": True, "detail": "skipped"})
                continue
            why = self.fail(s) if self.fail else None
            if why:
                error = why
            results.append({"action": s["action"], "ok": not why, "detail": why or "done"})
        if error:
            return ActResult(False, f"✗ {error}", steps=results, error=error)
        return ActResult(True, "✓ done\n→ screen changed 5%", steps=results)


def call(call_id, *actions, checks=None, **extra):
    item = {
        "type": "computer_call",
        "id": f"cu_{call_id}",
        "call_id": call_id,
        "actions": list(actions),
        "pending_safety_checks": checks or [],
        "status": "completed",
    }
    item.update(extra)
    return item


def click(x, y, button="left", **kw):
    return {"type": "click", "button": button, "x": x, "y": y, **kw}


# -- tool definitions -------------------------------------------------------------------
def test_tool_definitions_and_request_params():
    d = FakeDesktop()
    cu = ComputerUse(d)
    assert cu.tool() == {"type": "computer"}
    assert cu.params() == {"tools": [{"type": "computer"}]}
    preview = ComputerUse(d, version=PREVIEW)
    assert preview.tool() == {
        "type": "computer_use_preview",
        "display_width": 1280,
        "display_height": 800,
        "environment": "linux",
    }
    assert preview.params() == {"tools": [preview.tool()], "truncation": "auto"}
    small = ComputerUse(d, version=PREVIEW, max_long_edge=1024, environment="browser")
    assert (small.tool()["display_width"], small.tool()["display_height"]) == (1024, 640)
    assert small.tool()["environment"] == "browser"
    with pytest.raises(MinionError):
        ComputerUse(d, version="computer_use_2024")
    with pytest.raises(MinionError):
        ComputerUse(d, version=PREVIEW, environment="android")


# -- coordinates --------------------------------------------------------------------------
def test_coordinates_map_back_through_screenshot_scaling():
    d = FakeDesktop(2560, 1600)
    cu = ComputerUse(d, max_long_edge=1280)
    assert cu.scale == 0.5 and cu.shot == (1280, 800)
    assert cu.steps(click(640, 400))[0]["target"] == [1280, 800]
    assert cu.to_screen(1279.9, 799.9) == [2559, 1599]
    with pytest.raises(ComputerError, match="outside the 1280x800 screenshot"):
        cu.to_screen(1280, 10)
    with pytest.raises(ComputerError, match="outside"):
        cu.to_screen(-1, 10)
    with pytest.raises(ComputerError, match="must be numbers"):
        cu.to_screen("left", None)
    cu.output("c1")
    assert d.shots[-1] == {"scale": 0.5}
    pixels = ComputerUse(FakeDesktop(1920, 1080), max_pixels=1920 * 1080 // 4)
    assert pixels.shot == (960, 540)
    full = ComputerUse(FakeDesktop(1280, 800))
    full.output("c2")
    assert full.scale == 1.0 and full.desktop.shots[-1] == {"scale": None}


# -- every action type --------------------------------------------------------------------
def test_click_buttons_and_held_modifiers():
    cu = ComputerUse(FakeDesktop())
    assert cu.steps(click(100, 200)) == [{"action": "click", "target": [100, 200], "button": "left", "count": 1}]
    assert cu.steps({"type": "click", "x": 1, "y": 2})[0]["button"] == "left"  # button defaults to left
    assert cu.steps(click(1, 2, "right"))[0]["button"] == "right"
    assert cu.steps(click(1, 2, "wheel"))[0]["button"] == "middle"
    assert cu.steps(click(5, 6, "back")) == [
        {"action": "move", "target": [5, 6]},
        {"action": "key", "keys": "alt+Left"},
    ]
    assert cu.steps(click(5, 6, "forward"))[1] == {"action": "key", "keys": "alt+Right"}
    with pytest.raises(ComputerError, match="unknown mouse button"):
        cu.steps(click(1, 2, "side"))
    assert cu.steps(click(1, 2, keys=["SHIFT"]))[0]["modifiers"] == "shift"
    assert cu.steps(click(1, 2, keys=["CTRL", "ALT", "CTRL"]))[0]["modifiers"] == "ctrl+alt"
    assert cu.steps(click(1, 2, keys=["META"]))[0]["modifiers"] == "super"
    with pytest.raises(ComputerError, match="cannot hold 'A'"):
        cu.steps(click(1, 2, keys=["A"]))
    assert cu.steps({"type": "double_click", "x": 3, "y": 4, "keys": ["CTRL"]}) == [
        {"action": "click", "target": [3, 4], "button": "left", "count": 2, "modifiers": "ctrl"}
    ]


def test_drag_paths():
    cu = ComputerUse(FakeDesktop())
    two = {"type": "drag", "path": [{"x": 10, "y": 20}, {"x": 30, "y": 40}]}
    assert cu.steps(two) == [{"action": "drag", "from": [10, 20], "to": [30, 40]}]
    assert cu.steps({"type": "drag", "path": [[10, 20], [30, 40]]}) == cu.steps(two)  # [x, y] pairs too
    assert cu.steps({"type": "drag", "path": [NS(x=10, y=20), NS(x=30, y=40)]}) == cu.steps(two)  # SDK points
    long = {"type": "drag", "path": [{"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}, {"x": 4, "y": 4}]}
    assert cu.steps(long) == [
        {"action": "mouse_down", "target": [1, 1]},
        {"action": "move", "target": [2, 2]},
        {"action": "move", "target": [3, 3]},
        {"action": "mouse_up", "target": [4, 4]},
    ]
    assert cu.steps({**long, "keys": ["SHIFT"]}) == [
        {"action": "drag", "from": [1, 1], "to": [4, 4], "modifiers": "shift"}
    ]
    with pytest.raises(ComputerError, match="at least two points"):
        cu.steps({"type": "drag", "path": [{"x": 1, "y": 1}]})
    with pytest.raises(ComputerError, match="outside"):
        cu.steps({"type": "drag", "path": [{"x": 1, "y": 1}, {"x": 5000, "y": 1}]})


def test_move_and_scroll_become_wheel_clicks():
    cu = ComputerUse(FakeDesktop())
    assert cu.steps({"type": "move", "x": 5, "y": 6, "keys": ["SHIFT"]}) == [{"action": "move", "target": [5, 6]}]

    def scroll(sx, sy, **kw):
        return cu.steps({"type": "scroll", "x": 50, "y": 60, "scroll_x": sx, "scroll_y": sy, **kw})

    assert scroll(0, 300) == [{"action": "scroll", "direction": "down", "amount": 3, "target": [50, 60]}]
    assert scroll(0, -250)[0]["direction"] == "up" and scroll(0, -250)[0]["amount"] == 3
    assert scroll(0, 20)[0]["amount"] == 1  # always at least one click
    assert scroll(0, 100_000)[0]["amount"] == 50  # and at most 50
    assert scroll(200, 0) == [{"action": "scroll", "direction": "right", "amount": 2, "target": [50, 60]}]
    assert [s["direction"] for s in scroll(-100, 400)] == ["down", "left"]
    assert scroll(0, 0) == [{"action": "move", "target": [50, 60]}]
    assert scroll(0, 100, keys=["CTRL"])[0]["modifiers"] == "ctrl"
    with pytest.raises(ComputerError, match="must be numbers"):
        scroll("lots", 0)
    half = ComputerUse(FakeDesktop(2560, 1600), max_long_edge=1280)  # 100 screenshot px = 200 desktop px
    assert half.steps({"type": "scroll", "x": 1, "y": 1, "scroll_x": 0, "scroll_y": 100})[0]["amount"] == 2
    fine = ComputerUse(FakeDesktop(), scroll_unit=50)
    assert fine.steps({"type": "scroll", "x": 1, "y": 1, "scroll_x": 0, "scroll_y": 100})[0]["amount"] == 2


def test_keypress_maps_key_names_to_xdotool():
    cu = ComputerUse(FakeDesktop())

    def keys(*names):
        return cu.steps({"type": "keypress", "keys": list(names)})[0]["keys"]

    assert keys("CTRL", "C") == "ctrl+c"
    assert keys("ENTER") == "Return"
    assert keys("ctrl", "shift", "t") == "ctrl+shift+t"
    assert keys("CMD", "A") == "super+a"
    assert keys("ALT", "F4") == "alt+F4"
    assert keys("CTRL", "+") == "ctrl++"  # the desktop reads a trailing "+" as the plus key
    assert [xdotool_key(k) for k in ("ARROWLEFT", "LEFT", "PAGEDOWN", "PAGEUP", "ESC", "BACKSPACE", "DEL")] == [
        "Left",
        "Left",
        "Page_Down",
        "Page_Up",
        "Escape",
        "BackSpace",
        "Delete",
    ]
    assert [xdotool_key(k) for k in ("SPACE", " ", "TAB", "HOME", "END", "OPTION", "f12", "Print")] == [
        "space",
        "space",
        "Tab",
        "Home",
        "End",
        "alt",
        "F12",
        "Print",
    ]
    with pytest.raises(ComputerError, match="keypress needs keys"):
        cu.steps({"type": "keypress", "keys": []})


def test_type_wait_screenshot_and_unknown_actions():
    cu = ComputerUse(FakeDesktop(), wait=0.5)
    assert cu.steps({"type": "type", "text": "penguin"}) == [{"action": "type", "text": "penguin"}]
    assert cu.steps({"type": "type", "text": ""}) == []
    assert cu.steps({"type": "wait"}) == [{"action": "wait", "seconds": 0.5}]
    assert ComputerUse(FakeDesktop()).steps({"type": "wait"}) == [{"action": "wait", "seconds": 2.0}]
    assert cu.steps({"type": "screenshot"}) == []
    with pytest.raises(ComputerError, match="unknown computer action 'zoom'"):
        cu.steps({"type": "zoom"})


# -- run(): batches, outputs, generations -------------------------------------------------
def test_run_executes_a_batch_as_one_act_and_returns_the_output_item():
    d = FakeDesktop()
    cu = ComputerUse(d)
    output = [
        {"type": "reasoning", "id": "rs_1", "summary": []},
        call("call_002", click(405, 157), {"type": "type", "text": "penguin"}, {"type": "keypress", "keys": ["ENTER"]}),
        {"type": "message", "role": "assistant", "content": []},
    ]
    items = cu.run(output)
    assert d.acts == [
        [
            {"action": "click", "target": [405, 157], "button": "left", "count": 1},
            {"action": "type", "text": "penguin"},
            {"action": "key", "keys": "Return"},
        ]
    ]
    assert items == [
        {
            "type": "computer_call_output",
            "call_id": "call_002",
            "output": {"type": "computer_screenshot", "image_url": PNG_URL, "detail": "original"},
        }
    ]
    assert cu.errors == []
    assert cu.run([{"type": "message", "role": "assistant", "content": []}]) == []
    assert cu.run(None) == []


def test_screenshot_only_call_does_not_touch_the_desktop():
    d = FakeDesktop()
    items = ComputerUse(d).run([call("call_001", {"type": "screenshot"})])
    assert d.acts == [] and len(d.shots) == 1
    assert items[0]["call_id"] == "call_001" and items[0]["output"]["image_url"] == PNG_URL
    empty = {"type": "computer_call", "call_id": "c", "actions": [], "pending_safety_checks": []}
    assert ComputerUse(d).run([empty])[0]["call_id"] == "c"


def test_preview_calls_carry_one_action_and_no_detail():
    d = FakeDesktop()
    cu = ComputerUse(d, version=PREVIEW)
    item = {
        "type": "computer_call",
        "id": "cu_1",
        "call_id": "call_1",
        "action": {"type": "scroll", "x": 10, "y": 20, "scroll_x": 0, "scroll_y": 500},
        "pending_safety_checks": [],
        "status": "completed",
    }
    items = cu.run([item])
    assert d.acts == [[{"action": "scroll", "direction": "down", "amount": 5, "target": [10, 20]}]]
    assert items == [
        {
            "type": "computer_call_output",
            "call_id": "call_1",
            "output": {"type": "computer_screenshot", "image_url": PNG_URL},
        }
    ]
    assert ComputerUse(d, version=PREVIEW, detail="high").output("x")["output"]["detail"] == "high"
    assert "detail" not in ComputerUse(d, detail=None).output("x")["output"]


def test_sdk_objects_are_read_through_attributes():
    d = FakeDesktop()
    sdk_call = NS(
        type="computer_call",
        id="cu_1",
        call_id="call_9",
        status="completed",
        action=None,
        actions=[
            NS(type="double_click", x=10, y=20, keys=None),
            NS(type="drag", path=[NS(x=1, y=2), NS(x=3, y=4)], keys=["CTRL"]),
            NS(type="keypress", keys=["CTRL", "S"]),
        ],
        pending_safety_checks=[],
    )
    items = ComputerUse(d).run([NS(type="reasoning"), sdk_call])
    assert d.acts == [
        [
            {"action": "click", "target": [10, 20], "button": "left", "count": 2},
            {"action": "drag", "from": [1, 2], "to": [3, 4], "modifiers": "ctrl"},
            {"action": "key", "keys": "ctrl+s"},
        ]
    ]
    assert items[0]["call_id"] == "call_9"


# -- safety checks ------------------------------------------------------------------------
CHECK = {
    "id": "cu_sc_1",
    "code": "malicious_instructions",
    "message": "We've detected instructions that may cause your application to perform malicious actions.",
}


def test_pending_safety_checks_are_returned_and_never_acknowledged_silently():
    d = FakeDesktop()
    cu = ComputerUse(d)
    output = [call("call_7", click(1, 2), checks=[CHECK])]
    assert cu.pending_safety_checks(output) == [CHECK]
    with pytest.raises(SafetyCheckRequired) as err:
        cu.run(output)
    assert err.value.checks == [CHECK] and not err.value.declined
    assert "malicious_instructions" in str(err.value)
    assert d.acts == [] and d.shots == []  # nothing ran
    items = cu.run(output, acknowledge=err.value.checks)
    assert items[0]["acknowledged_safety_checks"] == [CHECK]
    assert len(d.acts) == 1
    assert cu.run(output, acknowledge=True)[0]["acknowledged_safety_checks"] == [CHECK]
    assert cu.run(output, acknowledge=["cu_sc_1"])[0]["acknowledged_safety_checks"] == [CHECK]
    with pytest.raises(SafetyCheckRequired):
        cu.run(output, acknowledge=["some_other_check"])
    sdk_output = [NS(**{**call("c", click(1, 2)), "pending_safety_checks": [NS(id="sc", code=None, message="m")]})]
    assert cu.pending_safety_checks(sdk_output) == [{"id": "sc", "message": "m"}]


def test_confirm_callable_decides_about_safety_checks():
    seen = []

    def yes(checks):
        seen.append(checks)
        return True

    d = FakeDesktop()
    output = [call("call_7", click(1, 2), checks=[CHECK])]
    items = ComputerUse(d, confirm=yes).run(output)
    assert seen == [[CHECK]] and items[0]["acknowledged_safety_checks"] == [CHECK]
    with pytest.raises(SafetyCheckRequired) as err:
        ComputerUse(d, confirm=lambda checks: False).run(output)
    assert err.value.declined and "declined" in str(err.value)
    assert len(d.acts) == 1  # the declined call did not run
    assert "acknowledged_safety_checks" not in ComputerUse(d, confirm=yes).run([call("c", click(1, 2))])[0]


# -- errors -------------------------------------------------------------------------------
def test_a_bad_action_stops_the_batch_after_running_what_came_before():
    d = FakeDesktop()
    cu = ComputerUse(d)
    items = cu.run([call("c1", click(1, 2), click(99999, 2), {"type": "type", "text": "never"})])
    assert d.acts == [[{"action": "click", "target": [1, 2], "button": "left", "count": 1}]]
    assert items[0]["type"] == "computer_call_output" and items[0]["call_id"] == "c1"
    note = items[1]
    assert note["role"] == "user"
    assert "Action 2 of 3 (click) failed" in note["content"] and "outside the 1280x800 screenshot" in note["content"]
    assert "The 1 action(s) after it were not executed." in note["content"]
    assert cu.errors and cu.errors[0].startswith("Action 2 of 3 (click)")


def test_desktop_failures_are_attributed_to_the_failing_action_and_halt_later_calls():
    d = FakeDesktop(fail=lambda s: "no window to type into" if s["action"] == "type" else None)
    cu = ComputerUse(d)
    items = cu.run(
        [
            call("c1", click(1, 2), {"type": "type", "text": "x"}, {"type": "keypress", "keys": ["ENTER"]}),
            call("c2", click(3, 4)),
        ]
    )
    assert len(d.acts) == 1  # c2 never ran
    assert [i.get("call_id") for i in items] == ["c1", "c2", None]  # c2 is still answered with a screenshot
    assert items[1]["output"]["image_url"] == PNG_URL
    assert cu.errors == [
        "Action 2 of 3 (type) failed: no window to type into. The 1 action(s) after it were not executed.",
        f"Call c2: {HALT}",
    ]
    assert HALT in items[2]["content"]
    # a step expanded from one action (a two-axis scroll) is reported as that action
    d2 = FakeDesktop(fail=lambda s: "boom" if s.get("direction") == "left" else None)
    cu2 = ComputerUse(d2, report_errors=False)
    items2 = cu2.run([call("c", click(1, 1), {"type": "scroll", "x": 1, "y": 1, "scroll_x": -100, "scroll_y": 100})])
    assert cu2.errors == ["Action 2 of 2 (scroll) failed: boom."]
    assert len(items2) == 1  # report_errors=False: no message, just the output


def test_partially_generated_calls_are_refused():
    d = FakeDesktop()
    with pytest.raises(MinionError, match="incomplete"):
        ComputerUse(d).run([call("c1", click(1, 2), status="incomplete")])
    assert d.acts == [] and d.shots == []
