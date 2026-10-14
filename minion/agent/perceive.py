"""Perception: describe the screen as text ("see") and resolve click targets.

A target can be:
  * coordinates: [x, y], {"x": .., "y": ..} or "x,y"
  * an element reference from the last `see`: "@12"
  * visible text: "Save", "Sign in" (accessibility names first, then OCR)
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from . import a11y
from . import ocr as ocr_mod

_POINT = re.compile(r"^\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*\)?\s*$")
_REF = re.compile(r"^\s*@(\d+)\s*$")


class TargetError(Exception):
    pass


@dataclass
class Target:
    x: int
    y: int
    desc: str
    element: object = None  # a11y.Element or ocr Line (only for references/text)


@dataclass
class OcrRef:
    id: int
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


_CELL_REF = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")
_COORDS = re.compile(r" \(-?\d+,-?\d+\)$")


def _same_content(a: tuple, b: tuple) -> bool:
    """Equal, ignoring how much of a long text was shown (a normal look vs. a full_text look)."""
    if a == b:
        return True
    if len(a) != len(b) or a[:2] != b[:2] or a[3:] != b[3:]:
        return False
    ta, tb = (a[2] or "").rstrip("…"), (b[2] or "").rstrip("…")
    return ta.startswith(tb) or tb.startswith(ta)


def _quote(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold()
    s = s.replace("…", "").replace("&", "").replace("_", "")
    s = " ".join(s.split())
    return s.strip(" :.*")


# A text target must match at least this well before anything is clicked or filled, and wait_for
# needs a stronger match: a fragment such as "x" or "alc" never stands in for "Qwxyzzy" or "Calc".
TARGET_MIN = 30
WAIT_MIN = 40


def _bounded(hay: str, needle: str) -> bool:
    """`needle` occurs in `hay` on word boundaries ("save" in "save as", not in "unsaved")."""
    start = 0
    while (i := hay.find(needle, start)) >= 0:
        j = i + len(needle)
        before_ok = i == 0 or not (hay[i - 1].isalnum() and needle[0].isalnum())
        after_ok = j == len(hay) or not (hay[j].isalnum() and needle[-1].isalnum())
        if before_ok and after_ok:
            return True
        start = i + 1
    return False


def match_score(query: str, label: str) -> int:
    """0-100: how well `label` (an element name or OCR line) matches what the caller asked for."""
    q, lab = _norm(query), _norm(label)
    if not q or not lab:
        return 0
    if q == lab:
        return 100
    if _bounded(lab, q):  # the query as whole words of the label
        edge = lab.startswith(q) or lab.endswith(q)
        return (80 if edge else 65) - min(25, (len(lab) - len(q)) // 2)
    if len(q) >= 4 and q in lab:  # inside a longer word
        return 40 - min(20, len(lab) - len(q))
    if len(lab) >= 4 and len(lab) >= 0.6 * len(q) and _bounded(q, lab):  # a truncated label or OCR line
        return 30
    return 0


class Perception:
    def __init__(self, screen, windows, display_size):
        self.screen = screen
        self.windows = windows
        self.size = display_size
        self.registry: dict[int, object] = {}
        self.registry_time = 0.0
        # Stable @ids: the same control keeps its id across looks (keys: AT-SPI node objects,
        # which libatspi/PyGObject keep identical while they live, or a role/name/place key).
        self._ids: dict[object, int] = {}
        self._seen_at: dict[object, int] = {}
        self._alt_ids: dict[tuple, int] = {}  # (role, label, place) -> id, for apps that recreate nodes
        self._labels: dict[int, str] = {}  # id -> what it was, for "no longer on screen" errors
        self._reg_look: dict[int, int] = {}  # id -> the look it was last registered in
        self._next_id = 1
        self._look = 0
        self.last_view: dict | None = None  # for "changes" diffs
        self.xi = None  # set by the server: used to nudge the pointer (see _sync_coords)
        self._synced: set = set()

    # -- coordinates ----------------------------------------------------
    def _sync_coords(self) -> None:
        """LibreOffice reports its controls ~25 px too high until its window has seen a pointer
        event, so a click "by @id" would hit the control above. Nudge the pointer across the window
        once (per window and geometry) and put it back."""
        if self.xi is None:
            return
        try:
            win = self.windows.focused()
        except Exception:
            return
        if win is None or not re.search(r"libreoffice|soffice", win.app or "", re.I):
            return
        key = (win.id, win.x, win.y, win.w, win.h)
        if key in self._synced:
            return
        if len(self._synced) > 200:
            self._synced.clear()
        self._synced.add(key)
        try:
            px, py = self.xi.position()
            cx, cy = win.x + win.w // 2, win.y + win.h // 2
            self.xi.move(cx, cy)
            self.xi.move(cx + 1, cy + 1)
            self.xi.move(px, py)
            time.sleep(0.08)
        except Exception:
            pass

    # -- ids ----------------------------------------------------------
    def _key(self, el) -> object:
        if getattr(el, "role", "") == "cell" and _CELL_REF.match(getattr(el, "name", "") or ""):
            return ("cell", el.name)  # spreadsheet cells: the address is the identity (nodes are transient)
        node = getattr(el, "node", None)
        if node is not None and not isinstance(el, OcrRef):
            return node
        cx, cy = el.center
        return ("ocr", getattr(el, "text", ""), cx // 12, cy // 12)

    @staticmethod
    def _alt_key(el) -> tuple:
        label = el.label() if hasattr(el, "label") else getattr(el, "text", "")
        cx, cy = el.center
        return (getattr(el, "role", "ocr"), (label or "")[:40], cx // 10, cy // 10)

    def _assign(self, items: list) -> None:
        self._look += 1
        used: set[int] = set()
        for el in items:
            key = self._key(el)
            eid = self._ids.get(key)
            if eid is None:
                # Some apps (LibreOffice) recreate a control's node: same role, label and place = same id.
                old = self._alt_ids.get(self._alt_key(el))
                if old is not None and old not in used:
                    eid = old
                else:
                    eid = self._next_id
                    self._next_id += 1
                self._ids[key] = eid
            self._seen_at[key] = self._look
            self._alt_ids[self._alt_key(el)] = eid
            used.add(eid)
            el.id = eid
            label = el.label() if hasattr(el, "label") else getattr(el, "text", "")
            self._labels[eid] = f"{getattr(el, 'role', 'text')} {_quote(label[:60])}" if label else el.role
        if len(self._ids) > 4000 or self._look % 20 == 0:  # forget controls unseen for a while
            stale = [k for k, look in self._seen_at.items() if self._look - look > 5]
            for k in stale:
                self._ids.pop(k, None)
                self._seen_at.pop(k, None)
            live = set(self._ids.values())
            self._alt_ids = {k: v for k, v in self._alt_ids.items() if v in live}
            self._labels = {k: v for k, v in self._labels.items() if k in live}
        if self._next_id > 99999:
            self._ids.clear()
            self._seen_at.clear()
            self._alt_ids.clear()
            self._labels.clear()
            self._next_id = 1

    # -- see ----------------------------------------------------------
    def see(
        self,
        ocr="auto",
        window: str | None = None,
        max_elements: int = 250,
        register: bool = True,
        text_limit: int = 160,
        changes: bool = False,
    ) -> dict:
        t0 = time.monotonic()
        self._sync_coords()
        wins = self.windows.list()
        target = None
        if window:
            target = self.windows.find(window)
        else:
            target = next((w for w in wins if w.focused), None)
        sw, sh = self.size
        snap = None
        a11y_note = ""
        if a11y.AVAILABLE:
            aw = a11y.find_window(title=target.title if target else None, pid=target.pid if target else None)
            if aw is not None:
                snap = a11y.snapshot(aw, max_elements=max_elements, screen=(sw, sh), text_limit=text_limit)
                if snap.error:
                    a11y_note = snap.error
            else:
                a11y_note = "the focused window exposes no accessibility tree"
        else:
            a11y_note = "accessibility is not available"
        elements = snap.elements if snap else []
        useful = sum(1 for e in elements if e.name or e.text)
        want_ocr = ocr is True or (ocr == "auto" and useful < 5)
        ocr_lines = []
        ocr_note = ""
        if want_ocr:
            if ocr_mod.available():
                if target and not target.minimized:
                    x0, y0 = max(0, target.x), max(0, target.y)
                    x1, y1 = min(sw, target.x + target.w), min(sh, target.y + target.h)
                    region = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
                else:
                    region = (0, 0, sw, sh)
                try:
                    img = self.screen.grab(region)
                    ocr_lines = ocr_mod.recognize(img, offset=region[:2])
                except Exception as e:  # OCR is best-effort
                    ocr_note = f"OCR failed: {e}"
            else:
                ocr_note = "OCR is not installed"
        # Fragments with fewer than two letters or digits ("&", "»>", "Oe") are noise, not text to act on.
        ocr_lines = [ln for ln in ocr_lines if sum(ch.isalnum() for ch in ln.text) >= 2]
        ocr_refs = [OcrRef(0, ln.text, ln.x, ln.y, ln.w, ln.h) for ln in ocr_lines]
        if register:
            self._assign(list(elements) + ocr_refs)
            fresh = {el.id: el for el in elements}
            fresh.update({r.id: r for r in ocr_refs})
            keep = {
                i: e for i, e in self.registry.items() if i not in fresh and self._look - self._reg_look.get(i, 0) <= 2
            }
            self.registry = {**keep, **fresh}
            self._reg_look = {i: self._reg_look.get(i, self._look) for i in keep} | dict.fromkeys(fresh, self._look)
            self.registry_time = time.time()
        else:
            for i, el in enumerate(list(elements) + ocr_refs, 1):
                el.id = i

        where = f'"{target.title}"' if target else "the screen"
        full = self._compose((sw, sh), wins, where, elements, ocr_refs, snap, a11y_note, ocr_note, want_ocr)
        view = self._view(wins, target, elements, ocr_refs)
        text = full
        diff = None
        if changes and register and self.last_view is not None:
            diff = self._diff(self.last_view, view)
            if "full" not in diff and len(diff["text"]) >= 0.8 * len(full):
                diff = {"full": "the changes are about as long as the whole view"}
            if "full" in diff:
                text = f"(Full view: {diff['full']}.)\n{full}"
                diff = None
            else:
                text = diff["text"]
        if register:
            self.last_view = view
        return {
            "text": text,
            "screen": [sw, sh],
            "windows": [w.to_dict() for w in wins],
            "focused": target.to_dict() if target else None,
            "elements": [e.to_dict() for e in elements],
            "ocr": [
                {"id": f"@{r.id}", "text": r.text, "x": r.center[0], "y": r.center[1], "box": [r.x, r.y, r.w, r.h]}
                for r in ocr_refs
            ],
            "sources": {"a11y": bool(elements), "ocr": bool(ocr_refs)},
            "changes": {k: v for k, v in diff.items() if k != "text"} if diff else None,
            "elapsed": round(time.monotonic() - t0, 3),
        }

    @staticmethod
    def _compose(size, wins, where, elements, ocr_refs, snap, a11y_note, ocr_note, want_ocr) -> str:
        out = [f"Screen {size[0]}x{size[1]} · {len(wins)} window{'s' if len(wins) != 1 else ''}"]
        for i, w in enumerate(wins, 1):
            flags = []
            if w.focused:
                flags.append("focused")
            if w.minimized:
                flags.append("minimized")
            tag = f" ({', '.join(flags)})" if flags else ""
            out.append(f'  [{i}] "{w.title}" — {w.app}{tag} at {w.x},{w.y} {w.w}x{w.h}')
        if not wins:
            out.append("  (no windows open — use `open` to launch an app)")
        if elements:
            out.append("")
            out.append(f"UI of {where} (click/fill with @id; (x,y) is the element center):")
            out.extend(snap.header if snap else [])
            out.extend(a11y.format_elements(elements))
            if snap and snap.truncated:
                out.append("  … truncated (large UI). Use `see` with window=..., OCR, or a screenshot for the rest.")
        if ocr_refs:
            out.append("")
            out.append(f"Text on {where} (OCR):")
            for r in ocr_refs:
                cx, cy = r.center
                out.append(f'  @{r.id} "{r.text}" ({cx},{cy})')
        if not elements and not ocr_refs:
            note = a11y_note or ocr_note or "nothing readable"
            out.append("")
            out.append(f"(No readable UI: {note}. Take a screenshot to look at it.)")
        elif ocr_note and want_ocr:
            out.append(f"({ocr_note})")
        return "\n".join(out)

    @staticmethod
    def _view(wins, target, elements, ocr_refs) -> dict:
        items = {}
        for el in elements:
            cx, cy = el.center
            line = a11y.format_elements([el])[0].strip()
            items[el.id] = ((el.role, el.name, el.text, el.value, tuple(el.states)), (cx // 6, cy // 6), line)
        for r in ocr_refs:
            cx, cy = r.center
            items[r.id] = (("ocr", r.text), (cx // 6, cy // 6), f'@{r.id} text "{r.text}" ({cx},{cy}) [OCR]')
        return {
            "time": time.time(),
            "windows": {w.id: (w.title, w.focused) for w in wins},
            "focused": target.id if target else None,
            "items": items,
        }

    @staticmethod
    def _diff(old: dict, new: dict) -> dict:
        """What changed between two looks; {"full": reason} when the full view is the better answer."""
        if old.get("focused") != new.get("focused"):
            return {"full": "another window is in front"}
        o, n = dict(old["items"]), dict(new["items"])
        if any(v[0][0] != "ocr" for v in n.values()) and any(v[0][0] != "ocr" for v in o.values()):
            # OCR fragments shift between looks: with an accessibility tree they are noise in a diff
            o = {k: v for k, v in o.items() if v[0][0] != "ocr"}
            n = {k: v for k, v in n.items() if v[0][0] != "ocr"}
        added = [i for i in n if i not in o]
        removed = [i for i in o if i not in n]
        changed = [i for i in n if i in o and not _same_content(o[i][0], n[i][0])]
        moved = [i for i in n if i in o and i not in changed and o[i][1] != n[i][1]]
        if len(added) + len(changed) > max(25, 0.6 * max(1, len(n))):
            return {"full": "most of the screen changed"}
        lines = []
        ow, nw = old["windows"], new["windows"]
        for wid, (title, _) in nw.items():
            if wid not in ow:
                lines.append(f'  window opened: "{title}"')
            elif ow[wid][0] != title:
                lines.append(f'  window renamed: "{ow[wid][0]}" → "{title}"')
        for wid, (title, _) in ow.items():
            if wid not in nw:
                lines.append(f'  window closed: "{title}"')
        for i in added:
            lines.append("  + " + n[i][2])
        for i in changed:
            lines.append("  ~ " + n[i][2])
        for i in removed[:8]:
            lines.append("  - " + _COORDS.sub("", o[i][2]))
        if len(removed) > 8:
            lines.append(f"  - … and {len(removed) - 8} more gone (closed, or scrolled out of view)")
        ago = max(0.0, new["time"] - old["time"])
        unchanged = len(n) - len(added) - len(changed)
        note = f", {len(moved)} moved" if moved else ""
        head = (
            f"Changes since your last look {ago:.1f}s ago "
            f"({unchanged} element{'s' if unchanged != 1 else ''} unchanged{note}; their @ids still work):"
        )
        if not lines:
            lines.append(
                "  (nothing changed)" if not moved else "  (only positions changed: same elements, new places)"
            )
        return {
            "text": "\n".join([head, *lines]),
            "added": len(added),
            "changed": len(changed),
            "removed": len(removed),
            "moved": len(moved),
        }

    # -- targets ------------------------------------------------------
    def resolve(self, target, allow_text: bool = True, prefer_input: bool = False) -> Target:
        if target is None:
            raise TargetError("missing target")
        if isinstance(target, (list, tuple)):
            if len(target) != 2:
                raise TargetError(f"coordinates must be [x, y], got {target!r}")
            return self._point(target[0], target[1])
        if isinstance(target, dict):
            if "x" in target and "y" in target:
                return self._point(target["x"], target["y"])
            raise TargetError(f"unsupported target {target!r}")
        s = str(target)
        m = _POINT.match(s)
        if m:
            return self._point(m.group(1), m.group(2))
        m = _REF.match(s)
        if m:
            return self._ref(int(m.group(1)))
        if not allow_text:
            raise TargetError(f"expected coordinates or @id, got {s!r}")
        return self._text(s, prefer_input)

    def _point(self, x, y) -> Target:
        try:
            xi, yi = round(float(x)), round(float(y))
        except (TypeError, ValueError) as e:
            raise TargetError(f"bad coordinates {x!r}, {y!r}") from e
        sw, sh = self.size
        if not (0 <= xi < sw and 0 <= yi < sh):
            raise TargetError(f"({xi},{yi}) is outside the {sw}x{sh} screen")
        return Target(xi, yi, f"({xi},{yi})")

    def _ref(self, rid: int) -> Target:
        el = self.registry.get(rid)
        if el is None:
            if rid in self._labels:
                raise TargetError(
                    f"@{rid} ({self._labels[rid]}) is no longer on screen: scroll back to it, or call `see` "
                    "for the current ids"
                )
            raise TargetError(f"@{rid} is unknown: call `see` first and use an id from its output")
        if isinstance(el, OcrRef):
            cx, cy = el.center
            return Target(cx, cy, f'@{rid} "{el.text}" ({cx},{cy})', el)
        self._sync_coords()
        box = a11y.refresh(el)
        if box is None:
            raise TargetError(f'@{rid} ({el.role} "{el.label()}") is gone: call `see` again')
        x, y, w, h = box
        sw, sh = self.size
        if w > 0 and h > 0 and (x + w <= 0 or y + h <= 0 or x >= sw or y >= sh):
            if a11y.scroll_into_view(el):
                time.sleep(0.25)
                box = a11y.refresh(el) or box
                x, y, w, h = box
        if w > 0 and h > 0:  # aim at the visible part of a partly scrolled element
            x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, sw), min(y + h, sh)
            if x1 > x0 and y1 > y0:
                x, y, w, h = x0, y0, x1 - x0, y1 - y0
        cx, cy = x + max(w, 1) // 2, y + max(h, 1) // 2
        cx, cy = min(max(cx, 0), sw - 1), min(max(cy, 0), sh - 1)
        label = el.label()
        desc = f"@{rid} {el.role}{f' {chr(34)}{label}{chr(34)}' if label else ''} ({cx},{cy})"
        return Target(cx, cy, desc, el)

    def find_text(
        self, query: str, use_ocr: bool = True, prefer_input: bool = False, min_score: int = TARGET_MIN
    ) -> list[tuple[int, Target]]:
        """All on-screen matches for `query` that match at least `min_score` well, best first."""
        self._sync_coords()
        found: list[tuple[int, Target]] = []
        sw, sh = self.size
        if a11y.AVAILABLE:
            focused = self.windows.focused()
            aw = a11y.find_window(title=focused.title if focused else None, pid=focused.pid if focused else None)
            if aw is not None:
                snap = a11y.snapshot(aw, max_elements=600, budget=2.5, screen=(sw, sh))
                for el in snap.elements:
                    best = max(
                        match_score(query, el.name), match_score(query, el.text) - 5, match_score(query, el.value) - 10
                    )
                    if best < min_score:
                        continue
                    if el.interactive:
                        best += 15
                    if prefer_input and el.role in a11y.TEXT_INPUT:
                        best += 30
                    if prefer_input and el.role == "label":
                        labelled = a11y.labelled_target(el)
                        if labelled is not None:
                            el, best = labelled, best + 25
                    cx, cy = el.center
                    if not (0 <= cx < sw and 0 <= cy < sh):
                        continue
                    found.append((best, Target(cx, cy, f'{el.role} "{el.label()}" ({cx},{cy})', el)))
        if not found and use_ocr and ocr_mod.available():
            # The focused window first, as `see` reads it: OCR of the whole screen inverts mostly-dark
            # screens, which loses the text of a small light dialog in front of the dark wallpaper.
            regions = []
            focused = self.windows.focused()
            if focused and not focused.minimized:
                x0, y0 = max(0, focused.x), max(0, focused.y)
                x1, y1 = min(sw, focused.x + focused.w), min(sh, focused.y + focused.h)
                if x1 > x0 and y1 > y0 and (x0, y0, x1, y1) != (0, 0, sw, sh):
                    regions.append((x0, y0, x1 - x0, y1 - y0))
            regions.append((0, 0, sw, sh))
            qn = _norm(query).split()
            for region in regions:
                for ln in ocr_mod.recognize(self.screen.grab(region), offset=region[:2]):
                    score = match_score(query, ln.text)
                    if score >= min_score:
                        cx, cy = ln.center
                        # Narrow to the matching words inside a longer line.
                        words = ln.words
                        for i in range(len(words)):
                            seg = words[i : i + len(qn)]
                            if seg and _norm(" ".join(w.text for w in seg)) == " ".join(qn):
                                x0, y0 = seg[0].x, min(w.y for w in seg)
                                x1 = seg[-1].x + seg[-1].w
                                y1 = max(w.y + w.h for w in seg)
                                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                                score = max(score, 90)
                                break
                        found.append((score, Target(cx, cy, f'text "{ln.text}" ({cx},{cy}) via OCR', ln)))
                if found:
                    break
        found.sort(key=lambda t: -t[0])
        return found

    def _text(self, query: str, prefer_input: bool = False) -> Target:
        found = self.find_text(query, prefer_input=prefer_input)
        if not found:
            hint = self._near_misses(query)
            raise TargetError(
                f'no visible element or text matches "{query}"'
                + (f". Similar: {hint}" if hint else "")
                + ". Use an @id from `see`, or coordinates from a screenshot"
            )
        best = found[0]
        t = best[1]
        ties = [f for f in found[1:] if f[0] == best[0]]
        if ties:
            t.desc += f" (first of {len(ties) + 1} matches; use @id to pick another)"
        return t

    def _near_misses(self, query: str, limit: int = 3) -> str:
        """Names of focused-window elements that look like `query`, for error messages."""
        import difflib

        names = []
        for e in (self.registry or {}).values():
            label = e.label() if hasattr(e, "label") else getattr(e, "text", "")
            if label and len(label) <= 80:
                names.append(label)
        pool = {_norm(n): n for n in names}
        close = difflib.get_close_matches(_norm(query), list(pool), n=limit, cutoff=0.55)
        return ", ".join(f'"{pool[c]}"' for c in close)

    def wait_for(
        self, query: str, timeout: float = 10.0, gone: bool = False, interval: float = 0.4
    ) -> tuple[bool, float, str]:
        """Wait until text is visible (or gone). Returns (ok, seconds, where it was seen)."""
        start = time.monotonic()
        tries = 0
        while True:
            tries += 1
            where = next(
                (
                    f'window title "{w.title}"'
                    for w in self.windows.list(with_states=False)
                    if match_score(query, w.title) >= WAIT_MIN
                ),
                "",
            )
            if not where:
                # OCR is slow: when waiting for text to appear, only every third poll uses it (and never
                # past the deadline). When waiting for it to go, absence only counts if OCR looked too.
                late = time.monotonic() - start > timeout - 1.0
                found = self.find_text(query, use_ocr=gone or (tries % 3 == 1 and not late), min_score=WAIT_MIN)
                where = found[0][1].desc if found else ""
            if bool(where) != gone:
                return True, time.monotonic() - start, where
            if time.monotonic() - start >= timeout:
                return False, time.monotonic() - start, ""
            time.sleep(interval)
