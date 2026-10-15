"""One toolset for every agent.

The same nine tools (or one compact `computer` tool) are served over MCP, HTTP and Python,
and exported in the function-calling formats of every major model API:

    from minion.tools import Toolkit

    tk = Toolkit()
    tools = tk.definitions("openai")         # or "anthropic", "gemini", "openai-responses", "mcp"
    ...                                       # give `tools` to your model; when it calls some:
    messages += tk.run_calls(msg.tool_calls)  # run them all, get the reply messages in that API's shape
    result = tk.call(name, arguments)         # or one at a time -> ToolResult(.text, .images, .is_error)

Only the standard library is used. Results carry text and (for screenshots) images; helpers
convert them to each API's message shapes.
"""

from __future__ import annotations

import copy
import json
import os
import re
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
   research, data, windows (Windows .exe programs via Wine), base; count=N creates several at once.
2. see() — the screen as text: windows + UI elements with stable @ids. Exact and cheap; prefer it to
   screenshots. see(changes=true) returns only what changed since your last look.
3. act(actions=[...]) — click/type/key/scroll/fill/drag by @id, visible text ("Save", or "button:Save" for one
   kind of control) or "x,y". Batch several actions per call; the reply says what changed. menu ("File > Export
   as PDF") runs any menu command (see(menus=true) lists them with shortcuts); path ("~/out.pdf") fills the open
   file dialog.
4. screenshot() when looks matter; marks=true labels clickable elements; detail="low" costs 4x fewer tokens.
5. script(code=...) — for loops/repetition: Python runs inside the desktop with click/write/key/see/...;
   only what it prints comes back. run() executes shell commands (sudo works; `minion-install X`
   installs any app: apt names, .deb/.AppImage URLs, pip:, npm:).
open() launches apps, URLs and files; any app by name ("gimp", "vscode", "chrome") is installed the first time,
and web apps ("figma", "gmail") open in the browser. files() moves files, and reads any document as text (docx,
xlsx, pptx, pdf, ...) or converts it (files(action="convert", to="pdf")). view() gives a human a live link or
hands off (logins, CAPTCHAs) until they press Done.
"""

COMPACT_INSTRUCTIONS = """\
Minion gives you real Linux computers (isolated desktops with GUI apps; any program can be installed).
Use the `computer` tool, one command per call:
  create [office|browser|dev|research|data|windows|base] [--name NAME] [--count N]
  see [--changes] [--full] [--ocr] [--lang=heb]  -> the screen as text; act on the @ids it lists
  click|dclick|rclick TARGET · type TEXT · key KEYS · fill TARGET TEXT · select TARGET OPTION · scroll up|down [N]
  menu File > Save As · path FILE [--overwrite] (in a file dialog) · see --menus (all menu commands)
  wait-for TEXT · scroll-to TEXT (on a long page) · close [WINDOW] · copy TARGET (its text to the clipboard)
  open APP|URL|FILE · run SHELL · script PYTHON · screenshot [--marks] [--low]
  read FILE (any document as text) · convert FILE FORMAT · list · use NAME · remove NAME · fork · view [MESSAGE]
TARGET is @12 (from see), exact visible text ("Save"), button:Save, or x,y. open installs apps it doesn't
have (open gimp). Prefer see to screenshots, and see --changes after acting. For loops, use script.
"""


def instructions(compact: bool = False, images: bool = True) -> str:
    """The usage notes for an MCP server's `initialize` reply (or a system prompt)."""
    if compact:
        text = COMPACT_INSTRUCTIONS
        return text if images else text.replace(" · screenshot [--marks] [--low]", "")
    if images:
        return INSTRUCTIONS
    lines = [line for line in INSTRUCTIONS.splitlines() if not line.startswith("4. screenshot()")]
    return "\n".join(line.replace("5. script(", "4. script(", 1) for line in lines)


DESKTOP_PROP = {"type": "string", "description": "Desktop name (default: the one you created or used last)."}

TOOLS: list[dict] = [
    {
        "name": "desktop",
        "description": (
            "Create and manage Linux desktops (isolated computers with GUI apps). Actions: create (profile, "
            "name, size, count for several at once), list, profiles, remove, freeze (0% CPU; any later call "
            "wakes it), thaw, fork (clone disk state into a new desktop to try something risky), snapshot, "
            "restore, replay (HTML timeline of everything done), macro (the actions so far as a Python script that "
            "replays them with the script tool, no model needed). Profiles: browser (Firefox, blocks ads and "
            "cookie banners), office (LibreOffice + Firefox), dev (git, Python, Node.js, Chromium, IDE), "
            "research (Firefox + PDF/notes tools), data (office + pandas/matplotlib), windows (Windows .exe/.msi "
            "programs via Wine, x86-64 hosts), base (minimal)."
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
                        "macro",
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
        "annotations": {
            "title": "Manage desktops",
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "see",
        "description": (
            "Read the screen as text: windows, then the focused window's UI elements with stable @ids, roles, "
            "names, values, states and center coordinates (accessibility tree). Text that accessibility doesn't "
            "have (an app without it, slides, canvases, pictures of text, remote screens) is read with OCR in the "
            "screen's language. Exact and far cheaper than a screenshot. changes=true returns only what changed "
            "since your last look."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "desktop": DESKTOP_PROP,
                "changes": {"type": "boolean", "description": "Only what changed since your previous see()."},
                "ocr": {
                    "type": "boolean",
                    "description": "Also OCR smaller pictures and, when nothing is missing, the whole window (slower).",
                },
                "lang": {
                    "type": "string",
                    "description": 'OCR language when the screen\'s own is wrong: "heb", "ara+eng", "jpn"... (implies ocr)',
                },
                "window": {"type": "string", "description": "Describe this window (title, app or index) instead."},
                "full_text": {"type": "boolean", "description": "Keep paragraphs whole (to read an article/document)."},
                "menus": {
                    "type": "boolean",
                    "description": "Also list the app's menu commands and their keyboard shortcuts (for act menu).",
                },
            },
        },
        "annotations": {"title": "See the screen as text", "readOnlyHint": True, "destructiveHint": False},
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
        "annotations": {"title": "Screenshot", "readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "act",
        "description": (
            "Mouse and keyboard. Runs the actions in order, stops at the first failure, waits for the screen to "
            "settle and reports what changed. Actions (objects with an `action` field): click | double_click | "
            'triple_click (select a line) | right_click | middle_click (target; modifiers "ctrl"), move (target), '
            "drag (from, to), type (text; \\n = Enter, \\t = Tab), paste (text), fill (target, text: replace a "
            "field's content), select (target, option: pick a dropdown option by its text), key (keys: "
            '"ctrl+s", "Return", or a sequence "Tab Tab Return"; repeat), scroll '
            "(direction, amount, target), wait (seconds), wait_for (text, timeout; gone=true), scroll_to (text: "
            "brings it into view wherever it is on a long page, loading more of a feed), focus (window), close "
            "(window, like its X button), copy (target: its whole text to the clipboard), goto (target: a URL in the "
            "browser's current tab), "
            'menu (item: a menu path like "File > Export as PDF"; see(menus=true) lists them), path (path: fill the '
            "open Open/Save/Export dialog with a full file path and confirm; overwrite=true replaces a file), "
            "mouse_down/mouse_up (target: press/release for custom drags), hold_key (keys, seconds). Targets: "
            '"@12" from your latest see (best), exact visible text ("Save"; fails if not on screen), a kind and a '
            'label ("button:Save", "link:Docs", "field:Email", "tab:Settings"), or "x,y". '
            "The reply says what changed: windows, a page's alert/confirm dialog, files saved or downloaded; it "
            'waits while the app shows "Loading…". A page may still fill in after a click: wait_for text you expect.'
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
                                    "select",
                                    "key",
                                    "scroll",
                                    "wait",
                                    "wait_for",
                                    "scroll_to",
                                    "focus",
                                    "close",
                                    "copy",
                                    "goto",
                                    "mouse_down",
                                    "mouse_up",
                                    "hold_key",
                                    "menu",
                                    "path",
                                ],
                            },
                            "target": {
                                "type": "string",
                                "description": 'Required for clicks, move and fill: "@12", exact visible text, or "x,y".',
                            },
                            "text": {"type": "string", "description": "type/paste/fill/wait_for/scroll_to: the text."},
                            "option": {"type": "string", "description": "select: the option's visible text."},
                            "keys": {
                                "type": "string",
                                "description": 'key/hold_key: "ctrl+s", "Return", or a sequence "Tab Tab Return".',
                            },
                            "repeat": {"type": "integer", "description": "key: press it this many times."},
                            "modifiers": {"type": "string", "description": 'clicks: keys to hold, e.g. "ctrl".'},
                            "from": {"type": "string", "description": "drag: start target."},
                            "to": {"type": "string", "description": "drag: end target."},
                            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                            "amount": {"type": "integer", "description": "scroll: wheel clicks (default 3)."},
                            "seconds": {"type": "number", "description": "wait/hold_key: seconds."},
                            "timeout": {"type": "number", "description": "wait_for: seconds (default 10)."},
                            "gone": {"type": "boolean", "description": "wait_for: wait until the text disappears."},
                            "window": {"type": "string", "description": "focus/close: a window title or app name."},
                            "item": {"type": "string", "description": 'menu: the menu path, e.g. "File > Save As".'},
                            "path": {"type": "string", "description": "path: the full file path for the dialog."},
                            "overwrite": {"type": "boolean", "description": "path: replace an existing file."},
                        },
                        "required": ["action"],
                    },
                },
                "desktop": DESKTOP_PROP,
                "observe": {
                    "type": "string",
                    "enum": ["auto", "summary", "changes", "see", "screenshot", "crop"],
                    "description": "What to return after acting: auto (default: the summary, plus the changed UI as "
                    "text when a page, window or dialog changed or the app finished working), summary, changes (+ the "
                    "changed UI as text), see (the whole screen as text), screenshot, crop (an image of just the "
                    "changed region).",
                },
            },
            "required": ["actions"],
        },
        "annotations": {"title": "Mouse and keyboard", "readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "open",
        "description": (
            'Open something and wait until its window is ready: an app ("writer", "calc", "firefox", "terminal", or '
            'any app by name: "gimp", "inkscape", "vscode", "chrome", "thunderbird", "blender", "dbeaver"... '
            'installed the first time, which can take a minute), a web app by name ("gmail", "figma", '
            '"google sheets"), a URL ("github.com"), a file in the desktop ("~/Documents/report.docx"), or a shell '
            "command. The reply includes short tips for the app the first time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "install": {"type": "boolean", "description": "Install a missing app first (default true)."},
                "desktop": DESKTOP_PROP,
            },
            "required": ["target"],
        },
        "annotations": {
            "title": "Open app, URL or file",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
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
        "annotations": {"title": "Run a shell command", "readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "script",
        "description": (
            "Run Python inside the desktop to do many GUI steps in one call (loops, retries, data entry): only "
            "what it prints comes back. Preloaded: see(changes=False), elements(role, name), find(text), "
            'cells() (visible spreadsheet cells {"A1": ...}), click(target), double_click, right_click, '
            "write(text), paste(text), key(keys), scroll(dir, n), fill(target, text), drag(a, b), wait(s), "
            'wait_for(text, timeout) -> bool, menu("File > Save"), menus(), path(file), read(file) -> text, '
            "convert(file, to) -> path, launch(app_or_url), run(cmd) -> dict, windows(), focus(title), scroll_to(text), "
            "close(window), copy(target), "
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
        "annotations": {"title": "Script the desktop", "readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "files",
        "description": (
            "Files in a desktop. read: any file as text: text files as they are, documents converted (docx, "
            "xlsx with values and formulas, pptx, odt/ods/odp, pdf, epub, html, images by OCR, doc/xls/ppt). "
            "convert: path -> another format (to: pdf, docx, xlsx, csv, pptx, png, md, ...; returns the new "
            "path). write: text -> path (replaces the file; creates folders). upload: local_path (on the "
            "machine running Minion) -> path. download: path -> local_path (never overwrites unless "
            "overwrite=true). local_path is limited to Minion's files folder (relative paths start there). "
            "Desktop paths may start with ~."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["upload", "download", "read", "write", "convert"]},
                "to": {"type": "string", "description": "convert: the new format, e.g. pdf, docx, xlsx, csv, png."},
                "path": {"type": "string", "description": "Path inside the desktop, e.g. ~/Documents/report.docx."},
                "local_path": {
                    "type": "string",
                    "description": "upload/download: path on the machine running Minion (download default: .).",
                },
                "text": {"type": "string", "description": "write: the whole new content."},
                "overwrite": {"type": "boolean", "description": "download: replace an existing local file."},
                "desktop": DESKTOP_PROP,
            },
            "required": ["action", "path"],
        },
        "annotations": {"title": "Files", "readOnlyHint": False, "destructiveHint": True},
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
        "annotations": {"title": "Live view / hand off to the human", "readOnlyHint": False, "destructiveHint": False},
    },
]

COMPUTER_TOOL = {
    "name": "computer",
    "description": (
        "Use Linux computers through one command per call (CLI syntax). Commands: "
        "create [profile] [--name NAME] [--count N] · "
        "list · use NAME · remove [NAME] · see [--changes] [--ocr] [--lang=X] [--full] · screenshot [--marks] [--low] "
        "[--zoom x,y,w,h] · click TARGET · dclick TARGET · rclick TARGET · type TEXT · key KEYS · "
        "scroll up|down [N] · scroll-to TEXT · fill TARGET TEXT · select TARGET OPTION · drag FROM TO · "
        "wait-for TEXT [--timeout N] · close [WINDOW] · copy TARGET · goto URL · "
        "menu File > Save As · path FILE [--overwrite] · see --menus · read FILE · convert FILE FORMAT · "
        "focus WINDOW · windows · open TARGET (any app by name; installed the first time) · run SHELL... · "
        "script PYTHON... · view [MESSAGE]. Targets: @id from see, visible text (quote it), button:Save, or x,y. "
        "Profiles: browser, office, dev, research, data, windows, base. Example: create office · open calc · see · "
        "click @12 · type 'Total' · key Return."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "One command, e.g. `click @12`."}},
        "required": ["command"],
    },
    "annotations": {"title": "Computer", "readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
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
        (tool messages there cannot hold images). For several calls in one turn, use
        Toolkit.run_calls(), which puts every tool message before the images as the API requires."""
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


_NEEDS = {
    "click": ("target",),
    "double_click": ("target",),
    "triple_click": ("target",),
    "right_click": ("target",),
    "middle_click": ("target",),
    "move": ("target",),
    "fill": ("target", "text"),
    "select": ("target", "option"),
    "drag": ("from", "to"),
    "type": ("text",),
    "paste": ("text",),
    "key": ("keys",),
    "hold_key": ("keys",),
    "wait_for": ("text",),
    "menu": ("item",),
    "path": ("path",),
    "focus": ("window",),
}


def _check_step(i: int, step: dict) -> None:
    """Refuse an action that is missing what it acts on, instead of clicking wherever the mouse is."""
    action = str(step.get("action") or "")
    if not action:
        return  # shorthand forms like {"click": "@3"} are checked by the desktop
    missing = [k for k in _NEEDS.get(action, ()) if step.get(k) in (None, "")]
    if action == "fill" and step.get("text") == "":
        missing = [k for k in missing if k != "text"]  # fill with "" clears the field
    if missing:
        raise ToolError(f"action {i} ({action}) needs {' and '.join(missing)}")


# The same act-string grammar as the desktop agent (minion/agent/server.py), which the host can't import.
def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


# A Windows path (C:\\users\\x.txt, no second ":") keeps its backslashes, as in the desktop's act steps.
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^:\n\t]*")


def _escapes(text: str) -> str:
    if WINDOWS_PATH.fullmatch(text) and "\\\\" not in text:  # (C:\\\\temp: the escape convention, as before)
        return text[:-2] + "\n" if text.endswith("\\n") else text
    return text.replace("\\\\", "\0").replace("\\n", "\n").replace("\\t", "\t").replace("\0", "\\")


def _first_word(rest: str) -> tuple[str, str]:
    rest = rest.lstrip()
    if rest[:1] in ("'", '"'):
        end = rest.find(rest[0], 1)
        if end > 0:
            return rest[1:end], rest[end + 1 :].lstrip()
    word, _, tail = rest.partition(" ")
    return word, tail.lstrip()


def _split_words(text: str) -> list[str]:
    """Split like a shell (quotes group words) but keep backslashes: Windows paths survive."""
    lex = shlex.shlex(text, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.escape = ""
    return list(lex)


def _unknown_args(tool: str, args: dict) -> str:
    """A note about arguments the tool doesn't take (they are ignored), with the likely intended ones."""
    import difflib

    spec = next((t for t in [*TOOLS, COMPUTER_TOOL] if t["name"] == tool), None)
    if spec is None:
        return ""
    known = set(spec["input_schema"].get("properties", {}))
    extra = sorted(set(args) - known)
    if not extra:
        return ""
    hints = []
    for key in extra:
        close = difflib.get_close_matches(key, sorted(known), n=1)
        hints.append(f"{key} (did you mean {close[0]}?)" if close else key)
    return f"(Ignored unknown argument{'s' if len(extra) > 1 else ''}: {', '.join(hints)}.)"


def default_files_root() -> Path:
    """Where `files` may read and write on this machine by default: the working directory (a project
    folder for coding agents), or ~/Minion when that is the filesystem root or the home folder itself
    (GUI apps start MCP servers there)."""
    cwd, home = Path.cwd().resolve(), Path.home().resolve()
    if cwd == Path(cwd.anchor) or cwd == home:
        return home / "Minion"
    return cwd


def _get(obj, key: str):
    """A field from an SDK object or a plain dict (None when missing)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# ---------------------------------------------------------------------------
class Toolkit:
    """The tools, bound to a backend and a notion of "the current desktop"."""

    def __init__(
        self,
        backend: Backend | str | None = None,
        *,
        in_process_viewer: bool | None = None,
        files_root: str | os.PathLike | None = None,
        images: bool = True,
    ):
        self.backend = _backend(backend)
        self.images = images  # False: text-only clients (no screenshot tool, images left out of results)
        self._local = threading.local()
        # With no desktop chosen yet, may a call use "the" desktop (when exactly one exists)? Fine for one local
        # agent; servers turn it off, so one session never acts on another session's desktop.
        self.fallback = True
        self.current: str | None = None
        self.desktops: dict[str, Desktop] = {}
        self._pending: dict[str, Future] = {}
        self._lock = threading.Lock()
        self.in_process_viewer = in_process_viewer
        # `files` upload/download touch this machine's disk: a prompt-injected agent must not be able to
        # copy ~/.ssh into an internet-connected desktop. They stay inside one folder (MINION_FILES_ROOT=/
        # allows everything).
        root = files_root if files_root is not None else os.environ.get("MINION_FILES_ROOT") or default_files_root()
        self.files_root = Path(root).expanduser().resolve() if root else None

    # -- definitions ----------------------------------------------------
    def definitions(self, format: str = "mcp", *, compact: bool = False) -> list[dict]:
        """Tool definitions for: mcp, openai (Chat Completions), openai-responses, anthropic, gemini."""
        tools = [COMPUTER_TOOL] if compact else [t for t in TOOLS if self.images or t["name"] != "screenshot"]
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
                out.append(  # strict: false, or Responses tries strict mode, which makes every optional field required
                    {
                        "type": "function",
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": schema,
                        "strict": False,
                    }
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
        if not isinstance(args, dict):  # e.g. '"see"' or '[1, 2]'
            args = {"command": args} if name == "computer" and isinstance(args, str) else {}
        args = {k: v for k, v in args.items() if v is not None}  # explicit nulls mean "use the default"
        fn = getattr(self, f"t_{name}", None) if name in self.names else None
        if fn is None:
            return ToolResult([_text(f"unknown tool {name!r}; tools: {', '.join(self.names)}")], True)
        self._local.note = None
        unknown = _unknown_args(name, args)
        try:
            result = ToolResult(fn(args, progress or (lambda _line: None)))
        except MinionError as e:
            return ToolResult([_text(str(e))], True)
        except Exception as e:  # report instead of crashing the caller's agent loop
            return ToolResult([_text(f"{type(e).__name__}: {e}")], True)
        if not self.images and result.images:
            n = len(result.images)
            result.content = [c for c in result.content if c["type"] != "image"]
            result.content.append(
                _text(f"({n} image(s) left out: this client gets text only; see() reads the screen.)")
            )
        if self._local.note:
            result.content.append(_text(self._local.note))
        if unknown:
            result.content.append(_text(unknown))
        return result

    def run_calls(self, calls, format: str = "openai"):
        """Run a model's tool calls and return what to send back, in that API's shape.

        openai:           Chat Completions messages to append (tool messages first, then one user
                          message with any screenshots, so parallel calls stay valid)
        openai-responses: input items to append
        anthropic:        one user message holding a tool_result per tool_use block
        gemini:           a list of parts (function responses, then images) for one user turn

        `calls` may be SDK objects or plain dicts: Chat Completions `message.tool_calls`, Responses
        `function_call` items, Anthropic `content` blocks (non-tool blocks are skipped), or Gemini
        function calls.
        """
        fmt = format.lower()
        out: list[dict] = []
        images: list[dict] = []
        tool_results: list[dict] = []
        for c in calls or []:
            if fmt in ("anthropic", "claude"):
                if _get(c, "type") != "tool_use":
                    continue
                tool_results.append(self.call(_get(c, "name"), _get(c, "input")).to_anthropic(_get(c, "id")))
            elif fmt in ("openai", "openai-chat", "chat"):
                fn = _get(c, "function")
                msgs = self.call(_get(fn, "name"), _get(fn, "arguments")).to_openai(_get(c, "id"))
                out.append(msgs[0])
                images += msgs[1]["content"][1:] if len(msgs) > 1 else []
            elif fmt in ("openai-responses", "responses"):
                if _get(c, "type") not in (None, "function_call"):
                    continue
                items = self.call(_get(c, "name"), _get(c, "arguments")).to_openai_responses(_get(c, "call_id"))
                out.append(items[0])
                images += items[1]["content"] if len(items) > 1 else []
            elif fmt in ("gemini", "google"):
                fc = _get(c, "function_call") or c
                name = _get(fc, "name")
                if not name:  # a text or thought part
                    continue
                args = _get(fc, "args")
                if args is not None and not isinstance(args, (dict, str)):
                    args = dict(args)
                parts = self.call(name, args).to_gemini(name)
                if _get(fc, "id"):
                    parts[0]["function_response"]["id"] = _get(fc, "id")
                out.append(parts[0])
                images += parts[1:]
            else:
                raise MinionError(f"unknown format {format!r}: openai, openai-responses, anthropic, gemini")
        if fmt in ("anthropic", "claude"):
            return [{"role": "user", "content": tool_results}] if tool_results else []
        if images and fmt in ("openai", "openai-chat", "chat"):
            out.append({"role": "user", "content": [{"type": "text", "text": "Screenshots from the tool calls:"}]})
            out[-1]["content"] += images
        elif images and fmt in ("openai-responses", "responses"):
            out.append({"role": "user", "content": images})
        else:
            out += images
        return out

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
        if not name and not self.fallback:
            names = ", ".join(d.name for d in self.backend.list()) or "none yet"
            raise ToolError(
                'No desktop is selected in this session: create one with desktop(action="create"), or pass '
                f"desktop=NAME to use an existing one (desktops: {names})."
            )
        if not name:
            try:
                name = Desktop.attach(None, self.backend).name
            except NotFound:
                raise ToolError(
                    'No desktop yet. Create one: desktop(action="create", profile="browser") '
                    "(profiles: browser, office, dev, research, data, windows, base)."
                ) from None
            # A client that starts a new server per call has no "current desktop": say which one this used.
            self._local.note = f"(Used desktop {name!r}, the most recent one; pass desktop=NAME to choose.)"
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
        if action != "fork" and args.get("name"):
            if args.get("desktop") and args["desktop"] != args["name"]:
                raise ToolError(
                    f"name={args['name']!r} and desktop={args['desktop']!r} disagree: pass the one desktop to {action}"
                )
            args = {**args, "desktop": args["name"]}  # desktop(action="remove", name="x") means desktop x
        if action in ("remove", "restore") and not args.get("desktop"):
            # Never on an implied desktop: removing or rewinding the wrong one loses work.
            raise ToolError(f"{action} needs desktop=NAME: say which desktop to {action}")
        d = self.desk(args)
        if action == "info":
            hello = d.hello()
            info = d.info()
            lines = [
                f"{d.name}: {info.profile} profile, {info.size}, "
                f"{'frozen' if info.state == 'paused' else info.state}, backend {info.backend}",
                f"Apps you can open: {', '.join(a.lower() for a in hello.get('apps', [])) or 'none'}",
                f"Windows open: {int(hello.get('windows') or 0)}",
            ]
            return [_text("\n".join(lines))]
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
            snaps = [s.tag for s in be.snapshots(d.name)]
            if not args.get("tag") or args["tag"] not in snaps:
                what = "needs a tag" if not args.get("tag") else f"has no snapshot {args['tag']!r}"
                raise ToolError(f"restore {what}. Snapshots of {d.name}: " + (", ".join(snaps) or "none"))
            d.restore(args["tag"])
            return [_text(f"{d.name} restored to {args['tag']!r} (apps start fresh).")]
        if action == "replay":
            path = Path(tempfile.gettempdir()) / f"minion-{d.name}-replay.html"
            d.recording("html", path)
            url = self.view_url(d.name)
            link = f"\nOpen it in a browser: {url.split('/view/')[0]}/api/desktops/{d.name}/replay" if url else ""
            return [_text(f"Timeline of everything done on {d.name}: {path}{link}")]
        if action == "macro":
            code = d.recording("script")
            return [_text("Replayable script (run it with the script tool on a desktop of this profile):\n\n" + code)]
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
            f"Apps you can open: {', '.join(a.lower() for a in hello.get('apps', []))}"
            + ("" if hello.get("windows") else " (no window is open yet: open one first)"),
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
            ocr=str(args["lang"]) if args.get("lang") else (True if args.get("ocr") else "auto"),
            window=args.get("window"),
            full_text=bool(args.get("full_text")),
            changes=bool(args.get("changes")),
            menus=bool(args.get("menus")),
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
            cursor=not region,  # a crop is for reading details: no pointer on top
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
        actions = args.get("actions")
        if isinstance(actions, (dict, str)):
            actions = [actions]
        if not actions:
            raise ToolError('act needs actions, e.g. [{"action": "click", "target": "@3"}]')
        for i, step in enumerate(actions, 1):
            if isinstance(step, dict):
                _check_step(i, {k: v for k, v in step.items() if v is not None})
        d = self.desk(args)
        observe = args.get("observe") or "auto"
        if not self.images and observe in ("screenshot", "crop"):
            observe = "changes"  # this client gets text only
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
        install = args.get("install", True) is not False
        if install:
            progress(f"Opening {args['target']} (an app that isn't installed yet is installed first)")
        res = d.open(args["target"], install=install)
        first = f"Installed {res['installed']}. " if res.get("installed") else ""
        tips = f"\nTips: {res['tips']}" if res.get("tips") else ""
        w = res.get("window")
        if "error" in res:
            raise ToolError(first + res["error"])
        if w:
            also = f" Also opened: {', '.join(repr(t) for t in res['also'])}." if res.get("also") else ""
            look = f"\n{res['look']}" if res.get("look") else ""
            return [
                _text(
                    f'{first}Opened {res["command"]} → window "{w["title"]}" ({w["app"]}).{also} '
                    f"{'It opened on a dialog:' if look else 'Use see() to read it.'}{tips}{look}"
                )
            ]
        return [
            _text(f"{first}Launched {res['command']}; no new window yet (it may still be loading — check see()).{tips}")
        ]

    def t_run(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("command"):
            raise ToolError("run needs a command")
        res = d.run(args["command"], timeout=float(args.get("timeout") or 120), background=bool(args.get("background")))
        if args.get("background"):
            log = f" Output goes to {res.log} (read it with run('tail -n 50 {res.log}'))." if res.log else ""
            return [_text(f"Started in the background (pid {res.pid}).{log} Stop it with run('kill {res.pid}').")]
        return [_text(_run_text(res.code, res.stdout, res.stderr, res.timed_out))]

    def t_script(self, args: dict, progress) -> list:
        d = self.desk(args)
        if not args.get("code"):
            raise ToolError("script needs code")
        res = d.script(args["code"], timeout=float(args.get("timeout") or 120))
        if res.ok and not res.stdout and not res.stderr:
            return [_text(f"The script finished in {res.elapsed:.1f}s and printed nothing (print() what you need).")]
        if res.ok:  # only what the script printed: the point of code mode is a small result
            return [
                _text(
                    _clip_output(res.stdout, RUN_TEXT_LIMIT)
                    + (f"\n(stderr: {res.stderr.strip()})" if res.stderr else "")
                )
            ]
        raise ToolError(_run_text(res.code, res.stdout, res.stderr, res.timed_out))

    def _host_path(self, path: str) -> str:
        """A path on this machine for upload/download, kept inside files_root when one is set."""
        raw = os.path.expanduser(path)
        if self.files_root is None:
            return raw
        self.files_root.mkdir(parents=True, exist_ok=True)
        full = (self.files_root / raw).resolve()
        if full != self.files_root and self.files_root not in full.parents:
            raise ToolError(
                f"local_path must be inside {self.files_root} (relative paths start there; MINION_FILES_ROOT "
                "changes the folder)"
            )
        return str(full)

    def t_files(self, args: dict, progress) -> list:
        d = self.desk(args)
        action, path = args.get("action"), args.get("path") or ""
        if action == "upload":
            if not args.get("local_path"):
                raise ToolError("upload needs local_path: a file on this machine")
            local = self._host_path(args["local_path"])
            if not os.path.exists(local):
                raise ToolError(f"local_path {local!r} does not exist (relative paths start in {self.files_root})")
            d.upload(local, path or "~/")
            return [_text(f"Uploaded {local} → {d.name}:{path or '~/'}")]
        if not path and action in ("download", "read", "write", "convert"):
            raise ToolError(f"{action} needs path: the file in the desktop, e.g. ~/Documents/report.docx")
        if action == "download":
            local = Path(self._host_path(args.get("local_path") or ".")).absolute()
            dest = local / Path(path).name if local.is_dir() else local
            if dest.exists() and not args.get("overwrite"):
                raise ToolError(f"{dest} already exists on this machine; pass overwrite=true to replace it")
            dest.parent.mkdir(parents=True, exist_ok=True)
            return [_text(f"Downloaded {d.name}:{path} → {d.download(path, dest)}")]
        if action == "read":
            text = d.read(path, max_chars=100_000)
            return [_text(text)]
        if action == "convert":
            if not args.get("to"):
                raise ToolError('convert needs to: the new format, e.g. "pdf", "docx", "xlsx", "csv" or "png"')
            return [_text(f"Converted {path} → {d.convert(path, str(args['to']))}")]
        if action == "write":
            if args.get("text") is None:
                raise ToolError('write needs text (use text="" for an empty file); it replaces the whole file')
            d.write_text(path, args["text"])
            return [_text(f"Wrote {len(args['text'])} characters to {d.name}:{path}")]
        raise ToolError("action must be upload, download, read, write or convert")

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
            words = _split_words(rest)
        except ValueError:
            words = rest.split()
        flags = {w for w in words if w.startswith("--")}
        plain = [w for w in words if not w.startswith("--")]
        allowed = _COMPACT_FLAGS.get(verb)
        if allowed is not None:
            bad = sorted(f.split("=", 1)[0] for f in flags if f.split("=", 1)[0] not in allowed)
            if bad:
                hint = " ".join(sorted(allowed)) or "none"
                raise ToolError(f"unknown option {', '.join(bad)} for {verb} (options: {hint})")

        def target(ws):
            if len(ws) == 2 and all(w.lstrip("-").isdigit() for w in ws):
                return f"{ws[0]},{ws[1]}"
            return " ".join(ws)

        if verb in ("create", "up", "new"):
            # create [profile] [--name NAME | NAME] [--count N | -c N]; "-n X" is a count if X is a number
            count, name, rest_words, it = 1, None, [], iter(words)
            for w in it:
                if w in ("--count", "-c"):
                    count = int(next(it, "1"))
                elif w.startswith("--count="):
                    count = int(w.split("=", 1)[1])
                elif w in ("--name", "-n"):
                    value = next(it, "")
                    if w == "-n" and value.isdigit():
                        count = int(value)
                    else:
                        name = value or None
                elif w.startswith("--name="):
                    name = w.split("=", 1)[1] or None
                elif w.startswith("-"):
                    raise ToolError(f"unknown option {w!r}: use create [profile] [--name NAME] [--count N]")
                else:
                    rest_words.append(w)
            if len(rest_words) > 2:
                raise ToolError("use: create [profile] [--name NAME] [--count N]")
            if len(rest_words) == 2 and name is None:
                name = rest_words[1]
            args_ = {"action": "create", "profile": rest_words[0] if rest_words else None, "count": count}
            if name:
                args_["name"] = name
            return self.t_desktop(args_, progress)
        if verb in ("list", "ls"):
            return self.t_desktop({"action": "list"}, progress)
        if verb == "profiles":
            return self.t_desktop({"action": "profiles"}, progress)
        if verb == "use":
            self.desk({"desktop": rest})
            return [_text(f"Current desktop: {rest}")]
        if verb in ("remove", "rm"):
            if not rest:
                raise ToolError("remove NAME: which desktop to remove (see `list`)")
            return self.t_desktop({"action": "remove", "desktop": rest}, progress)
        if verb == "windows":
            wins = self.desk(args).windows()
            lines = [
                f'[{i}] "{w["title"]}" ({w["app"]}){" focused" if w.get("focused") else ""}'
                for i, w in enumerate(wins, 1)
            ]
            return [_text("\n".join(lines) or "No windows are open.")]
        if verb == "focus":
            return self.t_act({"actions": [{"action": "focus", "window": _unquote(rest)}]}, progress)
        if verb == "select":
            target_, option_ = _first_word(rest)
            if not target_ or not option_:
                raise ToolError("select TARGET OPTION, e.g. select @14 Title")
            return self.t_act(
                {"actions": [{"action": "select", "target": target_, "option": _unquote(option_)}]}, progress
            )
        if verb == "restore":  # rewinds the session's current desktop (never an implied one)
            if not self.current:
                raise ToolError("restore TAG rewinds the current desktop: `use NAME` first (see `list`)")
            return self.t_desktop({"action": "restore", "tag": rest or None, "desktop": self.current}, progress)
        if verb in ("freeze", "thaw", "fork", "snapshot", "replay", "macro"):
            key = "tag" if verb == "snapshot" else "name"
            return self.t_desktop({"action": verb, key: rest or None}, progress)
        if verb == "see":
            return self.t_see(
                {
                    "changes": "--changes" in flags,
                    "ocr": "--ocr" in flags,
                    "lang": next((f.split("=", 1)[1] for f in flags if f.startswith("--lang=")), None),
                    "full_text": "--full" in flags,
                    "menus": "--menus" in flags,
                },
                progress,
            )
        if verb == "menu":  # the rest is the menu path: menu File > Export > PDF
            if not rest:
                raise ToolError("menu PATH, e.g. menu File > Save As (see --menus lists them)")
            return self.t_act({"actions": [{"action": "menu", "item": _unquote(rest)}]}, progress)
        if verb == "path":
            file_path = " ".join(w for w in words if w != "--overwrite")
            if not file_path:
                raise ToolError("path FILE [--overwrite]: a full path for the open file dialog")
            step = {
                "action": "path",
                "path": _unquote(file_path),
                **({"overwrite": True} if "--overwrite" in flags else {}),
            }
            return self.t_act({"actions": [step]}, progress)
        if verb in ("read", "cat"):
            if not rest:
                raise ToolError("read FILE: any document as text (docx, xlsx, pptx, pdf, ...)")
            return self.t_files({"action": "read", "path": _unquote(rest)}, progress)
        if verb == "convert":
            if len(plain) != 2:
                raise ToolError("convert FILE FORMAT, e.g. convert ~/report.docx pdf")
            return self.t_files({"action": "convert", "path": plain[0], "to": plain[1]}, progress)
        if verb in ("screenshot", "shot"):
            a = {
                "marks": "--marks" in flags,
                "grid": "--grid" in flags,
                "detail": "low" if "--low" in flags else "full",
            }
            for w in words:
                if w.startswith("--zoom="):
                    a.update(region=[int(v) for v in w[7:].split(",")], zoom=True)
            if "--zoom" in words:
                i = words.index("--zoom")
                a.update(region=[int(v) for v in words[i + 1].split(",")], zoom=True)
            return self.t_screenshot(a, progress)
        if verb in ("click", "dclick", "rclick", "move", "hover"):
            action = {"dclick": "double_click", "rclick": "right_click", "hover": "move"}.get(verb, verb)
            for flag, name in (
                ("--double", "double_click"),
                ("--right", "right_click"),
                ("--triple", "triple_click"),
                ("--middle", "middle_click"),
            ):
                if flag in flags:
                    action = name
            return self.t_act({"actions": [{"action": action, "target": target(plain)}]}, progress)
        if verb == "type":  # the rest of the command, verbatim (\n = Return, \t = Tab), as in act steps
            return self.t_act({"actions": [{"action": "type", "text": _escapes(_unquote(rest))}]}, progress)
        if verb in ("key", "press"):
            return self.t_act({"actions": [{"action": "key", "keys": k} for k in plain]}, progress)
        if verb == "scroll":
            if len(plain) > 1 and not plain[1].isdigit():
                raise ToolError("scroll up|down|left|right [N]: N is a number of wheel clicks")
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
            target_, text_ = _first_word(rest)
            if not target_:
                raise ToolError("fill TARGET TEXT")
            return self.t_act(
                {"actions": [{"action": "fill", "target": target_, "text": _escapes(_unquote(text_))}]}, progress
            )
        if verb == "drag":
            if len(plain) != 2:
                raise ToolError("drag FROM TO")
            return self.t_act({"actions": [{"action": "drag", "from": plain[0], "to": plain[1]}]}, progress)
        if verb in ("wait-for", "wait_for"):
            step, it, text_words = {"action": "wait_for"}, iter(words), []
            for w in it:
                if w == "--timeout" or w.startswith("--timeout="):
                    value = w.split("=", 1)[1] if "=" in w else next(it, "")
                    try:
                        step["timeout"] = float(value)
                    except ValueError:
                        raise ToolError(f"wait-for --timeout takes seconds, got {value!r}") from None
                elif w == "--gone":
                    step["gone"] = True
                else:
                    text_words.append(w)
            step["text"] = " ".join(text_words)
            return self.t_act({"actions": [step]}, progress)
        if verb in ("scroll-to", "scroll_to", "find"):
            if not rest.strip():
                raise ToolError(
                    'scroll-to TEXT: brings it into view wherever it is on the page, e.g. scroll-to "Entry 87"'
                )
            return self.t_act({"actions": [{"action": "scroll_to", "text": _unquote(rest.strip())}]}, progress)
        if verb == "goto":
            if not rest.strip():
                raise ToolError("goto URL: load it in the browser's current tab")
            return self.t_act({"actions": [{"action": "goto", "target": _unquote(rest.strip())}]}, progress)
        if verb == "close":
            return self.t_act(
                {"actions": [{"action": "close", **({"window": _unquote(rest)} if rest else {})}]}, progress
            )
        if verb == "copy":
            return self.t_act({"actions": [{"action": "copy", "target": target(plain)}]}, progress)
        if verb == "open":
            target_ = " ".join(w for w in words if w != "--no-install") if "--no-install" in flags else rest
            return self.t_open({"target": target_, "install": "--no-install" not in flags}, progress)
        if verb in ("run", "exec", "sh"):
            return self.t_run({"command": rest}, progress)
        if verb in ("script", "py", "python"):
            return self.t_script({"code": rest}, progress)
        if verb == "view":
            return self.t_view({"message": rest or None}, progress)
        raise ToolError(f"unknown command {verb!r}. Try: see · click @12 · type hello · open firefox · run ls")


# Options each compact command takes (others take their text verbatim and are not checked).
_COMPACT_FLAGS = {
    "see": {"--changes", "--ocr", "--lang", "--full", "--menus"},
    "path": {"--overwrite"},
    "convert": set(),
    "screenshot": {"--marks", "--low", "--zoom", "--grid"},
    "shot": {"--marks", "--low", "--zoom", "--grid"},
    "click": {"--double", "--right", "--triple", "--middle"},
    "dclick": set(),
    "rclick": set(),
    "move": set(),
    "hover": set(),
    "key": set(),
    "press": set(),
    "scroll": set(),
    "drag": set(),
    "wait-for": {"--timeout", "--gone"},
    "wait_for": {"--timeout", "--gone"},
    "list": set(),
    "ls": set(),
    "windows": set(),
}

RUN_TEXT_LIMIT = 12_000  # characters of command output a tool result carries (head + tail)


def _clip_output(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head, tail = text[: limit // 4], text[-(limit - limit // 4) :]
    return (
        f"{head}\n… [{len(text) - len(head) - len(tail):,} characters left out; to keep everything, redirect it to a "
        f"file (cmd > /tmp/out.txt) and read the parts you need] …\n{tail}"
    )


def _run_text(code, stdout: str, stderr: str, timed_out: bool) -> str:
    parts = [f"exit code: {code}" + (" (timed out)" if timed_out else "")]
    if stdout:
        parts.append("stdout:\n" + _clip_output(stdout, RUN_TEXT_LIMIT))
    if stderr:
        parts.append("stderr:\n" + _clip_output(stderr, RUN_TEXT_LIMIT // 3))
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
