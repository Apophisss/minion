"""Accessibility snapshots through AT-SPI.

Turns the UI of the focused window into a compact, numbered list of elements
("@12 push button "Save" (210,62)") that an agent can read for a fraction of the
tokens of a screenshot, and click by reference. Works with GTK, Qt, Firefox,
Chromium/Electron (with accessibility enabled) and LibreOffice.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

try:  # optional dependency: python3-gi + gir1.2-atspi-2.0
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi  # type: ignore

    AVAILABLE = True
except Exception:  # pragma: no cover - depends on the desktop image
    Atspi = None  # type: ignore
    AVAILABLE = False

LOCK = threading.RLock()
_initialized = False

INTERACTIVE = {
    "push button", "toggle button", "check box", "radio button", "menu item",
    "check menu item", "radio menu item", "tearoff menu item", "menu", "combo box",
    "entry", "password text", "spin button", "slider", "link", "page tab",
    "list item", "tree item", "split button", "button", "toggle", "switch",
    "date editor", "font chooser", "color chooser", "icon", "tool bar item",
}
TEXT_INPUT = {"entry", "password text", "text", "terminal", "spin button", "combo box"}
TEXTUAL = {
    "heading", "paragraph", "label", "static", "caption", "text", "terminal",
    "block quote", "list item", "table cell", "cell", "description term",
    "description value", "footer", "header", "comment", "math", "mark",
    "notification", "alert", "status bar", "info bar", "tooltip", "title bar",
}
CONTAINERS_WITH_TITLE = {
    "dialog", "alert", "file chooser", "page tab list", "menu bar", "tool bar",
    "table", "tree table", "tree", "list", "list box", "document frame",
    "document web", "document text", "document spreadsheet", "document presentation",
    "document email", "form", "landmark", "navigation", "group", "grouping",
    "panel", "section", "article", "region", "scroll pane", "frame", "window",
}
SKIP_ROLES = {"scroll bar", "separator"}  # never emitted, never descended
TOP_LEVEL = {"frame", "window", "dialog", "alert", "file chooser"}
LEAVES = {
    "push button", "button", "toggle button", "split button", "check box", "radio button",
    "menu item", "check menu item", "radio menu item", "link", "entry", "password text",
    "terminal", "spin button", "slider", "switch",
}


@dataclass
class Element:
    id: int
    role: str
    name: str
    depth: int
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    value: str = ""
    states: list[str] = field(default_factory=list)
    node: object = None  # Atspi.Accessible (not serialized)

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def interactive(self) -> bool:
        return self.role in INTERACTIVE or self.role in TEXT_INPUT

    def label(self) -> str:
        return self.name or self.text or self.value

    def to_dict(self) -> dict:
        cx, cy = self.center
        d = {"id": f"@{self.id}", "role": self.role, "name": self.name,
             "x": cx, "y": cy, "box": [self.x, self.y, self.w, self.h]}
        if self.text:
            d["text"] = self.text
        if self.value:
            d["value"] = self.value
        if self.states:
            d["states"] = self.states
        return d


@dataclass
class Snapshot:
    app: str = ""
    window: str = ""
    elements: list[Element] = field(default_factory=list)
    truncated: bool = False
    visited: int = 0
    elapsed: float = 0.0
    error: str = ""


def _init() -> bool:
    global _initialized
    if not AVAILABLE:
        return False
    if not _initialized:
        try:
            Atspi.init()
            Atspi.set_timeout(1500, 5000)
        except Exception:
            return False
        _initialized = True
    return True


_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def _clip(s: str, n: int) -> str:
    s = " ".join((s or "").replace("\ufffc", " ").translate(_INVISIBLE).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _states(node) -> set:
    try:
        return set(node.get_state_set().get_states())
    except Exception:
        return set()


def _extents(node) -> tuple[int, int, int, int] | None:
    try:
        r = Atspi.Component.get_extents(node, Atspi.CoordType.SCREEN)
        return int(r.x), int(r.y), int(r.width), int(r.height)
    except Exception:
        return None


def _interfaces(node) -> set:
    try:
        return set(node.get_interfaces())
    except Exception:
        return set()


def _lines(raw: str, limit: int) -> str:
    """Keep line structure visible ("⏎") but collapse runs of spaces."""
    lines = [" ".join(ln.split()) for ln in raw.replace("\ufffc", " ").translate(_INVISIBLE).splitlines()]
    out = " ⏎ ".join(ln for ln in lines if ln)
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def _text(node, limit: int, tail: bool = False) -> str:
    """Text content; ``tail`` keeps the end (terminals: the latest output matters)."""
    try:
        n = Atspi.Text.get_character_count(node)
        if n <= 0:
            return ""
        if tail:
            raw = Atspi.Text.get_text(node, max(0, n - limit * 6), n)
            lines = [" ".join(ln.split()) for ln in raw.splitlines()]
            lines = [ln for ln in lines if ln][-12:]
            out = " ⏎ ".join(lines)
            return out if len(out) <= limit else "…" + out[-(limit - 1):].lstrip()
        return _lines(Atspi.Text.get_text(node, 0, min(n, limit * 4)), limit)
    except Exception:
        return ""


def _expand_embedded(node, text: str, limit: int) -> str:
    """Replace U+FFFC placeholders (embedded links/images) with their names."""
    try:
        raw = Atspi.Text.get_text(node, 0, min(Atspi.Text.get_character_count(node), limit * 4))
        n = node.get_child_count()
    except Exception:
        return text
    out, child = [], 0
    for ch in raw:
        if ch == "\ufffc":
            name = ""
            if child < n:
                try:
                    name = _name(node.get_child_at_index(child))
                except Exception:
                    name = ""
            child += 1
            out.append(name)
        else:
            out.append(ch)
    return _clip("".join(out), limit)


def _value(node) -> str:
    try:
        v = Atspi.Value.get_current_value(node)
        return f"{v:g}"
    except Exception:
        return ""


def _role(node) -> str:
    try:
        return node.get_role_name() or ""
    except Exception:
        return ""


def _name(node) -> str:
    try:
        return node.get_name() or ""
    except Exception:
        return ""


def top_windows() -> list[dict]:
    """All top-level accessible windows: [{app, pid, name, role, active, node}]"""
    out: list[dict] = []
    if not _init():
        return out
    with LOCK:
        desktop = Atspi.get_desktop(0)
        try:
            napps = desktop.get_child_count()
        except Exception:
            return out
        for i in range(napps):
            try:
                app = desktop.get_child_at_index(i)
            except Exception:
                continue
            if app is None:
                continue
            appname = _name(app)
            try:
                pid = app.get_process_id()
            except Exception:
                pid = 0
            try:
                nwin = app.get_child_count()
            except Exception:
                continue
            for j in range(min(nwin, 50)):
                try:
                    win = app.get_child_at_index(j)
                except Exception:
                    continue
                if win is None:
                    continue
                st = _states(win)
                out.append({
                    "app": appname, "pid": pid, "name": _name(win), "role": _role(win),
                    "active": Atspi.StateType.ACTIVE in st,
                    "showing": Atspi.StateType.SHOWING in st, "node": win,
                })
    return out


def find_window(title: str | None = None, pid: int | None = None) -> dict | None:
    wins = top_windows()
    active = [w for w in wins if w["active"]]
    if title is None and pid is None:
        return active[-1] if active else None
    # Prefer exact title (+pid) matches, then active ones.
    def score(w):
        s = 0
        if title is not None and w["name"] == title:
            s += 4
        elif title is not None and title and (title in w["name"] or w["name"] in title) and w["name"]:
            s += 2
        if pid and w["pid"] == pid:
            s += 2
        if w["active"]:
            s += 1
        return s
    best = max(wins, key=score, default=None)
    if best is None or score(best) < 2:
        return active[-1] if active else None
    return best


def snapshot(window: dict, max_elements: int = 250, budget: float = 3.0,
             text_limit: int = 160, max_children: int = 400,
             screen: tuple[int, int] | None = None) -> Snapshot:
    """Walk a window's accessible tree and collect visible, meaningful elements."""
    snap = Snapshot(app=window.get("app", ""), window=window.get("name", ""))
    if not _init():
        snap.error = "accessibility is not available in this desktop"
        return snap
    start = time.monotonic()
    deadline = start + budget
    sw, sh = screen or (100000, 100000)
    elements: list[Element] = []

    def walk(node, depth: int, shown_depth: int) -> None:
        if snap.truncated:
            return
        if len(elements) >= max_elements or time.monotonic() > deadline or snap.visited > 6000:
            snap.truncated = True
            return
        snap.visited += 1
        st = _states(node)
        if depth > 0 and Atspi.StateType.SHOWING not in st:
            return
        role = _role(node)
        if role in SKIP_ROLES:
            return
        ext = _extents(node)
        boxed = False
        if ext is not None:
            x, y, w, h = ext
            boxed = w > 0 and h > 0
            if boxed and depth > 0 and (x >= sw or y >= sh or x + w <= 0 or y + h <= 0):
                return  # entirely off-screen
        else:
            x = y = w = h = 0
        name = _clip(_name(node), text_limit)
        ifaces = _interfaces(node)
        text = ""
        value = ""
        if "Text" in ifaces and (role in TEXTUAL or role in TEXT_INPUT or role.startswith("document")):
            if role not in ("document web", "document frame") or not name:
                if role == "terminal":
                    text = _text(node, 600, tail=True)
                elif role in ("text", "document text"):
                    text = _text(node, 300)
                else:
                    text = _text(node, text_limit if role not in TEXT_INPUT else 80)
                if "\ufffc" in text:
                    text = _expand_embedded(node, text, text_limit)
            if text == name:
                text = ""
        if "Value" in ifaces and role in ("slider", "spin button", "progress bar", "scroll bar", "level bar"):
            value = _value(node)
        flags: list[str] = []
        if Atspi.StateType.FOCUSED in st:
            flags.append("focused")
        if Atspi.StateType.CHECKABLE in st or role in ("check box", "radio button", "toggle button",
                                                        "check menu item", "radio menu item", "switch"):
            flags.append("checked" if Atspi.StateType.CHECKED in st else "unchecked")
        if Atspi.StateType.SELECTED in st and role in ("page tab", "list item", "tree item",
                                                        "table cell", "menu item", "radio button"):
            flags.append("selected")
        if Atspi.StateType.EXPANDABLE in st:
            flags.append("expanded" if Atspi.StateType.EXPANDED in st else "collapsed")
        if role in INTERACTIVE and (Atspi.StateType.ENABLED not in st and Atspi.StateType.SENSITIVE not in st):
            flags.append("disabled")
        if Atspi.StateType.EDITABLE in st and role not in TEXT_INPUT and role.startswith("document"):
            flags.append("editable")

        emit = False
        if not boxed:
            pass  # no on-screen box: nothing to point at, but its children may have one
        elif role in INTERACTIVE or role in TEXT_INPUT:
            emit = bool(name or text or value or role in TEXT_INPUT or "focused" in flags)
        elif role in TEXTUAL:
            emit = bool(name or text)
        elif role in CONTAINERS_WITH_TITLE:
            emit = bool(name) and depth > 0
        elif name and role in ("image", "graphic", "icon", "canvas", "embedded object", "page"):
            emit = True

        child_shown_depth = shown_depth
        if emit:
            elements.append(Element(
                id=len(elements) + 1, role=role, name=name, depth=shown_depth,
                x=x, y=y, w=w, h=h, text=text, value=value, states=flags, node=node,
            ))
            child_shown_depth = shown_depth + 1
            # Leaves: their children only repeat the name.
            if role in LEAVES and (name or text):
                return
        try:
            n = node.get_child_count()
        except Exception:
            return
        if n > max_children * 10:
            elements.append(Element(
                id=len(elements) + 1, role=role or "container", name=name,
                depth=child_shown_depth, x=x, y=y, w=w, h=h,
                text=f"[{n} children — too many to list; use OCR or a screenshot]", node=node,
            ))
            return
        for i in range(min(n, max_children)):
            if snap.truncated:
                return
            try:
                child = node.get_child_at_index(i)
            except Exception:
                continue
            if child is not None:
                walk(child, depth + 1, child_shown_depth)
        if n > max_children:
            snap.truncated = True

    with LOCK:
        try:
            walk(window["node"], 0, 0)
        except Exception as e:  # never let a broken app break `see`
            snap.error = f"{type(e).__name__}: {e}"
    snap.elements = compact(elements)
    snap.elapsed = time.monotonic() - start
    return snap


WRAPPERS = {"list item", "paragraph", "label", "static", "table cell", "cell", "section", "heading"}


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold().strip(" :") == " ".join(b.split()).casefold().strip(" :")


def compact(elements: list[Element]) -> list[Element]:
    """Drop wrappers that only repeat their single child ("list item 'News'" > "link 'News'"),
    keeping the child (a heading's link becomes a "heading link"), then renumber the ids."""
    out: list[Element] = []
    n = len(elements)
    seen: list[tuple[str, str, int, int]] = []
    for i, el in enumerate(elements):
        # Twins: some apps expose the same control twice (e.g. two menu bars) a few pixels apart.
        cx, cy = el.center
        label = el.label()
        tol_x = 60 if el.role in ("menu", "menu item") else 12
        if label and el.interactive and any(r == el.role and lab == label and abs(cx - x) <= tol_x and abs(cy - y) <= 12
                                            for r, lab, x, y in seen):
            continue
        seen.append((el.role, label, cx, cy))
        nxt = elements[i + 1] if i + 1 < n else None
        only_child = (nxt is not None and nxt.depth == el.depth + 1
                      and (i + 2 >= n or elements[i + 2].depth <= el.depth))
        if (el.role in WRAPPERS and only_child and nxt.interactive
                and (not el.label() or _same(el.label(), nxt.label()))):
            if el.role == "heading":
                nxt.role = f"heading {nxt.role}"
            nxt.depth = el.depth
            continue
        out.append(el)
    for k, el in enumerate(out, 1):
        el.id = k
    return out


def refresh(el: Element) -> tuple[int, int, int, int] | None:
    """Current on-screen box of an element (it may have moved since the snapshot)."""
    if not _init() or el.node is None:
        return None
    with LOCK:
        st = _states(el.node)
        if not st or Atspi.StateType.DEFUNCT in st:
            return None
        ext = _extents(el.node)
        return ext


def scroll_into_view(el: Element) -> bool:
    if not _init() or el.node is None:
        return False
    with LOCK:
        try:
            return bool(Atspi.Component.scroll_to(el.node, Atspi.ScrollType.ANYWHERE))
        except Exception:
            return False


def set_text(el: Element, text: str) -> bool:
    """Replace an editable element's contents directly (fast, exact, no typing)."""
    if not _init() or el.node is None:
        return False
    with LOCK:
        try:
            if "EditableText" not in _interfaces(el.node):
                return False
            try:
                Atspi.Component.grab_focus(el.node)
            except Exception:
                pass
            return bool(Atspi.EditableText.set_text_contents(el.node, text))
        except Exception:
            return False


def format_elements(elements: list[Element], max_depth: int = 6) -> list[str]:
    lines = []
    for el in elements:
        indent = "  " * min(el.depth, max_depth)
        cx, cy = el.center
        s = f"{indent}@{el.id} {el.role}"
        if el.name:
            s += f' "{el.name}"'
        if el.text:
            s += f' "{el.text}"' if not el.name else f": {el.text}"
        if el.value:
            s += f" value={el.value}"
        if el.states:
            s += " [" + ", ".join(el.states) + "]"
        if el.w and el.h:
            s += f" ({cx},{cy})"
        lines.append(s)
    return lines
