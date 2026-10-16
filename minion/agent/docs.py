"""Read any document as text, and convert documents between formats, inside the desktop.

Agents often only need what a file says: reading it here costs one call and no screenshots.
Office Open XML and OpenDocument files (docx, xlsx, pptx, odt, ods, odp), EPUB and HTML are
read with the standard library alone, so this works in every profile. PDFs use pdftotext,
images use OCR, and other formats (doc, xls, ppt, rtf, ...) go through LibreOffice.

LibreOffice runs headless in a throwaway profile of its own: `soffice --convert-to` with the
user's profile silently does nothing while LibreOffice is open on the desktop.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"

TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".log", ".ini", ".cfg", ".toml"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
OFFICE_TEXT_EXT = {".doc", ".rtf", ".wpd", ".pages", ".dotx", ".dot", ".docm"}
OFFICE_SHEET_EXT = {".xls", ".xlsm", ".xlsb", ".numbers"}
OFFICE_SLIDE_EXT = {".ppt", ".pps", ".ppsx", ".pptm", ".key", ".odg"}
MAX_CELLS = 20_000  # per spreadsheet: enough to read a real sheet, small enough for a reply


class DocError(Exception):
    """The file cannot be read or converted; the message says what to do instead."""


# -- reading -----------------------------------------------------------------------------
def read(path: str, max_chars: int = 200_000, details: bool = False) -> tuple[str, str]:
    """(text, kind) for a document at `path`. Raises DocError with advice when it can't. `details` adds what
    formatting tasks are about: a slide's background and each shape's place, size, bullets and fonts; a Word
    paragraph's alignment, spacing and indents and its runs' formatting; a sheet's number formats and text colors."""
    p = Path(os.path.expanduser(path))
    if not p.exists():
        raise DocError(f"no such file: {path}")
    if p.is_dir():
        raise DocError(f"{path} is a folder: list it with run('ls -la {path}')")
    ext = p.suffix.lower()
    readers = {
        ".docx": ("Word document", _docx),
        ".docm": ("Word document", _docx),
        ".dotx": ("Word template", _docx),
        ".xlsx": ("Excel workbook", _xlsx),
        ".xlsm": ("Excel workbook", _xlsx),
        ".pptx": ("PowerPoint presentation", _pptx),
        ".ppsx": ("PowerPoint show", _pptx),
        ".odt": ("OpenDocument text", _odf),
        ".ods": ("OpenDocument spreadsheet", _odf),
        ".odp": ("OpenDocument presentation", _odf),
        ".epub": ("EPUB book", _epub),
        ".html": ("HTML page", _html_file),
        ".htm": ("HTML page", _html_file),
        ".xhtml": ("HTML page", _html_file),
        ".pdf": ("PDF", _pdf),
    }
    if ext in readers:
        kind, fn = readers[ext]
        try:
            text = fn(p, details) if fn in (_docx, _xlsx, _pptx) else fn(p)
        except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
            raise DocError(f"{path} is not a valid {kind} ({e})") from e
    elif ext in IMAGE_EXT:
        kind, text = "image (OCR)", _ocr(p)
    elif ext in OFFICE_TEXT_EXT | OFFICE_SHEET_EXT | OFFICE_SLIDE_EXT:
        kind, text = "document (via LibreOffice)", _via_office(p)
    else:
        data = p.read_bytes()[: max_chars * 4]
        if b"\x00" in data[:8192]:
            raise DocError(
                f"{path} is a binary file this reader doesn't know ({ext or 'no extension'})"
                + (
                    ": for its length, size and streams: run('ffprobe …') (minion-install ffmpeg)"
                    if ext in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".mp3", ".wav", ".ogg", ".m4a", ".flac")
                    else ": run('od -c FILE | head') or install `file` (minion-install file) to see what it is"
                )
            )
        kind, text = "text", data.decode("utf-8", errors="replace")
    if kind != "text":  # (text files come back exactly as they are)
        text = _tidy(text)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n… [{len(text) - max_chars:,} more characters]"
    return text, kind


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(z.read(name))


def _rels(z: zipfile.ZipFile, name: str) -> dict[str, str]:
    """Relationship id -> target path inside the package, for the part `name`."""
    folder, base = name.rsplit("/", 1)
    rels_name = f"{folder}/_rels/{base}.rels"
    if rels_name not in z.namelist():
        return {}
    out = {}
    for rel in _xml(z, rels_name).iter(f"{PKG}Relationship"):
        target = rel.get("Target", "")
        if not target.startswith("/"):
            target = os.path.normpath(f"{folder}/{target}").replace("\\", "/")
        out[rel.get("Id", "")] = target.lstrip("/")
    return out


# Word ------------------------------------------------------------------------------------
def _docx(p: Path, details: bool = False) -> str:
    with zipfile.ZipFile(p) as z:
        doc = _xml(z, "word/document.xml")
        body = doc.find(f"{W}body")
        lines: list[str] = []
        count = [0]

        def blocks(parent) -> None:
            for block in list(parent if parent is not None else []):
                if block.tag == f"{W}p":
                    count[0] += 1
                    lines.append(_docx_paragraph(block))
                    if details:
                        lines.extend(_docx_details(block, count[0]))
                elif block.tag == f"{W}tbl":
                    lines.extend(_docx_table(block))
                    lines.append("")
                elif block.tag == f"{W}sdt":  # a content control: a table of contents, a cover page
                    blocks(block.find(f"{W}sdtContent"))

        blocks(body)
        # What the text alone doesn't show, but a task may be about: tracked changes, comments, the page.
        notes = []
        ins, dels = len(list(doc.iter(f"{W}ins"))), len(list(doc.iter(f"{W}del")))
        if ins or dels:
            notes.append(f"Tracked changes not yet accepted: {ins} insertions, {dels} deletions")
        if "word/comments.xml" in z.namelist():
            for c in _xml(z, "word/comments.xml").iter(f"{W}comment"):
                text = " ".join(_docx_paragraph(par) for par in c.iter(f"{W}p")).strip()
                notes.append(f"Comment by {c.get(f'{W}author', '?')}: {text}")
        sect = body.find(f"{W}sectPr") if body is not None else None
        if sect is not None:
            size, margins = sect.find(f"{W}pgSz"), sect.find(f"{W}pgMar")
            if size is not None:
                w, h = int(size.get(f"{W}w", 0) or 0), int(size.get(f"{W}h", 0) or 0)
                page = f"Page: {w / 567:.1f} x {h / 567:.1f} cm" + (" (landscape)" if w > h else " (portrait)")
                if margins is not None:
                    m = [int(margins.get(f"{W}{k}", 0) or 0) / 567 for k in ("top", "right", "bottom", "left")]
                    page += ", margins " + " / ".join(f"{v:.2f}" for v in m) + " cm (top/right/bottom/left)"
                notes.append(page)
        if notes:
            lines += ["", "---", *notes]
        return "\n".join(lines)


def _docx_details(par: ET.Element, n: int) -> list[str]:
    """A paragraph's layout and its runs' formatting, as indented lines under its text (details mode)."""
    ppr = par.find(f"{W}pPr")
    props = []
    if ppr is not None:
        style = ppr.find(f"{W}pStyle")
        if style is not None:
            props.append(f"style {style.get(f'{W}val')}")
        jc = ppr.find(f"{W}jc")
        if jc is not None:
            props.append({"both": "justified"}.get(jc.get(f"{W}val", ""), jc.get(f"{W}val", "")))
        sp = ppr.find(f"{W}spacing")
        if sp is not None:
            line, rule = sp.get(f"{W}line"), sp.get(f"{W}lineRule", "auto")
            if line and line.lstrip("-").isdigit():
                props.append(
                    f"line spacing {int(line) / 240:g}"
                    if rule == "auto"
                    else f"line spacing {int(line) / 20:g} pt ({rule})"
                )
            for k in ("before", "after"):
                v = sp.get(f"{W}{k}")
                if v and v.isdigit() and int(v):
                    props.append(f"space {k} {int(v) / 20:g} pt")
        ind = ppr.find(f"{W}ind")
        if ind is not None:
            for k, label in (
                ("left", "indent"),
                ("start", "indent"),
                ("firstLine", "first line"),
                ("hanging", "hanging"),
            ):
                v = ind.get(f"{W}{k}")
                if v and v.lstrip("-").isdigit() and int(v):
                    props.append(f"{label} {int(v) / 567:.2f} cm")
        if ppr.find(f"{W}numPr") is not None:
            props.append("list item")
        tabs = [t for t in ppr.iter(f"{W}tab") if t.get(f"{W}pos")]
        if tabs:
            props.append(
                "tab stops " + ", ".join(f"{t.get(f'{W}val')} {int(t.get(f'{W}pos')) / 567:.2f} cm" for t in tabs)
            )
    runs = []
    for r in par.iter(f"{W}r"):
        text = "".join(t.text or "" for t in r.iter(f"{W}t"))
        if not text:
            continue
        fmt = _docx_run_format(r.find(f"{W}rPr"))
        if runs and runs[-1][1] == fmt:
            runs[-1][0] += text
        else:
            runs.append([text, fmt])
    out = []
    if props:
        out.append(f"    ¶{n}: " + ", ".join(props))
    if any(fmt for _, fmt in runs):
        out.append(
            f"    ¶{n} runs: "
            + " · ".join(f"{_short(text)!r}" + (f" ({fmt})" if fmt else "") for text, fmt in runs[:40])
            + (" · …" if len(runs) > 40 else "")
        )
    return out


def _docx_run_format(rpr) -> str:
    if rpr is None:
        return ""
    out = []

    def on(tag: str) -> bool:
        el = rpr.find(f"{W}{tag}")
        return el is not None and el.get(f"{W}val", "true") not in ("0", "false", "none")

    for tag, label in (
        ("b", "bold"),
        ("i", "italic"),
        ("strike", "strikethrough"),
        ("caps", "all caps"),
        ("smallCaps", "small caps"),
    ):
        if on(tag):
            out.append(label)
    if on("u"):
        out.append("underline")
    va = rpr.find(f"{W}vertAlign")
    if va is not None and va.get(f"{W}val") in ("subscript", "superscript"):
        out.append(va.get(f"{W}val"))
    sz = rpr.find(f"{W}sz")
    if sz is not None and (sz.get(f"{W}val") or "").isdigit():
        out.append(f"{int(sz.get(f'{W}val')) / 2:g} pt")
    fonts = rpr.find(f"{W}rFonts")
    if fonts is not None and fonts.get(f"{W}ascii"):
        out.append(fonts.get(f"{W}ascii"))
    color = rpr.find(f"{W}color")
    if color is not None and color.get(f"{W}val") not in (None, "auto", "000000"):
        out.append(f"#{color.get(f'{W}val')}")
    hl = rpr.find(f"{W}highlight")
    if hl is not None and hl.get(f"{W}val") not in (None, "none"):
        out.append(f"highlight {hl.get(f'{W}val')}")
    shd = rpr.find(f"{W}shd")
    if shd is not None and shd.get(f"{W}fill") not in (None, "auto", "FFFFFF"):
        out.append(f"shading #{shd.get(f'{W}fill')}")
    return ", ".join(out)


def _short(text: str, n: int = 50) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _docx_paragraph(par: ET.Element) -> str:
    parts = []
    for node in par.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
        elif node.tag == f"{W}drawing" or node.tag.endswith("}pict"):
            parts.append("[image]")
    text = "".join(parts)
    style = par.find(f"{W}pPr/{W}pStyle")
    level = re.match(r"(?i)heading\s*(\d)", style.get(f"{W}val", "")) if style is not None else None
    if level and text.strip():
        return "#" * int(level.group(1)) + " " + text
    if par.find(f"{W}pPr/{W}numPr") is not None and text.strip():
        return "- " + text
    return text


def _docx_table(tbl: ET.Element) -> list[str]:
    rows = []
    for tr in tbl.iter(f"{W}tr"):
        cells = [" ".join(_docx_paragraph(p) for p in tc.iter(f"{W}p")).strip() for tc in tr.iter(f"{W}tc")]
        rows.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return rows


# Excel -----------------------------------------------------------------------------------
def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _xlsx(p: Path, details: bool = False) -> str:
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(z, "xl/sharedStrings.xml").iter(f"{S}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{S}t")))
        rels = _rels(z, "xl/workbook.xml")
        bold, fills = _xlsx_styles(z) if "xl/styles.xml" in names else (set(), [])
        looks = _xlsx_looks(z, details) if "xl/styles.xml" in names else {}
        out, budget = [], MAX_CELLS
        for sheet in _xml(z, "xl/workbook.xml").iter(f"{S}sheet"):
            target = rels.get(sheet.get(f"{R}id", ""), "")
            if target not in names:
                continue
            root = _xml(z, target)
            text, used = _xlsx_sheet(root, shared, budget)
            budget -= used
            notes = _xlsx_notes(z, target, root, bold, fills) + _xlsx_layout(root, looks)
            out.append(f"## Sheet: {sheet.get('name', '?')}\n{text}" + ("\n" + "\n".join(notes) if notes else ""))
            if budget <= 0:
                out.append("… [more cells not shown]")
                break
        return "\n\n".join(out)


def _xlsx_styles(z: zipfile.ZipFile) -> tuple[set, list]:
    """(the cell styles that are bold, the fill colour of each conditional format style)."""
    st = _xml(z, "xl/styles.xml")
    fonts = []
    for f in st.iter(f"{S}font"):
        b = f.find(f"{S}b")
        fonts.append(b is not None and b.get("val", "1") not in ("0", "false"))
    xfs = st.find(f"{S}cellXfs")
    bold = {
        i
        for i, xf in enumerate(list(xfs) if xfs is not None else [])
        if int(xf.get("fontId", 0) or 0) < len(fonts) and fonts[int(xf.get("fontId", 0) or 0)]
    }
    fills = []
    dxfs = st.find(f"{S}dxfs")
    for dxf in list(dxfs) if dxfs is not None else []:
        color = dxf.find(f".//{S}fill//{S}bgColor")
        if color is None:  # (an element without children is falsy: no `or` here)
            color = dxf.find(f".//{S}fill//{S}fgColor")
        font = dxf.find(f".//{S}font/{S}color")
        parts = []
        if color is not None and color.get("rgb"):
            parts.append("fill #" + color.get("rgb")[-6:])
        if font is not None and font.get("rgb"):
            parts.append("text #" + font.get("rgb")[-6:])
        fills.append(", ".join(parts))
    return bold, fills


def _xlsx_looks(z: zipfile.ZipFile, details: bool) -> dict[int, list[str]]:
    """For each cell style (its index), what it shows beyond the defaults: its fill colour, and with details
    its number format and text colour."""
    st = _xml(z, "xl/styles.xml")
    fills = []
    for f in st.iter(f"{S}fill"):
        pat = f.find(f"{S}patternFill")
        color = pat.find(f"{S}fgColor") if pat is not None and pat.get("patternType") not in (None, "none") else None
        fills.append(f"fill #{color.get('rgb')[-6:]}" if color is not None and color.get("rgb") else "")
    fonts = []
    for f in st.iter(f"{S}font"):
        color = f.find(f"{S}color")
        rgb = color.get("rgb", "")[-6:] if color is not None else ""
        fonts.append(f"text #{rgb}" if rgb and rgb.upper() != "000000" else "")
    formats = {n.get("numFmtId"): n.get("formatCode") for n in st.iter(f"{S}numFmt")}
    out: dict[int, list[str]] = {}
    xfs = st.find(f"{S}cellXfs")
    for i, xf in enumerate(list(xfs) if xfs is not None else []):
        parts = []
        fill = int(xf.get("fillId", 0) or 0)
        if fill < len(fills) and fills[fill]:
            parts.append(fills[fill])
        if details:
            fmt = xf.get("numFmtId", "0")
            if fmt in formats:
                parts.append(f"format {formats[fmt]}")
            font = int(xf.get("fontId", 0) or 0)
            if font < len(fonts) and fonts[font]:
                parts.append(fonts[font])
        if parts:
            out[i] = parts
    return out


def _xlsx_layout(root: ET.Element, looks: dict[int, list[str]]) -> list[str]:
    """What a sheet looks like beyond its values: filled cells, hidden rows and columns, merged cells, a filter,
    its zoom (and with details, number formats and text colours)."""
    notes = []
    groups: dict[str, list[str]] = {}
    for c in root.iter(f"{S}c"):
        st = c.get("s", "")
        if st.isdigit() and int(st) in looks:
            for part in looks[int(st)]:
                groups.setdefault(part, []).append(c.get("r", ""))
    for part, refs in sorted(groups.items()):
        label = part[0].upper() + part[1:]
        notes.append(f"{label}: " + ", ".join(refs[:40]) + (f" … ({len(refs)} cells)" if len(refs) > 40 else ""))
    hidden = [r.get("r", "") for r in root.iter(f"{S}row") if r.get("hidden") in ("1", "true")]
    if hidden:
        notes.append("Hidden rows: " + ", ".join(hidden[:60]) + (" …" if len(hidden) > 60 else ""))
    cols = []
    for col in root.iter(f"{S}col"):
        if col.get("hidden") in ("1", "true"):
            lo, hi = int(col.get("min", 0) or 0), int(col.get("max", 0) or 0)
            cols.append(_col(lo) if lo == hi else f"{_col(lo)}:{_col(min(hi, 16384))}")
    if cols:
        notes.append("Hidden columns: " + ", ".join(cols))
    merged = [m.get("ref", "") for m in root.iter(f"{S}mergeCell")]
    if merged:
        notes.append("Merged: " + ", ".join(merged[:30]))
    flt = root.find(f"{S}autoFilter")
    if flt is not None:
        notes.append(f"Filter: {flt.get('ref', '?')}")
    view = root.find(f".//{S}sheetView")
    if view is not None and view.get("zoomScale") not in (None, "100"):
        notes.append(f"Zoom: {view.get('zoomScale')}%")
    return notes


def _xlsx_notes(z: zipfile.ZipFile, target: str, root: ET.Element, bold: set, fills: list) -> list[str]:
    """What a sheet's values don't show: bold cells, frozen panes, conditional formats, charts."""
    notes = []
    bolds = [c.get("r", "") for c in root.iter(f"{S}c") if c.get("s", "").isdigit() and int(c.get("s")) in bold]
    if bolds:
        notes.append("Bold: " + ", ".join(bolds[:30]) + (f" … ({len(bolds)} cells)" if len(bolds) > 30 else ""))
    pane = root.find(f".//{S}sheetView/{S}pane")
    if pane is not None and pane.get("state") in ("frozen", "frozenSplit"):
        notes.append(f"Frozen panes: rows and columns before {pane.get('topLeftCell', '?')} stay in view")
    for cf in root.iter(f"{S}conditionalFormatting"):
        for rule in cf.iter(f"{S}cfRule"):
            what = rule.get("operator") or rule.get("type", "")
            formula = "; ".join(f.text or "" for f in rule.iter(f"{S}formula"))
            dxf = int(rule.get("dxfId", -1) or -1)
            style = fills[dxf] if 0 <= dxf < len(fills) and fills[dxf] else "no format"
            notes.append(f"Conditional format: {cf.get('sqref', '?')} {what} {formula} → {style}")
    folder, name = target.rsplit("/", 1)
    rels = _rels(z, target) if f"{folder}/_rels/{name}.rels" in z.namelist() else {}
    for drawing in (t for t in rels.values() if "drawings/" in t and t in z.namelist()):
        for chart in _rels(z, drawing).values():
            if chart in z.namelist() and "charts/" in chart:
                plot = _xml(z, chart).find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}plotArea")
                kinds = [
                    el.tag.split("}")[1] for el in list(plot if plot is not None else []) if el.tag.endswith("Chart")
                ]
                refs = [
                    f.text for f in _xml(z, chart).iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}f")
                ][:3]
                notes.append(f"Chart: {', '.join(kinds) or 'chart'}" + (f" of {', '.join(refs)}" if refs else ""))
    return notes


def _xlsx_sheet(root: ET.Element, shared: list[str], budget: int) -> tuple[str, int]:
    rows, formulas, used = [], [], 0
    for row in root.iter(f"{S}row"):
        cells = []
        for c in row.iter(f"{S}c"):
            ref, kind = c.get("r", ""), c.get("t", "")
            v = c.find(f"{S}v")
            value = v.text if v is not None and v.text is not None else ""
            if kind == "s" and value.isdigit() and int(value) < len(shared):
                value = shared[int(value)]
            elif kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(f"{S}t"))
            elif kind == "b":
                value = "TRUE" if value == "1" else "FALSE"
            elif kind == "e":
                value = value or "#ERROR"
            f = c.find(f"{S}f")
            if f is not None and f.text:
                formulas.append(f"{ref} ={f.text}")
                if v is None:  # written by a library: no result stored until a spreadsheet app recalculates it
                    value = "(not calculated yet)"
            if value != "":
                cells.append(f"{ref}: {value}")
                used += 1
        if cells:
            rows.append("  ".join(cells))
        if used >= budget:
            break
    text = "\n".join(rows) or "(empty)"
    if formulas:
        text += "\nFormulas: " + "; ".join(formulas[:500])
    return text, used


# PowerPoint ------------------------------------------------------------------------------
P14 = "{http://schemas.microsoft.com/office/powerpoint/2010/main}"
EMU_CM = 360_000


def _pptx(p: Path, details: bool = False) -> str:
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        pres = _xml(z, "ppt/presentation.xml")
        rels = _rels(z, "ppt/presentation.xml")
        order = [rels.get(s.get(f"{R}id", ""), "") for s in pres.iter(f"{P}sldId")] or sorted(
            (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n).group(1)),
        )
        out = []
        size = pres.find(f"{P}sldSz")
        if details and size is not None:
            out.append(f"Slides are {int(size.get('cx', 0)) / EMU_CM:.2f} x {int(size.get('cy', 0)) / EMU_CM:.2f} cm")
        for i, name in enumerate(order, 1):
            if name not in names:
                continue
            slide = _xml(z, name)
            folder, base = name.rsplit("/", 1)
            srels = _rels(z, name) if f"{folder}/_rels/{base}.rels" in names else {}
            lines = [f"## Slide {i}"]
            if details:
                lines.append(f"Background: {_pptx_background(slide)}")
            tree = slide.find(f"{P}cSld/{P}spTree")
            for shape in list(tree if tree is not None else []):
                lines.extend(_pptx_shape(shape, srels, details, ""))
            notes = next((t for t in srels.values() if "notesSlide" in t and t in names), None)
            if notes:
                text = _pptx_notes(_xml(z, notes))
                if text:
                    lines.append(f"Notes: {text}")
            out.append("\n".join(lines))
        return "\n\n".join(out)


def _pptx_background(slide: ET.Element) -> str:
    bg = slide.find(f"{P}cSld/{P}bg")
    if bg is None:
        return "from the layout or master"
    rgb = bg.find(f".//{A}srgbClr")
    if rgb is not None:
        return f"#{rgb.get('val')}" + (" (solid)" if bg.find(f".//{A}solidFill") is not None else "")
    scheme = bg.find(f".//{A}schemeClr")
    if scheme is not None:
        return f"theme colour {scheme.get('val')}"
    if bg.find(f".//{A}blipFill") is not None:
        return "a picture"
    if bg.find(f".//{A}gradFill") is not None:
        return "a gradient"
    return "set on the slide"


def _pptx_box(shape: ET.Element) -> str:
    xfrm = shape.find(f"{P}spPr/{A}xfrm")
    if xfrm is None:
        xfrm = shape.find(f"{P}xfrm")  # (a table's frame)
    if xfrm is None:
        xfrm = shape.find(f"{P}grpSpPr/{A}xfrm")
    off, ext = (xfrm.find(f"{A}off"), xfrm.find(f"{A}ext")) if xfrm is not None else (None, None)
    if off is None or ext is None:
        return "placed by its layout"
    x, y = int(off.get("x", 0)) / EMU_CM, int(off.get("y", 0)) / EMU_CM
    w, h = int(ext.get("cx", 0)) / EMU_CM, int(ext.get("cy", 0)) / EMU_CM
    return f"at {x:.2f}, {y:.2f} cm, {w:.2f} x {h:.2f} cm"


def _pptx_shape(shape: ET.Element, srels: dict, details: bool, indent: str) -> list[str]:
    tag = shape.tag.split("}")[-1]
    props = shape.find(f".//{P}cNvPr")
    name = props.get("name", "") if props is not None else ""
    out: list[str] = []
    if tag == "grpSp":
        if details:
            out.append(f"{indent}[group{_named(name)} {_pptx_box(shape)}]")
        for kid in shape:
            out.extend(_pptx_shape(kid, srels, details, indent + ("  " if details else "")))
        return out
    if tag == "pic":
        media = []
        for el in shape.iter():
            kind = el.tag.split("}")[-1]
            if kind in ("audioFile", "videoFile", "media"):
                target = srels.get(el.get(f"{R}link") or el.get(f"{R}embed") or "", "")
                media.append(f"{kind.replace('File', '')} {target.rsplit('/', 1)[-1] or '?'}")
        what = media[0] if media else "picture"
        out.append(f"{indent}[{what}{_named(name)}" + (f" {_pptx_box(shape)}" if details else "") + "]")
        return out
    if tag == "graphicFrame":
        tbl = shape.find(f".//{A}tbl")
        if tbl is not None:
            rows = [
                [
                    " ".join("".join(t.text or "" for t in par.iter(f"{A}t")) for par in tc.iter(f"{A}p")).strip()
                    for tc in tr.iter(f"{A}tc")
                ]
                for tr in tbl.iter(f"{A}tr")
            ]
            cols = max((len(r) for r in rows), default=0)
            out.append(
                f"{indent}[table{_named(name)}: {len(rows)} rows x {cols} columns"
                + (f" {_pptx_box(shape)}" if details else "")
                + "]"
            )
            out.extend(f"{indent}| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows if any(r))
        elif details:
            out.append(
                f"{indent}[{shape.find(f'.//{A}graphicData').get('uri', 'object').rsplit('/', 1)[-1]}{_named(name)} {_pptx_box(shape)}]"
            )
        return out
    body = shape.find(f"{P}txBody")
    paras = list(body.iter(f"{A}p")) if body is not None else []
    has_text = any("".join(t.text or "" for t in par.iter(f"{A}t")).strip() for par in paras)
    box = _pptx_box(shape)
    if details and not has_text and not name and box == "placed by its layout":
        return out  # (an empty placeholder of the layout: nothing to say)
    if details:
        out.append(f"{indent}[shape{_named(name)} {box}]")
    for par in paras:
        text = "".join(t.text or "" for t in par.iter(f"{A}t")).strip()
        if not text and not details:
            continue
        line = f"{indent}{'  ' if details else ''}{text}"
        if details:
            info = _pptx_paragraph(par)
            line += f"  ({info})" if info else ""
        if text or details:
            out.append(
                line if text else f"{indent}  (empty paragraph)" + (f"  ({_pptx_paragraph(par)})" if details else "")
            )
    return out


def _named(name: str) -> str:
    return f' "{name}"' if name else ""


def _pptx_paragraph(par: ET.Element) -> str:
    out = []
    ppr = par.find(f"{A}pPr")
    if ppr is not None:
        if ppr.get("lvl") not in (None, "0"):
            out.append(f"level {ppr.get('lvl')}")
        if ppr.find(f"{A}buNone") is not None:
            out.append("no bullet")
        elif ppr.find(f"{A}buChar") is not None:
            out.append(f"bullet {ppr.find(f'{A}buChar').get('char', '')!r}")
        elif ppr.find(f"{A}buAutoNum") is not None:
            out.append(f"numbered {ppr.find(f'{A}buAutoNum').get('type', '')}")
        for k, label in (("marL", "indent"), ("indent", "first line")):
            if ppr.get(k) not in (None, "0"):
                out.append(f"{label} {int(ppr.get(k)) / EMU_CM:.2f} cm")
        if ppr.get("algn"):
            out.append(
                {"l": "left", "ctr": "centered", "r": "right", "just": "justified"}.get(
                    ppr.get("algn"), ppr.get("algn")
                )
            )
    sizes, looks = set(), set()
    for rpr in par.iter(f"{A}rPr"):
        if rpr.get("sz"):
            sizes.add(f"{int(rpr.get('sz')) / 100:g} pt")
        for k, label in (("b", "bold"), ("i", "italic")):
            if rpr.get(k) in ("1", "true"):
                looks.add(label)
        if rpr.get("u") not in (None, "none"):
            looks.add("underline")
        rgb = rpr.find(f"{A}solidFill/{A}srgbClr")
        if rgb is not None:
            looks.add(f"#{rgb.get('val')}")
    out += sorted(sizes) + sorted(looks)
    return ", ".join(out)


def _pptx_notes(notes: ET.Element) -> str:
    for sp in notes.iter(f"{P}sp"):
        ph = sp.find(f".//{P}ph")
        if ph is not None and ph.get("type") == "body":
            return " ".join(
                "".join(t.text or "" for t in par.iter(f"{A}t")).strip() for par in sp.iter(f"{A}p")
            ).strip()
    return ""


# OpenDocument ----------------------------------------------------------------------------
def _odf(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        body = _xml(z, "content.xml").find(f"{OFFICE}body")
    out: list[str] = []
    if body is not None:
        for kind in body:
            if kind.tag == f"{OFFICE}spreadsheet":
                for table in kind.iter(f"{TABLE}table"):
                    out.append(f"## Sheet: {table.get(f'{TABLE}name', '?')}\n{_odf_table(table, cells=True)}")
            elif kind.tag == f"{OFFICE}presentation":
                for i, page in enumerate(kind.iter(f"{DRAW}page"), 1):
                    lines = [_odf_text(par) for par in page.iter() if par.tag in (f"{TEXT}p", f"{TEXT}h")]
                    out.append(f"## Slide {i}\n" + "\n".join(line for line in lines if line.strip()))
            else:
                _odf_blocks(kind, out)
    return "\n".join(out)


def _odf_blocks(node: ET.Element, out: list[str]) -> None:
    for child in node:
        if child.tag == f"{TEXT}h":
            out.append("#" * int(child.get(f"{TEXT}outline-level", "1")) + " " + _odf_text(child))
        elif child.tag == f"{TEXT}p":
            out.append(_odf_text(child))
        elif child.tag == f"{TABLE}table":
            out.append(_odf_table(child))
        elif child.tag in (f"{TEXT}list", f"{TEXT}list-item", f"{TEXT}section"):
            before = len(out)
            _odf_blocks(child, out)
            if child.tag == f"{TEXT}list-item" and len(out) > before:
                out[before] = "- " + out[before]


def _odf_text(node: ET.Element) -> str:
    parts = [node.text or ""]
    for child in node:
        if child.tag == f"{TEXT}s":
            parts.append(" " * int(child.get(f"{TEXT}c", "1")))
        elif child.tag == f"{TEXT}tab":
            parts.append("\t")
        elif child.tag == f"{TEXT}line-break":
            parts.append("\n")
        else:
            parts.append(_odf_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _odf_table(table: ET.Element, cells: bool = False) -> str:
    rows, r, used = [], 0, 0
    for row in table.iter(f"{TABLE}table-row"):
        repeat_rows = int(row.get(f"{TABLE}number-rows-repeated", "1"))
        values, c = [], 0
        for cell in row:
            if cell.tag not in (f"{TABLE}table-cell", f"{TABLE}covered-table-cell"):
                continue
            repeat = int(cell.get(f"{TABLE}number-columns-repeated", "1"))
            text = "\n".join(_odf_text(par) for par in cell.iter(f"{TEXT}p"))
            formula = cell.get(f"{TABLE}formula", "")
            if not text:  # empty cells often repeat thousands of times: skip them in one step
                c += repeat
                continue
            for col in range(c + 1, c + min(repeat, 1024) + 1):
                values.append((col, text, formula))
            c += repeat
        if not values:
            r += repeat_rows  # (addresses below a big empty block stay right)
            continue
        for i in range(repeat_rows):
            r += 1
            if i == 1000:  # the same row repeated: show it 1000 times at most, but keep counting
                r += repeat_rows - 1001
                break
            if cells:
                rows.append(
                    "  ".join(
                        f"{_col(col)}{r}: {text}" + (f" ({re.sub(r'^of:', '', formula)})" if formula else "")
                        for col, text, formula in values
                    )
                )
            else:
                rows.append("| " + " | ".join(text for _, text, _ in values) + " |")
            used += len(values)
            if used >= MAX_CELLS:
                return "\n".join(rows) + "\n… [more cells not shown]"
    return "\n".join(rows) or "(empty)"


# EPUB and HTML ---------------------------------------------------------------------------
class _TextOf(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "pre", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
            if tag in ("h1", "h2", "h3") and not self.skip:
                self.parts.append("#" * int(tag[1]) + " ")
            elif tag == "li":
                self.parts.append("- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(markup: str) -> str:
    parser = _TextOf()
    parser.feed(markup)
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(lines)


def _html_file(p: Path) -> str:
    return html_to_text(p.read_text(encoding="utf-8", errors="replace"))


def _epub(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        container = _xml(z, "META-INF/container.xml")
        opf_path = next(
            (e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile") and e.get("full-path")), ""
        )
        opf = _xml(z, opf_path)
        folder = os.path.dirname(opf_path)
        items = {e.get("id"): e.get("href") for e in opf.iter() if e.tag.endswith("}item")}
        chapters = []
        for ref in opf.iter():
            if ref.tag.endswith("}itemref") and ref.get("idref") in items:
                name = os.path.normpath(os.path.join(folder, html.unescape(items[ref.get("idref")]))).replace("\\", "/")
                if name in z.namelist():
                    chapters.append(html_to_text(z.read(name).decode("utf-8", errors="replace")))
        return "\n\n".join(chapters)


# PDF, images and everything else --------------------------------------------------------
def _need(tool: str, package: str) -> str:
    """The path of `tool`, installing its Debian package once if it is missing."""
    found = shutil.which(tool)
    if found:
        return found
    ok = subprocess.run(
        [
            "bash",
            "-lc",
            f"sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {package}",
        ],
        capture_output=True,
        timeout=600,
    )
    found = shutil.which(tool)
    if not found:
        detail = (ok.stderr or ok.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        raise DocError(
            f"{tool} is not installed and installing {package} failed"
            + (f": {detail[0]}" if detail else "")
            + f". Try run('minion-install {package}')"
        )
    return found


def _pdf(p: Path) -> str:
    tool = _need("pdftotext", "poppler-utils")
    res = subprocess.run([tool, "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=180)
    if res.returncode != 0:
        raise DocError(f"pdftotext failed: {res.stderr.decode('utf-8', 'replace').strip()[:300]}")
    text = res.stdout.decode("utf-8", errors="replace")
    if len(text.strip()) < 20:  # a scanned PDF: no text layer, so read its pages with OCR
        text = _pdf_ocr(p) or text
    return text.rstrip("\f\n").replace("\f", "\n\n--- page break ---\n\n")


def _pdf_ocr(p: Path, max_pages: int = 20) -> str:
    from PIL import Image

    from . import ocr

    tool = _need("pdftoppm", "poppler-utils")
    with tempfile.TemporaryDirectory() as tmp:
        # 300 dpi in grayscale (PGM: no PNG compression to wait for), the resolution Tesseract reads best.
        subprocess.run(
            [tool, "-r", "300", "-gray", "-l", str(max_pages), str(p), f"{tmp}/page"], capture_output=True, timeout=300
        )
        pages, langs = [], ocr.ensure(ocr.langs_for(p.stem))[0]
        for page in sorted(Path(tmp).glob("page*")):
            with Image.open(page) as img:
                text, langs = ocr.page_text(img, langs)  # the first page settles the language for the rest
            pages.append(text)
        return "\n\n--- page break ---\n\n".join(pages)


def _ocr(p: Path) -> str:
    """A picture of text, read in its language: a Hebrew file name says Hebrew; otherwise English, unless it
    reads poorly in English, when the script is detected and the picture read again."""
    from PIL import Image

    from . import ocr

    if not shutil.which("tesseract"):
        raise DocError("OCR needs tesseract: run('minion-install tesseract-ocr')")
    with Image.open(p) as img:
        img.load()
        text = ocr.page_text(img, ocr.ensure(ocr.langs_for(p.stem))[0])[0]
        about = f"[{img.format or p.suffix.lstrip('.').upper()} image, {img.width}x{img.height}"
    if sum(ch.isalnum() for ch in text) < 4:  # a photo or a drawing: say what it is, not a stray "y"
        return about + ": no text in it that OCR could read. To see it, open it and take a screenshot]"
    return text


def office_profile() -> str:
    """A LibreOffice profile just for conversions, so they work while LibreOffice is open."""
    folder = Path(os.environ.get("MINION_RUNTIME_DIR", tempfile.gettempdir())) / "lo-convert"
    return folder.as_uri()


def _soffice() -> str:
    tool = shutil.which("soffice") or shutil.which("libreoffice")
    if not tool:
        raise DocError(
            "this needs LibreOffice, which this desktop doesn't have: use the office profile, "
            "or run('minion-install libreoffice-writer libreoffice-calc libreoffice-impress')"
        )
    return tool


WEB_EXT = {".html", ".htm", ".xhtml"}
SHEET_OUT = {"xlsx", "xls", "ods", "csv"}


def _office_convert(src: Path, fmt: str, outdir: Path, timeout: float = 180) -> Path:
    tool = _soffice()
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [tool, f"-env:UserInstallation={office_profile()}", "--headless", "--norestore", "--convert-to", fmt]
    ext = fmt.split(":", 1)[0]
    if src.suffix.lower() in WEB_EXT:  # a web page opens in Writer/Web, which can't save docx/odt: import it
        cmd.append("--infilter=" + ("HTML (StarCalc)" if ext in SHEET_OUT else "HTML (StarWriter)"))
    res = subprocess.run([*cmd, "--outdir", str(outdir), str(src)], capture_output=True, timeout=timeout)
    out = outdir / f"{src.stem}.{ext}"
    if not out.exists():
        detail = (res.stderr or res.stdout).decode("utf-8", "replace").strip()
        raise DocError(f"LibreOffice could not convert {src.name} to {ext}" + (f": {detail[-300:]}" if detail else ""))
    return out


def _via_office(p: Path) -> str:
    ext = p.suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        if ext in OFFICE_SHEET_EXT:
            return _xlsx(_office_convert(p, "xlsx", Path(tmp)))
        if ext in OFFICE_SLIDE_EXT:
            return _pdf(_office_convert(p, "pdf", Path(tmp)))
        return _office_convert(p, "txt:Text (encoded):UTF8", Path(tmp)).read_text(encoding="utf-8", errors="replace")


# -- converting --------------------------------------------------------------------------
ALIASES = {"word": "docx", "excel": "xlsx", "powerpoint": "pptx", "text": "txt", "markdown": "md", "jpeg": "jpg"}
IMAGE_FORMATS = {"png", "jpg", "webp", "bmp", "gif", "tiff"}


def convert(path: str, to: str, outdir: str | None = None) -> str:
    """Convert a document or image to another format; returns the new file's path. `to` is an extension
    ("pdf", "docx", "xlsx", "csv", "png", "md", ...), or the new file's name or path ("sales_sorted.xlsx",
    "~/out/report.pdf"). The output goes next to the input unless `outdir` is given."""
    src = Path(os.path.expanduser(path))
    if not src.is_file():
        raise DocError(f"no such file: {path}")
    if "/" in to or ("." in to.strip(".") and not to.startswith(".")):  # a file name or path, not a format
        dest = Path(os.path.expanduser(to))
        if not dest.is_absolute():
            dest = (Path(os.path.expanduser(outdir)) if outdir else src.parent) / dest
        if not dest.suffix:
            raise DocError(f"{to}: give the new file an extension (.pdf, .xlsx, ...), or just a format")
        with tempfile.TemporaryDirectory() as tmp:
            made = Path(convert(path, dest.suffix.lstrip("."), tmp).split(" (and ")[0])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(made), dest)
        return str(dest)
    fmt = ALIASES.get(to.lower().lstrip("."), to.lower().lstrip("."))
    dest_dir = Path(os.path.expanduser(outdir)) if outdir else src.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower().lstrip(".")
    if fmt == ext and dest_dir.resolve() == src.parent.resolve():
        raise DocError(f"{src.name} is already .{fmt} (give a new file name to save a recalculated copy)")
    if ext in IMAGE_FORMATS | {"jpeg", "tif"} and fmt in IMAGE_FORMATS | {"pdf"}:
        from PIL import Image

        out = dest_dir / f"{src.stem}.{fmt}"
        with Image.open(src) as im:
            im = im.convert("RGB") if fmt in ("jpg", "pdf", "bmp") else im
            im.save(out, "JPEG" if fmt == "jpg" else fmt.upper())
        return str(out)
    if ext == "pdf" and fmt in ("png", "jpg"):
        tool = _need("pdftoppm", "poppler-utils")
        prefix = dest_dir / src.stem
        flag = "-png" if fmt == "png" else "-jpeg"
        subprocess.run([tool, "-r", "120", flag, str(src), str(prefix)], capture_output=True, timeout=300)
        pages = sorted(dest_dir.glob(f"{src.stem}-*.{'png' if fmt == 'png' else 'jpg'}"))
        if not pages:
            raise DocError(f"could not render {src.name}")
        return str(pages[0]) + (f" (and {len(pages) - 1} more pages)" if len(pages) > 1 else "")
    if ext == "pdf" and fmt in ("txt", "md"):
        out = dest_dir / f"{src.stem}.{fmt}"
        out.write_text(_pdf(src), encoding="utf-8")
        return str(out)
    if fmt == "md" or ext == "md":
        pandoc = shutil.which("pandoc")
        if pandoc:
            out = dest_dir / f"{src.stem}.{fmt}"
            res = subprocess.run([pandoc, str(src), "-o", str(out)], capture_output=True, timeout=180)
            if res.returncode == 0 and out.exists():
                return str(out)
        if fmt == "md":  # no pandoc: the reader's plain text, which keeps headings and tables readable
            out = dest_dir / f"{src.stem}.md"
            out.write_text(read(str(src))[0], encoding="utf-8")
            return str(out)
        raise DocError("converting Markdown needs pandoc: run('minion-install pandoc')")
    office_fmt = {"txt": "txt:Text (encoded):UTF8", "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1"}.get(fmt, fmt)
    return str(_office_convert(src, office_fmt, dest_dir))


def main(argv: list[str] | None = None) -> int:
    """`minion-read FILE` prints a document's text; `minion-convert FILE FORMAT [OUTDIR]` (which runs this
    with --convert) converts it."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "--convert":
            args = args[1:]
            if len(args) < 2:
                print("usage: minion-convert FILE FORMAT [OUTDIR]   (e.g. minion-convert report.docx pdf)")
                return 2
            print(convert(args[0], args[1], args[2] if len(args) > 2 else None))
            return 0
        if not args:
            print("usage: minion-read FILE   (docx, xlsx, pptx, odt, ods, odp, pdf, epub, html, images, ...)")
            return 2
        for path in args:
            text, kind = read(path)
            if len(args) > 1:
                print(f"==> {path} ({kind}) <==")
            print(text, end="")
        return 0
    except DocError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
