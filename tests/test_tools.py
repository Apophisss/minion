import json
from types import SimpleNamespace

import pytest

from minion.errors import MinionError
from minion.tools import TOOLS, ToolError, Toolkit, ToolResult, openapi


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
    t.files_root = None
    t.images = True
    t._local = threading.local()
    return t


def test_definitions_in_every_format(tk):
    names = [t["name"] for t in TOOLS]
    assert [t["name"] for t in tk.definitions("mcp")] == names
    assert all(
        t["type"] == "function" and t["function"]["parameters"]["type"] == "object" for t in tk.definitions("openai")
    )
    assert [t["name"] for t in tk.definitions("openai-responses")] == names
    assert all(t["strict"] is False for t in tk.definitions("openai-responses"))  # schemas have optional fields
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
    tk.call("computer", {"command": r"type C:\Users\agent"})
    assert calls[-1][1]["actions"][0]["text"] == r"C:\Users\agent"
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


def _shot_toolkit():
    t = _toolkit()
    t.t_see = lambda a, p: [{"type": "text", "text": f"saw {a.get('window', 'all')}"}]
    t.t_screenshot = lambda a, p: [{"type": "image", "data": "QUJD", "mimeType": "image/png"}]
    return t


def test_run_calls_openai_keeps_tool_messages_together():
    class Fn:  # SDK-style objects work as well as dicts
        name, arguments = "see", '{"window": "Editor"}'

    class Call:
        id, function = "c1", Fn()

    tk = _shot_toolkit()
    msgs = tk.run_calls([{"id": "c0", "function": {"name": "screenshot", "arguments": "{}"}}, Call()])
    assert [m["role"] for m in msgs] == ["tool", "tool", "user"]  # images after *all* tool messages
    assert msgs[1] == {"role": "tool", "tool_call_id": "c1", "content": "saw Editor"}
    assert msgs[2]["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert tk.run_calls([]) == []


def test_run_calls_anthropic_responses_gemini():
    tk = _shot_toolkit()
    blocks = [
        {"type": "text", "text": "Let me look."},
        {"type": "tool_use", "id": "t1", "name": "see", "input": {}},
        {"type": "tool_use", "id": "t2", "name": "screenshot", "input": {}},
    ]
    (msg,) = tk.run_calls(blocks, "anthropic")
    assert msg["role"] == "user" and [b["tool_use_id"] for b in msg["content"]] == ["t1", "t2"]
    assert msg["content"][1]["content"][0]["type"] == "image"
    assert tk.run_calls([{"type": "text", "text": "done"}], "anthropic") == []

    items = tk.run_calls(
        [{"type": "reasoning"}, {"type": "function_call", "call_id": "r1", "name": "screenshot", "arguments": "{}"}],
        "openai-responses",
    )
    assert items[0]["type"] == "function_call_output" and items[0]["call_id"] == "r1"
    assert items[1]["content"][0]["type"] == "input_image"

    parts = tk.run_calls(
        [{"text": "thinking"}, {"function_call": {"name": "see", "args": {"window": "x"}, "id": "g1"}}], "gemini"
    )
    assert parts == [
        {"function_response": {"name": "see", "response": {"result": "saw x", "error": False}, "id": "g1"}}
    ]
    with pytest.raises(MinionError):
        tk.run_calls([{}], "cobol")


def test_files_root_confines_host_paths(tmp_path):
    tk = _toolkit()
    assert tk._host_path("~/x.pdf").endswith("/x.pdf")  # no root: any path (the local MCP/Python default)
    root = (tmp_path / "files").resolve()
    tk.files_root = root
    assert tk._host_path("report.pdf") == str(root / "report.pdf") and root.is_dir()
    assert tk._host_path(".") == str(root)
    (root / "escape").symlink_to("/etc")
    for bad in ("/etc/passwd", "../secret", "~/.ssh/id_rsa", "escape/passwd"):
        with pytest.raises(ToolError):
            tk._host_path(bad)


def test_http_toolkits_get_a_files_root(tmp_path, monkeypatch):
    from minion import server

    monkeypatch.setenv("MINION_HOME", str(tmp_path))
    monkeypatch.delenv("MINION_FILES_ROOT", raising=False)
    monkeypatch.setattr(server, "_toolkits", {})
    monkeypatch.setattr("minion.tools._backend", lambda b: FakeBackend())
    assert server._toolkit("agent-1").files_root == (tmp_path / "data" / "files").resolve()


def test_text_only_clients_and_nulls():
    tk = _shot_toolkit()
    tk.images = False
    assert "screenshot" not in [t["name"] for t in tk.definitions("anthropic")]
    r = tk.call("screenshot", {})
    assert not r.images and "1 image(s) left out" in r.text and not r.is_error
    seen = []
    tk.t_see = lambda a, p: seen.append(a) or [{"type": "text", "text": "ok"}]
    tk.call("see", {"window": None, "ocr": None, "changes": True})
    assert seen == [{"changes": True}]  # nulls dropped
    assert not tk.call("see", "[1, 2]").is_error  # non-object JSON arguments are ignored


def test_fallback_desktop_is_named_in_the_result(monkeypatch):
    tk = _toolkit()
    tk.backend.get = lambda name: SimpleNamespace(name=name)
    monkeypatch.setattr("minion.tools.Desktop.attach", lambda name, backend: SimpleNamespace(name="other-agent-1"))
    tk.t_see = lambda a, p: (tk.desk(a), [{"type": "text", "text": "screen"}])[1]
    r = tk.call("see", {})
    assert "Used desktop 'other-agent-1'" in r.text
    assert "Used desktop" not in tk.call("see", {}).text  # now it is this session's current desktop
