"""On-screen text recognition with Tesseract (fallback when an app has no accessibility tree)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from PIL import Image, ImageOps


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


def parse_tsv(tsv: str, scale: float = 1.0, offset: tuple[int, int] = (0, 0), min_conf: float = 35.0) -> list[Line]:
    """Group Tesseract TSV word rows into lines, mapping coordinates back to the screen."""
    ox, oy = offset
    groups: dict[tuple, list[Word]] = {}
    order: list[tuple] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
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
    lines: list[Line] = []
    for key in order:
        words = groups[key]
        # Split a "line" where words are far apart (UI labels side by side).
        chunk: list[Word] = []
        for w in words:
            if chunk and w.x - (chunk[-1].x + chunk[-1].w) > max(18, 2.2 * w.h):
                lines.append(_line(chunk))
                chunk = []
            chunk.append(w)
        if chunk:
            lines.append(_line(chunk))
    lines.sort(key=lambda ln: (ln.y // 8, ln.x))
    return lines


def _line(words: list[Word]) -> Line:
    x0 = min(w.x for w in words)
    y0 = min(w.y for w in words)
    x1 = max(w.x + w.w for w in words)
    y1 = max(w.y + w.h for w in words)
    conf = sum(w.conf for w in words) / len(words)
    return Line(" ".join(w.text for w in words), x0, y0, x1 - x0, y1 - y0, conf, list(words))


def recognize(
    img: Image.Image, lang: str = "eng", offset: tuple[int, int] = (0, 0), upscale: float = 2.0, timeout: float = 30.0
) -> list[Line]:
    """OCR an image. ``offset`` is the image's position on screen."""
    if not available():
        raise RuntimeError("tesseract is not installed in this desktop")
    gray = ImageOps.grayscale(img)
    if upscale and upscale != 1.0:
        gray = gray.resize((round(gray.width * upscale), round(gray.height * upscale)), Image.Resampling.LANCZOS)
    # Dark UIs: tesseract prefers dark text on a light background.
    if sum(gray.reduce(8).getdata()) / max(1, (gray.width // 8) * (gray.height // 8)) < 110:
        gray = ImageOps.invert(gray)
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        gray.save(path, "PNG")
        out = subprocess.run(
            ["tesseract", path, "stdout", "-l", lang, "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if out.returncode != 0:
        raise RuntimeError(f"tesseract failed: {out.stderr.strip()[:300]}")
    return parse_tsv(out.stdout, scale=upscale or 1.0, offset=offset)
