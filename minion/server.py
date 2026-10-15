"""HTTP API, dashboard, live view and remote MCP endpoint (standard library only).

    minion serve            # http://127.0.0.1:4747/?token=...
                            # MCP over Streamable HTTP: http://127.0.0.1:4747/mcp

Every endpoint needs the token (query ?token=, a cookie set on first visit, or
`Authorization: Bearer`; /mcp takes only the first two). It binds to 127.0.0.1 unless told otherwise.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import queue
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
from .tools import ToolError, Toolkit

WEB = Path(__file__).parent / "web"
COOKIE = "minion_token"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", ""})  # "": HTTP/1.0 clients send no Host
# Web chat apps whose backends call MCP servers with their own Origin (claude.ai does). See _mcp_origin_ok.
WEB_CLIENT_ORIGINS = frozenset(
    {"https://claude.ai", "https://chatgpt.com", "https://chat.openai.com", "https://chat.mistral.ai"}
)
MCP_SESSIONS_MAX = 100  # least recently used sessions beyond this are ended (clients then initialize again)
MCP_SESSION_IDLE = 24 * 3600.0  # seconds; idle sessions are ended
SSE_KEEPALIVE = 10.0  # seconds between SSE comments while a tool works (proxies and tunnels drop quiet streams)

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


FILES_IN_DESKTOP = (
    "Read or write text files inside a desktop. read: path -> text; write: text -> path. Desktop paths may "
    "start with ~. (This server does not copy files to or from its own disk: fetch files inside the desktop "
    "with run or open instead.)"
)


class ServedToolkit(Toolkit):
    """The toolkit as this HTTP server serves it, to /mcp sessions and /api/tools.

    Live-view links and hand-offs point at this server (its public URL behind a tunnel), long waits
    can be capped below a client's timeout (`wait_cap`), and `files` upload/download, which touch this
    server's disk, can be turned off (`host_files=False`, the default of `minion share`)."""

    def __init__(self, *, files_root=None, images: bool = True, host_files: bool = True, wait_cap=None, token=None):
        super().__init__(in_process_viewer=True, files_root=files_root, images=images)
        self.fallback = False  # each session (a chat, an agent) works on the desktops it created or names
        self.host_files = host_files
        self.wait_cap = wait_cap  # seconds, or None
        self.token = token
        self.base_url: str | None = None  # where clients reach this server; set per request

    def definitions(self, format: str = "mcp", *, compact: bool = False) -> list[dict]:
        defs = super().definitions(format, compact=compact)
        if not self.host_files:
            for d in defs:
                fn = d.get("function", d)  # Chat Completions nests the definition
                if fn.get("name") != "files":
                    continue
                fn["description"] = FILES_IN_DESKTOP
                schema = fn.get("inputSchema") or fn.get("input_schema") or fn.get("parameters") or {}
                props = schema.get("properties", {})
                props.pop("local_path", None)
                if "action" in props:
                    props["action"]["enum"] = ["read", "write"]
        return defs

    def view_url(self, name: str) -> str | None:
        if not self.base_url:
            return super().view_url(name)
        return f"{self.base_url}/view/{name}" + (f"?token={self.token}" if self.token else "")

    def t_files(self, args: dict, progress) -> list:
        if not self.host_files and args.get("action") in ("upload", "download"):
            raise ToolError(
                "upload and download are turned off on this server (they would use its disk). Use files "
                "read/write for text, or run (curl, wget, …) to fetch files inside the desktop."
            )
        return super().t_files(args, progress)

    def t_view(self, args: dict, progress) -> list:
        if not args.get("message"):
            return super().t_view(args, progress)
        d = self.desk(args)
        url = self.view_url(d.name)
        wanted = float(args.get("timeout") or 600)
        timeout = min(wanted, self.wait_cap) if self.wait_cap else wanted
        progress(f"Waiting for the human at {url}")
        note = _wait_for_human(d.name, args["message"], timeout)
        if note is None and timeout < wanted:  # the client would time out first: let the agent ask again
            text = (
                f"The human has not pressed Done yet ({url}). Call view again with the same message to keep "
                "waiting; the request stays on their screen."
            )
        elif note is None:
            text = f"The human did not finish within {timeout:.0f}s. Link: {url}"
        else:
            said = f' They said: "{note}".' if note else ""
            text = f"The human is done.{said} Call see() to check the screen."
        return [{"type": "text", "text": text}]


_toolkits: dict = {}


def _toolkit(session: str, **options) -> ServedToolkit:
    """The toolkit of one HTTP session (an MCP session, or a /api/tools `session`): each keeps its own
    "current desktop". `options` (images, host_files, wait_cap, token) apply when it is first created."""
    with _desk_lock:
        tk = _toolkits.get(session)
        if tk is None:  # over HTTP, `files` may only touch the server's disk inside one folder
            root = os.environ.get("MINION_FILES_ROOT") or str(config.data_dir() / "files")
            tk = ServedToolkit(files_root=root, **options)
            _toolkits[session] = tk
        return tk


def _forget_toolkit(session: str) -> None:
    with _desk_lock:
        tk = _toolkits.pop(session, None)
    for d in list(getattr(tk, "desktops", {}).values()):
        try:
            d.close()  # its connection (a `docker exec` process); the desktop itself stays
        except Exception:
            pass


def _wait_for_human(name: str, message: str, timeout: float) -> str | None:
    """A hand-off served by this process: the live view shows `message` until the human presses Done.
    Returns their note, or None on timeout. The request stays up after a timeout, so an agent whose
    client gave up first can wait again (same message) and still get the answer."""
    with _handoff_lock:
        h = _handoffs.get(name)
        stale = h is not None and h["done"] and time.time() - h.get("done_at", 0) > 600
        if h is None or h["message"] != message or stale:
            h = {"message": message, "created": time.time(), "done": False, "note": None, "event": threading.Event()}
            _handoffs[name] = h
    if not h["event"].wait(timeout):
        return None
    with _handoff_lock:
        if _handoffs.get(name) is h:
            _handoffs.pop(name)
    return h["note"] or ""


class _McpEntry:
    """An MCP session over HTTP: the protocol state, its toolkit's key, and use for expiry."""

    def __init__(self, sid: str, session, key: str):
        self.id, self.session, self.key = sid, session, key
        self.used = time.monotonic()
        self.busy = 0


_mcp_lock = threading.Lock()


def _forget(name: str) -> None:
    with _desk_lock:
        d = _desktops.pop(name, None)
    if d is not None:
        d.close()


class Handler(BaseHTTPRequestHandler):
    server_version = f"minion/{__version__}"
    token: str | None = None
    quiet = False
    local_only = True
    # Set per server by make_server() (and by `minion share` once its tunnel is up):
    extra_hosts: frozenset = frozenset()  # more Host names to answer to: a tunnel's or reverse proxy's public name
    base_url = ""  # this server's own address, e.g. http://127.0.0.1:4747
    public_url: str | None = None  # the address clients use, if it differs (https://….trycloudflare.com)
    host_files = True  # `files` upload/download may use this server's disk (inside MINION_FILES_ROOT)
    wait_cap: float | None = None  # cap for long waits inside a tool call (chat apps time out after ~1 min)
    activity = None  # callable(tool, arguments, client) told about each MCP tool call (`minion share` prints it)
    mcp_sessions: dict = {}  # replaced by a fresh dict per server

    # -- plumbing -----------------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: N802 - stdlib API
        if not self.quiet:
            line = re.sub(r"(token=)[^&\s\"]+", r"\1…", fmt % args)  # keep the token out of logs
            sys.stderr.write(f"[minion] {self._client()} {line}\n")

    def _client(self) -> str:
        """The caller's address; behind a Cloudflare tunnel, the visitor rather than cloudflared."""
        headers = getattr(self, "headers", None)  # not parsed yet when a malformed request is logged
        return (headers.get("Cf-Connecting-Ip") if headers else None) or self.address_string()

    def _authorized(self, query: dict, cookie: bool = True) -> bool:
        if not self.token:
            return True
        token = self.token.encode()
        given = query.get("token", [None])[0]
        if given and secrets.compare_digest(given.encode(), token):
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and secrets.compare_digest(auth[7:].strip().encode(), token):
            return True
        jar = SimpleCookie(self.headers.get("Cookie", "")) if cookie else {}
        if COOKIE in jar and secrets.compare_digest(jar[COOKIE].value.encode(), token):
            return True
        return False

    def _host_name(self) -> str:
        host = self.headers.get("Host") or ""
        return (host[: host.find("]") + 1] if host.startswith("[") else host.split(":")[0]).lower()

    def _host_ok(self) -> bool:
        """Only Host names this server answers to (blocks DNS-rebinding pages): loopback names on a loopback
        bind, plus extra_hosts (a tunnel's public name, MINION_ALLOWED_HOSTS). Any name on a non-loopback
        bind that has no extra_hosts."""
        if not self.local_only and not self.extra_hosts:
            return True
        name = self._host_name()
        return name in LOOPBACK_HOSTS or name in self.extra_hosts

    def _public_base(self) -> str:
        """The base URL this request came in on, for links handed back to the client (live views)."""
        if self.public_url:
            return self.public_url
        host = self.headers.get("Host")
        if not host:
            return self.base_url
        proto = (self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip().lower()
        return f"{'https' if proto == 'https' else 'http'}://{host}"

    def _csrf_ok(self) -> bool:
        """Mutating requests must be impossible to forge from another web page: a Bearer token,
        our custom header or a JSON body all force a CORS preflight, which this server never grants."""
        if self.headers.get("Authorization", "").startswith("Bearer "):
            return True
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != (self.headers.get("Host") or ""):
            return False
        return self.headers.get("X-Minion") == "1" or (self.headers.get("Content-Type") or "").startswith(
            "application/json"
        )

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
            secure = "; Secure" if self._public_base().startswith("https:") else ""  # behind a TLS tunnel/proxy
            headers["Set-Cookie"] = f"{COOKIE}={self.token}; Path=/; HttpOnly; SameSite=Strict{secure}"
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
        if not self._host_ok():
            return self._error(403, "forbidden host")
        if [p.lower() for p in parts] == ["mcp"]:  # remote MCP (some clients change the path's case)
            return self._mcp(method, query)
        if parts[:1] == [".well-known"]:  # no OAuth metadata: the token in the URL or header is the credential
            return self._error(404, "not found")
        if method == "GET" and parts[:1] == ["static"]:  # public assets (no data in them)
            return self._static("/".join(parts[1:]), query)
        if method == "GET" and parts == ["openapi.json"]:  # public: describes the API, holds no data
            from .tools import openapi

            return self._json(openapi(self._public_base()))
        if method in ("POST", "DELETE") and not self._csrf_ok():
            return self._error(403, "cross-site request refused: send JSON, a Bearer token or `X-Minion: 1`")
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
        if parts and parts[0] == "tools":
            return self._tools(method, parts[1:], query)
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
        op = parts[2] if len(parts) > 2 else None
        if op == "handoff":  # pure server state: no desktop connection needed
            return self._handoff(method, name, query)
        d = _desk(name)
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
            ocr = q("lang") or (True if q("ocr") == "1" else "auto")
            obs = d.see(ocr=ocr, window=q("window"), menus=q("menus") == "1")
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
            install = body.get("install", True) is not False
            return self._json(d.open(body.get("target") or "", wait=float(body.get("wait") or 12), install=install))
        if op == "read":  # any document as text
            return self._json({"text": d.read(body.get("path") or "", max_chars=int(body.get("max_chars") or 200_000))})
        if op == "convert":
            return self._json({"path": d.convert(body.get("path") or "", body.get("to") or "", body.get("outdir"))})
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

    def _tools(self, method: str, parts: list[str], query: dict) -> None:
        """The universal toolkit over HTTP: definitions in every format, and calls.
        Pass a session id (body "session" or header X-Minion-Session) to keep each agent's
        "current desktop" separate."""
        fmt = query.get("format", ["mcp"])[0]
        compact = query.get("compact", ["0"])[0] in ("1", "true")
        if method == "GET" and not parts:
            return self._json(_toolkit("default", **self._toolkit_options()).definitions(fmt, compact=compact))
        if method != "POST":
            return self._error(405, "POST a tool call")
        body = self._body()
        session = body.get("session") or self.headers.get("X-Minion-Session") or "default"
        if parts == ["call"]:
            name, args = body.get("name"), body.get("arguments") or {}
        elif len(parts) == 1:
            name, args = parts[0], {k: v for k, v in body.items() if k != "session"}
        else:
            return self._error(404, "unknown tools endpoint")
        tk = _toolkit(str(session), **self._toolkit_options())
        tk.base_url = self._public_base()
        return self._json(tk.call(name, args).to_mcp())

    def _toolkit_options(self, **more) -> dict:
        """How this server's toolkits are made (see ServedToolkit)."""
        return {"host_files": self.host_files, "wait_cap": self.wait_cap, "token": self.token, **more}

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
                h["done_at"] = time.time()
                h["note"] = (body.get("note") or "").strip()
                h["event"].set()
                return self._json({"ok": True})
            if method == "DELETE":
                _handoffs.pop(name, None)
                return self._json({"ok": True})
        return self._error(400, "no hand-off pending")

    # -- MCP over Streamable HTTP (spec 2025-11-25, also serves 2025-06-18 and 2025-03-26 clients) ----------
    # POST carries one JSON-RPC message. initialize opens a session (Mcp-Session-Id) with its own toolkit,
    # so "the current desktop" is per session; DELETE ends it. tools/call answers as an SSE stream when the
    # client accepts one (progress notifications, and keep-alive comments so proxies and tunnels don't cut
    # a slow first-time image download); everything else is plain JSON. There is no server-initiated
    # stream, so GET is 405. JSON-RPC batches are refused (removed from the spec in 2025-06-18).
    # Protocol 2026-07-28 (stateless) is not served: its clients probe first and, on our 400 (no
    # session), fall back to initialize as the spec's backward-compatibility rules require.
    def _mcp(self, method: str, query: dict) -> None:
        try:
            if not self._mcp_origin_ok():
                return self._mcp_error(403, "Forbidden: requests from this Origin may not use the MCP endpoint")
            if not self._authorized(query, cookie=False):
                return self._mcp_error(
                    401,
                    "Unauthorized: add ?token=... to the URL or send Authorization: Bearer <token>",
                    {"WWW-Authenticate": 'Bearer realm="minion"'},
                )
            if method not in ("POST", "DELETE"):
                return self._mcp_error(
                    405, "Method not allowed: POST JSON-RPC messages here", {"Allow": "POST, DELETE"}
                )
            sid = self.headers.get("Mcp-Session-Id")
            if method == "DELETE":
                if not sid:
                    return self._mcp_error(400, "Bad Request: missing Mcp-Session-Id header")
                if not self._mcp_end(sid):
                    return self._mcp_error(404, "Session not found")
                self.send_response(204)
                self.end_headers()
                return
            return self._mcp_post(query, sid)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # pragma: no cover - unexpected
            self._mcp_error(500, f"{type(e).__name__}: {e}", code=-32603)

    def _mcp_origin_ok(self) -> bool:
        """The MCP spec asks servers to check Origin (403 when present and invalid) against DNS rebinding.

        Clients that run on servers (ChatGPT's and Le Chat's backends, Cursor, VS Code, the MCP SDKs)
        usually send no Origin: allowed. Browsers always send one, and so does claude.ai's backend
        (https://claude.ai), so its mere presence proves nothing. What Origin can tell us depends on
        the address the request came to:
        - A public name (a tunnel's, a reverse proxy's domain): whoever holds the token can call that URL
          directly, with or without a browser, so Origin adds nothing and every Origin is accepted. A
          DNS-rebinding page can't get here: it would arrive with its own hostname, which the Host
          check (_host_ok) refuses. (A non-loopback bind without allowed names turns the Host check
          off; then, as for the rest of the API, the token is the only protection.)
        - A loopback name: a local client, or a page in a browser on this machine. Accept loopback
          origins (local tools such as the MCP Inspector), WEB_CLIENT_ORIGINS (a reverse proxy that
          rewrites Host to 127.0.0.1 forwards chat apps' calls) and MINION_ALLOWED_ORIGINS; refuse every
          other web page with 403, even if it somehow knows the token.
        Cookies never authenticate /mcp (only ?token= or a Bearer header), so a cross-site page can't
        borrow a session from the dashboard either."""
        origin = (self.headers.get("Origin") or "").strip()
        if not origin or self._host_name() not in LOOPBACK_HOSTS:
            return True
        origin = origin.rstrip("/").lower()
        allowed = {o.strip().rstrip("/").lower() for o in os.environ.get("MINION_ALLOWED_ORIGINS", "").split(",")}
        if origin in WEB_CLIENT_ORIGINS or origin in allowed:
            return True
        try:
            return urlparse(origin).hostname in ("localhost", "127.0.0.1", "::1")
        except ValueError:
            return False

    def _mcp_error(self, status: int, message: str, headers: dict | None = None, code: int = -32600) -> None:
        """A transport-level rejection: an HTTP error status with a JSON-RPC error that has no id."""
        body = {"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}}
        self._send(status, json.dumps(body).encode(), "application/json", headers)

    def _mcp_json(self, status: int, msg: dict, sid: str | None = None) -> None:
        body = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode()
        self._send(status, body, "application/json", {"Mcp-Session-Id": sid} if sid else None)

    def _mcp_body(self, limit: int = 50 * 1024 * 1024) -> bytes:
        """The request body, sent with a Content-Length or chunked."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            out = bytearray()
            while True:
                size = int(self.rfile.readline(1024).split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline(1024) not in (b"\r\n", b"\n", b""):  # trailers
                        pass
                    return bytes(out)
                if len(out) + size > limit:
                    raise MinionError("request body too large")
                out += self.rfile.read(size)
                self.rfile.readline(1024)  # the CRLF after each chunk
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise MinionError("request body too large")
        return self.rfile.read(n) if n > 0 else b""

    def _mcp_post(self, query: dict, sid: str | None) -> None:
        from .mcp import PROTOCOL_VERSIONS, is_tool_call, rpc_error

        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._mcp_error(415, "Unsupported Media Type: POST one JSON-RPC message as application/json")
        try:
            msg = json.loads(self._mcp_body())
        except MinionError as e:
            return self._mcp_error(413, str(e))
        except ValueError:
            return self._mcp_error(400, "Parse error: the body is not valid JSON", code=-32700)
        if isinstance(msg, list):
            return self._mcp_error(400, "Batches are not supported: POST one JSON-RPC message per request")
        if not isinstance(msg, dict):
            return self._mcp_error(400, "Invalid request: expected a JSON-RPC object")
        is_request = isinstance(msg.get("method"), str) and msg.get("id") is not None
        if is_request and msg["method"] == "initialize":  # always a new session, whatever headers come with it
            return self._mcp_initialize(msg, query)
        version = self.headers.get("MCP-Protocol-Version")
        if version and version not in PROTOCOL_VERSIONS:  # e.g. a 2026-07-28 probe: a plain 400 makes it fall back
            supported = ", ".join(PROTOCOL_VERSIONS)
            return self._mcp_error(
                400,
                f"Bad Request: unsupported MCP-Protocol-Version {version!r} (supported: {supported}; initialize first)",
            )
        if not sid:
            return self._mcp_error(400, "Bad Request: missing Mcp-Session-Id header (initialize first)")
        entry = self._mcp_find(sid)
        if entry is None:
            return self._mcp_error(404, "Session not found: it ended or expired, initialize a new one")
        if not is_request:  # a notification (initialized, cancelled) or a response
            reply = entry.session.handle(msg)
            if reply is not None:  # not a valid message
                return self._mcp_json(400, reply, sid)
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.send_header("Mcp-Session-Id", sid)
            self.end_headers()
            return
        hook = type(self).activity  # read off the class: through self, a function would become a method
        if is_tool_call(msg) and hook:
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            try:
                hook(params.get("name"), params.get("arguments"), self._client())
            except Exception:  # a broken log line must not break the call
                pass
        if is_tool_call(msg) and self._accepts_sse():
            return self._mcp_stream(entry, msg)
        reply = self._mcp_run(entry, msg)
        if reply is None:  # cancelled while it ran; a request must still be answered over HTTP
            reply = rpc_error(msg["id"], -32800, "Request cancelled")
        return self._mcp_json(200, reply, sid)

    def _mcp_initialize(self, msg: dict, query: dict) -> None:
        from .mcp import Session

        def flag(name: str, default: str) -> bool:
            return (query.get(name, [default])[0] or default).lower() not in ("0", "false", "no", "off")

        sid = secrets.token_hex(16)
        key = f"mcp:{sid}"
        tk = _toolkit(key, **self._toolkit_options(images=flag("images", "1")))
        tk.base_url = self._public_base()
        session = Session(tk, compact=flag("compact", "0"), log=_quiet if self.quiet else _log)
        reply = session.handle(msg)
        if "error" in reply:
            _forget_toolkit(key)
            return self._mcp_json(400, reply)
        closing = []
        with _mcp_lock:
            sessions = self.mcp_sessions
            now = time.monotonic()
            idle = sorted((e for e in sessions.values() if not e.busy), key=lambda e: e.used)
            for e in idle:  # expire idle sessions, and the least recently used beyond the limit
                if now - e.used > MCP_SESSION_IDLE or len(sessions) >= MCP_SESSIONS_MAX:
                    sessions.pop(e.id, None)
                    closing.append(e.key)
            sessions[sid] = _McpEntry(sid, session, key)
        for k in closing:
            _forget_toolkit(k)
        return self._mcp_json(200, reply, sid)

    def _mcp_find(self, sid: str) -> _McpEntry | None:
        with _mcp_lock:
            entry = self.mcp_sessions.get(sid)
            if entry is not None:
                entry.used = time.monotonic()
            return entry

    def _mcp_end(self, sid: str) -> bool:
        with _mcp_lock:
            entry = self.mcp_sessions.pop(sid, None)
        if entry is None:
            return False
        _forget_toolkit(entry.key)
        return True

    def _mcp_run(self, entry: _McpEntry, msg: dict, notify=None) -> dict | None:
        with _mcp_lock:
            entry.busy += 1
        try:
            return entry.session.handle(msg, notify=notify)
        finally:
            with _mcp_lock:
                entry.busy -= 1
                entry.used = time.monotonic()

    def _accepts_sse(self) -> bool:
        types = [t.split(";")[0].strip().lower() for t in (self.headers.get("Accept") or "").split(",")]
        return any(t in ("text/event-stream", "text/*", "*/*") for t in types)

    def _mcp_stream(self, entry: _McpEntry, msg: dict) -> None:
        """Answer a tools/call with an SSE stream: progress notifications while the tool works, a comment
        every SSE_KEEPALIVE seconds so nothing in between closes a quiet connection, then the result.
        If the client goes away the tool still finishes (a disconnect is not a cancellation); its
        result is dropped."""
        from .mcp import rpc_error

        events: queue.Queue = queue.Queue()
        done = object()

        def work() -> None:
            try:
                reply = self._mcp_run(entry, msg, notify=events.put)
            except BaseException as e:  # pragma: no cover - Session.handle reports errors itself
                reply = rpc_error(msg.get("id"), -32603, f"{type(e).__name__}: {e}")
            events.put((done, reply))

        threading.Thread(target=work, daemon=True, name="minion-mcp-call").start()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")  # nginx: don't buffer the stream
        self.send_header("Mcp-Session-Id", entry.id)
        self.end_headers()
        while True:
            try:
                item = events.get(timeout=SSE_KEEPALIVE)
            except queue.Empty:
                if not self._sse(b": keep-alive\n\n"):
                    return
                continue
            if isinstance(item, tuple) and item[0] is done:
                if item[1] is not None:  # None: the client cancelled the call, so no response
                    self._sse(_sse_event(item[1]))
                return
            if not self._sse(_sse_event(item)):
                return

    def _sse(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except OSError:
            return False


def _sse_event(msg: dict) -> bytes:
    return b"event: message\ndata: " + json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode() + b"\n\n"


def _log(text: str) -> None:
    sys.stderr.write(f"[minion] {text}\n")


def _quiet(text: str) -> None:
    pass


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
    host: str = "127.0.0.1",
    port: int = 4747,
    token: str | None = "",
    quiet: bool = False,
    fallback: bool = True,
    allowed_hosts=(),
) -> tuple[ThreadingHTTPServer, str, str | None]:
    """A server (not yet serving) and its base URL. `allowed_hosts` (plus MINION_ALLOWED_HOSTS, comma-separated)
    are Host names to answer to besides loopback ones, e.g. a reverse proxy's domain; once set, the Host check
    applies on any bind address."""
    if token == "":
        token = secrets.token_urlsafe(16)
    port = _free_port(host, port, fallback)
    local_only = host in ("127.0.0.1", "localhost", "::1")
    names = [*allowed_hosts, *os.environ.get("MINION_ALLOWED_HOSTS", "").split(",")]
    extra = frozenset(n.strip().lower() for n in names if n.strip())
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else (f"[{host}]" if ":" in host else host)
    base = f"http://{shown}:{port}"
    attrs = {"token": token, "quiet": quiet, "local_only": local_only, "extra_hosts": extra, "base_url": base}
    handler = type("MinionHandler", (Handler,), {**attrs, "mcp_sessions": {}})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd, base, token


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
        mcp_url = f"{base}/mcp?token={token}" if token else f"{base}/mcp"
        print(f"Remote MCP (Streamable HTTP) at {mcp_url}  (public URL for chat apps: minion share)", flush=True)
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
