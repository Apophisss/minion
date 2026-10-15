"""On-screen text recognition with Tesseract: text that accessibility doesn't expose (images, canvas apps, photos
of screens, remote desktops, programs without an accessibility tree), in the language it is written in."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

# Scripts whose text needs its own Tesseract language data: (first code point, last code point, language).
SCRIPTS = (
    (0x0590, 0x05FF, "heb"),
    (0xFB1D, 0xFB4F, "heb"),
    (0x0600, 0x06FF, "ara"),
    (0x0750, 0x077F, "ara"),
    (0x0400, 0x04FF, "rus"),
    (0x0370, 0x03FF, "ell"),
    (0x0900, 0x097F, "hin"),
    (0x0E00, 0x0E7F, "tha"),
    (0x3040, 0x30FF, "jpn"),
    (0x1100, 0x11FF, "kor"),
    (0xAC00, 0xD7AF, "kor"),
    (0x4E00, 0x9FFF, "chi_sim"),
)
NAMES = {
    "eng": "English",
    "heb": "Hebrew",
    "ara": "Arabic",
    "rus": "Russian",
    "ell": "Greek",
    "hin": "Hindi",
    "tha": "Thai",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi_sim": "Chinese",
    "chi_tra": "Chinese (traditional)",
}
RTL = {"heb", "ara"}


@dataclass
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float


@dataclass
class Line:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    words: list[Word] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def to_dict(self) -> dict:
        cx, cy = self.center
        return {
            "text": self.text,
            "x": cx,
            "y": cy,
            "box": [self.x, self.y, self.w, self.h],
            "conf": round(self.conf, 1),
        }


def available() -> bool:
    return shutil.which("tesseract") is not None


def langs_for(text: str, limit: int = 2) -> list[str]:
    """The Tesseract languages for the scripts in `text` (window titles, labels: what the screen is written in),
    most frequent first, then English for Latin text and digits: "מבוא למנהיגות — Firefox" -> ["heb", "eng"]."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        if cp < 0x0370:
            continue
        for lo, hi, lang in SCRIPTS:
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if counts.get("jpn"):  # kana means Japanese, whose kanji are CJK ideographs too
        counts["jpn"] += counts.pop("chi_sim", 0)
    found = [lang for lang, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= 2]
    return found[:limit] + ["eng"]


def blind_spots(
    img: Image.Image,
    covered: list[tuple[int, int, int, int]],
    origin: tuple[int, int] = (0, 0),
    min_share: float = 0.04,
    limit: int = 3,
    cell: int = 32,
) -> list[tuple[int, int, int, int]]:
    """Parts of a window that show detail (text, maybe) that no accessible element with text covers: a slide, a
    canvas, a picture of text, a remote screen. `img` is the window at `origin`; `covered` are the screen boxes of
    elements that do have text. Returns up to `limit` regions of at least `min_share` of the window, largest
    first, in screen coordinates."""
    ox, oy = origin
    cols, rows = max(1, img.width // cell), max(1, img.height // cell)
    edges = ImageOps.grayscale(img).filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
    ImageDraw.Draw(edges).rectangle([0, 0, img.width - 1, img.height - 1], outline=0)  # the filter marks the border
    # The share of edge pixels in each cell (exact cells: the last few pixels that don't fill one are left out).
    density = edges.crop((0, 0, cols * cell, rows * cell)).resize((cols, rows), Image.Resampling.BOX).load()
    cov = [[False] * cols for _ in range(rows)]
    for x, y, w, h in covered:  # a cell is covered when its center is inside an element with text
        for r in range(max(0, (y - oy) // cell), min(rows, (y - oy + h) // cell + 1)):
            for c in range(max(0, (x - ox) // cell), min(cols, (x - ox + w) // cell + 1)):
                cx, cy = ox + c * cell + cell // 2, oy + r * cell + cell // 2
                if x <= cx < x + w and y <= cy < y + h:
                    cov[r][c] = True
    busy = {(r, c) for r in range(rows) for c in range(cols) if not cov[r][c] and density[c, r] > 6}
    regions = []
    while busy:  # group busy cells, bridging gaps of one cell (the space between lines of text)
        stack = [busy.pop()]
        group = []
        while stack:
            r, c = stack.pop()
            group.append((r, c))
            for dr in (-2, -1, 0, 1, 2):
                for dc in (-2, -1, 0, 1, 2):
                    if (r + dr, c + dc) in busy:
                        busy.discard((r + dr, c + dc))
                        stack.append((r + dr, c + dc))
        r0, r1 = min(r for r, _ in group), max(r for r, _ in group)
        c0, c1 = min(c for _, c in group), max(c for _, c in group)
        if len(group) >= 4:
            regions.append((c0, r0, c1, r1, len(group)))
    merged = True
    while merged:  # boxes that overlap become one, or the text where they meet is read twice
        merged = False
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                a, b = regions[i], regions[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    regions[i] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]), a[4] + b[4])
                    del regions[j]
                    merged = True
                    break
            if merged:
                break
    out = []
    for c0, r0, c1, r1, _n in sorted(regions, key=lambda g: -(g[2] - g[0] + 1) * (g[3] - g[1] + 1)):
        x, y = ox + c0 * cell, oy + r0 * cell
        w, h = min(img.width, (c1 + 1) * cell) - c0 * cell, min(img.height, (r1 + 1) * cell) - r0 * cell
        if w * h >= min_share * img.width * img.height:
            out.append((x, y, w, h))
    return out[:limit]


# Tesseract's script detection (--psm 0) names: the language to read each script with.
OSD_SCRIPTS = {
    "Hebrew": "heb",
    "Arabic": "ara",
    "Cyrillic": "rus",
    "Greek": "ell",
    "Devanagari": "hin",
    "Thai": "tha",
    "Japanese": "jpn",
    "Katakana": "jpn",
    "Hiragana": "jpn",
    "Hangul": "kor",
    "Korean": "kor",
    "Han": "chi_sim",
    "HanS": "chi_sim",
    "HanT": "chi_tra",
}


def detect(img: Image.Image, timeout: float = 30.0) -> list[str]:
    """A guess at the languages of a picture of text, from Tesseract's script detection: ["heb", "eng"] for
    Hebrew, ["eng"] for Latin or when it can't tell. It often can't, so callers check the guess by reading."""
    if "osd" not in installed():
        return ["eng"]
    gray = _prepare(img, 2.0 if max(img.size) <= 1600 else 1.0)
    out = _tesseract(gray, ["--psm", "0"], timeout)
    script = next((ln.split(":", 1)[1].strip() for ln in (out or "").splitlines() if ln.startswith("Script:")), "")
    lang = OSD_SCRIPTS.get(script)
    return [lang, "eng"] if lang else ["eng"]


def mask(img: Image.Image, boxes: list[tuple[int, int, int, int]], origin: tuple[int, int]) -> Image.Image:
    """The picture with the parts accessibility already reads (screen `boxes`) painted over in its background
    colour: their text would be dropped anyway, and next to a picture it confuses Tesseract's layout analysis
    (a page heading above a slide made it lose the slide's title)."""
    ox, oy = origin
    inside = [
        (x - ox, y - oy, w, h)
        for x, y, w, h in boxes
        if x < ox + img.width and y < oy + img.height and x + w > ox and y + h > oy
    ]
    if not inside:
        return img
    colours = img.convert("RGB").reduce(8).getcolors(maxcolors=1 << 16) or [(1, (255, 255, 255))]
    out = img.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for x, y, w, h in inside:
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=max(colours)[1])
    return out


def trim(img: Image.Image, pad: int = 0) -> tuple[Image.Image, tuple[int, int]]:
    """The picture without its plain margins (the page around an image, parts painted over by mask()), and where
    the rest starts, cut to the edge: around a slide, even a few pixels of white page turn into a black frame
    when the light-text pass inverts the picture, and Tesseract then lost the slide's white-on-colour title."""
    rgb = img.convert("RGB")
    colours = rgb.reduce(8).getcolors(maxcolors=1 << 16) or [(1, (255, 255, 255))]
    plain = Image.new("RGB", rgb.size, max(colours)[1])
    box = ImageChops.difference(rgb, plain).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        return img, (0, 0)
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(img.width, box[2] + pad), min(img.height, box[3] + pad)
    if (x1 - x0) * (y1 - y0) > 0.95 * img.width * img.height:
        return img, (0, 0)
    return img.crop((x0, y0, x1, y1)), (x0, y0)


_installed: set[str] | None = None
_failed: set[str] = set()
_install_lock = threading.Lock()


def installed() -> set[str]:
    """The languages Tesseract has data for in this desktop."""
    global _installed
    if _installed is None:
        try:
            out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=15)
            _installed = {ln.strip() for ln in out.stdout.splitlines()[1:] if ln.strip()}
        except (OSError, subprocess.TimeoutExpired):
            _installed = set()
    return _installed


def ensure(langs: list[str]) -> tuple[list[str], str]:
    """The languages of `langs` that OCR can use, installing missing language data once (a few MB each, from
    Debian). Returns them and a note on what was installed or couldn't be."""
    global _installed
    missing = [lg for lg in langs if lg not in installed() and lg not in _failed]
    note = ""
    if missing:
        from . import catalog

        with _install_lock:
            missing = [lg for lg in missing if lg not in installed()]
            if missing:
                names = ", ".join(NAMES.get(lg, lg) for lg in missing)
                try:
                    catalog.install(["tesseract-ocr-" + lg.replace("_", "-") for lg in missing], timeout=300)
                    note = f"installed {names} OCR"
                except Exception as e:  # offline, or installing is turned off: read with what there is
                    _failed.update(missing)
                    note = f"no {names} OCR: {e}"
                _installed = None
    usable = [lg for lg in langs if lg in installed()]
    return usable or ["eng"], note


# Tesseract settings, measured on 24 photographed Hebrew slides and on English terminals and dialogs (word recall
# 0.90 and 0.99, against 0.02 and 0.85 with English-only psm 11): psm 4 reads a column of text of mixed sizes in
# order, and Sauvola thresholding keeps light text on busy or low-contrast backgrounds.
PSM = 4
SAUVOLA = ["-c", "thresholding_method=2", "-c", "thresholding_kfactor=0.5"]
DOUBTFUL = 50.0  # a mean word confidence below this, over 5+ words, usually means the wrong language
_BIDI_MARKS = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"))


class Lines(list):
    """Lines of text, with how sure Tesseract was about the words it saw (all of them, kept or not)."""

    conf: float = 0.0
    words: int = 0


def parse_tsv(tsv: str, scale: float = 1.0, offset: tuple[int, int] = (0, 0), min_conf: float = 35.0) -> Lines:
    """Group Tesseract TSV word rows into lines, mapping coordinates back to the screen. Words stay in Tesseract's
    order, which is reading order (right to left in Hebrew and Arabic, with English runs inside kept left to right),
    and a line is split where words are far apart on screen (UI labels side by side)."""
    ox, oy = offset
    groups: dict[tuple, list[Word]] = {}
    order: list[tuple] = []
    confs: list[float] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = _digits(cols[11].translate(_BIDI_MARKS).strip())
        if not text:
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        confs.append(max(0.0, conf))
        if conf < min_conf:
            continue
        left, top, width, height = (int(c) for c in cols[6:10])
        word = Word(
            text=text,
            x=round(left / scale) + ox,
            y=round(top / scale) + oy,
            w=max(1, round(width / scale)),
            h=max(1, round(height / scale)),
            conf=conf,
        )
        key = (cols[1], cols[2], cols[3], cols[4])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(word)
    lines = Lines()
    for key in order:
        words = groups[key]
        heights = sorted(w.h for w in words)
        gap = max(18, 2.2 * heights[len(heights) // 2])
        rank = {id(w): i for i, w in enumerate(words)}
        chunks: list[list[Word]] = []
        for w in sorted(words, key=lambda w: w.x):  # split where words are far apart on screen...
            if chunks and w.x - max(v.x + v.w for v in chunks[-1]) > gap:
                chunks.append([])
            if not chunks:
                chunks.append([])
            chunks[-1].append(w)
        rtl = sum(_is_rtl(w.text) for w in words) * 2 > len(words)
        for chunk in reversed(chunks) if rtl else chunks:  # ...and keep each part in reading order
            lines.append(_line(sorted(chunk, key=lambda w: rank[id(w)])))
    _sort_lines(lines)
    lines.conf = sum(confs) / len(confs) if confs else 0.0
    lines.words = len(confs)
    return lines


_LOOKALIKE = str.maketrans({"i": "1", "I": "1", "l": "1", "|": "1", "o": "0", "O": "0"})
_NUMBERISH = re.compile(r"^[(\[$€£₪]?[\d.,:/-]*[iIl|oO][\diIl|oO.,:/-]*[)\]%]?$")


def _digits(text: str) -> str:
    """A number OCR misread with a lookalike letter ("7i" for 71, "2O26" for 2026): mostly digits, and its only
    letters are ones that look like digits."""
    digits = sum(ch.isdigit() for ch in text)
    if digits and _NUMBERISH.match(text) and digits * 2 >= sum(ch.isalnum() for ch in text):
        return text.translate(_LOOKALIKE)
    return text


def _is_rtl(text: str) -> bool:
    return any(0x0590 <= ord(ch) <= 0x08FF or 0xFB1D <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF for ch in text)


def _line(words: list[Word]) -> Line:
    x0 = min(w.x for w in words)
    y0 = min(w.y for w in words)
    x1 = max(w.x + w.w for w in words)
    y1 = max(w.y + w.h for w in words)
    conf = sum(w.conf for w in words) / len(words)
    return Line(" ".join(w.text for w in words), x0, y0, x1 - x0, y1 - y0, conf, list(words))


def _prepare(img: Image.Image, upscale: float) -> Image.Image:
    """Grayscale, enlarged (small screen text reads far better at 2x), dark text on light."""
    gray = ImageOps.grayscale(img)
    if upscale and upscale != 1.0:
        gray = gray.resize((round(gray.width * upscale), round(gray.height * upscale)), Image.Resampling.LANCZOS)
    if ImageStat.Stat(gray.reduce(8)).mean[0] < 110:
        gray = ImageOps.invert(gray)  # dark UIs: Tesseract prefers dark text on a light background
    return gray


def _tesseract(gray: Image.Image, args: list[str], timeout: float) -> str | None:
    """Run Tesseract on an image; its output, or None if it took too long (a very busy machine)."""
    if not available():
        raise RuntimeError("tesseract is not installed in this desktop")
    with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
        path = f.name
    try:
        gray.save(path, "PPM")  # PGM: written in milliseconds, where a compressed PNG takes over half a second
        out = subprocess.run(
            ["tesseract", path, "stdout", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(os.environ, OMP_THREAD_LIMIT="1"),
        )
    except subprocess.TimeoutExpired:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if out.returncode != 0 and "--psm" in args and args[args.index("--psm") + 1] != "0":
        raise RuntimeError(f"tesseract failed: {out.stderr.strip()[:300]}")
    return out.stdout


def recognize(
    img: Image.Image,
    lang: str = "eng",
    offset: tuple[int, int] = (0, 0),
    upscale: float = 2.0,
    timeout: float = 30.0,
    psm: int = PSM,
    min_conf: float = 35.0,
) -> Lines:
    """OCR an image into lines with screen coordinates (``offset`` is the image's position on screen)."""
    tsv = _tesseract(_prepare(img, upscale), ["-l", lang, "--psm", str(psm), *SAUVOLA, "tsv"], timeout)
    if tsv is None:
        return Lines()  # callers treat OCR as best-effort
    return parse_tsv(tsv, scale=upscale or 1.0, offset=offset, min_conf=min_conf)


def _colourful(img: Image.Image) -> float:
    """The share of the picture in clear colour (boxes, banners, buttons), where white text often sits."""
    hsv = img.convert("RGB").convert("HSV").reduce(4)
    strong = ImageChops.multiply(
        hsv.getchannel("S").point(lambda v: 255 if v > 80 else 0),
        hsv.getchannel("V").point(lambda v: 255 if v > 80 else 0),
    )
    return strong.histogram()[255] / max(1, strong.width * strong.height)


def _has_colour(img: Image.Image) -> bool:
    """Enough clear colour for light text on it to be worth its own pass: a good share of the picture, or a few
    boxes' worth of it in a big picture (a coloured slide inside a white web page)."""
    share = _colourful(img)
    return share >= COLOURFUL or share * img.width * img.height >= 4_000  # (a selected row in a list: ~4,000 px)


def _overlaps(a, b) -> bool:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    return x1 > x0 and y1 > y0 and (x1 - x0) * (y1 - y0) > 0.3 * min(a.w * a.h, b.w * b.h)


def _sort_lines(lines: Lines) -> Lines:
    """Reading order: rows top to bottom (lines whose middles are within half a line height share a row), and in
    a row right to left when it is mostly Hebrew or Arabic, else left to right."""
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda ln: ln.y + ln.h / 2):
        mid, last = ln.y + ln.h / 2, rows[-1][-1] if rows else None
        if last is not None and abs(mid - (last.y + last.h / 2)) <= max(4, min(ln.h, last.h) / 2):
            rows[-1].append(ln)
        else:
            rows.append([ln])
    out = []
    for row in rows:
        rtl = sum(_is_rtl(ln.text) for ln in row) * 2 > len(row)
        out.extend(sorted(row, key=lambda ln: -ln.x if rtl else ln.x))
    lines[:] = out
    return lines


def _light_text(img: Image.Image, lang: str, upscale: float, found: Lines, timeout: float) -> list[Line]:
    """Lines of light text on colour (white on an orange box) that a normal pass misses: taking the darkest of
    the three channels makes a coloured background dark while white text stays white, and inverting that gives
    dark text on light. Its lines go where the first pass read nothing, or replace what it read with clearly less
    confidence (see _merge). On 24 photographed slides this raised word recall from 0.90 to 0.94."""
    r, g, b = img.convert("RGB").split()
    light = ImageOps.invert(ImageChops.darker(ImageChops.darker(r, g), b))
    if upscale != 1.0:
        light = light.resize((round(light.width * upscale), round(light.height * upscale)), Image.Resampling.LANCZOS)
    tsv = _tesseract(light, ["-l", lang, "--psm", str(PSM), *SAUVOLA, "tsv"], timeout)
    return [ln for ln in parse_tsv(tsv or "", scale=upscale, min_conf=60) if sum(ch.isalnum() for ch in ln.text) >= 3]


COLOURFUL = 0.08  # the share of strong colour above which light text on colour gets its own pass

_cache: OrderedDict[tuple, Lines] = OrderedDict()


def _merge(lines: Lines, more: list[Line], better: bool = False, short_ok: bool = False) -> Lines:
    """`lines` and the lines of another pass: those where nothing was read yet, and with better=True those that
    read the same place with clearly more confidence. short_ok lets in sure two-letter words ("OK")."""
    out = list(lines)
    for ln in more:
        alnum = sum(ch.isalnum() for ch in ln.text)
        if alnum < 2 or (alnum == 2 and not (short_ok and ln.conf >= 85)):
            continue
        clash = [o for o in out if any(_overlaps(w, v) for w in ln.words for v in o.words)]
        if not clash:
            out.append(ln)
        elif better:  # confidence weighted by length: a sure line beats a smudge, even one with a sure digit in it
            size = sum(len(o.text) for o in clash)
            if ln.conf > sum(o.conf * len(o.text) for o in clash) / size + 10 and len(ln.text) >= 0.7 * size:
                out = [o for o in out if not any(o is c for c in clash)] + [ln]
    merged = _sort_lines(Lines(out))
    merged.conf, merged.words = lines.conf, lines.words
    return merged


def _read_lines(img: Image.Image, langs: list[str], timeout: float, ui: bool = False) -> Lines:
    """All the passes that read a picture well (measured on 24 photographed slides: word recall 0.94):
    - 2x, for normal and small text; if English reads poorly, the script is detected and read again;
    - 1x, for large text (titles), which Tesseract misses when it is too big: its lines replace weaker ones;
    - light text on colour, when there is colour (a selected row too);
    - with ui=True (a whole window without accessibility: a Windows program), a sparse pass that finds lone
      words a layout pass skips, such as the OK, Cancel and Apply of a dialog."""
    lang = "+".join(langs)
    lines = recognize(img, lang=lang, timeout=timeout)
    if langs == ["eng"] and lines.words >= 5 and lines.conf < DOUBTFUL:  # probably another language
        other, _ = ensure(detect(img))
        if other != ["eng"]:
            again = recognize(img, lang="+".join(other), timeout=timeout)
            if again.conf > lines.conf:
                lines, lang = again, "+".join(other)
    lines = _merge(lines, recognize(img, lang=lang, upscale=1.0, timeout=timeout, min_conf=60), better=True)
    if _has_colour(img):
        lines = _merge(lines, _light_text(img, lang, 2.0, lines, timeout), better=True)
    if ui:
        lines = _merge(lines, list(recognize(img, lang=lang, timeout=timeout, psm=11, min_conf=60)), short_ok=True)
    return lines


def read(
    img: Image.Image, langs: list[str], offset: tuple[int, int] = (0, 0), timeout: float = 45.0, ui: bool = False
) -> Lines:
    """The text of a part of the screen that shows a page, a slide or a picture, line by line in reading order
    (see _read_lines). The same picture always gives the same answer, from a cache, so looking again costs
    nothing."""
    key = (hashlib.blake2b(img.tobytes(), digest_size=16).hexdigest(), img.size, "+".join(langs), ui)
    lines = _cache.get(key)
    if lines is None:
        lines = _read_lines(img, langs, timeout, ui)
        _cache[key] = lines
        while len(_cache) > 64:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    ox, oy = offset
    out = Lines(
        replace(ln, x=ln.x + ox, y=ln.y + oy, words=[replace(w, x=w.x + ox, y=w.y + oy) for w in ln.words])
        for ln in lines
    )
    out.conf, out.words = lines.conf, lines.words
    return out


def page_text(img: Image.Image, langs: list[str], timeout: float = 120.0) -> tuple[str, list[str]]:
    """The text of a page (a scan, a photo, a screenshot file) and the languages it was read in. Screenshots and
    photos get every pass of _read_lines; scans (big already) are read once, keeping their paragraphs. If English
    reads poorly, the script is detected and the page read again in its language."""
    if max(img.size) <= 1600:
        lines = _read_lines(img, langs, timeout)
        return _lines_text(lines), langs if langs != ["eng"] else _langs_of(lines, langs)
    gray = _prepare(img, 1.0)

    def run(lg: list[str]) -> str:
        return _tesseract(gray, ["-l", "+".join(lg), "--psm", str(PSM), *SAUVOLA, "tsv"], timeout) or ""

    tsv = run(langs)
    if langs == ["eng"]:
        first = parse_tsv(tsv)
        if first.words >= 5 and first.conf < DOUBTFUL:
            other, _ = ensure(detect(img))
            if other != ["eng"]:
                again = run(other)
                if parse_tsv(again).conf > first.conf:
                    tsv, langs = again, other
    if _has_colour(img):
        found = parse_tsv(tsv)
        extra = _light_text(img, "+".join(langs), 1.0, found, timeout)
        if extra:
            return _lines_text(_merge(found, extra, better=True)), langs
    return tsv_text(tsv), langs


def _langs_of(lines: Lines, langs: list[str]) -> list[str]:
    """The languages a picture turned out to be in: English, unless its text is in another script."""
    found = langs_for(" ".join(ln.text for ln in lines))
    return found if found != ["eng"] else langs


def _lines_text(lines: Lines) -> str:
    """Lines as text, with a blank line where a line starts well below the one before (a new paragraph)."""
    out: list[str] = []
    prev = None
    for ln in lines:
        if prev is not None and ln.y - (prev.y + prev.h) > 0.8 * prev.h:
            out.append("")
        out.append(ln.text)
        prev = ln
    return "\n".join(out)


def tsv_text(tsv: str) -> str:
    """Tesseract TSV as plain text: words in reading order, a line per line, a blank line between paragraphs."""
    paras: list[list[str]] = []
    lines: dict[tuple, list[str]] = {}
    last_par = None
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        word = cols[11].translate(_BIDI_MARKS).strip()
        if not word:
            continue
        par, line = (cols[1], cols[2], cols[3]), (cols[1], cols[2], cols[3], cols[4])
        if par != last_par:
            paras.append([])
            last_par = par
        if line not in lines:
            lines[line] = []
            paras[-1].append(line)
        lines[line].append(word)
    return "\n\n".join("\n".join(" ".join(lines[ln]) for ln in para) for para in paras)
