"""HTTP API, dashboard and live view (standard library only).

    minion serve            # http://127.0.0.1:4747/?token=...

Every endpoint needs the token (query ?token=, a cookie set on first visit, or
`Authorization: Bearer`). It binds to 127.0.0.1 unless told otherwise.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, config, profiles
from .backends import get_backend
from .desktop import Desktop
from .errors import AgentError, MinionError, NotFound

WEB = Path(__file__).parent / "web"
COOKIE = "minion_token"

_desktops: dict[str, Desktop] = {}
_desk_lock = threading.Lock()
_handoffs: dict[str, dict] = {}
_handoff_lock = threading.Lock()


def _desk(name: str) -> Desktop:
    with _desk_lock:
        d = _desktops.get(name)
        if d is None:
            d = Desktop(name, get_backend())
            _desktops[name] = d
        return d


def _forget(name: str) -> None:
    with _desk_lock:
        d = _desktops.pop(name, None)
    if d is not None:
        d.close()


class Handler(BaseHTTPRequestHandler):
    server_version = f"minion/{__version__}"
    token: str | None = None
    quiet = False

    # -- plumbing -----------------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: N802 - stdlib API
        if not self.quiet:
            sys.stderr.write(f"[minion] {self.address_string()} {fmt % args}\n")

    def _authorized(self, query: dict) -> bool:
        if not self.token:
            return True
        if query.get("token", [None])[0] == self.token:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], self.token):
            return True
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        if COOKIE in cookie and secrets.compare_digest(cookie[COOKIE].value, self.token):
            return True
        return False

    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200, headers: dict | None = None) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json", headers)

    def _error(self, code: int, message: str) -> None:
        self._json({"error": message}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > 50 * 1024 * 1024:
            raise MinionError("request body too large")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            raise MinionError(f"invalid JSON body: {e}") from e
        return data if isinstance(data, dict) else {"actions": data}

    def _static(self, rel: str, query: dict) -> None:
        path = (WEB / rel).resolve()
        if WEB.resolve() not in path.parents or not path.is_file():
            self._error(404, "not found")
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        headers = {}
        if self.token and query.get("token", [None])[0] == self.token:
            headers["Set-Cookie"] = f"{COOKIE}={self.token}; Path=/; HttpOnly; SameSite=Strict"
        self._send(200, path.read_bytes(), ctype, headers)

    # -- routing ------------------------------------------------------------
    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        self._route("GET")

    def do_POST(self):  # noqa: N802
        self._route("POST")

    def do_DELETE(self):  # noqa: N802
        self._route("DELETE")

    def _route(self, method: str) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        parts = [p for p in url.path.split("/") if p]
        if method == "GET" and parts[:1] == ["static"]:  # public assets (no data in them)
            return self._static("/".join(parts[1:]), query)
        if not self._authorized(query):
            if method == "GET" and (not parts or parts[0] in ("view",)):
                self._send(
                    401,
                    (WEB / "locked.html").read_bytes()
                    if (WEB / "locked.html").exists()
                    else b"Unauthorized: add ?token=...",
                    "text/html; charset=utf-8",
                )
            else:
                self._error(401, "unauthorized: pass ?token=..., a Bearer token or the cookie")
            return
        try:
            if method == "GET" and not parts:
                return self._static("index.html", query)
            if method == "GET" and parts[0] == "view" and len(parts) == 2:
                return self._static("view.html", query)
            if method == "GET" and parts[0] == "static" and len(parts) >= 2:
                return self._static("/".join(parts[1:]), query)
            if parts and parts[0] == "api":
                return self._api(method, parts[1:], query)
            self._error(404, "not found")
        except NotFound as e:
            self._error(404, str(e))
        except AgentError as e:
            self._error(422, str(e))
        except MinionError as e:
            self._error(400, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # pragma: no cover - unexpected
            self._error(500, f"{type(e).__name__}: {e}")

    def _api(self, method: str, parts: list[str], query: dict) -> None:
        q = lambda k, d=None: query.get(k, [d])[0]  # noqa: E731
        if parts == ["health"]:
            return self._json({"ok": True, "version": __version__, "backend": get_backend().name})
        if parts == ["profiles"]:
            reg = profiles.load_all()
            return self._json([reg[n].summary() for n in profiles.names(reg)])
        if not parts or parts[0] != "desktops":
            return self._error(404, "unknown endpoint")
        be = get_backend()
        if len(parts) == 1:
            if method == "GET":
                return self._json([d.to_dict() for d in be.list(stats=q("stats") == "1")])
            if method == "POST":
                body = self._body()
                d = Desktop.create(
                    body.get("profile") or config.DEFAULT_PROFILE,
                    name=body.get("name"),
                    size=body.get("size"),
                    backend=be,
                )
                with _desk_lock:
                    _desktops[d.name] = d
                return self._json({**d.to_dict(), "hello": d.hello()}, 201)
        name = parts[1]
        d = _desk(name)
        op = parts[2] if len(parts) > 2 else None
        if op is None:
            if method == "GET":
                return self._json({**d.to_dict(), "hello": d.hello()})
            if method == "DELETE":
                d.remove()
                _forget(name)
                return self._json({"ok": True})
        if method == "GET" and op == "frame":
            res = d.call(
                "frame",
                {
                    "since": q("since"),
                    "wait": int(q("wait", "0") or 0),
                    "max_width": int(q("max_width", "1600") or 1600),
                    "quality": int(q("quality", "72") or 72),
                },
                timeout=30,
            )
            if res.get("unchanged"):
                self.send_response(204)
                self.send_header("X-Frame-Key", res.get("key", ""))
                self.end_headers()
                return
            screen = "x".join(str(v) for v in res.get("screen", []))
            return self._send(
                200, base64.b64decode(res["data"]), res["mime"], {"X-Frame-Key": res["key"], "X-Screen": screen}
            )
        if method == "GET" and op == "screenshot":
            shot = d.screenshot(
                max_width=int(q("max_width")) if q("max_width") else None,
                format=q("format", "png"),
                marks=q("marks") == "1",
                grid=q("grid") == "1",
            )
            headers = {}
            if q("download") == "1":
                headers["Content-Disposition"] = (
                    f'attachment; filename="{name}-{time.strftime("%H%M%S")}.{shot.format}"'
                )
            return self._send(200, shot.data, shot.mime, headers)
        if method == "GET" and op == "see":
            obs = d.see(ocr=True if q("ocr") == "1" else "auto", window=q("window"))
            return self._json(obs.__dict__)
        if method == "GET" and op == "info":  # no wake-up: safe to poll on frozen desktops
            return self._json(d.info().to_dict())
        if method == "GET" and op == "windows":
            return self._json(d.windows())
        if method == "GET" and op == "status":
            return self._json({**d.to_dict(), **d.status()})
        if method == "GET" and op == "replay":
            if q("format") == "gif":
                return self._send(200, d.recording("gif"), "image/gif")
            return self._send(200, d.recording("html").encode(), "text/html; charset=utf-8")
        if op == "handoff":
            return self._handoff(method, name, query)
        if method != "POST":
            return self._error(405, "method not allowed")
        body = self._body()
        if op == "act":
            res = d.act(
                body.get("actions") or [],
                screenshot=bool(body.get("screenshot")),
                see=bool(body.get("see")),
                check=False,
            )
            out = {k: v for k, v in res.__dict__.items() if k not in ("screenshot", "observation")}
            if res.screenshot:
                out["screenshot"] = {"data": res.screenshot.base64(), "mime": res.screenshot.mime}
            if res.observation:
                out["see"] = res.observation.__dict__
            return self._json(out)
        if op == "input":
            return self._json(d.call("input", body, timeout=30))
        if op == "run":
            r = d.run(
                body.get("command") or "",
                timeout=float(body.get("timeout") or 120),
                background=bool(body.get("background")),
            )
            return self._json(r.__dict__)
        if op == "open":
            return self._json(d.open(body.get("target") or "", wait=float(body.get("wait") or 12)))
        if op == "clipboard":
            if "text" in body:
                d.clipboard = body["text"]
                return self._json({"ok": True})
            return self._json({"text": d.clipboard})
        if op in ("freeze", "thaw", "stop", "start"):
            getattr(d, op)()
            return self._json({"ok": True, "state": d.info().state})
        if op == "snapshot":
            return self._json({"tag": d.snapshot(body.get("tag"))})
        if op == "restore":
            d.restore(body.get("tag") or "")
            return self._json({"ok": True})
        if op == "fork":
            new = d.fork(body.get("name"))
            return self._json(new.to_dict(), 201)
        return self._error(404, f"unknown operation {op!r}")

    def _handoff(self, method: str, name: str, query: dict) -> None:
        with _handoff_lock:
            h = _handoffs.get(name)
            if method == "GET":
                return self._json(None if h is None else {k: v for k, v in h.items() if k != "event"})
            body = self._body()
            if method == "POST" and "message" in body:  # agent requests a hand-off
                _handoffs[name] = {
                    "message": body["message"],
                    "created": time.time(),
                    "done": False,
                    "note": None,
                    "event": threading.Event(),
                }
                return self._json({"ok": True})
            if method == "POST" and h is not None:  # human finished
                h["done"] = True
                h["note"] = (body.get("note") or "").strip()
                h["event"].set()
                return self._json({"ok": True})
            if method == "DELETE":
                _handoffs.pop(name, None)
                return self._json({"ok": True})
        return self._error(400, "no hand-off pending")


def _free_port(host: str, preferred: int, fallback: bool = True) -> int:
    for port in (preferred, 0) if fallback else (preferred,):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    raise MinionError(f"port {preferred} is already in use (choose another with --port)")


def make_server(
    host: str = "127.0.0.1", port: int = 4747, token: str | None = "", quiet: bool = False, fallback: bool = True
) -> tuple[ThreadingHTTPServer, str, str | None]:
    if token == "":
        token = secrets.token_urlsafe(16)
    port = _free_port(host, port, fallback)
    handler = type("MinionHandler", (Handler,), {"token": token, "quiet": quiet})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    return httpd, f"http://{shown}:{port}", token


def serve(
    host: str = "127.0.0.1",
    port: int = 4747,
    token: str | None = "",
    idle_freeze: float = 600,
    quiet: bool = False,
    record_state: bool = True,
) -> None:
    httpd, base, token = make_server(host, port, token, quiet, fallback=False)
    if record_state:
        config.update_state(server={"url": base, "token": token, "pid": os.getpid()})
    if idle_freeze and idle_freeze > 0:
        from .reaper import start_reaper

        start_reaper(get_backend(), idle_freeze)
    url = f"{base}/?token={token}" if token else base + "/"
    if not quiet:
        print(f"Minion {__version__} · dashboard and API at {url}", flush=True)
        if host not in ("127.0.0.1", "localhost", "::1") and not token:
            print(
                "WARNING: no token and not bound to localhost — anyone on the network can control your desktops.",
                file=sys.stderr,
            )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# -- helpers used by the CLI and the MCP server ---------------------------------
def _healthy(base: str, token: str | None) -> bool:
    try:
        req = urllib.request.Request(f"{base}/api/health", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


_inproc: tuple[str, str | None] | None = None
_inproc_lock = threading.Lock()


def ensure_server(in_process: bool | None = None) -> tuple[str, str | None]:
    """Return (base_url, token) of a running server, starting one if needed.

    In a long-lived process (the MCP server) it runs in a thread; from the CLI it is
    spawned as a background process that outlives the command."""
    global _inproc
    st = config.load_state().get("server") or {}
    if st.get("url") and _healthy(st["url"], st.get("token")):
        return st["url"], st.get("token")
    if in_process is None:
        in_process = "minion.mcp" in sys.modules
    if in_process:
        with _inproc_lock:
            if _inproc is None:
                httpd, base, token = make_server(port=int(os.environ.get("MINION_PORT", "4747")), quiet=True)
                threading.Thread(target=httpd.serve_forever, daemon=True, name="minion-http").start()
                _inproc = (base, token)
                config.update_state(server={"url": base, "token": token, "pid": os.getpid()})
            return _inproc
    token = secrets.token_urlsafe(16)
    port = _free_port("127.0.0.1", int(os.environ.get("MINION_PORT", "4747")))
    log = config.config_dir() / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as f:
        kwargs = (
            {"start_new_session": True}
            if os.name != "nt"
            else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008}
        )  # DETACHED_PROCESS
        subprocess.Popen(
            [sys.executable, "-m", "minion", "serve", "--port", str(port), "--token", token, "--quiet"],
            stdout=f,
            stderr=f,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if _healthy(base, token):
            return base, token
        time.sleep(0.1)
    raise MinionError(f"the live view server did not start (see {log})")


def _api(base: str, token: str | None, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def handoff_wait(name: str, message: str, timeout: float = 600) -> str | None:
    """Ask the human (in the live view) to take over; block until they press Done."""
    base, token = ensure_server()
    path = f"/api/desktops/{re.sub(r'[^a-z0-9_-]', '', name)}/handoff"
    _api(base, token, "POST", path, {"message": message})
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            h = _api(base, token, "GET", path)
            if h and h.get("done"):
                return h.get("note") or ""
            time.sleep(1.0)
        return None
    finally:
        try:
            _api(base, token, "DELETE", path)
        except (urllib.error.URLError, OSError):
            pass
