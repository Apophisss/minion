"""MCP server (stdio, zero dependencies): gives any MCP client desktops to use.

    claude mcp add minion -- uvx minion-desktop mcp

Implements the Model Context Protocol's tools surface (initialize, tools/list,
tools/call, ping, progress notifications) over newline-delimited JSON-RPC.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import traceback
from concurrent.futures import Future
from pathlib import Path

from . import __version__, config, profiles
from .backends import get_backend
from .desktop import Desktop
from .errors import MinionError, NotFound

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = """\
Minion gives you real Linux desktops (isolated containers with GUI apps). Typical loop:
1. desktop(action="create", profile=...) — browser, office (LibreOffice), dev (git/Python/Node/Chromium), research, data, base.
2. see() — read the screen as text: windows plus UI elements with @ids. Cheap and exact; prefer it over screenshots.
3. act(actions=[...]) — click/type/key/scroll/fill/drag using @ids, visible text ("Save") or "x,y" pixels.
   Batch several actions in one call; the reply says what changed.
4. screenshot() when you need to look (layout, images, charts); marks=true labels clickable elements with @ids.
Use run() for shell commands and files(action=...) to move files — far faster than doing it through the GUI.
open() launches apps ("writer", "calc", "firefox"), URLs or files. view() gives the human a live link to watch or take over;
with a message it hands control to the human (e.g. for a login or CAPTCHA) and waits until they are done.
"""

DESKTOP_PROP = {"type": "string", "description": "Desktop name (default: the one you created or used last)."}

TOOLS = [
    {
        "name": "desktop",
        "description": (
            "Create and manage Linux desktops. Each desktop is an isolated computer with GUI apps that you "
            "drive with `see`, `screenshot` and `act`.\n"
            "Actions: create, list, profiles, remove, freeze (pause: 0% CPU; any later call wakes it), thaw, "
            "fork (clone the disk state into a new desktop to try something risky), snapshot, restore, replay "
            "(save an HTML timeline of everything done so far).\n"
            "Profiles: browser (Firefox, ad/cookie-banner blocking), office (LibreOffice Writer/Calc/Impress + "
            "Firefox), dev (git, Python, Node.js, Chromium, Geany, terminal), research (Firefox + PDF/notes "
            "tools), data (office + pandas/matplotlib), base (minimal)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create",
                        "list",
                        "profiles",
                        "remove",
                        "freeze",
                        "thaw",
                        "fork",
                        "snapshot",
                        "restore",
                        "replay",
                        "info",
                    ],
                },
                "profile": {"type": "string", "description": "Profile for create (default: browser)."},
                "name": {"type": "string", "description": "Desktop name. For create/fork: the new name (optional)."},
                "size": {
                    "type": "string",
                    "description": "Screen size for create: 1280x800 (default) or e.g. 1024x768 for cheaper screenshots.",
                },
                "tag": {"type": "string", "description": "Snapshot tag for snapshot/restore."},
            },
            "required": ["action"],
        },
        "annotations": {"title": "Manage desktops", "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "see",
        "description": (
            "Read the screen as text: open windows, then the focused window's UI elements with @ids, roles, "
            "names, values, states and center coordinates (from the accessibility tree; OCR text when an app "
            "exposes none). Exact for text and far cheaper than a screenshot. Use the @ids as targets in `act`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "ocr": {
                    "type": "boolean",
                    "description": "Also read text with OCR (slower). Use for canvases, images, or apps that expose no UI tree.",
                },
                "window": {
                    "type": "string",
                    "description": "Describe this window (title, app or index) instead of the focused one.",
                },
                "full_text": {
                    "type": "boolean",
                    "description": "Keep paragraphs whole instead of truncating them (to read an article or document).",
                },
            },
        },
        "annotations": {"title": "See the screen as text", "readOnlyHint": True},
    },
    {
        "name": "screenshot",
        "description": (
            "Look at the screen (PNG). Pixel coordinates in the full screenshot are desktop coordinates for `act`. "
            "marks=true draws the @ids of clickable elements on the image. region=[x, y, w, h] crops; with "
            "zoom=true the region is magnified to read small details (coordinates in the reply explain the mapping)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "marks": {"type": "boolean", "description": "Label clickable elements with their @ids."},
                "region": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "[x, y, width, height] to crop.",
                },
                "zoom": {"type": "boolean", "description": "Magnify the region to 1024 px wide."},
                "grid": {"type": "boolean", "description": "Overlay a labelled 100 px coordinate grid."},
            },
        },
        "annotations": {"title": "Screenshot", "readOnlyHint": True},
    },
    {
        "name": "act",
        "description": (
            "Use the mouse and keyboard. Runs the actions in order, stops at the first failure, waits for the "
            "screen to settle, then reports what changed (windows opened/closed, focus, changed region).\n"
            "Each action is an object with an `action` field:\n"
            '- click | double_click | right_click: target (omit to click where the mouse is); modifiers e.g. "ctrl"\n'
            "- move: target (hover)\n- drag: from, to\n"
            "- type: text (\\n presses Enter, \\t presses Tab)\n- paste: text (instant, through the clipboard)\n"
            "- fill: target, text (replace a field's contents)\n"
            '- key: keys such as "ctrl+s", "Return", "Escape", "alt+Tab", "ctrl+shift+t"; repeat\n'
            "- scroll: direction (up|down|left|right), amount (default 3), optional target\n"
            "- wait: seconds\n- wait_for: text, timeout (default 10); gone=true waits until it disappears\n"
            "- focus: window (title or app)\n"
            'Targets: "@12" (an id from the latest `see`), visible text like "Save" or "Sign in", or "x,y" pixels.'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "click",
                                    "double_click",
                                    "triple_click",
                                    "right_click",
                                    "middle_click",
                                    "move",
                                    "drag",
                                    "type",
                                    "paste",
                                    "fill",
                                    "key",
                                    "scroll",
                                    "wait",
                                    "wait_for",
                                    "focus",
                                    "mouse_down",
                                    "mouse_up",
                                    "hold_key",
                                ],
                            },
                            "target": {"type": "string", "description": '@id, visible text, or "x,y".'},
                            "text": {"type": "string"},
                            "keys": {"type": "string"},
                            "repeat": {"type": "integer"},
                            "modifiers": {"type": "string"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                            "amount": {"type": "integer"},
                            "seconds": {"type": "number"},
                            "timeout": {"type": "number"},
                            "gone": {"type": "boolean"},
                            "window": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                },
                "desktop": DESKTOP_PROP,
                "screenshot": {"type": "boolean", "description": "Attach a screenshot taken after the actions."},
                "see": {"type": "boolean", "description": "Attach a fresh `see` text after the actions."},
            },
            "required": ["actions"],
        },
        "annotations": {"title": "Mouse and keyboard", "destructiveHint": True},
    },
    {
        "name": "open",
        "description": (
            'Open something in the desktop and wait for its window: a profile app ("writer", "calc", '
            '"impress", "firefox", "terminal", "chromium", "geany"), a URL ("github.com"), a file '
            'inside the desktop ("~/Documents/report.docx"), or a shell command for a GUI program.'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}, "desktop": DESKTOP_PROP},
            "required": ["target"],
        },
        "annotations": {"title": "Open app, URL or file"},
    },
    {
        "name": "run",
        "description": (
            "Run a shell command inside the desktop (bash, as the desktop user, with sudo available) and get "
            "stdout, stderr and the exit code. Faster and more exact than the GUI for files, installs "
            "(sudo apt-get install -y ...), git, scripts and converting documents. background=true for servers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "description": "Seconds (default 120)."},
                "background": {"type": "boolean"},
                "desktop": DESKTOP_PROP,
            },
            "required": ["command"],
        },
        "annotations": {"title": "Run a shell command", "destructiveHint": True},
    },
    {
        "name": "files",
        "description": (
            "Move files between this machine and a desktop, or read/write text files in it. "
            "upload: local_path → path; download: path → local_path; read: path → text; write: text → path. "
            "Desktop paths may start with ~ (the desktop user's home)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["upload", "download", "read", "write"]},
                "path": {"type": "string", "description": "Path inside the desktop."},
                "local_path": {
                    "type": "string",
                    "description": "Path on this machine (upload source / download destination).",
                },
                "text": {"type": "string", "description": "Content for write."},
                "desktop": DESKTOP_PROP,
            },
            "required": ["action", "path"],
        },
        "annotations": {"title": "Files"},
    },
    {
        "name": "view",
        "description": (
            "Get a live link where the human can watch the desktop and take over the mouse and keyboard. "
            'With `message`, hand control to the human (e.g. "Please sign in to your Google account") and '
            "wait until they press Done (up to `timeout` seconds); returns their note."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "message": {"type": "string"},
                "timeout": {"type": "number", "description": "Seconds to wait for the human (default 600)."},
            },
        },
        "annotations": {"title": "Live view / hand off to the human"},
    },
]


class ToolError(Exception):
    pass


class Server:
    def __init__(self, preload: str | None = None, idle_freeze: float = 600):
        self.out_lock = threading.Lock()
        self.current: str | None = None
        self.desktops: dict[str, Desktop] = {}
        self.pending: dict[str, Future] = {}
        self.pending_lock = threading.Lock()
        self.backend = get_backend()
        self.protocol = PROTOCOL_VERSIONS[0]
        self.idle_freeze = idle_freeze
        if preload:
            threading.Thread(target=self._preload, args=(preload,), daemon=True).start()
        if idle_freeze and idle_freeze > 0:
            from .reaper import start_reaper

            start_reaper(self.backend, idle_freeze)

    # -- io -----------------------------------------------------------------
    def send(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        with self.out_lock:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()

    def log(self, text: str) -> None:
        sys.stderr.write(f"[minion] {text}\n")
        sys.stderr.flush()

    def _preload(self, names: str) -> None:
        for n in [x.strip() for x in names.split(",") if x.strip()]:
            try:
                self.backend.prepare(profiles.get(n), progress=None)
                self.log(f"profile {n} ready")
            except Exception as e:
                self.log(f"preload {n} failed: {e}")

    # -- protocol -----------------------------------------------------------
    def handle(self, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method is None:
            return  # a response to something we never send
        if mid is None:
            return  # notifications: initialized, cancelled, ...
        try:
            if method == "initialize":
                requested = (msg.get("params") or {}).get("protocolVersion")
                self.protocol = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "minion", "title": "Minion desktops", "version": __version__},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                threading.Thread(target=self._call_tool, args=(mid, msg.get("params") or {}), daemon=True).start()
                return
            elif method in ("resources/list", "resources/templates/list"):
                result = {"resources": []} if method == "resources/list" else {"resourceTemplates": []}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                self.send(
                    {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
                )
                return
            self.send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as e:
            self.send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})

    def _call_tool(self, mid, params: dict) -> None:
        name = params.get("name")
        args = params.get("arguments") or {}
        token = (params.get("_meta") or {}).get("progressToken")
        counter = [0]

        def progress(text: str) -> None:
            if token is None:
                return
            counter[0] += 1
            self.send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/progress",
                    "params": {"progressToken": token, "progress": counter[0], "message": text[-200:]},
                }
            )

        try:
            fn = getattr(self, f"tool_{name}", None)
            if fn is None:
                raise ToolError(f"unknown tool {name!r}")
            content = fn(args, progress)
            result = {"content": content, "isError": False}
        except (ToolError, MinionError) as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:  # report instead of crashing the session
            self.log(traceback.format_exc())
            result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        self.send({"jsonrpc": "2.0", "id": mid, "result": result})

    # -- helpers ------------------------------------------------------------
    def desk(self, args: dict) -> Desktop:
        name = args.get("desktop") or self.current
        if not name:
            try:
                d = Desktop.attach(None, self.backend)
            except NotFound:
                raise ToolError(
                    'No desktop yet. Create one: desktop(action="create", profile="browser") '
                    "— profiles: browser, office, dev, research, data, base."
                ) from None
            name = d.name
        if name not in self.desktops:
            self.desktops[name] = Desktop(name, self.backend)
        self.current = name
        return self.desktops[name]

    @staticmethod
    def text(t: str) -> dict:
        return {"type": "text", "text": t}

    @staticmethod
    def image(data_b64: str, mime: str = "image/png") -> dict:
        return {"type": "image", "data": data_b64, "mimeType": mime}

    def _view_url(self, name: str) -> str | None:
        try:
            from .server import ensure_server

            base, token = ensure_server()
            return f"{base}/view/{name}?token={token}"
        except Exception as e:
            self.log(f"live view unavailable: {e}")
            return None

    # -- tools --------------------------------------------------------------
    def tool_desktop(self, args: dict, progress) -> list:
        action = (args.get("action") or "").lower()
        be = self.backend
        if action == "profiles":
            reg = profiles.load_all()
            lines = [f"- {n}: {reg[n].description}" for n in profiles.names(reg)]
            return [self.text("Profiles:\n" + "\n".join(lines))]
        if action == "list":
            desks = be.list()
            if not desks:
                return [self.text('No desktops. Create one with action="create".')]
            lines = [
                f"- {d.name} ({d.profile}, {d.size}, {'frozen' if d.state == 'paused' else d.state})"
                + (" ← current" if d.name == self.current else "")
                for d in desks
            ]
            return [self.text("Desktops:\n" + "\n".join(lines))]
        if action == "create":
            return self._create(args, progress)
        name = args.get("name") or args.get("desktop")
        d = self.desk({"desktop": name})
        if action == "info":
            hello = d.hello()
            info = d.info()
            return [
                self.text(
                    json.dumps(
                        {**info.to_dict(), "apps": hello.get("apps"), "features": hello.get("features")}, indent=2
                    )
                )
            ]
        if action == "remove":
            d.remove()
            self.desktops.pop(d.name, None)
            if self.current == d.name:
                self.current = None
            return [self.text(f"Removed {d.name}.")]
        if action == "freeze":
            d.freeze()
            return [self.text(f"{d.name} is frozen (0% CPU). Any tool call on it wakes it up.")]
        if action == "thaw":
            d.thaw()
            return [self.text(f"{d.name} is running.")]
        if action == "fork":
            new = d.fork(args.get("name") if args.get("name") != d.name else None, progress=progress)
            self.desktops[new.name] = new
            self.current = new.name
            return [
                self.text(
                    f"Forked {d.name} → {new.name} (now the current desktop). The fork has the same "
                    "files; apps start fresh."
                )
            ]
        if action == "snapshot":
            tag = d.snapshot(args.get("tag"))
            return [self.text(f'Saved snapshot {tag!r} of {d.name}. Restore with action="restore", tag="{tag}".')]
        if action == "restore":
            if not args.get("tag"):
                snaps = be.snapshots(d.name)
                raise ToolError("restore needs a tag. Snapshots: " + (", ".join(s.tag for s in snaps) or "none"))
            d.restore(args["tag"])
            return [self.text(f"{d.name} restored to {args['tag']!r} (apps start fresh).")]
        if action == "replay":
            path = Path(tempfile.gettempdir()) / f"minion-{d.name}-replay.html"
            d.recording("html", path)
            return [self.text(f"Timeline of everything done on {d.name}: {path}")]
        raise ToolError(f"unknown action {action!r}")

    def _create(self, args: dict, progress) -> list:
        profile = args.get("profile") or config.DEFAULT_PROFILE
        name = args.get("name")
        key = f"{profile}:{name or ''}"
        with self.pending_lock:
            fut = self.pending.get(key)
            if fut is None:
                fut = Future()
                self.pending[key] = fut

                def work():
                    try:
                        d = Desktop.create(
                            profile,
                            name=name,
                            size=args.get("size"),
                            backend=self.backend,
                            progress=lambda line: (self.log(line), progress(line)),
                        )
                        fut.set_result(d)
                    except BaseException as e:
                        fut.set_exception(e)

                threading.Thread(target=work, daemon=True).start()
        wait = config.env_float("MINION_MCP_CREATE_WAIT", 240)
        try:
            d = fut.result(timeout=wait)
        except TimeoutError:
            return [
                self.text(
                    f"Still preparing the {profile!r} desktop (the first run downloads or builds its "
                    'image, which can take a few minutes). Call desktop(action="create") again with the '
                    "same arguments to keep waiting — the work continues in the background."
                )
            ]
        finally:
            with self.pending_lock:
                if fut.done() and self.pending.get(key) is fut:
                    self.pending.pop(key, None)
        self.desktops[d.name] = d
        self.current = d.name
        hello = d.hello()
        prof = profiles.get(profile)
        w, h = hello["screen"]
        lines = [
            f"Desktop {d.name} is ready ({profile}, {w}x{h}). It is now the current desktop.",
            f"Apps (use with open): {', '.join(a.lower() for a in hello.get('apps', []))}",
        ]
        if prof.merged("tips"):
            lines.append("Tips: " + prof.merged("tips"))
        url = self._view_url(d.name)
        if url:
            lines.append(f"Live view for the human (share it if useful): {url}")
        lines.append("Next: see() to read the screen, or open() an app/URL.")
        return [self.text("\n".join(lines))]

    def tool_see(self, args: dict, progress) -> list:
        d = self.desk(args)
        ocr = True if args.get("ocr") else "auto"
        obs = d.see(ocr=ocr, window=args.get("window"), full_text=bool(args.get("full_text")))
        return [self.text(obs.text)]

    def tool_screenshot(self, args: dict, progress) -> list:
        d = self.desk(args)
        region = args.get("region")
        zoom = bool(args.get("zoom")) and region
        shot = d.screenshot(
            region=region, width=1024 if zoom else None, marks=bool(args.get("marks")), grid=bool(args.get("grid"))
        )
        if region:
            x, y = shot.region[0], shot.region[1]
            note = (
                f"Region {list(shot.region)} at {shot.scale:g}x. Desktop coordinates = "
                f"({x} + px/{shot.scale:g}, {y} + py/{shot.scale:g})."
            )
        else:
            note = f"Screen {shot.width}x{shot.height}; image pixels = desktop coordinates."
        if args.get("marks"):
            note += " Pink labels are @ids you can use as act targets."
        return [self.image(shot.base64(), shot.mime), self.text(note)]

    def tool_act(self, args: dict, progress) -> list:
        d = self.desk(args)
        actions = args.get("actions")
        if not actions:
            raise ToolError('act needs actions, e.g. [{"action": "click", "target": "@3"}]')
        res = d.act(actions, screenshot=bool(args.get("screenshot")), see=bool(args.get("see")), check=False)
        out = [self.text(res.summary)]
        if res.observation is not None:
            out.append(self.text(res.observation.text))
        if res.screenshot is not None:
            out.append(self.image(res.screenshot.base64(), res.screenshot.mime))
        if not res.ok:
            raise ToolError(res.summary)
        return out

    def tool_open(self, args: dict, progress) -> list:
        d = self.desk(args)
        res = d.open(args.get("target") or "")
        w = res.get("window")
        if w:
            return [self.text(f'Opened {res["command"]} → window "{w["title"]}" ({w["app"]}). Use see() to read it.')]
        if "error" in res:
            raise ToolError(f"{res['command']}: {res['error']}")
        return [
            self.text(
                f"Launched {res['command']}; no new window appeared yet (it may still be loading — check with see())."
            )
        ]

    def tool_run(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("command"):
            raise ToolError("run needs a command")
        res = d.run(args["command"], timeout=float(args.get("timeout") or 120), background=bool(args.get("background")))
        if args.get("background"):
            return [self.text(f"Started in the background (pid {res.pid}).")]
        parts = [f"exit code: {res.code}" + (" (timed out)" if res.timed_out else "")]
        if res.stdout:
            parts.append("stdout:\n" + res.stdout)
        if res.stderr:
            parts.append("stderr:\n" + res.stderr)
        return [self.text("\n".join(parts))]

    def tool_files(self, args: dict, progress) -> list:
        d = self.desk(args)
        action = args.get("action")
        path = args.get("path") or ""
        if action == "upload":
            local = os.path.expanduser(args.get("local_path") or "")
            if not local or not os.path.exists(local):
                raise ToolError(f"local_path {local!r} does not exist on this machine")
            d.upload(local, path or "~/")
            return [self.text(f"Uploaded {local} → {d.name}:{path or '~/'}")]
        if action == "download":
            local = os.path.expanduser(args.get("local_path") or ".")
            out = d.download(path, local)
            return [self.text(f"Downloaded {d.name}:{path} → {out}")]
        if action == "read":
            text = d.read_text(path)
            if len(text) > 100_000:
                text = text[:100_000] + f"\n… [{len(text) - 100_000} more characters]"
            return [self.text(text)]
        if action == "write":
            d.write_text(path, args.get("text") or "")
            return [self.text(f"Wrote {len(args.get('text') or '')} characters to {d.name}:{path}")]
        raise ToolError("action must be upload, download, read or write")

    def tool_view(self, args: dict, progress) -> list:
        d = self.desk(args)
        url = self._view_url(d.name)
        if not url:
            raise ToolError("the live view server could not start")
        message = args.get("message")
        if not message:
            return [self.text(f"Live view of {d.name}: {url}\nThe human can watch and take over mouse and keyboard.")]
        from .server import handoff_wait

        timeout = float(args.get("timeout") or 600)
        progress(f"Waiting for the human at {url}")
        self.log(f"handoff on {d.name}: {message} — {url}")
        note = handoff_wait(d.name, message, timeout)
        if note is None:
            return [self.text(f"The human did not finish within {timeout:.0f}s. Link: {url}")]
        said = f' They said: "{note}".' if note else ""
        return [self.text(f"The human is done.{said} Call see() to check the screen.")]


def main(preload: str | None = None, idle_freeze: float = 600) -> None:
    server = Server(preload=preload, idle_freeze=idle_freeze)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            server.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if isinstance(msg, list):  # JSON-RPC batch (2025-03-26)
            for m in msg:
                server.handle(m)
        else:
            server.handle(msg)


if __name__ == "__main__":
    main()
