import base64

from minion.desktop import ActResult, Screenshot
from minion.integrations.anthropic import HALT, ComputerUse


class FakeDesktop:
    def __init__(self, w=1920, h=1080):
        self.size = (w, h)
        self.acts = []
        self.shots = []

    def screenshot(self, **kw):
        self.shots.append(kw)
        return Screenshot(b"PNG", 10, 10, "png")

    def act(self, step, check=False):
        self.acts.append(step)
        if step.get("target") == "fail":
            return ActResult(False, "✗ nope", error="nope")
        return ActResult(True, "✓ done\n→ screen changed 5%")

    def cursor(self):
        return (960, 540)


def tool_use(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "toolset_name": "computer", "input": inp}


def test_scaling_for_toolset_and_legacy():
    d = FakeDesktop(1920, 1080)
    cu = ComputerUse(d)  # toolset: 2576 px / 3.75 MP -> fits as is
    assert cu.scale == 1.0 and cu.shot == (1920, 1080)
    legacy = ComputerUse(d, version="computer_20251124")  # 1568 px / 1.15 MP
    assert legacy.shot[0] < 1920 and legacy.shot[0] * legacy.shot[1] <= 1_150_000
    assert legacy.tool()["display_width_px"] == legacy.shot[0]
    assert legacy.beta_header == "computer-use-2025-11-24"
    assert ComputerUse(d).tool() == {"type": "computer_toolset_20260801"}
    assert ComputerUse(d, zoom=False).tool()["configs"] == {"zoom": {"enabled": False}}


def test_coordinates_are_mapped_back_to_the_screen():
    d = FakeDesktop(2560, 1600)
    cu = ComputerUse(d, version="computer_20251124")
    x, y = cu.shot[0] // 2, cu.shot[1] // 2
    cu.run([tool_use("a", "left_click", coordinate=[x, y], text="shift")])
    step = d.acts[-1]
    assert step["action"] == "click" and step["modifiers"] == "shift"
    tx, ty = step["target"]
    assert abs(tx - 1280) <= 2 and abs(ty - 800) <= 2


def test_batch_runs_in_order_and_halts_after_failure():
    d = FakeDesktop()
    out = ComputerUse(d).run(
        [
            tool_use("1", "screenshot"),
            {"type": "text", "text": "thinking"},
            tool_use("2", "key", text="ctrl+s", repeat=2),
            tool_use("3", "left_click", coordinate=[99999, 1]),
            tool_use("4", "type", text="never"),
        ]
    )
    assert [r["tool_use_id"] for r in out] == ["1", "2", "3", "4"]
    assert all(r["toolset_name"] == "computer" for r in out)
    assert out[0]["content"][0]["type"] == "image"
    assert out[1]["content"][0]["text"].startswith("OK")
    assert out[2]["is_error"] and "outside" in out[2]["content"]
    assert out[3] == {
        "type": "tool_result",
        "tool_use_id": "4",
        "toolset_name": "computer",
        "is_error": True,
        "content": HALT,
    }
    assert d.acts == [{"action": "key", "keys": "ctrl+s", "repeat": 2}]


def test_legacy_action_blocks_and_cursor():
    d = FakeDesktop(1280, 800)
    cu = ComputerUse(d, version="computer_20251124")
    res = cu.run([{"type": "tool_use", "id": "x", "name": "computer", "input": {"action": "cursor_position"}}])
    assert res[0]["content"][0]["text"] == "X=960,Y=540"
    assert "toolset_name" not in res[0]


def test_zoom_region_fits_screenshot_size():
    d = FakeDesktop(1280, 800)
    ComputerUse(d).run([tool_use("z", "zoom", region=[100, 100, 420, 300])])
    kw = d.shots[-1]
    assert kw["region"] == [100, 100, 320, 200]
    assert kw["width"] == 1280  # 320x200 scaled to fit 1280x800


def test_validation_errors():
    d = FakeDesktop()
    res = ComputerUse(d).run([tool_use("a", "scroll", scroll_direction="down", scroll_amount=500)])
    assert res[0]["is_error"]
    res = ComputerUse(d).run([tool_use("b", "wait", duration=301)])
    assert res[0]["is_error"]
    assert base64  # silence unused import linters
