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
            return out if len(out) <= limit else "…" + out[-(limit - 1) :].lstrip()
        raw = Atspi.Text.get_text(node, 0, min(n, limit * 4))
        if "\ufffc" in raw:  # embedded objects (links, images): use their names
            raw = _expand_embedded(node, raw)
        return _lines(raw, limit)
    except Exception:
        return ""


def _expand_embedded(node, raw: str) -> str:
    """Replace U+FFFC placeholders (embedded links/images) with their names."""
    try:
        n = node.get_child_count()
    except Exception:
        return raw
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
    return "".join(out)


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
    found = []
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
                continue
            ext = _extents(cell) or (0, 0, 0, 0)
            found.append((f"{_col(c)}{r + 1}", content, cell, ext))
    return (r0, c0, r1, c1), found


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


def snapshot(
    window: dict,
    max_elements: int = 250,
    budget: float = 3.0,
    text_limit: int = 160,
    max_children: int = 400,
    screen: tuple[int, int] | None = None,
) -> Snapshot:
    """Walk a window's accessible tree and collect visible, meaningful elements."""
    snap = Snapshot(app=window.get("app", ""), window=window.get("name", ""))
    if not _init():
        snap.error = "accessibility is not available in this desktop"
        return snap
    start = time.monotonic()
    deadline = start + budget
    sw, sh = screen or (100000, 100000)
    elements: list[Element] = []

    def walk(node, depth: int, shown_depth: int, in_doc: bool = False) -> None:
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
            if depth > 0 and role in ("menu bar", "tool bar") and (w > 0) != (h > 0):
                return  # a collapsed bar (e.g. LibreOffice's hidden twin menu bar): its items are phantoms
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
            if text == name:
                text = ""
        if "Value" in ifaces and role in ("slider", "spin button", "progress bar", "scroll bar", "level bar"):
            value = _value(node)
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
                for ref, content, cell, (cx0, cy0, cw, ch) in found:
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
                walk(child, depth + 1, child_shown_depth, in_doc or role in WEB_DOCS)
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
WEB_DOCS = {"document web", "document frame"}
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
    keep: list[Element] = []
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


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold().strip(" :") == " ".join(b.split()).casefold().strip(" :")


def compact(elements: list[Element]) -> list[Element]:
    """Drop wrappers that only repeat their single child ("list item 'News'" > "link 'News'"),
    keeping the child (a heading's link becomes a "heading link"), then renumber the ids."""
    out: list[Element] = []
    n = len(elements)
    seen: list[tuple[str, str, int, int]] = []
    skip: set[int] = set()
    for i, el in enumerate(elements):
        if i in skip:
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
        if el.role in CONTAINER_TEXT and nxt is not None and nxt.depth > el.depth:
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
