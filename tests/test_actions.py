import pytest

from minion.agent.server import RpcError, parse_step


def test_object_form():
    assert parse_step({"action": "click", "target": "@3"}) == ("click", {"target": "@3"})


def test_shorthand_objects():
    assert parse_step({"click": "@3"}) == ("click", {"target": "@3"})
    assert parse_step({"type": "hello"}) == ("type", {"text": "hello"})
    assert parse_step({"key": "ctrl+s"}) == ("key", {"keys": "ctrl+s"})
    assert parse_step({"scroll": "down", "amount": 5}) == ("scroll", {"direction": "down", "amount": 5})
    assert parse_step({"fill": ["@2", "x"]}) == ("fill", {"target": "@2", "text": "x"})
    assert parse_step({"drag": ["1,1", "9,9"]}) == ("drag", {"from": "1,1", "to": "9,9"})


def test_strings():
    assert parse_step("click @3") == ("click", {"target": "@3"})
    assert parse_step("click Sign in") == ("click", {"target": "Sign in"})
    assert parse_step("type 'hello world'") == ("type", {"text": "hello world"})
    assert parse_step("key ctrl+s 3") == ("key", {"keys": "ctrl+s", "repeat": 3})
    assert parse_step("scroll up 2") == ("scroll", {"direction": "up", "amount": 2})
    assert parse_step("double_click @4") == ("click", {"count": 2, "target": "@4"})
    assert parse_step("wait 0.5") == ("wait", {"seconds": 0.5})
    assert parse_step("drag 1,2 3,4") == ("drag", {"from": "1,2", "to": "3,4"})


def test_claude_field_names():
    assert parse_step({"action": "left_click", "coordinate": [5, 6], "text": "shift"}) == (
        "click",
        {"button": "left", "target": [5, 6], "modifiers": "shift"},
    )
    assert parse_step({"action": "left_click_drag", "start_coordinate": [1, 2], "coordinate": [3, 4]}) == (
        "drag",
        {"from": [1, 2], "to": [3, 4]},
    )
    assert parse_step({"action": "scroll", "scroll_direction": "up", "scroll_amount": 2}) == (
        "scroll",
        {"direction": "up", "amount": 2},
    )
    assert parse_step({"action": "key", "text": "Return"}) == ("key", {"keys": "Return"})
    assert parse_step({"action": "wait", "duration": 2}) == ("wait", {"seconds": 2})
    assert parse_step({"action": "right_click"}) == ("click", {"button": "right"})


@pytest.mark.parametrize("bad", [42, "", "fly away", {"nothing": 1}, {"click": 1, "type": "x"}])
def test_invalid(bad):
    with pytest.raises(RpcError):
        parse_step(bad)


def test_explicit_nulls_mean_defaults():
    # Some MCP clients (CrewAI) send every optional field, as null.
    assert parse_step({"action": "click", "target": "@3", "button": None, "count": None, "text": None}) == parse_step(
        {"action": "click", "target": "@3"}
    )
    assert parse_step({"click": "@3", "key": None, "target": None}) == ("click", parse_step("click @3")[1])
    assert parse_step({"action": None, "type": "hi"})[0] == "type"


def test_backslashes_survive_in_string_steps():
    # Windows paths (Wine programs, file dialogs) must not lose their backslashes.
    assert parse_step(r"type C:\Users\agent")[1]["text"] == r"C:\Users\agent"
    assert parse_step(r"type 'C:\Program Files\App'")[1]["text"] == r"C:\Program Files\App"
    assert parse_step(r'fill @4 "D:\data\q3.xlsx"')[1]["text"] == r"D:\data\q3.xlsx"
    assert parse_step("type #1 in the queue")[1]["text"] == "#1 in the queue"  # no shell comments


def test_window_app_names():
    from minion.agent.windows import app_name

    assert app_name("notepad.exe.notepad.exe") == "notepad"  # Wine
    assert app_name("Navigator.firefox-esr") == "firefox-esr"
    assert app_name("libreoffice.libreoffice-writer") == "libreoffice-writer"
    assert app_name("geany") == "geany"
