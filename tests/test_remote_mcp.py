"""MCP over Streamable HTTP (`/mcp` in `minion serve` and `minion share`), and the `share` command's plumbing.

A fake backend stands in for Docker, and no real tunnel is started."""

import json
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from minion import server, share
from minion.errors import MinionError, NotFound
from minion.tools import Toolkit, ToolResult

ACCEPT = "application/json, text/event-stream"


class FakeBackend:
    name = "fake"
    desktops = ("a", "b")

    def list(self, stats=False):
        return []

    def get(self, name):
        if name not in self.desktops:
            raise NotFound(name)
        return SimpleNamespace(name=name, state="running")

    def available(self):
        return True, "fake"


@pytest.fixture()
def fake_backend(monkeypatch):
    be = FakeBackend()
    monkeypatch.setattr("minion.desktop.get_backend", lambda name=None: be)
    monkeypatch.setattr(server, "get_backend", lambda name=None: be)
    monkeypatch.setattr(server, "_toolkits", {})
    return be


def start(**kw):
    httpd, base, token = server.make_server("127.0.0.1", 0, token=kw.pop("token", ""), quiet=True, **kw)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, base, token


@pytest.fixture()
def http(fake_backend):
    httpd, base, token = start()
    yield SimpleNamespace(base=base, token=token, handler=httpd.RequestHandlerClass)
    httpd.shutdown()
    httpd.server_close()


def request(url, body=None, method="POST", headers=None):
    """(status, headers, raw body) for any response, errors included."""
    data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json", "Accept": ACCEPT, **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def events(raw: bytes) -> list[dict]:
    """The JSON-RPC messages of an SSE body."""
    return [json.loads(line[5:]) for line in raw.decode().splitlines() if line.startswith("data:")]


class Client:
    """A minimal Streamable HTTP MCP client."""

    def __init__(self, base, token, query="", headers=None):
        self.url = f"{base}/mcp?token={token}{query}"
        self.headers = dict(headers or {})
        self.sid = None
        self.n = 0

    def post(self, msg, accept=ACCEPT, extra=None):
        hdrs = {**self.headers, "Accept": accept, **(extra or {})}
        if self.sid:
            hdrs["Mcp-Session-Id"] = self.sid
            hdrs.setdefault("MCP-Protocol-Version", "2025-06-18")
        return request(self.url, msg, headers=hdrs)

    def initialize(self, version="2025-06-18"):
        params = {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}
        status, headers, raw = self.post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": params})
        assert status == 200, raw
        self.sid = headers["Mcp-Session-Id"]
        assert self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})[0] == 202
        return json.loads(raw)["result"]

    def rpc(self, method, params=None, accept=ACCEPT):
        """The response message (from JSON or the SSE stream), plus the notifications streamed before it."""
        self.n += 1
        status, headers, raw = self.post(
            {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}, accept=accept
        )
        assert status == 200, raw
        if headers["Content-Type"].startswith("text/event-stream"):
            msgs = events(raw)
            return msgs[-1], msgs[:-1]
        return json.loads(raw), []

    def call(self, name, arguments=None, **kw):
        reply, _ = self.rpc("tools/call", {"name": name, "arguments": arguments or {}}, **kw)
        return reply["result"]


# -- the protocol -----------------------------------------------------------------
def test_initialize_list_and_call_over_json_and_sse(http):
    c = Client(http.base, http.token)
    init = c.initialize()
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "minion"
    assert all(0x21 <= ord(ch) <= 0x7E for ch in c.sid) and len(c.sid) >= 32
    tools, _ = c.rpc("tools/list")
    names = [t["name"] for t in tools["result"]["tools"]]
    assert names == ["desktop", "see", "screenshot", "act", "open", "run", "script", "files", "view"]
    pong, _ = c.rpc("ping", accept="application/json")
    assert pong["result"] == {}

    status, headers, raw = c.post(
        {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {"name": "desktop", "arguments": {"action": "list"}},
        },
        accept="application/json",
    )
    assert status == 200 and headers["Content-Type"] == "application/json"
    assert "No desktops" in json.loads(raw)["result"]["content"][0]["text"]

    status, headers, raw = c.post(
        {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {"name": "desktop", "arguments": {"action": "list"}},
        }
    )
    assert status == 200 and headers["Content-Type"] == "text/event-stream"
    assert headers["Mcp-Session-Id"] == c.sid
    (reply,) = events(raw)
    assert reply["id"] == 51 and "No desktops" in reply["result"]["content"][0]["text"]

    unknown, _ = c.rpc("tools/call", {"name": "bogus"})
    assert unknown["error"]["code"] == -32602 and "Unknown tool: bogus" in unknown["error"]["message"]
    missing, _ = c.rpc("nope/nope")
    assert missing["error"]["code"] == -32601


def test_progress_is_streamed_before_the_result(http, monkeypatch):
    def slow_call(self, name, arguments=None, progress=None):
        progress("Downloading image 1/2")
        progress("Downloading image 2/2")
        return ToolResult([{"type": "text", "text": "Ready: browser-1"}])

    monkeypatch.setattr(Toolkit, "call", slow_call)
    c = Client(http.base, http.token)
    c.initialize()
    reply, notes = c.rpc("tools/call", {"name": "desktop", "arguments": {}, "_meta": {"progressToken": "p1"}})
    assert [n["params"]["message"] for n in notes] == ["Downloading image 1/2", "Downloading image 2/2"]
    assert all(n["method"] == "notifications/progress" and n["params"]["progressToken"] == "p1" for n in notes)
    assert reply["result"]["content"][0]["text"] == "Ready: browser-1"


def test_keep_alive_comments_while_a_tool_works(http, monkeypatch):
    def slow_call(self, name, arguments=None, progress=None):
        time.sleep(0.4)
        return ToolResult([{"type": "text", "text": "done"}])

    monkeypatch.setattr(Toolkit, "call", slow_call)
    monkeypatch.setattr(server, "SSE_KEEPALIVE", 0.05)
    c = Client(http.base, http.token)
    c.initialize()
    status, _, raw = c.post({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "see"}})
    assert status == 200 and b": keep-alive\n\n" in raw  # SSE comments: clients ignore them, proxies see traffic
    assert events(raw)[-1]["result"]["content"][0]["text"] == "done"


def test_a_cancelled_call_gets_no_result(http, monkeypatch):
    started = threading.Event()

    def slow_call(self, name, arguments=None, progress=None):
        started.set()
        time.sleep(0.5)
        return ToolResult([{"type": "text", "text": "too late"}])

    monkeypatch.setattr(Toolkit, "call", slow_call)
    c = Client(http.base, http.token)
    c.initialize()
    out = {}
    t = threading.Thread(
        target=lambda: out.update(
            r=c.post({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "see"}})
        )
    )
    t.start()
    assert started.wait(5)
    cancel = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7, "reason": "user"}}
    assert c.post(cancel)[0] == 202
    t.join(10)
    status, _, raw = out["r"]
    assert status == 200 and events(raw) == []  # the stream ends without a response


def test_transport_errors(http):
    c = Client(http.base, http.token)
    url = c.url
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    status, _, raw = request(url, ping)  # no session
    assert status == 400 and json.loads(raw)["error"]["code"] == -32600
    status, _, _ = request(url, ping, headers={"Mcp-Session-Id": "f" * 32})
    assert status == 404  # unknown or ended session: the client must initialize again
    c.initialize()
    assert c.post(ping, extra={"MCP-Protocol-Version": "2026-07-28"})[0] == 400  # a version we don't speak
    assert c.post(ping, extra={"MCP-Protocol-Version": "2025-03-26"})[0] == 200
    status, headers, _ = request(url, method="GET", headers={"Accept": "text/event-stream"})
    assert status == 405 and "POST" in headers["Allow"]  # no server-initiated stream
    assert c.post([ping])[0] == 400  # no batches
    status, _, raw = request(url, b"{nope", headers={"Mcp-Session-Id": c.sid})
    assert status == 400 and json.loads(raw)["error"]["code"] == -32700
    status, _, _ = request(url, b"{}", headers={"Content-Type": "text/plain", "Mcp-Session-Id": c.sid})
    assert status == 415
    assert c.post({"jsonrpc": "2.0", "id": 5, "result": {}})[0] == 202  # a response to us: accepted, ignored
    status, _, _ = request(f"{http.base}/MCP?token={http.token}", ping, headers={"Mcp-Session-Id": c.sid})
    assert status == 200  # some clients change the path's case
    assert request(f"{http.base}/.well-known/oauth-protected-resource/mcp", method="GET")[0] == 404


def test_the_token_is_required(http):
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    status, headers, _ = request(f"{http.base}/mcp", init)
    assert status == 401 and headers["WWW-Authenticate"].startswith("Bearer")
    assert request(f"{http.base}/mcp", init, headers={"Authorization": "Bearer wrong"})[0] == 401
    assert request(f"{http.base}/mcp?token=wrong", init)[0] == 401
    cookie = {"Cookie": f"minion_token={http.token}"}  # the dashboard's cookie is not a credential for /mcp
    assert request(f"{http.base}/mcp", init, headers=cookie)[0] == 401
    assert request(f"{http.base}/mcp", init, headers={"Authorization": f"Bearer {http.token}"})[0] == 200
    assert request(f"{http.base}/mcp?token={http.token}", init)[0] == 200


def test_each_session_has_its_own_current_desktop(http, monkeypatch):
    def t_see(self, args, progress):
        return [{"type": "text", "text": f"screen of {self.desk(args).name}"}]

    monkeypatch.setattr(Toolkit, "t_see", t_see)
    one, two = Client(http.base, http.token), Client(http.base, http.token)
    one.initialize()
    two.initialize()
    assert one.sid != two.sid
    assert one.call("see", {"desktop": "a"})["content"][0]["text"] == "screen of a"
    assert one.call("see")["content"][0]["text"] == "screen of a"  # now this session's current desktop
    other = two.call("see")
    assert other["isError"] and "No desktop yet" in other["content"][0]["text"]
    assert two.call("see", {"desktop": "b"})["content"][0]["text"] == "screen of b"
    assert one.call("see")["content"][0]["text"] == "screen of a"

    key = f"mcp:{one.sid}"
    assert key in server._toolkits
    status, _, _ = request(one.url, method="DELETE", headers={"Mcp-Session-Id": one.sid})
    assert status == 204 and key not in server._toolkits
    assert one.post({"jsonrpc": "2.0", "id": 99, "method": "ping"})[0] == 404
    assert request(one.url, method="DELETE", headers={"Mcp-Session-Id": one.sid})[0] == 404
    assert request(one.url, method="DELETE")[0] == 400
    assert two.call("see")["content"][0]["text"] == "screen of b"  # the other session is untouched


def test_old_sessions_make_room(http, monkeypatch):
    monkeypatch.setattr(server, "MCP_SESSIONS_MAX", 2)
    clients = [Client(http.base, http.token) for _ in range(3)]
    for c in clients:
        c.initialize()
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert [c.post(ping)[0] for c in clients] == [404, 200, 200]  # the least recently used one ended


def test_compact_and_text_only_urls(http):
    compact = Client(http.base, http.token, "&compact=1")
    info = compact.initialize()
    assert "see()" not in info["instructions"]
    assert [t["name"] for t in compact.rpc("tools/list")[0]["result"]["tools"]] == ["computer"]
    text = Client(http.base, http.token, "&images=0")
    text.initialize()
    assert "screenshot" not in [t["name"] for t in text.rpc("tools/list")[0]["result"]["tools"]]


# -- browser protections ---------------------------------------------------------------
def test_origin_rules(fake_backend, monkeypatch):
    httpd, base, token = start(allowed_hosts=["demo.trycloudflare.com"])
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    url = f"{base}/mcp?token={token}"
    try:
        # Loopback address: only local pages and known chat apps' backends (claude.ai sends its Origin).
        assert request(url, init, headers={"Origin": "https://evil.example"})[0] == 403
        assert request(url, init, headers={"Origin": "null"})[0] == 403
        assert request(url, init, headers={"Origin": "http://localhost:6274"})[0] == 200
        assert request(url, init, headers={"Origin": "https://claude.ai"})[0] == 200
        assert request(url, init)[0] == 200  # server-to-server clients send none
        monkeypatch.setenv("MINION_ALLOWED_ORIGINS", "https://my-app.example")
        assert request(url, init, headers={"Origin": "https://my-app.example"})[0] == 200
        # A public name (tunnel, proxy): the URL itself is public, the token is what counts.
        tunnel = {"Host": "demo.trycloudflare.com", "Origin": "https://some-web-client.example"}
        assert request(url, init, headers=tunnel)[0] == 200
        status, _, raw = request(f"{base}/mcp", init, headers=tunnel)
        assert status == 401
        # DNS rebinding: a Host this server doesn't answer to is refused before anything else.
        assert request(url, init, headers={"Host": "evil.example:4747", "Origin": "http://evil.example:4747"})[0] == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_allowed_hosts_from_the_environment(fake_backend, monkeypatch):
    monkeypatch.setenv("MINION_ALLOWED_HOSTS", "minion.example.com, other.example")
    httpd, base, token = start()
    try:
        health = f"{base}/api/health?token={token}"
        assert request(health, method="GET", headers={"Host": "minion.example.com"})[0] == 200
        assert request(health, method="GET", headers={"Host": "nope.example.com"})[0] == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


# -- what a shared server hands out ---------------------------------------------------
def test_host_files_can_be_turned_off(http, monkeypatch):
    http.handler.host_files = False
    c = Client(http.base, http.token)
    c.initialize()
    files = next(t for t in c.rpc("tools/list")[0]["result"]["tools"] if t["name"] == "files")
    assert files["inputSchema"]["properties"]["action"]["enum"] == ["read", "write"]
    assert "local_path" not in files["inputSchema"]["properties"]
    monkeypatch.setattr(Toolkit, "desk", lambda self, args: SimpleNamespace(name="a"))
    refused = c.call("files", {"action": "upload", "path": "~/x", "local_path": "secret.txt"})
    assert refused["isError"] and "turned off" in refused["content"][0]["text"]
    status, _, raw = request(f"{http.base}/api/tools?format=openai&token={http.token}", method="GET")
    fn = next(d["function"] for d in json.loads(raw) if d["function"]["name"] == "files")
    assert fn["parameters"]["properties"]["action"]["enum"] == ["read", "write"]


def test_links_point_where_the_client_reached_us(http):
    c = Client(http.base, http.token, headers={"Host": "demo.trycloudflare.com", "X-Forwarded-Proto": "https"})
    http.handler.extra_hosts = frozenset({"demo.trycloudflare.com"})
    c.initialize()
    tk = server._toolkits[f"mcp:{c.sid}"]
    assert tk.view_url("office-1") == f"https://demo.trycloudflare.com/view/office-1?token={http.token}"
    http.handler.public_url = "https://fixed.example"
    d = Client(http.base, http.token)
    d.initialize()
    assert server._toolkits[f"mcp:{d.sid}"].view_url("x").startswith("https://fixed.example/view/x?token=")


def test_hand_off_survives_a_client_timeout():
    name = "handoff-test"
    assert server._wait_for_human(name, "Please sign in", 0.05) is None  # the agent's client gave up
    assert server._handoffs[name]["message"] == "Please sign in"  # still on the human's screen
    with server._handoff_lock:
        h = server._handoffs[name]
        h.update(done=True, done_at=time.time(), note="signed in")
        h["event"].set()
    assert server._wait_for_human(name, "Please sign in", 5) == "signed in"  # asked again: answered at once
    assert name not in server._handoffs


def test_capped_hand_off_tells_the_agent_to_ask_again(fake_backend, monkeypatch):
    tk = server.ServedToolkit(wait_cap=0.05, token="T")
    tk.base_url = "https://demo.example"
    monkeypatch.setattr(tk, "desk", lambda args: SimpleNamespace(name="cap-test"))
    text = tk.t_view({"message": "Solve the CAPTCHA", "timeout": 600}, lambda line: None)[0]["text"]
    assert "Call view again" in text and "https://demo.example/view/cap-test?token=T" in text
    server._handoffs.pop("cap-test", None)


def test_tokens_stay_out_of_the_log(fake_backend, capsys):
    httpd, base, token = server.make_server("127.0.0.1", 0, token="", quiet=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        request(f"{base}/api/health?token={token}", method="GET")
        time.sleep(0.1)
    finally:
        httpd.shutdown()
        httpd.server_close()
    err = capsys.readouterr().err
    assert "/api/health?token=" in err and token not in err


# -- minion share -----------------------------------------------------------------------
def test_tunnel_plans():
    p = share.tunnel_plan(4748, cloudflared="/usr/local/bin/cloudflared")
    assert p.argv[:3] == ["/usr/local/bin/cloudflared", "tunnel", "--no-autoupdate"]
    assert p.argv[-2:] == ["--url", "http://127.0.0.1:4748"]
    assert p.via == "cloudflared" and p.container is None
    assert p.argv[p.argv.index("--metrics") + 1] == "127.0.0.1:0"  # not on every interface
    p = share.tunnel_plan(4748, engine="/usr/bin/docker", name="minion-share-x")
    assert p.argv[:7] == ["/usr/bin/docker", "run", "--rm", "--name", "minion-share-x", "--label", "dev.minion.share=1"]
    assert "--network" in p.argv and p.argv[p.argv.index("--network") + 1] == "host"
    assert p.origin == "http://127.0.0.1:4748" and p.container == "minion-share-x" and share.IMAGE in p.argv
    p = share.tunnel_plan(4748, engine="docker", engine_in_vm=True)  # Docker Desktop
    assert "--network" not in p.argv and p.origin == "http://host.docker.internal:4748"
    p = share.tunnel_plan(4748, engine="/opt/podman/bin/podman", engine_in_vm=True)
    assert p.origin == "http://host.containers.internal:4748" and p.via == "podman"
    with pytest.raises(MinionError, match="cloudflared or Docker"):
        share.tunnel_plan(4748)


def test_tunnel_url_in_cloudflared_output():
    line = "2026-10-14T10:50:59Z INF |  https://clark-cookies-metadata-earnings.trycloudflare.com                 |"
    assert share.find_tunnel_url(line) == "https://clark-cookies-metadata-earnings.trycloudflare.com"
    assert share.find_tunnel_url("INF Requesting new quick Tunnel on trycloudflare.com...") is None
    assert share.find_tunnel_url("https://api.trycloudflare.com/tunnel failed") is None


def test_share_urls_and_tokens():
    u = share.share_urls("https://x.trycloudflare.com", "tok")
    assert u["mcp_url"] == "https://x.trycloudflare.com/mcp?token=tok"
    assert u["mcp_endpoint"] == "https://x.trycloudflare.com/mcp" and u["authorization"] == "Bearer tok"
    assert u["dashboard_url"] == "https://x.trycloudflare.com/?token=tok"
    u = share.share_urls("https://x.ts.net", "tok", compact=True, images=False)
    assert u["mcp_url"] == "https://x.ts.net/mcp?token=tok&compact=1&images=0"
    assert u["mcp_endpoint"] == "https://x.ts.net/mcp?compact=1&images=0"
    assert share.check_token("A" * 24) == "A" * 24
    for bad in ("short", "has spaces in it, quite a few of them", "x" * 23, "ä" * 30):
        with pytest.raises(MinionError):
            share.check_token(bad)
    assert share.funnel_command(4748) == "tailscale funnel 4748"


def test_tailscale_name(monkeypatch):
    status = {"BackendState": "Running", "Self": {"DNSName": "laptop.tail1234.ts.net."}}
    monkeypatch.setattr(share.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(status)))
    assert share.tailscale_name() == "laptop.tail1234.ts.net"
    status["BackendState"] = "Stopped"
    with pytest.raises(MinionError, match="tailscale up"):
        share.tailscale_name()


def test_activity_lines():
    assert share.describe_call("desktop", {"action": "create", "profile": "office"}) == "desktop create"
    assert share.describe_call("act", {"actions": [{"action": "click"}, {"action": "type"}]}) == "act click, type"
    assert share.describe_call("computer", {"command": "click @12"}) == "computer click @12"
    assert share.describe_call("run", {"command": "x" * 100}).endswith("…")
    assert share.describe_call("see", None) == "see"


def test_share_command_with_a_fake_tunnel(fake_backend, monkeypatch, capsys):
    """`minion share` from start to stop, with cloudflared replaced: the fake tunnel calls the server the
    way the internet would (its public Host name), then stops."""
    seen = {}

    class FakeTunnel:
        def __init__(self, plan):
            self.plan, self.origin_down, self.n = plan, False, 0

        def wait_url(self, timeout):
            return "https://fake-words.trycloudflare.com"

        def alive(self):  # the first check finds the server set up, then the tunnel "dies"
            self.n += 1
            if self.n == 1:
                hdrs = {"Host": "fake-words.trycloudflare.com", "Origin": "https://chatgpt.com"}
                c = Client(self.plan.origin, seen["token"], headers=hdrs)
                seen["instructions"] = c.initialize()["instructions"]
                seen["tools"] = c.rpc("tools/list")[0]["result"]["tools"]
                seen["upload"] = c.call("files", {"action": "upload", "path": "~", "local_path": "x"})
                seen["evil_host"] = request(
                    f"{self.plan.origin}/api/health?token={seen['token']}", method="GET", headers={"Host": "x.example"}
                )[0]
            return self.n < 3

        def log_tail(self, n=12):
            return "    (fake cloudflared stopped)"

        def stop(self):
            seen["stopped"] = True

    monkeypatch.setattr(share, "Tunnel", FakeTunnel)
    monkeypatch.setattr(share, "check_public", lambda url, token, tunnel=None, timeout=45: (True, ""))
    monkeypatch.setattr(share.shutil, "which", lambda name: "/usr/bin/cloudflared" if name == "cloudflared" else None)
    monkeypatch.setattr(share, "_images_hint", lambda: None)
    monkeypatch.setattr(share.secrets, "token_urlsafe", lambda n=32: seen.setdefault("token", "T" * 43))
    monkeypatch.setattr(Toolkit, "desk", lambda self, args: SimpleNamespace(name="a"))
    monkeypatch.delenv("MINION_MCP_CREATE_WAIT", raising=False)
    monkeypatch.setenv("MINION_IDLE_FREEZE", "0")
    from minion import cli

    args = cli.build_parser().parse_args(["share", "--port", "0"])
    with pytest.raises(MinionError, match="the tunnel stopped"):
        share.run(args)
    out = capsys.readouterr().out
    assert "https://fake-words.trycloudflare.com/mcp?token=" + "T" * 43 in out
    assert "Anyone with this URL" in out and "Ctrl+C" in out
    assert "files upload  (127.0.0.1)" in out  # each tool call is logged in the terminal, with the caller
    assert seen["stopped"]
    files = next(t for t in seen["tools"] if t["name"] == "files")
    assert files["inputSchema"]["properties"]["action"]["enum"] == ["read", "write"]  # host files off by default
    assert seen["upload"]["isError"] and seen["evil_host"] == 403
    import os

    assert os.environ["MINION_MCP_CREATE_WAIT"] == share.CHAT_WAIT  # replies come before chat apps time out
