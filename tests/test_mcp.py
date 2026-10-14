import io
import json

from minion import mcp


class FakeBackend:
    name = "fake"

    def list(self, stats=False):
        return []

    def get(self, name):
        from minion.errors import NotFound

        raise NotFound(name)


def run_session(monkeypatch, messages, compact=False):
    import minion.desktop as desktop_mod

    monkeypatch.setattr(desktop_mod, "get_backend", lambda name=None: FakeBackend())
    out = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"))
    monkeypatch.setattr("sys.stdout", out)
    mcp.main(idle_freeze=0, compact=compact)
    import time

    time.sleep(0.3)  # tools/call replies come from worker threads
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def test_initialize_and_list(monkeypatch):
    replies = run_session(
        monkeypatch,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "nope"},
        ],
    )
    by_id = {r["id"]: r for r in replies}
    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["capabilities"] == {"tools": {"listChanged": False}}
    assert "see()" in init["instructions"]
    names = [t["name"] for t in by_id[2]["result"]["tools"]]
    assert names == ["desktop", "see", "screenshot", "act", "open", "run", "script", "files", "view"]
    for t in by_id[2]["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object" and t["description"]
    assert by_id[3]["result"] == {}
    assert by_id[4]["error"]["code"] == -32601


def test_unknown_protocol_version_falls_back(monkeypatch):
    replies = run_session(
        monkeypatch,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}},
        ],
    )
    assert replies[0]["result"]["protocolVersion"] == mcp.PROTOCOL_VERSIONS[0]


def test_tool_errors_are_reported_not_raised(monkeypatch):
    replies = run_session(
        monkeypatch,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "see", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "bogus", "arguments": {}}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "desktop", "arguments": {"action": "list"}},
            },
        ],
    )
    by_id = {r["id"]: r for r in replies}
    assert by_id[1]["result"]["isError"] and "No desktop yet" in by_id[1]["result"]["content"][0]["text"]
    assert by_id[2]["result"]["isError"]
    assert not by_id[3]["result"]["isError"] and "No desktops" in by_id[3]["result"]["content"][0]["text"]


def test_compact_mode_has_one_tool(monkeypatch):
    replies = run_session(
        monkeypatch,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "computer", "arguments": {"command": "list"}},
            },
        ],
        compact=True,
    )
    by_id = {r["id"]: r for r in replies}
    assert [t["name"] for t in by_id[1]["result"]["tools"]] == ["computer"]
    assert "No desktops" in by_id[2]["result"]["content"][0]["text"]


def test_malformed_messages_do_not_kill_the_server(monkeypatch):
    replies = run_session(monkeypatch, ["hello", [1, 2], {"jsonrpc": "2.0", "id": 9, "method": "ping"}])
    assert any(r.get("id") == 9 and r.get("result") == {} for r in replies)
    assert sum(1 for r in replies if r.get("error", {}).get("code") == -32600) == 3
