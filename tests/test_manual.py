"""People working at a desktop by hand: files in and out of the live view, the clipboard, saved sign-ins."""

import io
import json
import os
import sys
import threading
import types
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from minion import cli, server
from minion.agent.server import Agent as AgentServer
from minion.agent.server import RpcError
from minion.backends import DesktopInfo, Login, check_login
from minion.desktop import Desktop
from minion.errors import MinionError, NotFound
from minion.tools import Toolkit


# -- a desktop whose files live in a temporary folder ----------------------------------------------
class FakeDesk:
    def __init__(self, root: Path):
        self.name = "demo"
        self.root = root  # stands for /home/agent
        self.saved = []
        self.clip = ""

    def _local(self, path: str) -> Path:
        path = path.replace("~", str(self.root), 1) if path.startswith("~") else path
        return Path(path)

    def ls(self, path="~", hidden=False, limit=1000):
        p = self._local(path)
        if not p.is_dir():
            raise MinionError(f"no such folder in the desktop: {path}")
        entries = [
            {"name": e.name, "dir": e.is_dir(), "size": None if e.is_dir() else e.stat().st_size, "modified": 1.0}
            for e in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            if hidden or not e.name.startswith(".")
        ]
        # (a desktop's paths are always POSIX ones, whatever the host runs)
        return {"path": p.as_posix(), "home": self.root.as_posix(), "entries": entries[:limit], "total": len(entries)}

    def download(self, src, dst="."):
        p = self._local(src)
        if not p.exists():
            raise NotFound(f"no such file in the desktop: {src}")
        target = Path(dst) / p.name
        if p.is_dir():
            import shutil

            shutil.copytree(p, target)
        else:
            target.write_bytes(p.read_bytes())
        return target

    def upload(self, src, dst="~/"):
        target = self._local(dst.rstrip("/")) / Path(src).name
        target.write_bytes(Path(src).read_bytes())
        return dst

    def save_login(self, login, site=""):
        check_login(login)
        self.saved.append((login, site))
        return Login(login, "browser", f"minion-login:{login}", site)

    def call(self, method, params=None, timeout=120.0):
        assert method == "clipboard"
        if params and "text" in params:
            self.clip = params["text"]
            return {"ok": True}
        return {"text": self.clip}


class NoBackend:
    name = "fake"

    def list(self, stats=False):
        return []


@pytest.fixture()
def http(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Downloads" / "report.pdf").write_bytes(b"%PDF-1.4 hello")
    (home / "Documents" / "notes").mkdir(parents=True)
    (home / "Documents" / "notes" / "a.txt").write_text("alpha")
    desk = FakeDesk(home)
    monkeypatch.setattr(server, "get_backend", lambda name=None: NoBackend())
    monkeypatch.setattr(server, "_desk", lambda name: desk)
    httpd, base, token = server.make_server("127.0.0.1", 0, token="", quiet=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(base=base, token=token, desk=desk, home=home, handler=httpd.RequestHandlerClass)
    httpd.shutdown()
    httpd.server_close()
    server._handoffs.clear()  # (the server's state, shared by every test)


def request(h, method, path, body=None, headers=None):
    hdr = {"Authorization": f"Bearer {h.token}", **(headers or {})}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        hdr.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(h.base + path, data=body, method=method, headers=hdr)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.headers, r.read()


def test_files_lists_a_folder_with_home_as_tilde(http):
    code, _, body = request(http, "GET", "/api/desktops/demo/files?path=~/Documents")
    data = json.loads(body)
    assert code == 200 and data["shown"] == "~/Documents"
    assert [e["name"] for e in data["entries"]] == ["notes"] and data["entries"][0]["dir"]


def test_download_a_file_and_a_folder_as_zip(http):
    code, headers, body = request(http, "GET", "/api/desktops/demo/download?path=~/Downloads/report.pdf")
    assert code == 200 and body == b"%PDF-1.4 hello"
    assert headers["Content-Type"] == "application/pdf"
    assert 'attachment; filename="report.pdf"' in headers["Content-Disposition"]
    code, headers, body = request(http, "GET", "/api/desktops/demo/download?path=~/Documents/notes")
    assert "notes.zip" in headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        assert z.read("notes/a.txt") == b"alpha"
    with pytest.raises(urllib.error.HTTPError) as e:
        request(http, "GET", "/api/desktops/demo/download?path=~/missing.txt")
    assert e.value.code == 404


def test_upload_puts_the_file_in_the_folder_under_a_free_name(http):
    up = "/api/desktops/demo/upload?path=~/Downloads&name=report.pdf"
    code, _, body = request(
        http, "POST", up, b"new bytes", {"X-Minion": "1", "Content-Type": "application/octet-stream"}
    )
    assert code == 201 and json.loads(body)["path"] == "~/Downloads/report (1).pdf"  # report.pdf was there
    assert (http.home / "Downloads" / "report (1).pdf").read_bytes() == b"new bytes"
    assert (http.home / "Downloads" / "report.pdf").read_bytes() == b"%PDF-1.4 hello"
    code, _, body = request(http, "POST", "/api/desktops/demo/upload?path=~&name=../../etc/x", b"z", {"X-Minion": "1"})
    assert json.loads(body)["path"] == "~/_.._etc_x"  # no way out of the folder


def test_upload_needs_the_custom_header_from_a_page(http):
    req = urllib.request.Request(  # what a form on another site could send: the cookie, no header, no JSON
        http.base + "/api/desktops/demo/upload?path=~&name=x",
        data=b"x",
        method="POST",
        headers={"Content-Type": "text/plain", "Origin": "https://evil.example"},
    )
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 403


def test_a_file_uploaded_during_a_handoff_is_in_the_agents_note(http):
    path = "/api/desktops/demo/handoff"
    request(http, "POST", path, {"message": "Please attach the contract"})
    request(http, "POST", "/api/desktops/demo/upload?path=~/Downloads&name=contract.pdf", b"c", {"X-Minion": "1"})
    request(http, "POST", path, {"note": "done"})
    _, _, body = request(http, "GET", path)
    assert json.loads(body)["note"] == "done (uploaded ~/Downloads/contract.pdf)"


def test_clipboard_comes_out_whole(http):
    http.desk.clip = "x" * 100_000  # more than an agent's reply holds
    _, _, body = request(http, "POST", "/api/desktops/demo/clipboard", {})
    assert len(json.loads(body)["text"]) == 100_000


def test_save_sign_in_from_the_live_view(http):
    code, _, body = request(http, "POST", "/api/desktops/demo/login", {"name": "github", "site": "github.com"})
    assert code == 201 and json.loads(body)["name"] == "github" and http.desk.saved == [("github", "github.com")]
    with pytest.raises(urllib.error.HTTPError) as e:
        request(http, "POST", "/api/desktops/demo/login", {"name": "Bad Name"})
    assert e.value.code == 400


def test_a_shared_server_has_no_saved_sign_ins(http):
    http.handler.host_files = False  # `minion share` without --files
    for method, path, body in (
        ("POST", "/api/desktops/demo/login", {"name": "github"}),
        ("GET", "/api/logins", None),
        ("POST", "/api/desktops", {"login": "github"}),
    ):
        with pytest.raises(urllib.error.HTTPError) as e:
            request(http, method, path, body)
        assert e.value.code == 403 and "sign-ins are off" in json.loads(e.value.read())["error"]
    assert http.desk.saved == []


def test_names_for_files_from_a_browser():
    assert server._safe_name("../a/b\\c.txt") == "_a_b_c.txt"
    assert server._free_name("a.pdf", {"a.pdf", "a (1).pdf"}) == "a (2).pdf"
    assert server._free_name("Makefile", {"Makefile"}) == "Makefile (1)"
    assert server._free_name("new.txt", {"a.pdf"}) == "new.txt"
    disposition = server._attachment("דוח.pdf")
    assert 'filename="___.pdf"' in disposition and "filename*=UTF-8''%D7%93%D7%95%D7%97.pdf" in disposition
    assert server._shown("/home/agent/Downloads", "/home/agent") == "~/Downloads"
    assert server._shown("/tmp/x", "/home/agent") == "/tmp/x"


# -- the agent's listing ------------------------------------------------------------------------------
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the desktop agent runs on Linux")
def test_agent_lists_folders_first_and_hides_dotfiles(tmp_path):
    (tmp_path / "b.txt").write_text("hi")
    (tmp_path / "A").mkdir()
    (tmp_path / ".secret").write_text("x")
    (tmp_path / "gone").symlink_to(tmp_path / "nowhere")  # a broken link is left out
    me = types.SimpleNamespace(home=str(tmp_path))
    res = AgentServer.m_ls(me, {"path": str(tmp_path)})
    assert [(e["name"], e["dir"], e["size"]) for e in res["entries"]] == [("A", True, None), ("b.txt", False, 2)]
    assert res["total"] == 2 and res["home"] == str(tmp_path)
    assert ".secret" in [e["name"] for e in AgentServer.m_ls(me, {"path": str(tmp_path), "hidden": True})["entries"]]
    with pytest.raises(RpcError, match="no such folder"):
        AgentServer.m_ls(me, {"path": str(tmp_path / "nope")})


# -- saved sign-ins -------------------------------------------------------------------------------------
class LoginBackend:
    name = "fake"
    supports_logins = True

    def __init__(self):
        self.saved = {"github": Login("github", "browser", "minion-login:github", "github.com")}
        self.created = []

    def list(self, stats=False):
        return []

    def logins(self):
        return list(self.saved.values())

    def delete_login(self, login):
        if login not in self.saved:
            raise NotFound(f"no saved sign-in {login!r}")
        del self.saved[login]

    def create(self, name, profile, options, progress=None, login=None):
        self.created.append((name, profile.name, login.name if login else None))
        return DesktopInfo(name, profile.name, "running", "fake")


def test_create_starts_from_a_saved_sign_in_with_its_profile():
    be = LoginBackend()
    d = Desktop.create(login="github", backend=be)
    assert be.created == [("github-1", "browser", "github")] and d.name == "github-1"
    with pytest.raises(MinionError, match="saved from a browser desktop"):
        Desktop.create("office", login="github", backend=be)
    with pytest.raises(NotFound, match="no saved sign-in 'mail'.*saved: github"):
        Desktop.create(login="mail", backend=be)
    with pytest.raises(MinionError, match="need the Docker backend"):
        Desktop.create(login="github", backend=NoBackend())
    with pytest.raises(MinionError, match="invalid sign-in name"):
        check_login("My Bank")


def test_cli_login_list_and_rm(monkeypatch, capsys):
    be = LoginBackend()
    monkeypatch.setattr("minion.desktop.get_backend", lambda name=None: be)
    assert cli.main(["login", "list"]) == 0
    out = capsys.readouterr().out
    assert "github" in out and "github.com" in out and "minion up --login NAME" in out
    assert cli.main(["logins"]) == 0  # the alias lists them too
    assert "github.com" in capsys.readouterr().out
    assert cli.main(["login", "rm", "github"]) == 0 and be.saved == {}
    assert cli.main(["login", "rm", "github"]) == 2  # not found
    assert cli.main(["login"]) == 1  # which one?


def test_tools_list_sign_ins_and_create_signed_in(monkeypatch):
    be = LoginBackend()
    tk = Toolkit.__new__(Toolkit)
    tk.backend, tk.current, tk.desktops, tk._pending = be, None, {}, {}
    tk._lock, tk._local = threading.Lock(), threading.local()
    tk.in_process_viewer, tk.files_root, tk.images, tk.fallback = None, None, True, True
    text = tk.t_desktop({"action": "logins"}, print)[0]["text"]
    assert "- github (browser, github.com)" in text
    monkeypatch.setattr(
        Desktop, "hello", lambda self: {"screen": [1280, 800], "apps": ["Firefox"], "profile": "browser"}
    )
    monkeypatch.setattr(Toolkit, "view_url", lambda self, name: None)
    text = tk.t_desktop({"action": "create", "login": "github"}, print)[0]["text"]
    assert "signed in from the saved sign-in 'github'" in text and be.created[-1] == ("github-1", "browser", "github")
    assert tk.t_computer({"command": "logins"}, print)[0]["text"].startswith("Saved sign-ins")


def test_shared_server_tools_hide_sign_ins():
    st = server.ServedToolkit(host_files=False)
    desk = next(d for d in st.definitions("mcp") if d["name"] == "desktop")
    assert "login" not in desk["inputSchema"]["properties"]
    assert "logins" not in desk["inputSchema"]["properties"]["action"]["enum"]
    with pytest.raises(Exception, match="sign-ins are off"):
        st.t_desktop({"action": "create", "login": "github"}, print)
    local = server.ServedToolkit(host_files=True)
    desk = next(d for d in local.definitions("mcp") if d["name"] == "desktop")
    assert "login" in desk["inputSchema"]["properties"]


def test_live_view_has_the_manual_controls():
    page = (Path(server.WEB) / "view.html").read_text(encoding="utf-8")
    for control in ('id="files-btn"', 'id="copy"', 'id="keys"', 'id="open"', 'id="login"', 'id="files-input"'):
        assert control in page
    script = (Path(server.WEB) / "view.js").read_text(encoding="utf-8")
    for route in ("/files?path=", "/download?path=", "/upload?path=", '"/login"', '"/clipboard"'):
        assert route in script
    assert os.path.exists(Path(server.WEB) / "dashboard.js")
