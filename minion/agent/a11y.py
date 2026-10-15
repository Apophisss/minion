"""Accessibility snapshots through AT-SPI.

Turns the UI of the focused window into a compact, numbered list of elements
("@12 push button "Save" (210,62)") that an agent can read for a fraction of the
tokens of a screenshot, and click by reference. Works with GTK, Qt, Firefox,
Chromium/Electron (with accessibility enabled) and LibreOffice.
"""

from __future__ import annotations

import importlib.util
import re
import threading
import time
from dataclasses import dataclass, field

# Optional dependency (python3-gi + gir1.2-atspi-2.0), loaded on first use so that idle
# desktops never pay for it.
Atspi = None  # type: ignore
try:
    AVAILABLE = importlib.util.find_spec("gi") is not None
except (ImportError, ValueError):  # pragma: no cover
    AVAILABLE = False


def _load() -> bool:
    global Atspi, AVAILABLE
    if Atspi is not None:
        return True
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi as _atspi  # type: ignore

        Atspi = _atspi
        return True
    except Exception:
        AVAILABLE = False
        return False


LOCK = threading.RLock()
_initialized = False

INTERACTIVE = {
    "push button",
    "toggle button",
    "check box",
    "radio button",
    "menu item",
    "check menu item",
    "radio menu item",
    "tearoff menu item",
    "menu",
    "combo box",
    "entry",
    "password text",
    "spin button",
    "slider",
    "link",
    "page tab",
    "list item",
    "tree item",
    "split button",
    "button",
    "toggle",
    "switch",
    "date editor",
    "font chooser",
    "color chooser",
    "icon",
    "tool bar item",
}
TEXT_INPUT = {"entry", "password text", "text", "terminal", "spin button", "combo box"}
TEXTUAL = {
    "heading",
    "paragraph",
    "label",
    "static",
    "caption",
    "text",
    "terminal",
    "block quote",
    "list item",
    "table cell",
    "cell",
    "column header",
    "row header",
    "table column header",
    "table row header",
    "description term",
    "description value",
    "footer",
    "header",
    "comment",
    "math",
    "mark",
    "notification",
    "alert",
    "status bar",
    "info bar",
    "tooltip",
    "title bar",
}
CONTAINERS_WITH_TITLE = {
    "dialog",
    "alert",
    "file chooser",
    "page tab list",
    "menu bar",
    "tool bar",
    "table",
    "tree table",
    "tree",
    "list",
    "list box",
    "document frame",
    "document web",
    "document text",
    "document spreadsheet",
    "document presentation",
    "document email",
    "form",
    "landmark",
    "navigation",
    "group",
    "grouping",
    "panel",
    "section",
    "article",
    "region",
    "scroll pane",
    "frame",
    "window",
}
SKIP_ROLES = {"scroll bar", "separator"}  # never emitted, never descended
TOP_LEVEL = {"frame", "window", "dialog", "alert", "file chooser"}
LEAVES = {
    "push button",
    "button",
    "toggle button",
    "split button",
    "check box",
    "radio button",
    "menu item",
    "check menu item",
    "radio menu item",
    "link",
    "entry",
    "password text",
    "terminal",
    "spin button",
    "slider",
    "switch",
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
    in_doc: bool = False  # inside a web page (vs. the browser's own UI)
    own: bool = False  # a container with text of its own besides its child elements
    lines: list | None = None  # editors and terminals: their text as lines, layout kept

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def interactive(self) -> bool:
        return self.role in INTERACTIVE or self.role in TEXT_INPUT

    def label(self) -> str:
        if self.role in ("combo box", "list box") and self.text.startswith("options: "):
            return self.name or self.value  # a dropdown is known by its name or value, not its option list
        return self.name or self.text or self.value

    def to_dict(self) -> dict:
        cx, cy = self.center
        d = {
            "id": f"@{self.id}",
            "role": self.role,
            "name": self.name,
            "x": cx,
            "y": cy,
            "box": [self.x, self.y, self.w, self.h],
        }
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
    header: list[str] = field(default_factory=list)


def _init() -> bool:
    global _initialized
    if not AVAILABLE or not _load():
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


def _text(node, limit: int, tail: bool = False, depth: int = 0) -> str:
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
            return out if len(out) <= limit else "…" + out[-(limit - 1) :].lstrip()
        raw = Atspi.Text.get_text(node, 0, min(n, limit * 4))
        if "\ufffc" in raw:  # embedded objects (links, inline code, images): what they show
            raw = _expand_embedded(node, raw, depth)
        return _lines(raw, limit)
    except Exception:
        return ""


# Embedded children that are part of the running text (their visible text goes inline); anything else
# (paragraphs, lists, tables...) is a block of its own: listed separately, shown inline as "…".
BLOCK_ROLES = {
    "paragraph",
    "heading",
    "list",
    "list item",
    "table",
    "table row",
    "table cell",
    "cell",
    "section",
    "article",
    "form",
    "block quote",
    "panel",
    "landmark",
    "grouping",
    "description list",
    "separator",
    "tree",
    "tree table",
    "page tab list",
    "tool bar",
    "menu bar",
}


def _embedded_text(child, depth: int) -> str:
    """What an embedded child shows inside its parent's text: its visible text, not a tooltip
    (<abbr title>) or a field's label; an image's name; a block becomes "…"."""
    role = _role(child)
    if role in BLOCK_ROLES or role.startswith("document"):
        return " … "
    if role in ("image", "graphic", "icon"):
        return _name(child)
    if role in TEXT_INPUT:
        return _text(child, 80, depth=depth + 1) if "Text" in _interfaces(child) else ""
    if "Text" in _interfaces(child):
        shown = _text(child, 200, depth=depth + 1)
        if shown:
            return shown
    return _name(child)


def _embedded_object(node, offset: int, hyper: bool):
    """The object behind the U+FFFC at `offset`, through the Hypertext interface. (Chromium also exposes
    plain text runs as children, so "the k-th placeholder is child k" is not reliable.)"""
    if not hyper:
        return None
    try:
        index = Atspi.Hypertext.get_link_index(node, offset)
        if index < 0:
            return None
        link = Atspi.Hypertext.get_link(node, index)
        return Atspi.Hyperlink.get_object(link, 0) if link is not None else None
    except Exception:
        return None


def _expand_embedded(node, raw: str, depth: int = 0) -> str:
    """Replace U+FFFC placeholders (embedded links, inline code, images...) with what they show."""
    try:
        n = node.get_child_count()
    except Exception:
        return raw
    hyper = "Hypertext" in _interfaces(node)
    out, child = [], 0
    for offset, ch in enumerate(raw):
        if ch == "\ufffc":
            shown = ""
            try:
                kid = _embedded_object(node, offset, hyper)
                if kid is None and child < n:
                    kid = node.get_child_at_index(child)
                if kid is not None:
                    shown = _embedded_text(kid, depth) if depth < 3 and child < 80 else _name(kid)
            except Exception:
                shown = ""
            child += 1
            out.append(shown)
        else:
            out.append(ch)
    return "".join(out)


def _layout(node, max_lines: int, tail: bool = False) -> list | None:
    """Multi-line text with its layout (indentation, blank lines) for editors and terminals, or None
    for single-line text. Long runs of one symbol (===== rules) are shortened."""
    try:
        n = Atspi.Text.get_character_count(node)
        if n <= 0:
            return None
        start = max(0, n - 6000) if tail else 0
        raw = Atspi.Text.get_text(node, start, min(n, start + 12000))
    except Exception:
        return None
    raw = raw.replace("\ufffc", " ").translate(_INVISIBLE).replace("\t", "    ")
    lines = [re.sub(r"([^\w\s]|_)\1{7,}", r"\1\1\1…", ln.rstrip()) for ln in raw.splitlines()]
    if len(lines) < 2:
        return None
    if tail:
        while lines and not lines[-1].strip():
            lines.pop()
        return lines[-max_lines:]
    more = len(lines) - max_lines
    lines = [ln[:200] for ln in lines[:max_lines]]
    if more > 0:
        lines.append(f"… {more} more lines")
    return lines


def _own_text(node, limit: int = 600) -> str:
    """A container's own text, without its embedded children ("1321 points by"): empty for
    containers that only hold other elements."""
    try:
        n = Atspi.Text.get_character_count(node)
        if n <= 0:
            return ""
        raw = Atspi.Text.get_text(node, 0, min(n, limit))
    except Exception:
        return ""
    return " ".join(raw.replace("\ufffc", " ").translate(_INVISIBLE).split())


def _overlap(a: str, b: str) -> bool:
    """Do two strings say mostly the same thing ("161 points by x | hide" vs the same plus a timestamp)?"""
    wa, wb = a.casefold().split(), b.casefold().split()
    if not wa or not wb:
        return False
    small, large = (wa, set(wb)) if len(wa) <= len(wb) else (wb, set(wa))
    return sum(w in large for w in small) >= 0.8 * len(small)


def _substantial(text: str) -> bool:
    return sum(ch.isalnum() for ch in text) >= 3


def _col(c: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA (spreadsheet column names)."""
    out, c = "", c + 1
    while c:
        c, r = divmod(c - 1, 26)
        out = chr(65 + r) + out
    return out


def _cell_rc(table, cell) -> tuple[int, int] | None:
    try:
        res = Atspi.TableCell.get_position(cell)
        if isinstance(res, tuple) and len(res) == 3 and res[0]:
            return int(res[1]), int(res[2])
    except Exception:
        pass
    try:
        idx = cell.get_index_in_parent()
        return int(Atspi.Table.get_row_at_index(table, idx)), int(Atspi.Table.get_column_at_index(table, idx))
    except Exception:
        return None


def _visible_cells(
    table, x: int, y: int, w: int, h: int, deadline: float, max_rows: int = 60, max_cols: int = 26, max_cells: int = 150
):
    """The non-empty cells currently on screen in a huge table (a spreadsheet), with their A1 refs."""
    try:
        tl = Atspi.Component.get_accessible_at_point(table, x + 3, y + 3, Atspi.CoordType.SCREEN)
        br = Atspi.Component.get_accessible_at_point(table, x + w - 4, y + h - 4, Atspi.CoordType.SCREEN)
    except Exception:
        return None
    if tl is None or br is None:
        return None
    a, b = _cell_rc(table, tl), _cell_rc(table, br)
    if a is None or b is None:
        return None
    r0, c0 = a
    r1, c1 = min(b[0], r0 + max_rows - 1), min(b[1], c0 + max_cols - 1)
    found, empty = [], []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if time.monotonic() > deadline or len(found) >= max_cells:
                return (r0, c0, r1, c1), found
            try:
                cell = Atspi.Table.get_accessible_at(table, r, c)
            except Exception:
                continue
            if cell is None:
                continue
            content = _text(cell, 80) if "Text" in _interfaces(cell) else ""
            if not content:
                empty.append((r, c, cell))
                continue
            ext = _extents(cell) or (0, 0, 0, 0)
            found.append((f"{_col(c)}{r + 1}", content, cell, ext, _formula(cell), r, c))
    if found:  # a formula that failed shows an error on screen but no text: look around the data
        rows = [f[5] for f in found]
        cols = [f[6] for f in found]
        for r, c, cell in empty:
            if min(rows) - 1 <= r <= max(rows) + 1 and min(cols) - 1 <= c <= max(cols) + 1:
                if time.monotonic() > deadline:
                    break
                formula = _formula(cell)
                if formula:
                    found.append((f"{_col(c)}{r + 1}", "#ERROR", cell, _extents(cell) or (0, 0, 0, 0), formula, r, c))
        found.sort(key=lambda f: (f[5], f[6]))
    return (r0, c0, r1, c1), [f[:5] for f in found]


def _formula(cell) -> str:
    """A spreadsheet cell's formula ("=SUM(B2:B6)"), from LibreOffice's object attributes, or ""."""
    try:
        formula = (cell.get_attributes() or {}).get("Formula", "")
    except Exception:
        return ""
    if formula.endswith("\\"):  # LibreOffice's attribute string loses everything after an escaped ":"
        formula = formula[:-1] + "…"
    formula = re.sub(r"\\(.)", r"\1", formula)  # and escapes "," and ";" in the rest: "=SUM(1\,2)"
    return "=" + formula if formula and not formula.startswith("=") else formula


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
                out.append(
                    {
                        "app": appname,
                        "pid": pid,
                        "name": _name(win),
                        "role": _role(win),
                        "active": Atspi.StateType.ACTIVE in st,
                        "showing": Atspi.StateType.SHOWING in st,
                        "node": win,
                    }
                )
    return out


def find_window(title: str | None = None, pid: int | None = None, box=None) -> dict | None:
    """The accessible window for an X window (its title, process and on-screen box [x, y, w, h]).
    The box is the strongest clue: a "Save" dialog's confirmation is also titled "Save" for the window
    manager, but accessibility calls it "Question"."""
    wins = top_windows()
    active = [w for w in wins if w["active"]]
    if title is None and pid is None:
        return active[-1] if active else None

    distances: dict[int, int] = {}

    def distance(w) -> int:
        if id(w) not in distances:
            with LOCK:
                e = _extents(w["node"])
            distances[id(w)] = sum(abs(a - b) for a, b in zip(e, box, strict=True)) if e else 1 << 30
        return distances[id(w)]

    # Same place and size, then exact title (+pid) matches, then active ones.
    def score(w):
        s = 0
        if box is not None and (not pid or w["pid"] == pid) and distance(w) <= 40:
            s += 5
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
    tied = [w for w in wins if score(w) == score(best)]
    if box is not None and len(tied) > 1:
        best = min(tied, key=distance)
    return best


def window_for(win) -> dict | None:
    """find_window for a Windows.Window (wmctrl): by title, process and geometry."""
    if win is None:
        return find_window()
    return find_window(title=win.title, pid=win.pid, box=(win.x, win.y, win.w, win.h))


def snapshot(
    window: dict,
    max_elements: int = 250,
    budget: float = 3.0,
    text_limit: int = 160,
    max_children: int = 400,
    screen: tuple[int, int] | None = None,
    clip: bool = True,
) -> Snapshot:
    """Walk a window's accessible tree and collect visible, meaningful elements. clip=False also keeps
    page content that is scrolled out of view (to find a target and scroll it into view)."""
    snap = Snapshot(app=window.get("app", ""), window=window.get("name", ""))
    if not _init():
        snap.error = "accessibility is not available in this desktop"
        return snap
    start = time.monotonic()
    deadline = start + budget
    sw, sh = screen or (100000, 100000)
    elements: list[Element] = []

    def walk(node, depth: int, shown_depth: int, in_doc: bool = False, view=None) -> None:
        if snap.truncated:
            return
        if len(elements) >= max_elements or time.monotonic() > deadline or snap.visited > 6000:
            snap.truncated = True
            return
        snap.visited += 1
        st = _states(node)
        if depth > 0 and Atspi.StateType.SHOWING not in st and (clip or not in_doc):
            return  # (a page's content scrolled out of view isn't "showing", but it is there to scroll to)
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
            if boxed and depth > 0 and (x < 0 or y < 0 or x + w > sw or y + h > sh):
                # Partly visible: keep the visible part, so its center is a point you can click.
                x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, sw), min(y + h, sh)
                x, y, w, h = x0, y0, x1 - x0, y1 - y0
            if boxed and in_doc and view is not None:
                # The page's own viewport: content scrolled away, or under the browser's toolbar, is hidden.
                vx, vy, vw, vh = view
                if x >= vx + vw or y >= vy + vh or x + w <= vx or y + h <= vy:
                    return
                if x < vx or y < vy or x + w > vx + vw or y + h > vy + vh:
                    x0, y0, x1, y1 = max(x, vx), max(y, vy), min(x + w, vx + vw), min(y + h, vy + vh)
                    x, y, w, h = x0, y0, x1 - x0, y1 - y0
            if depth > 0 and role in ("menu bar", "tool bar") and (w > 0) != (h > 0):
                return  # a collapsed bar (e.g. LibreOffice's hidden twin menu bar): its items are phantoms
        else:
            x = y = w = h = 0
        name = _clip(_name(node), text_limit)
        ifaces = _interfaces(node)
        lines = None
        if role in TEXT_INPUT and role != "terminal" and boxed and (not name or name.strip().isdigit()):
            label = _label_of(node)  # "Columns" for an unnamed spin button (or one named after its value)
            if label:
                name = _clip(label, text_limit)
        text = ""
        value = ""
        if "Text" in ifaces and (role in TEXTUAL or role in TEXT_INPUT or role.startswith("document")):
            if role not in WEB_DOCS or not name:
                if role == "terminal":
                    text = _text(node, 600, tail=True)
                    lines = _layout(node, max_lines=14, tail=True)
                elif role in ("text", "document text"):
                    text = _text(node, 300)
                    if not in_doc:  # a code or text editor: its lines, indentation included
                        lines = _layout(node, max_lines=200 if text_limit > 500 else 30)
                else:
                    text = _text(node, text_limit if role not in TEXT_INPUT else 80)
            if text == name:
                text = ""
        own = False
        if not text and "Text" in ifaces and role in OWN_TEXT_ROLES and boxed:
            own_text = _own_text(node)
            if _substantial(own_text):  # e.g. a <div>/<pre> with plain text, or "1321 points by" in a cell
                own = True
                text = _text(node, text_limit)
                if text == name:
                    text = ""
                block = _layout(node, max_lines=200 if text_limit > 500 else 30)
                if block and any(ln[:1] in (" ", "\t") for ln in block):
                    lines = block  # preformatted text (<pre>, code): its layout matters
        elif text and role in CONTAINER_TEXT:
            own = _substantial(_own_text(node))
        if role in ("combo box", "list box") and not text and boxed:  # a <select>: its value and options
            selected, options = combo_value(node)
            if selected:
                value = _clip(selected, 80)
            if options:
                listed = " | ".join(options[:12]) + (f" | … ({len(options)} options)" if len(options) > 12 else "")
                text = _clip("options: " + listed, 300)
        if "Value" in ifaces and role in ("slider", "spin button", "progress bar", "scroll bar", "level bar"):
            value = _value(node)
            if role == "spin button" and text:
                value = ""  # the text shows the value as displayed ("07"), the number may not ("0")
        flags: list[str] = []
        if Atspi.StateType.FOCUSED in st:
            flags.append("focused")
        if Atspi.StateType.CHECKABLE in st or role in (
            "check box",
            "radio button",
            "toggle button",
            "check menu item",
            "radio menu item",
            "switch",
        ):
            flags.append("checked" if Atspi.StateType.CHECKED in st else "unchecked")
        if Atspi.StateType.SELECTED in st and role in (
            "page tab",
            "list item",
            "tree item",
            "table cell",
            "menu item",
            "radio button",
        ):
            flags.append("selected")
        if Atspi.StateType.EXPANDABLE in st:
            flags.append("expanded" if Atspi.StateType.EXPANDED in st else "collapsed")
        if role in INTERACTIVE and (Atspi.StateType.ENABLED not in st and Atspi.StateType.SENSITIVE not in st):
            flags.append("disabled")
        if Atspi.StateType.EDITABLE in st and role not in TEXT_INPUT and role.startswith("document"):
            flags.append("editable")

        if name and text and role not in INTERACTIVE and role not in TEXT_INPUT and _overlap(name, text):
            name = ""  # a name computed from the content (plus hidden extras): show the visible text once
        elif name and text and role in INTERACTIVE and _overlap(text, name) and len(text) <= len(name) + 3:
            text = ""  # a radio button "Small" whose text is "Small" again
        emit = False
        if not boxed:
            pass  # no on-screen box: nothing to point at, but its children may have one
        elif role in INTERACTIVE or role in TEXT_INPUT:
            emit = bool(name or text or value or role in TEXT_INPUT or "focused" in flags)
        elif role in TEXTUAL:
            emit = bool(name or text)
        elif own:
            emit = True
        elif role in CONTAINERS_WITH_TITLE:
            emit = bool(name) and depth > 0
        elif name and role in ("image", "graphic", "icon", "canvas", "embedded object", "page"):
            emit = True

        child_shown_depth = shown_depth
        if emit:
            elements.append(
                Element(
                    id=len(elements) + 1,
                    role=role,
                    name=name,
                    depth=shown_depth,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    text=text,
                    value=value,
                    states=flags,
                    node=node,
                    in_doc=in_doc,
                    own=own,
                    lines=lines,
                )
            )
            child_shown_depth = shown_depth + 1
            # Leaves: their children only repeat the name.
            if role in LEAVES and (name or text):
                return
        try:
            n = node.get_child_count()
        except Exception:
            return
        if n > max_children * 10:
            cells = _visible_cells(node, x, y, w, h, deadline) if "Table" in ifaces and boxed else None
            if cells is not None:
                (r0, c0, r1, c1), found = cells
                if elements and elements[-1].node is node:  # replace the table's own line
                    child_shown_depth = elements.pop().depth
                elements.append(
                    Element(
                        id=len(elements) + 1,
                        role="sheet" if role == "table" else role,
                        name=name,
                        depth=child_shown_depth,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        text=f"visible {_col(c0)}{r0 + 1}:{_col(c1)}{r1 + 1}, {len(found)} non-empty cells",
                        node=node,
                        in_doc=in_doc,
                    )
                )
                for ref, content, cell, (cx0, cy0, cw, ch), formula in found:
                    elements.append(
                        Element(
                            id=len(elements) + 1,
                            role="cell",
                            name=ref,
                            depth=child_shown_depth + 1,
                            x=cx0,
                            y=cy0,
                            w=cw,
                            h=ch,
                            text=content,
                            value=formula,
                            node=cell,
                            in_doc=in_doc,
                        )
                    )
                return
            elements.append(
                Element(
                    id=len(elements) + 1,
                    role=role or "container",
                    name=name,
                    depth=child_shown_depth,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    text=f"[{n} children — too many to list; use OCR or a screenshot]",
                    node=node,
                )
            )
            return
        for i in range(min(n, max_children)):
            if snap.truncated:
                return
            try:
                child = node.get_child_at_index(i)
            except Exception:
                continue
            if child is not None:
                walk(
                    child,
                    depth + 1,
                    child_shown_depth,
                    in_doc or role in WEB_DOCS,
                    (x, y, w, h) if role in WEB_DOCS and boxed and clip else view,
                )
        if n > max_children:
            snap.truncated = True

    with LOCK:
        try:
            walk(window["node"], 0, 0)
        except Exception as e:  # never let a broken app break `see`
            snap.error = f"{type(e).__name__}: {e}"
    snap.elements, snap.header = browser_compact(compact(elements))
    snap.elapsed = time.monotonic() - start
    return snap


WRAPPERS = {"list item", "paragraph", "label", "static", "table cell", "cell", "section", "heading"}
CONTAINER_TEXT = {"list item", "table cell", "cell", "section"}
OWN_TEXT_ROLES = {"section", "article", "block quote", "form", "panel", "grouping", "list item", "table cell", "cell"}
WEB_DOCS = {"document web"}  # browsers' page role ("document frame" is also used by LibreOffice Impress panes)
ADDRESS_HINTS = ("address", "search or enter", "url", "location")


def _is_address(el: Element) -> bool:
    if el.role not in ("combo box", "entry", "text"):
        return False
    label = el.name.casefold()
    content = (el.text or el.value).casefold()
    return any(h in label for h in ADDRESS_HINTS) or "://" in content


def browser_compact(elements: list[Element]) -> tuple[list[Element], list[str]]:
    """In a web browser, keep the page and only the useful bits of the browser's own UI
    (tabs when there are several, the address bar, dialogs): saves many tokens per `see`."""
    if not any(e.in_doc for e in elements):
        return elements, []
    tabs = [e for e in elements if not e.in_doc and e.role == "page tab"]
    page = next((e for e in elements if not e.in_doc and e.role in WEB_DOCS), None)
    # An open menu (a right-click menu, the ≡ menu) is what the next action is about: it goes first.
    keep: list[Element] = [e for e in elements if not e.in_doc and e.role in MENU_ITEM_ROLES]
    for e in elements:
        if e.in_doc:
            keep.append(e)
        elif e.role in WEB_DOCS:
            continue
        elif (
            (e.role == "page tab" and len(tabs) > 1)
            or _is_address(e)
            or e.role in ("alert", "dialog", "notification", "info bar")
        ):
            e.depth = 0
            if _is_address(e):
                e.role = "address bar"
            keep.append(e)
    shift = min((e.depth for e in keep if e.in_doc), default=0)
    for e in keep:
        if e.in_doc:
            e.depth = max(0, e.depth - shift)
    for k, e in enumerate(keep, 1):
        e.id = k
    header = []
    if page is not None and page.name:
        header.append(f'Web page "{page.name}"' + (f" ({len(tabs)} tabs open)" if len(tabs) > 1 else ""))
    return keep, header


def popup_menus(window: dict, screen: tuple[int, int] | None = None) -> list[Element]:
    """The open popup menus of a window's app that live in windows of their own (GTK, Qt and LibreOffice
    right-click menus, an opened menu-bar menu): their items, so `see` lists them and targets reach them."""
    if not _init():
        return []
    out: list[Element] = []
    for tw in top_windows():
        if tw["pid"] != window.get("pid") or not tw["showing"] or tw["role"] not in ("window", "menu", "popup menu"):
            continue
        if tw["node"] is window.get("node"):
            continue
        snap = snapshot(tw, max_elements=80, budget=1.0, screen=screen)
        if any(e.role in MENU_ITEM_ROLES for e in snap.elements):
            out.extend(snap.elements)
    return out


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold().strip(" :") == " ".join(b.split()).casefold().strip(" :")


def compact(elements: list[Element]) -> list[Element]:
    """Drop wrappers that only repeat their single child ("list item 'News'" > "link 'News'"),
    keeping the child (a heading's link becomes a "heading link"), then renumber the ids."""
    out: list[Element] = []
    n = len(elements)
    seen: list[tuple[str, str, int, int]] = []
    skip: set[int] = set()
    parents: list[Element] = []  # the chain of ancestors of the current element
    for i, el in enumerate(elements):
        while parents and parents[-1].depth >= el.depth:
            parents.pop()
        parents.append(el)
        if i in skip:
            continue
        # Chromium lists a paragraph's text runs as children too: drop the ones the parent already shows.
        parent = parents[-2] if len(parents) > 1 else None
        if (
            el.role in ("static", "text")
            and not el.interactive
            and not el.lines
            and parent is not None
            and (parent.role in TEXTUAL or parent.own)
            and any(
                part and " ".join(part.split()) in " ".join((parent.text or parent.name).split())
                for part in (el.text, el.name)
            )
        ):
            continue
        # Twins: some apps expose the same control twice (e.g. two menu bars) a few pixels apart.
        cx, cy = el.center
        label = el.label()
        tol_x = 60 if el.role in ("menu", "menu item") else 12
        if (
            label
            and el.interactive
            and any(
                r == el.role and lab == label and abs(cx - x) <= tol_x and abs(cy - y) <= 12 for r, lab, x, y in seen
            )
        ):
            continue
        seen.append((el.role, label, cx, cy))
        nxt = elements[i + 1] if i + 1 < n else None
        if el.role in CONTAINER_TEXT and nxt is not None and nxt.depth > el.depth and not el.own:
            continue  # a list item/cell with children: the children carry the content
        only_child = nxt is not None and nxt.depth == el.depth + 1 and (i + 2 >= n or elements[i + 2].depth <= el.depth)
        if (
            el.role in WRAPPERS
            and only_child
            and nxt.interactive
            and (not el.label() or _same(el.label(), nxt.label()))
        ):
            if el.role == "heading":
                nxt.role = f"heading {nxt.role}"
            nxt.depth = el.depth
            continue
        if (
            only_child
            and nxt.role in ("static", "text", "label")
            and not nxt.interactive
            and el.label()
            and _same(el.label(), nxt.label())
        ):
            skip.add(i + 1)  # "paragraph X" > "static X": the child adds nothing
        out.append(el)
    _redepth(elements, out)
    for k, el in enumerate(out, 1):
        el.id = k
    return out


def _redepth(original: list[Element], kept: list[Element]) -> None:
    """Recompute indentation after dropping elements: depth = number of kept ancestors."""
    keep_ids = {id(e) for e in kept}
    stack: list[tuple[int, bool]] = []  # (original depth, kept?)
    new_depth: dict[int, int] = {}
    for e in original:
        while stack and stack[-1][0] >= e.depth:
            stack.pop()
        if id(e) in keep_ids:
            new_depth[id(e)] = sum(1 for _, k in stack if k)
        stack.append((e.depth, id(e) in keep_ids))
    for e in kept:
        e.depth = new_depth.get(id(e), e.depth)


def is_editable(el: Element) -> bool:
    """Can text be typed into it: a text input role, or the EDITABLE state (e.g. contenteditable)."""
    if el.role in TEXT_INPUT or "editable" in el.states or el.role.startswith("document"):
        return True
    node = el.node
    if node is None or not _load():
        return True  # can't tell: don't block
    try:
        return node.get_state_set().contains(Atspi.StateType.EDITABLE)
    except Exception:
        return True


OPTION_ROLES = ("list item", "menu item", "option", "check menu item", "radio menu item", "table cell")


def _option_nodes(node, limit: int = 60) -> list:
    """The options of a combo box / list box (also while it is closed), as (name, node, selected)."""
    out, queue = [], [(node, 0)]
    while queue and len(out) < limit:
        cur, depth = queue.pop(0)
        try:
            n = min(cur.get_child_count(), limit)
            kids = [cur.get_child_at_index(i) for i in range(n)]
        except Exception:
            continue
        for kid in kids:
            if kid is None:
                continue
            role = _role(kid)
            if role in OPTION_ROLES or "option" in role:
                st = _states(kid)
                selected = Atspi.StateType.SELECTED in st or Atspi.StateType.CHECKED in st
                out.append((_name(kid), kid, selected))
            elif depth < 3:
                queue.append((kid, depth + 1))
    return out


def combo_value(node) -> tuple[str, list[str]]:
    """(the selected option, the option names) of a combo box."""
    opts = _option_nodes(node)
    selected = next((name for name, _, sel in opts if sel and name), "")
    return selected, [name for name, _, _ in opts if name]


def select_option(el: Element, wanted: str) -> str | None:
    """Pick an option of a combo/list box through accessibility (no popup needed). Returns the option
    chosen, or None if the app offers no way to do it (the caller then uses the keyboard)."""
    if el.node is None or not _init():
        return None
    with LOCK:
        opts = [(name, node) for name, node, _ in _option_nodes(el.node) if name]
        if not opts:
            return None
        low = wanted.casefold().strip()
        pick = (
            next((o for o in opts if o[0].casefold() == low), None)
            or next((o for o in opts if o[0].casefold().startswith(low)), None)
            or next((o for o in opts if low in o[0].casefold()), None)
        )
        if pick is None:
            raise ValueError(f'no option "{wanted}"; options: ' + " | ".join(o[0] for o in opts[:20]))
        name, node = pick
        try:  # Selection interface on the option's list
            parent = node.get_parent()
            if parent is not None and "Selection" in _interfaces(parent):
                if Atspi.Selection.select_child(parent, node.get_index_in_parent()):
                    return name
        except Exception:
            pass
        try:  # or the option's own action
            for i in range(Atspi.Action.get_n_actions(node)):
                if Atspi.Action.get_action_name(node, i) in ("select", "click", "press", "activate"):
                    Atspi.Action.do_action(node, i)
                    return name
        except Exception:
            pass
    return None


MENU_ITEM_ROLES = {"menu item", "check menu item", "radio menu item", "menu"}
_MODIFIERS = {"primary": "ctrl", "control": "ctrl", "ctrl": "ctrl", "shift": "shift", "alt": "alt", "mod1": "alt"}
_MODIFIERS.update({"super": "super", "meta": "super", "cmd": "ctrl"})


def _shortcut(binding: str) -> str:
    """An action's key binding as "ctrl+shift+s". GTK gives "mnemonic;<Alt>f:s;<Primary><Shift>s",
    Qt and LibreOffice "Ctrl+Shift+S"."""
    accel = binding.split(";")[2] if binding.count(";") >= 2 else binding
    mods = re.findall(r"<(\w+)>", accel)
    key = re.sub(r"<\w+>", "", accel).strip()
    if not mods and "+" in key.rstrip("+"):
        *mods, key = key.split("+")
    if not key or key.startswith(":") or ":" in key:
        return ""
    names = [_MODIFIERS.get(m.lower(), m.lower()) for m in mods]
    order = [m for m in ("ctrl", "alt", "shift", "super") if m in names]
    return "+".join([*order, key.lower() if len(key) == 1 else key])


def _action_names(node) -> list[str]:
    try:
        return [Atspi.Action.get_action_name(node, i) or "" for i in range(Atspi.Action.get_n_actions(node))]
    except Exception:
        return []


def _key_binding(node) -> str:
    try:
        for i in range(Atspi.Action.get_n_actions(node)):
            found = _shortcut(Atspi.Action.get_key_binding(node, i) or "")
            if found:
                return found
    except Exception:
        pass
    return ""


def _children(node, limit: int = 200) -> list:
    try:
        n = min(node.get_child_count(), limit)
    except Exception:
        return []
    out = []
    for i in range(n):
        try:
            child = node.get_child_at_index(i)
        except Exception:
            continue
        if child is not None:
            out.append(child)
    return out


def _menu_bar(window: dict, max_depth: int = 6):
    """The window's menu bar (a real one: LibreOffice also exposes an empty, collapsed twin)."""
    queue, best = [(window["node"], 0)], None
    while queue:
        node, depth = queue.pop(0)
        if _role(node) == "menu bar":
            box = _extents(node)
            kids = len(_children(node, 40))
            if kids and (best is None or (box and box[2] > 0 and box[3] > 0)):
                best = node
                if box and box[2] > 0 and box[3] > 0:
                    return node
            continue
        if depth < max_depth:
            queue.extend((c, depth + 1) for c in _children(node, 60))
    return best


def menu_name(name: str) -> str:
    """Menu labels compare without mnemonics, ellipses and case: "Save _As…" == "save as"."""
    return " ".join(re.sub(r"[_&~]|\.\.\.|…", "", name).split()).casefold().rstrip(":")


def menu_items(window: dict, max_depth: int = 2, limit: int = 600) -> list[tuple[int, str, str, bool, bool]]:
    """The commands in the window's menus, without opening them: [(depth, name, shortcut, enabled, submenu)]."""
    if not _init():
        return []
    out: list[tuple[int, str, str, bool, bool]] = []
    with LOCK:
        bar = _menu_bar(window)
        if bar is None:
            return []

        def walk(node, depth: int) -> None:
            for child in _children(node):
                if len(out) >= limit:
                    return
                role = _role(child)
                if role not in MENU_ITEM_ROLES:
                    if role in ("panel", "filler", "unknown"):  # some toolkits wrap items in a container
                        walk(child, depth)
                    continue
                name = _name(child).strip()
                if not name:
                    continue
                st = _states(child)
                enabled = Atspi.StateType.ENABLED in st or Atspi.StateType.SENSITIVE in st
                sub = role == "menu"
                out.append((depth, name, "" if sub else _key_binding(child), enabled, sub))
                if sub and depth < max_depth:
                    walk(child, depth + 1)

        walk(bar, 0)
    return out


def format_menus(items: list[tuple[int, str, str, bool, bool]], width: int = 400) -> list[str]:
    """One line per menu: "File: New ▸ · Open... (ctrl+o) · Save (ctrl+s) · … (+3 greyed out)". Commands
    that can't be used right now are only counted (they cost tokens and can't be chosen)."""
    lines: list[str] = []
    path: list[str] = []
    current: dict[str, list[str]] = {}
    greyed: dict[str, int] = {}
    order: list[str] = []
    for depth, name, keys, enabled, sub in items:
        path = path[:depth]
        if depth == 0:
            path = [name]
            current.setdefault(name, [])
            order.append(name)
            continue
        parent = " > ".join(path)
        if parent not in current:
            current[parent] = []
            order.append(parent)
        if enabled:
            current[parent].append(name + (" ▸" if sub else "") + (f" ({keys})" if keys else ""))
        else:
            greyed[parent] = greyed.get(parent, 0) + 1
        if sub:
            path = [*path, name]
    for key in order:
        if current.get(key):
            line = f"{key}: " + " · ".join(current[key])
            line = line if len(line) <= width else line[: width - 1] + "…"
            lines.append(line + (f" (+{greyed[key]} greyed out)" if greyed.get(key) else ""))
    return lines


def _press(node) -> bool:
    for i, name in enumerate(_action_names(node)):
        if name.lower() in ("click", "press", "activate", "toggle", "select", "open"):
            try:
                return bool(Atspi.Action.do_action(node, i))
            except Exception:
                return False
    return False


def _menu_child(node, wanted: str):
    kids = [(menu_name(_name(c)), c) for c in _children(node) if _role(c) in MENU_ITEM_ROLES]
    for c in _children(node):  # items wrapped in a container
        if _role(c) in ("panel", "filler", "unknown"):
            kids.extend((menu_name(_name(k)), k) for k in _children(c) if _role(k) in MENU_ITEM_ROLES)
    w = menu_name(wanted)
    for test in (lambda n: n == w, lambda n: n.startswith(w), lambda n: w in n):
        found = [c for n, c in kids if n and test(n)]
        if found:
            return found[0], [n for n, _ in kids if n]
    return None, [n for n, _ in kids if n]


def find_menu_path(window: dict, path: list[str]) -> list:
    """The accessible nodes along a menu path (menu bar item first, the command last). Raises
    ValueError naming the items that do exist when a step is missing or the command is greyed out."""
    if not _init():
        raise ValueError("accessibility is not available in this desktop")
    with LOCK:
        bar = _menu_bar(window)
        if bar is None:
            raise ValueError("this window has no menu bar (try its keyboard shortcuts, or right-click for a menu)")
        nodes, node = [], bar
        for i, part in enumerate(path):
            child, names = _menu_child(node, part)
            if child is None:
                where = " > ".join(path[:i]) or "the menu bar"
                raise ValueError(f'no "{part}" in {where}; it has: ' + " · ".join(names[:30]))
            nodes.append(child)
            node = child
        last = nodes[-1]
        st = _states(last)
        if not (Atspi.StateType.ENABLED in st or Atspi.StateType.SENSITIVE in st):
            raise ValueError(f'"{" > ".join(path)}" is greyed out right now (disabled)')
        return nodes


def press_menu(nodes: list) -> bool:
    """Activate a menu command through accessibility, without opening its menus. False if the app
    doesn't support that (the caller then opens the menus with the mouse)."""
    if not _init():
        return False
    with LOCK:
        return _press(nodes[-1])


def menu_box(node) -> tuple[int, int, int, int] | None:
    """Where a menu item is on screen now (None while its menu is closed)."""
    if not _init():
        return None
    with LOCK:
        box = _extents(node)
        st = _states(node)
    if not box or box[2] <= 0 or box[3] <= 0 or Atspi.StateType.SHOWING not in st:
        return None
    return box


def page_state(window: dict, max_depth: int = 8, limit: int = 3000) -> tuple[bool | None, int]:
    """(is the web page loading, how many accessible nodes it has so far). (None, 0) without a web page.
    The node count shows whether the browser is still filling in the page's accessibility tree."""
    if not _init():
        return None, 0
    with LOCK:
        doc, queue = None, [(window["node"], 0)]
        while queue and doc is None:
            node, depth = queue.pop(0)
            if _role(node) == "document web":
                doc = node
                break
            if depth < max_depth:
                try:
                    n = min(node.get_child_count(), 40)
                    queue.extend((node.get_child_at_index(i), depth + 1) for i in range(n))
                except Exception:
                    continue
        if doc is None:
            return None, 0
        try:
            busy = doc.get_state_set().contains(Atspi.StateType.BUSY)
        except Exception:
            busy = None
        count, queue = 0, [doc]
        while queue and count < limit:
            node = queue.pop()
            count += 1
            try:
                n = min(node.get_child_count(), 200)
                queue.extend(node.get_child_at_index(i) for i in range(n))
            except Exception:
                continue
        return busy, count


def has_document(window: dict, max_depth: int = 6) -> bool:
    """Has this window's document (an office document, a web page) been created yet?"""
    if not _init():
        return True
    with LOCK:
        queue = [(window["node"], 0)]
        while queue:
            node, depth = queue.pop(0)
            if _role(node).startswith("document"):
                return True
            if depth < max_depth:
                try:
                    n = min(node.get_child_count(), 40)
                    queue.extend((node.get_child_at_index(i), depth + 1) for i in range(n))
                except Exception:
                    continue
    return False


def doc_viewport(el: Element) -> tuple[int, int, int, int] | None:
    """The visible area of the web page an element belongs to (below the browser's toolbar)."""
    if el.node is None or not el.in_doc or not _init():
        return None
    with LOCK:
        node = el.node
        for _ in range(60):
            try:
                node = node.get_parent()
            except Exception:
                return None
            if node is None:
                return None
            if _role(node) in WEB_DOCS:
                return _extents(node)
    return None


def editable_descendant(el: Element, max_depth: int = 4) -> Element | None:
    """The first editable control inside a container (a combo box's entry, a panel's field)."""
    if el.node is None or not _load():
        return None
    queue = [(el.node, 0)]
    with LOCK:
        while queue:
            node, depth = queue.pop(0)
            try:
                n = min(node.get_child_count(), 50)
                kids = [node.get_child_at_index(i) for i in range(n)]
            except Exception:
                continue
            for kid in kids:
                if kid is None:
                    continue
                role = _role(kid)
                try:
                    editable = role in TEXT_INPUT or kid.get_state_set().contains(Atspi.StateType.EDITABLE)
                except Exception:
                    editable = False
                if editable:
                    ext = _extents(kid) or (0, 0, 0, 0)
                    return Element(0, role, _name(kid), el.depth + 1, *ext, node=kid, in_doc=el.in_doc)
                if depth + 1 < max_depth:
                    queue.append((kid, depth + 1))
    return None


def _label_of(node) -> str:
    """The text of the label that names a field (AT-SPI LABELLED_BY), for fields without a name."""
    try:
        for rel in node.get_relation_set() or []:
            if rel.get_relation_type() == Atspi.RelationType.LABELLED_BY and rel.get_n_targets() > 0:
                target = rel.get_target(0)
                return (_name(target) or _text(target, 60)).strip().rstrip(":").strip()
    except Exception:
        pass
    return ""


def labelled_target(el: Element) -> Element | None:
    """For a label, the control it labels (AT-SPI LABEL_FOR relation), e.g. "Name:" -> its entry."""
    if not _init() or el.node is None:
        return None
    with LOCK:
        try:
            for rel in el.node.get_relation_set():
                if rel.get_relation_type() != Atspi.RelationType.LABEL_FOR or rel.get_n_targets() < 1:
                    continue
                target = rel.get_target(0)
                ext = _extents(target)
                if ext and ext[2] > 0 and ext[3] > 0:
                    x, y, w, h = ext
                    return Element(
                        id=0,
                        role=_role(target),
                        name=_clip(_name(target), 160),
                        depth=0,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        node=target,
                    )
        except Exception:
            return None
    return None


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


def _q(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def _plain_link(elements: list[Element], i: int) -> bool:
    el = elements[i]
    nxt = elements[i + 1] if i + 1 < len(elements) else None
    return (
        el.role == "link"
        and not el.text
        and not el.states
        and 0 < len(el.name) <= 40
        and (nxt is None or nxt.depth <= el.depth)  # no children of its own
    )


def format_elements(elements: list[Element], max_depth: int = 6) -> list[str]:
    lines = []
    i = 0
    while i < len(elements):
        el = elements[i]
        indent = "  " * min(el.depth, max_depth)
        # Runs of 3+ plain sibling links (navigation, author lists, "hide | past | comments"): one line.
        j = i
        while j < len(elements) and elements[j].depth == el.depth and _plain_link(elements, j):
            j += 1
        if j - i >= 3:
            line = f"{indent}links:"
            for link in elements[i:j]:
                part = f" @{link.id} {_q(link.name)}"
                if len(line) + len(part) > 160 and line.strip() != "links:":
                    lines.append(line)
                    line = f"{indent}links:"
                line += part if line.endswith(":") else " ·" + part
            lines.append(line)
            i = j
            continue
        cx, cy = el.center
        s = f"{indent}@{el.id} {el.role}"
        if el.name:
            s += f" {_q(el.name)}"
        options = el.text if el.role in ("combo box", "list box") and el.text.startswith("options: ") else ""
        if el.text and not options and not el.lines:
            s += f" {_q(el.text)}" if not el.name else f": {el.text}"
        if el.value and el.role == "cell" and el.value.startswith("="):
            s += f"  ({el.value})"  # its formula
        elif el.value:
            s += f" value={_q(el.value)}" if el.role in ("combo box", "list box") else f" value={el.value}"
        if el.states:
            s += " [" + ", ".join(el.states) + "]"
        if el.w and el.h:
            s += f" ({cx},{cy})"
        if options:  # a dropdown: pick one with select @id "Option"
            s += f" — {options}"
        if el.lines:  # editors: numbered lines (layout kept); terminals: the latest lines
            lines.append(s + ":")
            numbered = el.role != "terminal"
            for n, ln in enumerate(el.lines, 1):
                if numbered and not ln.startswith("… "):
                    lines.append(f"{indent}  {n:>4}  {ln}")
                else:
                    lines.append(f"{indent}  {ln}")
        else:
            lines.append(s)
        i += 1
    return lines
