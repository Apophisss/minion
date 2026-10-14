import json

import pytest

from minion.errors import MinionError
from minion.tools import TOOLS, Toolkit, ToolResult, openapi


class FakeBackend:
    name = "fake"

    def list(self, stats=False):
        return []


@pytest.fixture()
def tk():
    return _toolkit()


def _toolkit():
    t = Toolkit.__new__(Toolkit)
    t.backend = FakeBackend()
    t.current = None
    t.desktops = {}
    t._pending = {}
    import threading

    t._lock = threading.Lock()
    t.in_process_viewer = None
    return t


def test_definitions_in_every_format(tk):
    names = [t["name"] for t in TOOLS]
    assert [t["name"] for t in tk.definitions("mcp")] == names
    assert all(
        t["type"] == "function" and t["function"]["parameters"]["type"] == "object" for t in tk.definitions("openai")
    )
    assert [t["name"] for t in tk.definitions("openai-responses")] == names
    assert all("input_schema" in t for t in tk.definitions("anthropic"))
    gem = tk.definitions("gemini")
    assert all(set(t) == {"name", "description", "parameters"} for t in gem)
    assert "annotations" not in json.dumps(gem)
    assert [t["name"] for t in tk.definitions("mcp", compact=True)] == ["computer"]
    with pytest.raises(MinionError):
        tk.definitions("cobol")


def test_definitions_are_independent_copies(tk):
    a = tk.definitions("openai")
    a[0]["function"]["parameters"]["properties"].clear()
    assert tk.definitions("openai")[0]["function"]["parameters"]["properties"]


def test_tool_result_conversions():
    r = ToolResult([{"type": "text", "text": "hi"}, {"type": "image", "data": "QUJD", "mimeType": "image/png"}])
    assert r.text == "hi" and r.images == [("image/png", "QUJD")]
    oa = r.to_openai("call_1")
    assert oa[0] == {"role": "tool", "tool_call_id": "call_1", "content": "hi"}
    assert oa[1]["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    an = r.to_anthropic("toolu_1")
    assert an["content"][1]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}
    assert "is_error" not in an
    rs = r.to_openai_responses("c1")
    assert rs[0]["type"] == "function_call_output" and rs[1]["content"][0]["type"] == "input_image"
    gm = r.to_gemini("see")
    assert gm[0]["function_response"]["name"] == "see" and gm[1]["inline_data"]["mime_type"] == "image/png"
    assert ToolResult([{"type": "text", "text": "x"}], True).to_anthropic("t")["is_error"]


def test_errors_are_results_not_exceptions(tk):
    r = tk.call("nope", {})
    assert r.is_error and "unknown tool" in r.text
    r = tk.call("see", {})
    assert r.is_error and "No desktop yet" in r.text
    r = tk.call("desktop", '{"action": "list"}')  # JSON string arguments are accepted
    assert not r.is_error and "No desktops" in r.text


def test_computer_command_parsing(tk):
    calls = []
    tk.t_act = lambda a, p: calls.append(("act", a)) or []
    tk.t_desktop = lambda a, p: calls.append(("desktop", a)) or []
    tk.t_run = lambda a, p: calls.append(("run", a)) or []
    tk.t_see = lambda a, p: calls.append(("see", a)) or []
    for cmd in [
        "click 640 400",
        "click Sign in",
        "type 'hello world'",
        "key ctrl+s Return",
        "create office -n 2",
        "run ls -la | head",
        "see --changes",
        "fill @4 Ada Lovelace",
    ]:
        assert not tk.call("computer", {"command": cmd}).is_error, cmd
    assert calls[0] == ("act", {"actions": [{"action": "click", "target": "640,400"}]})
    assert calls[1][1]["actions"][0]["target"] == "Sign in"
    assert calls[2][1]["actions"][0]["text"] == "hello world"
    assert [a["keys"] for a in calls[3][1]["actions"]] == ["ctrl+s", "Return"]
    assert calls[4] == ("desktop", {"action": "create", "profile": "office", "count": 2})
    assert calls[5] == ("run", {"command": "ls -la | head"})
    assert calls[6][1]["changes"] is True
    assert calls[7][1]["actions"][0] == {"action": "fill", "target": "@4", "text": "Ada Lovelace"}
    assert tk.call("computer", {"command": "dance"}).is_error


def test_openapi_lists_every_tool():
    spec = openapi("http://127.0.0.1:4747")
    assert spec["openapi"].startswith("3.1")
    assert set(spec["paths"]) == {f"/api/tools/{t['name']}" for t in TOOLS} | {"/api/tools/computer"}


def test_functions_for_frameworks(tk):
    fns = tk.functions()
    assert set(fns) == {t["name"] for t in TOOLS}
    assert "accessibility" in fns["see"].__doc__
    assert "No desktop yet" in fns["see"]()
