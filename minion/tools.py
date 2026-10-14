"""One toolset for every agent.

The same nine tools (or one compact `computer` tool) are served over MCP, HTTP and Python,
and exported in the function-calling formats of every major model API:

    from minion.tools import Toolkit

    tk = Toolkit()
    tools = tk.definitions("openai")     # or "anthropic", "gemini", "openai-responses", "mcp"
    ...                                   # give `tools` to your model; when it calls one:
    result = tk.call(name, arguments)     # -> ToolResult(.text, .images, .is_error)
    messages += result.to_openai(tool_call_id)

Only the standard library is used. Results carry text and (for screenshots) images; helpers
convert them to each API's message shapes.
"""

from __future__ import annotations

import copy
import json
import os
import shlex
import tempfile
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path

from . import config, profiles
from .backends import Backend
from .desktop import Desktop, _backend
from .errors import MinionError, NotFound

INSTRUCTIONS = """\
Minion gives you real Linux computers (isolated desktops with GUI apps; any program can be installed).
1. desktop(action="create", profile=...) — browser, office (LibreOffice), dev (git/Python/Node/Chromium),
   research, data, base; count=N creates several at once for parallel work.
2. see() — the screen as text: windows + UI elements with stable @ids. Exact and cheap; prefer it to
   screenshots. see(changes=true) returns only what changed since your last look.
3. act(actions=[...]) — click/type/key/scroll/fill/drag by @id, visible text ("Save") or "x,y". Batch
   several actions per call; the reply says what changed (observe="changes" adds the changed UI).
4. screenshot() when looks matter; marks=true labels clickable elements; detail="low" costs 4x fewer tokens.
5. script(code=...) — for loops/repetition: Python runs inside the desktop with click/write/key/see/...;
   only what it prints comes back. run() executes shell commands (sudo works; `minion-install X`
   installs any app: apt names, .deb/.AppImage URLs, pip:, npm:).
open() launches apps/URLs/files. files() moves files. view() gives a human a live link or hands off
(logins, CAPTCHAs) until they press Done.
"""

DESKTOP_PROP = {"type": "string", "description": "Desktop name (default: the one you created or used last)."}

TOOLS: list[dict] = [
    {
        "name": "desktop",
        "description": (
            "Create and manage Linux desktops (isolated computers with GUI apps). Actions: create (profile, "
            "name, size, count for several at once), list, profiles, remove, freeze (0% CPU; any later call "
            "wakes it), thaw, fork (clone disk state into a new desktop to try something risky), snapshot, "
            "restore, replay (HTML timeline of everything done). Profiles: browser (Firefox, blocks ads and "
            "cookie banners), office (LibreOffice + Firefox), dev (git, Python, Node.js, Chromium, IDE), "
            "research (Firefox + PDF/notes tools), data (office + pandas/matplotlib), base (minimal)."
        ),
        "input_schema": {
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
                "name": {"type": "string", "description": "create/fork: name of the new desktop (optional)."},
                "desktop": DESKTOP_PROP,
                "size": {"type": "string", "description": "Screen for create: 1280x800 (default), 1024x768 cheaper."},
                "count": {"type": "integer", "description": "create: how many desktops (parallel work). Default 1."},
                "tag": {"type": "string", "description": "Snapshot tag for snapshot/restore."},
            },
            "required": ["action"],
        },
        "annotations": {"title": "Manage desktops", "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "see",
        "description": (
            "Read the screen as text: windows, then the focused window's UI elements with stable @ids, roles, "
            "names, values, states and center coordinates (accessibility tree; OCR when an app exposes none). "
            "Exact and far cheaper than a screenshot. changes=true returns only what changed since your last look."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "changes": {"type": "boolean", "description": "Only what changed since your previous see()."},
                "ocr": {
                    "type": "boolean",
                    "description": "Also read text by OCR (slower; canvases, images, remote screens).",
                },
                "window": {"type": "string", "description": "Describe this window (title, app or index) instead."},
                "full_text": {"type": "boolean", "description": "Keep paragraphs whole (to read an article/document)."},
            },
        },
        "annotations": {"title": "See the screen as text", "readOnlyHint": True},
    },
    {
        "name": "screenshot",
        "description": (
            "Look at the screen (PNG). Image pixels are desktop coordinates unless scaled or cropped (the reply "
            'explains the mapping). marks=true draws @ids on clickable elements. detail="low" halves each side '
            "(about 4x fewer image tokens). region=[x,y,w,h] crops; zoom=true magnifies the region."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "marks": {"type": "boolean", "description": "Label clickable elements with their @ids."},
                "detail": {"type": "string", "enum": ["full", "low"], "description": "low = half size."},
                "region": {"type": "array", "items": {"type": "integer"}, "description": "[x, y, width, height]."},
                "zoom": {"type": "boolean", "description": "Magnify the region to 1024 px wide."},
                "grid": {"type": "boolean", "description": "Overlay a labelled 100 px coordinate grid."},
            },
        },
        "annotations": {"title": "Screenshot", "readOnlyHint": True},
    },
    {
        "name": "act",
        "description": (
            "Mouse and keyboard. Runs the actions in order, stops at the first failure, waits for the screen to "
            "settle and reports what changed. Actions (objects with an `action` field): click | double_click | "
            'right_click (target; modifiers "ctrl"), move (target), drag (from, to), type (text; \\n = Enter, '
            '\\t = Tab), paste (text), fill (target, text: replace a field), key (keys like "ctrl+s", "Return", '
            '"alt+Tab"; repeat), scroll (direction up|down|left|right, amount, target), wait (seconds), '
            'wait_for (text, timeout; gone=true), focus (window). Targets: "@12" (from see), visible text '
            '("Save"), or "x,y". observe: summary (default) | changes (+ the changed UI as text) | see | '
            "screenshot | crop (image of just the changed region)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
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
                "observe": {"type": "string", "enum": ["summary", "changes", "see", "screenshot", "crop"]},
            },
            "required": ["actions"],
        },
        "annotations": {"title": "Mouse and keyboard", "destructiveHint": True},
    },
    {
        "name": "open",
        "description": (
            'Open something and wait until its window is ready: a profile app ("writer", "calc", "impress", '
            '"firefox", "terminal", "chromium"), a URL ("github.com"), a file in the desktop '
            '("~/Documents/report.docx"), or a shell command for any GUI program.'
        ),
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}, "desktop": DESKTOP_PROP},
            "required": ["target"],
        },
        "annotations": {"title": "Open app, URL or file"},
    },
    {
        "name": "run",
        "description": (
            "Run a bash command inside the desktop (as the desktop user; sudo works) and get stdout, stderr and "
            "the exit code. Best for files, data, git, conversions. Install anything with `minion-install <name "
            "or URL>` (apt packages, .deb/.AppImage/archive URLs, pip:pkg, npm:pkg). background=true for servers."
        ),
        "input_schema": {
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
        "name": "script",
        "description": (
            "Run Python inside the desktop to do many GUI steps in one call (loops, retries, data entry): only "
            "what it prints comes back. Preloaded: see(changes=False), elements(role, name), find(text), "
            'cells() (visible spreadsheet cells {"A1": ...}), click(target), double_click, right_click, '
            "write(text), paste(text), key(keys), scroll(dir, n), fill(target, text), drag(a, b), wait(s), "
            "wait_for(text, timeout) -> bool, launch(app_or_url), run(cmd) -> dict, windows(), focus(title), "
            "clipboard(text=None). Targets as in act. Errors raise MinionScriptError."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source."},
                "timeout": {"type": "number", "description": "Seconds (default 120)."},
                "desktop": DESKTOP_PROP,
            },
            "required": ["code"],
        },
        "annotations": {"title": "Script the desktop", "destructiveHint": True},
    },
    {
        "name": "files",
        "description": (
            "Move files between this machine and a desktop, or read/write text files in it. upload: local_path "
            "-> path; download: path -> local_path; read: path -> text; write: text -> path. Desktop paths may "
            "start with ~."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["upload", "download", "read", "write"]},
                "path": {"type": "string", "description": "Path inside the desktop."},
                "local_path": {"type": "string", "description": "Path on this machine."},
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
            "A live link where the human can watch the desktop and take over mouse and keyboard. With message, "
            'hand control to the human ("Please sign in to your bank") and wait until they press Done '
            "(up to timeout seconds); returns their note."
        ),
        "input_schema": {
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

COMPUTER_TOOL = {
    "name": "computer",
    "description": (
        "Use Linux computers through one command per call (CLI syntax). Commands: create [profile] [-n N] · "
        "list · use NAME · remove [NAME] · see [--changes] [--ocr] [--full] · screenshot [--marks] [--low] "
        "[--zoom x,y,w,h] · click TARGET · dclick TARGET · rclick TARGET · type TEXT · key KEYS · "
        "scroll up|down [N] · fill TARGET TEXT · drag FROM TO · wait-for TEXT · open TARGET · run SHELL... · "
        "script PYTHON... · view [MESSAGE]. Targets: @id from see, visible text (quote it), or x,y. "
        "Profiles: browser, office, dev, research, data, base. Example: create office · open calc · see · "
        "click @12 · type 'Total' · key Return."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "One command, e.g. `click @12`."}},
        "required": ["command"],
    },
    "annotations": {"title": "Computer"},
}

GEMINI_KEYS = {
    "type",
    "description",
    "properties",
    "required",
    "enum",
    "items",
    "format",
    "nullable",
    "minimum",
    "maximum",
}


def _gemini_schema(schema: dict) -> dict:
    """Gemini accepts an OpenAPI subset: drop the keywords it rejects."""
    out = {}
    for k, v in schema.items():
        if k not in GEMINI_KEYS:
            continue
        if k == "properties":
            out[k] = {pk: _gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _gemini_schema(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
@dataclass
class ToolResult:
    content: list[dict] = field(default_factory=list)  # {"type":"text","text"} | {"type":"image","data","mimeType"}
    is_error: bool = False

    @property
    def text(self) -> str:
        return "\n".join(c["text"] for c in self.content if c["type"] == "text")

    @property
    def images(self) -> list[tuple[str, str]]:
        """[(mime type, base64 data)]"""
        return [(c["mimeType"], c["data"]) for c in self.content if c["type"] == "image"]

    def to_mcp(self) -> dict:
        return {"content": self.content, "isError": self.is_error}

    def to_anthropic(self, tool_use_id: str) -> dict:
        """A `tool_result` content block for the Messages API (images included)."""
        blocks = []
        for c in self.content:
            if c["type"] == "text":
                blocks.append({"type": "text", "text": c["text"]})
            else:
                blocks.append(
                    {"type": "image", "source": {"type": "base64", "media_type": c["mimeType"], "data": c["data"]}}
                )
        out = {"type": "tool_result", "tool_use_id": tool_use_id, "content": blocks}
        if self.is_error:
            out["is_error"] = True
        return out

    def to_openai(self, tool_call_id: str) -> list[dict]:
        """Chat Completions messages: the tool message, plus a user message carrying any images
        (tool messages there cannot hold images)."""
        msgs = [{"role": "tool", "tool_call_id": tool_call_id, "content": self.text or "(no text)"}]
        if self.images:
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Screenshot from the previous tool call:"},
                        *[{"type": "image_url", "image_url": {"url": f"data:{m};base64,{d}"}} for m, d in self.images],
                    ],
                }
            )
        return msgs

    def to_openai_responses(self, call_id: str) -> list[dict]:
        """Responses API input items: a function_call_output, plus an input_image message if needed."""
        items = [{"type": "function_call_output", "call_id": call_id, "output": self.text or "(no text)"}]
        if self.images:
            items.append(
                {
                    "role": "user",
                    "content": [{"type": "input_image", "image_url": f"data:{m};base64,{d}"} for m, d in self.images],
                }
            )
        return items

    def to_gemini(self, name: str) -> list[dict]:
        """Gemini parts: a function_response, plus inline image parts."""
        parts = [{"function_response": {"name": name, "response": {"result": self.text, "error": self.is_error}}}]
        for m, d in self.images:
            parts.append({"inline_data": {"mime_type": m, "data": d}})
        return parts


class ToolError(MinionError):
    pass


def _text(t: str) -> dict:
    return {"type": "text", "text": t}


def _image(data_b64: str, mime: str = "image/png") -> dict:
    return {"type": "image", "data": data_b64, "mimeType": mime}


# ---------------------------------------------------------------------------
class Toolkit:
    """The tools, bound to a backend and a notion of "the current desktop"."""

    def __init__(self, backend: Backend | str | None = None, *, in_process_viewer: bool | None = None):
        self.backend = _backend(backend)
        self.current: str | None = None
        self.desktops: dict[str, Desktop] = {}
        self._pending: dict[str, Future] = {}
        self._lock = threading.Lock()
        self.in_process_viewer = in_process_viewer

    # -- definitions ----------------------------------------------------
    def definitions(self, format: str = "mcp", *, compact: bool = False) -> list[dict]:
        """Tool definitions for: mcp, openai (Chat Completions), openai-responses, anthropic, gemini."""
        tools = [COMPUTER_TOOL] if compact else TOOLS
        fmt = format.lower()
        out = []
        for t in tools:
            schema = copy.deepcopy(t["input_schema"])
            if fmt == "mcp":
                out.append(
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": schema,
                        "annotations": t.get("annotations", {}),
                    }
                )
            elif fmt in ("openai", "openai-chat", "chat"):
                out.append(
                    {
                        "type": "function",
                        "function": {"name": t["name"], "description": t["description"], "parameters": schema},
                    }
                )
            elif fmt in ("openai-responses", "responses"):
                out.append(
                    {"type": "function", "name": t["name"], "description": t["description"], "parameters": schema}
                )
            elif fmt in ("anthropic", "claude"):
                out.append({"name": t["name"], "description": t["description"], "input_schema": schema})
            elif fmt in ("gemini", "google"):
                out.append({"name": t["name"], "description": t["description"], "parameters": _gemini_schema(schema)})
            else:
                raise MinionError(f"unknown format {format!r}: mcp, openai, openai-responses, anthropic, gemini")
        return out

    @property
    def names(self) -> list[str]:
        return [t["name"] for t in TOOLS] + ["computer"]

    # -- dispatch -------------------------------------------------------
    def call(self, name: str, arguments: dict | None = None, progress=None) -> ToolResult:
        """Run a tool. Errors come back as ToolResult(is_error=True) with a helpful message."""
        args = arguments if isinstance(arguments, dict) else {}
        if isinstance(arguments, str):  # some models send JSON strings
            try:
                args = json.loads(arguments) or {}
            except json.JSONDecodeError:
                args = {"command": arguments} if name == "computer" else {}
        fn = getattr(self, f"t_{name}", None) if name in self.names else None
        if fn is None:
            return ToolResult([_text(f"unknown tool {name!r}; tools: {', '.join(self.names)}")], True)
        try:
            return ToolResult(fn(args, progress or (lambda _line: None)))
        except MinionError as e:
            return ToolResult([_text(str(e))], True)
        except Exception as e:  # report instead of crashing the caller's agent loop
            return ToolResult([_text(f"{type(e).__name__}: {e}")], True)

    def functions(self) -> dict:
        """Plain Python callables (text in, text out) for frameworks that wrap functions as tools."""

        def make(tool_name):
            def fn(**kwargs):
                return self.call(tool_name, kwargs).text

            fn.__name__ = tool_name
            fn.__doc__ = next(t["description"] for t in TOOLS if t["name"] == tool_name)
            return fn

        return {t["name"]: make(t["name"]) for t in TOOLS}

    # -- helpers --------------------------------------------------------
    def desk(self, args: dict) -> Desktop:
        name = args.get("desktop") or self.current
        if not name:
            try:
                name = Desktop.attach(None, self.backend).name
            except NotFound:
                raise ToolError(
                    'No desktop yet. Create one: desktop(action="create", profile="browser") '
                    "(profiles: browser, office, dev, research, data, base)."
                ) from None
        if name not in self.desktops:
            try:
                self.backend.get(name)  # validate before making it current
            except NotFound:
                names = ", ".join(d.name for d in self.backend.list()) or "none"
                raise ToolError(f"No desktop named {name!r}. Desktops: {names}.") from None
            self.desktops[name] = Desktop(name, self.backend)
        self.current = name
        return self.desktops[name]

    def view_url(self, name: str) -> str | None:
        try:
            from .server import ensure_server

            base, token = ensure_server(self.in_process_viewer)
            return f"{base}/view/{name}" + (f"?token={token}" if token else "")
        except Exception:
            return None

    # -- tools ----------------------------------------------------------
    def t_desktop(self, args: dict, progress) -> list:
        action = (args.get("action") or "").lower()
        be = self.backend
        if action == "profiles":
            reg = profiles.load_all()
            return [_text("Profiles:\n" + "\n".join(f"- {n}: {reg[n].description}" for n in profiles.names(reg)))]
        if action == "list":
            desks = be.list()
            if not desks:
                return [_text('No desktops. Create one with action="create".')]
            lines = [
                f"- {d.name} ({d.profile}, {d.size}, {'frozen' if d.state == 'paused' else d.state})"
                + (" ← current" if d.name == self.current else "")
                for d in desks
            ]
            return [_text("Desktops:\n" + "\n".join(lines))]
        if action == "create":
            return self._create(args, progress)
        d = self.desk(args)
        if action == "info":
            hello = d.hello()
            return [
                _text(
                    json.dumps(
                        {**d.info().to_dict(), "apps": hello.get("apps"), "features": hello.get("features")}, indent=2
                    )
                )
            ]
        if action == "remove":
            d.remove()
            self.desktops.pop(d.name, None)
            if self.current == d.name:
                self.current = None
            return [_text(f"Removed {d.name}.")]
        if action == "freeze":
            d.freeze()
            return [_text(f"{d.name} is frozen (0% CPU). Any call on it wakes it up.")]
        if action == "thaw":
            d.thaw()
            return [_text(f"{d.name} is running.")]
        if action == "fork":
            new = d.fork(args.get("name"), progress=progress)
            self.desktops[new.name] = new
            self.current = new.name
            return [_text(f"Forked {d.name} → {new.name} (now current). Same files; apps start fresh.")]
        if action == "snapshot":
            tag = d.snapshot(args.get("tag"))
            return [_text(f'Saved snapshot {tag!r} of {d.name}. Restore: action="restore", tag="{tag}".')]
        if action == "restore":
            if not args.get("tag"):
                snaps = be.snapshots(d.name)
                raise ToolError("restore needs a tag. Snapshots: " + (", ".join(s.tag for s in snaps) or "none"))
            d.restore(args["tag"])
            return [_text(f"{d.name} restored to {args['tag']!r} (apps start fresh).")]
        if action == "replay":
            path = Path(tempfile.gettempdir()) / f"minion-{d.name}-replay.html"
            d.recording("html", path)
            return [_text(f"Timeline of everything done on {d.name}: {path}")]
        raise ToolError(f"unknown action {action!r}")

    def _create(self, args: dict, progress) -> list:
        profile = args.get("profile") or config.DEFAULT_PROFILE
        count = max(1, min(int(args.get("count") or 1), 20))
        name = args.get("name")
        key = f"{profile}:{name or ''}:{count}"
        with self._lock:
            fut = self._pending.get(key)
            if fut is None:
                fut = Future()
                self._pending[key] = fut

                def work():
                    try:
                        names = (
                            [None] * count
                            if not name
                            else ([name] if count == 1 else [f"{name}-{i}" for i in range(1, count + 1)])
                        )
                        if count == 1:
                            made = [
                                Desktop.create(
                                    profile,
                                    name=names[0],
                                    size=args.get("size"),
                                    backend=self.backend,
                                    progress=progress,
                                )
                            ]
                        else:
                            made = Desktop.create_many(
                                profile,
                                count,
                                names=names if name else None,
                                size=args.get("size"),
                                backend=self.backend,
                                progress=progress,
                            )
                        fut.set_result(made)
                    except BaseException as e:
                        fut.set_exception(e)

                threading.Thread(target=work, daemon=True).start()
        wait = config.env_float("MINION_MCP_CREATE_WAIT", 240)
        try:
            made = fut.result(timeout=wait)
        except TimeoutError:
            return [
                _text(
                    f"Still preparing the {profile!r} desktop (the first run downloads or builds its image). "
                    'Call desktop(action="create") again with the same arguments to keep waiting.'
                )
            ]
        finally:
            with self._lock:
                if fut.done() and self._pending.get(key) is fut:
                    self._pending.pop(key, None)
        for d in made:
            self.desktops[d.name] = d
        self.current = made[0].name
        prof = profiles.get(profile)
        hello = made[0].hello()
        w, h = hello["screen"]
        names = ", ".join(d.name for d in made)
        lines = [
            f"Ready: {names} ({profile}, {w}x{h}). Current desktop: {made[0].name}"
            + (" (pass desktop=NAME to use the others)." if len(made) > 1 else "."),
            f"Apps (open): {', '.join(a.lower() for a in hello.get('apps', []))}",
        ]
        if prof.merged("tips"):
            lines.append("Tips: " + prof.merged("tips"))
        url = self.view_url(made[0].name)
        if url:
            lines.append(f"Live view for the human: {url}")
        lines.append("Next: see() to read the screen, or open() an app/URL.")
        return [_text("\n".join(lines))]

    def t_see(self, args: dict, progress) -> list:
        d = self.desk(args)
        obs = d.see(
            ocr=True if args.get("ocr") else "auto",
            window=args.get("window"),
            full_text=bool(args.get("full_text")),
            changes=bool(args.get("changes")),
        )
        return [_text(obs.text)]

    def t_screenshot(self, args: dict, progress) -> list:
        d = self.desk(args)
        region = args.get("region")
        if region is not None and (not isinstance(region, list) or len(region) != 4):
            raise ToolError("region must be [x, y, width, height]")
        zoom = bool(args.get("zoom")) and region
        low = args.get("detail") == "low" and not zoom
        shot = d.screenshot(
            region=region,
            width=1024 if zoom else None,
            scale=0.5 if low else None,
            marks=bool(args.get("marks")),
            grid=bool(args.get("grid")),
        )
        if region or shot.scale != 1:
            x, y = shot.region[0], shot.region[1]
            note = (
                f"Image {shot.width}x{shot.height} of region {list(shot.region)} at {shot.scale:g}x: desktop "
                f"x = {x} + px/{shot.scale:g}, y = {y} + py/{shot.scale:g}. Prefer @ids from see() for clicks."
            )
        else:
            note = f"Screen {shot.width}x{shot.height}; image pixels = desktop coordinates."
        if args.get("marks"):
            note += " Pink labels are @ids usable as act targets."
        return [_image(shot.base64(), shot.mime), _text(note)]

    def t_act(self, args: dict, progress) -> list:
        d = self.desk(args)
        actions = args.get("actions")
        if not actions:
            raise ToolError('act needs actions, e.g. [{"action": "click", "target": "@3"}]')
        observe = args.get("observe") or "summary"
        res = d.act(actions, observe=observe, check=False)
        out = [_text(res.summary)]
        if res.observation is not None:
            out.append(_text(res.observation.text))
        for shot in (res.screenshot, res.crop):
            if shot is not None:
                out.append(_image(shot.base64(), shot.mime))
                if shot is res.crop:
                    x, y = shot.region[0], shot.region[1]
                    out.append(_text(f"Changed region at ({x},{y}): desktop = ({x} + px, {y} + py)."))
        if not res.ok:
            raise ToolError("\n".join(c["text"] for c in out if c["type"] == "text"))
        return out

    def t_open(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("target"):
            raise ToolError("open needs a target")
        res = d.open(args["target"])
        w = res.get("window")
        if w:
            return [_text(f'Opened {res["command"]} → window "{w["title"]}" ({w["app"]}). Use see() to read it.')]
        if "error" in res:
            raise ToolError(f"{res['command']}: {res['error']}")
        return [_text(f"Launched {res['command']}; no new window yet (it may still be loading — check see()).")]

    def t_run(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("command"):
            raise ToolError("run needs a command")
        res = d.run(args["command"], timeout=float(args.get("timeout") or 120), background=bool(args.get("background")))
        if args.get("background"):
            return [_text(f"Started in the background (pid {res.pid}).")]
        return [_text(_run_text(res.code, res.stdout, res.stderr, res.timed_out))]

    def t_script(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("code"):
            raise ToolError("script needs code")
        res = d.script(args["code"], timeout=float(args.get("timeout") or 120))
        text = _run_text(res.code, res.stdout, res.stderr, res.timed_out)
        if res.code != 0:
            raise ToolError(text)
        return [_text(text)]

    def t_files(self, args: dict, progress) -> list:
        d = self.desk(args)
        action, path = args.get("action"), args.get("path") or ""
        if action == "upload":
            local = os.path.expanduser(args.get("local_path") or "")
            if not local or not os.path.exists(local):
                raise ToolError(f"local_path {local!r} does not exist on this machine")
            d.upload(local, path or "~/")
            return [_text(f"Uploaded {local} → {d.name}:{path or '~/'}")]
        if action == "download":
            local = os.path.expanduser(args.get("local_path") or ".")
            return [_text(f"Downloaded {d.name}:{path} → {d.download(path, local)}")]
        if action == "read":
            text = d.read_text(path)
            if len(text) > 100_000:
                text = text[:100_000] + f"\n… [{len(text) - 100_000} more characters]"
            return [_text(text)]
        if action == "write":
            d.write_text(path, args.get("text") or "")
            return [_text(f"Wrote {len(args.get('text') or '')} characters to {d.name}:{path}")]
        raise ToolError("action must be upload, download, read or write")

    def t_view(self, args: dict, progress) -> list:
        d = self.desk(args)
        url = self.view_url(d.name)
        if not url:
            raise ToolError("the live view server could not start")
        message = args.get("message")
        if not message:
            return [_text(f"Live view of {d.name}: {url}\nThe human can watch and take over mouse and keyboard.")]
        from .server import handoff_wait

        timeout = float(args.get("timeout") or 600)
        progress(f"Waiting for the human at {url}")
        note = handoff_wait(d.name, message, timeout)
        if note is None:
            return [_text(f"The human did not finish within {timeout:.0f}s. Link: {url}")]
        said = f' They said: "{note}".' if note else ""
        return [_text(f"The human is done.{said} Call see() to check the screen.")]

    # -- one tool, CLI syntax ----------------------------------------------
    def t_computer(self, args: dict, progress) -> list:
        command = str(args.get("command") or "").strip()
        if not command:
            raise ToolError("computer needs a command, e.g. `see` or `click @12`")
        verb, _, rest = command.partition(" ")
        verb = verb.lower()
        rest = rest.strip()
        try:
            words = shlex.split(rest)
        except ValueError:
            words = rest.split()
        flags = {w for w in words if w.startswith("--")}
        plain = [w for w in words if not w.startswith("--")]

        def target(ws):
            if len(ws) == 2 and all(w.lstrip("-").isdigit() for w in ws):
                return f"{ws[0]},{ws[1]}"
            return " ".join(ws)

        if verb in ("create", "up", "new"):
            count = 1
            if "-n" in plain:
                i = plain.index("-n")
                count = int(plain[i + 1]) if i + 1 < len(plain) else 1
                plain = plain[:i] + plain[i + 2 :]
            return self.t_desktop(
                {"action": "create", "profile": plain[0] if plain else None, "count": count}, progress
            )
        if verb in ("list", "ls"):
            return self.t_desktop({"action": "list"}, progress)
        if verb == "profiles":
            return self.t_desktop({"action": "profiles"}, progress)
        if verb == "use":
            self.desk({"desktop": rest})
            return [_text(f"Current desktop: {rest}")]
        if verb in ("remove", "rm"):
            return self.t_desktop({"action": "remove", "desktop": rest or None}, progress)
        if verb in ("freeze", "thaw", "fork", "snapshot", "restore", "replay"):
            key = "tag" if verb in ("snapshot", "restore") else "name"
            return self.t_desktop({"action": verb, key: rest or None}, progress)
        if verb == "see":
            return self.t_see(
                {"changes": "--changes" in flags, "ocr": "--ocr" in flags, "full_text": "--full" in flags}, progress
            )
        if verb in ("screenshot", "shot"):
            a = {"marks": "--marks" in flags, "detail": "low" if "--low" in flags else "full"}
            for w in words:
                if w.startswith("--zoom="):
                    a.update(region=[int(v) for v in w[7:].split(",")], zoom=True)
            if "--zoom" in words:
                i = words.index("--zoom")
                a.update(region=[int(v) for v in words[i + 1].split(",")], zoom=True)
            return self.t_screenshot(a, progress)
        if verb in ("click", "dclick", "rclick", "move", "hover"):
            step = {
                "action": {"dclick": "double_click", "rclick": "right_click", "hover": "move"}.get(verb, verb),
                "target": target(plain),
            }
            return self.t_act({"actions": [step]}, progress)
        if verb == "type":
            return self.t_act({"actions": [{"action": "type", "text": " ".join(words) if words else rest}]}, progress)
        if verb in ("key", "press"):
            return self.t_act({"actions": [{"action": "key", "keys": k} for k in plain]}, progress)
        if verb == "scroll":
            return self.t_act(
                {
                    "actions": [
                        {
                            "action": "scroll",
                            "direction": plain[0] if plain else "down",
                            "amount": int(plain[1]) if len(plain) > 1 else 3,
                        }
                    ]
                },
                progress,
            )
        if verb == "fill":
            if len(plain) < 2:
                raise ToolError("fill TARGET TEXT")
            return self.t_act(
                {"actions": [{"action": "fill", "target": plain[0], "text": " ".join(plain[1:])}]}, progress
            )
        if verb == "drag":
            if len(plain) != 2:
                raise ToolError("drag FROM TO")
            return self.t_act({"actions": [{"action": "drag", "from": plain[0], "to": plain[1]}]}, progress)
        if verb in ("wait-for", "wait_for"):
            return self.t_act({"actions": [{"action": "wait_for", "text": " ".join(plain)}]}, progress)
        if verb == "open":
            return self.t_open({"target": rest}, progress)
        if verb in ("run", "exec", "sh"):
            return self.t_run({"command": rest}, progress)
        if verb in ("script", "py", "python"):
            return self.t_script({"code": rest}, progress)
        if verb == "view":
            return self.t_view({"message": rest or None}, progress)
        raise ToolError(f"unknown command {verb!r}. Try: see · click @12 · type hello · open firefox · run ls")


def _run_text(code, stdout: str, stderr: str, timed_out: bool) -> str:
    parts = [f"exit code: {code}" + (" (timed out)" if timed_out else "")]
    if stdout:
        parts.append("stdout:\n" + stdout)
    if stderr:
        parts.append("stderr:\n" + stderr)
    return "\n".join(parts)


def openapi(base_url: str = "http://127.0.0.1:4747") -> dict:
    """OpenAPI 3.1 for the tool endpoints (GPT Actions, Dify, n8n, LangChain OpenAPI toolkits...)."""
    paths = {}
    for t in TOOLS + [COMPUTER_TOOL]:
        paths[f"/api/tools/{t['name']}"] = {
            "post": {
                "operationId": t["name"],
                "summary": t.get("annotations", {}).get("title", t["name"]),
                "description": t["description"],
                "requestBody": {"required": True, "content": {"application/json": {"schema": t["input_schema"]}}},
                "responses": {
                    "200": {
                        "description": "Tool result",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ToolResult"}}},
                    }
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Minion desktops",
            "version": __import__("minion").__version__,
            "description": "Linux desktops for AI agents. " + INSTRUCTIONS,
        },
        "servers": [{"url": base_url}],
        "security": [{"bearer": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "ToolResult": {
                    "type": "object",
                    "properties": {
                        "isError": {"type": "boolean"},
                        "content": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["text", "image"]},
                                    "text": {"type": "string"},
                                    "data": {"type": "string", "description": "base64 image"},
                                    "mimeType": {"type": "string"},
                                },
                            },
                        },
                    },
                }
            },
        },
    }


__all__ = ["Toolkit", "ToolResult", "TOOLS", "COMPUTER_TOOL", "INSTRUCTIONS", "openapi"]
