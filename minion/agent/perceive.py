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


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold()
    s = s.replace("…", "").replace("&", "").replace("_", "")
    s = " ".join(s.split())
    return s.strip(" :.*")


def match_score(query: str, label: str) -> int:
    q, lab = _norm(query), _norm(label)
    if not q or not lab:
        return 0
    if q == lab:
        return 100
    if lab.startswith(q) or lab.endswith(q):
        return 70 - min(30, len(lab) - len(q))
    if q in lab:
        return 50 - min(30, len(lab) - len(q))
    if len(q) > 3 and lab in q:
        return 20
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
        self._next_id = 1
        self._look = 0
        self.last_view: dict | None = None  # for "changes" diffs

    # -- ids ----------------------------------------------------------
    def _key(self, el) -> object:
        node = getattr(el, "node", None)
        if node is not None and not isinstance(el, OcrRef):
            return node
        cx, cy = el.center
        return ("ocr", getattr(el, "text", ""), cx // 12, cy // 12)

    def _assign(self, items: list) -> None:
        self._look += 1
        for el in items:
            key = self._key(el)
            eid = self._ids.get(key)
            if eid is None:
                eid = self._next_id
                self._next_id += 1
                self._ids[key] = eid
            self._seen_at[key] = self._look
            el.id = eid
        if len(self._ids) > 4000 or self._look % 20 == 0:  # forget controls unseen for a while
            stale = [k for k, look in self._seen_at.items() if self._look - look > 5]
            for k in stale:
                self._ids.pop(k, None)
                self._seen_at.pop(k, None)
        if self._next_id > 99999:
            self._ids.clear()
            self._seen_at.clear()
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
        ocr_refs = [OcrRef(0, ln.text, ln.x, ln.y, ln.w, ln.h) for ln in ocr_lines]
        if register:
            self._assign(list(elements) + ocr_refs)
            self.registry = {el.id: el for el in elements}
            self.registry.update({r.id: r for r in ocr_refs})
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
            if diff is not None:
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
            items[el.id] = ((el.role, el.name, el.text, el.value, tuple(el.states), cx // 6, cy // 6), line)
        for r in ocr_refs:
            cx, cy = r.center
            items[r.id] = (("ocr", r.text, cx // 6, cy // 6), f'@{r.id} text "{r.text}" ({cx},{cy}) [OCR]')
        return {
            "time": time.time(),
            "windows": {w.id: (w.title, w.focused) for w in wins},
            "focused": target.id if target else None,
            "items": items,
        }

    @staticmethod
    def _diff(old: dict, new: dict) -> dict | None:
        """What changed between two looks, or None when a full view is the better answer."""
        if old.get("focused") != new.get("focused"):
            return None  # another window: show everything
        o, n = old["items"], new["items"]
        added = [i for i in n if i not in o]
        removed = [i for i in o if i not in n]
        changed = [i for i in n if i in o and n[i][0] != o[i][0]]
        if len(added) + len(changed) > max(25, 0.6 * max(1, len(n))):
            return None  # most of the screen changed: show everything
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
            lines.append("  + " + n[i][1])
        for i in changed:
            lines.append("  ~ " + n[i][1])
        for i in removed:
            lines.append("  - " + o[i][1].split(" (")[0])
        ago = max(0.0, new["time"] - old["time"])
        unchanged = len(n) - len(added) - len(changed)
        head = (
            f"Changes since your last look {ago:.1f}s ago "
            f"({unchanged} element{'s' if unchanged != 1 else ''} unchanged; their @ids still work):"
        )
        if not lines:
            lines.append("  (nothing changed)")
        return {
            "text": "\n".join([head, *lines]),
            "added": len(added),
            "changed": len(changed),
            "removed": len(removed),
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
            raise TargetError(f"@{rid} is unknown — call `see` first and use an id from its output")
        if isinstance(el, OcrRef):
            cx, cy = el.center
            return Target(cx, cy, f'@{rid} "{el.text}" ({cx},{cy})', el)
        box = a11y.refresh(el)
        if box is None:
            raise TargetError(f'@{rid} ({el.role} "{el.label()}") is gone — call `see` again')
        x, y, w, h = box
        sw, sh = self.size
        if w > 0 and h > 0 and (x + w <= 0 or y + h <= 0 or x >= sw or y >= sh):
            if a11y.scroll_into_view(el):
                time.sleep(0.25)
                box = a11y.refresh(el) or box
                x, y, w, h = box
        cx, cy = x + max(w, 1) // 2, y + max(h, 1) // 2
        cx, cy = min(max(cx, 0), sw - 1), min(max(cy, 0), sh - 1)
        label = el.label()
        desc = f"@{rid} {el.role}{f' {chr(34)}{label}{chr(34)}' if label else ''} ({cx},{cy})"
        return Target(cx, cy, desc, el)

    def find_text(self, query: str, use_ocr: bool = True, prefer_input: bool = False) -> list[tuple[int, Target]]:
        """All on-screen matches for `query`, best first."""
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
                    if best <= 0:
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
            img = self.screen.grab()
            for ln in ocr_mod.recognize(img):
                score = match_score(query, ln.text)
                if score > 0:
                    cx, cy = ln.center
                    # Narrow to the matching words inside a longer line.
                    qn = _norm(query).split()
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
        found.sort(key=lambda t: -t[0])
        return found

    def _text(self, query: str, prefer_input: bool = False) -> Target:
        found = self.find_text(query, prefer_input=prefer_input)
        if not found:
            raise TargetError(f'no visible element or text matches "{query}" — try `see` or a screenshot')
        best = found[0]
        t = best[1]
        ties = [f for f in found[1:] if f[0] == best[0]]
        if ties:
            t.desc += f" (first of {len(ties) + 1} matches; use @id to pick another)"
        return t

    def wait_for(
        self, query: str, timeout: float = 10.0, gone: bool = False, interval: float = 0.4
    ) -> tuple[bool, float]:
        start = time.monotonic()
        tries = 0
        while True:
            tries += 1
            present = any(match_score(query, w.title) >= 50 for w in self.windows.list(with_states=False))
            if not present:
                # OCR is slow: when waiting for text to appear, only every third poll uses it. When
                # waiting for it to go, absence only counts if OCR looked too (text may be OCR-only).
                present = bool(self.find_text(query, use_ocr=gone or tries % 3 == 1))
            if present != gone:
                return True, time.monotonic() - start
            if time.monotonic() - start >= timeout:
                return False, time.monotonic() - start
            time.sleep(interval)
