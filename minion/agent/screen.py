"""Screen capture, encoding, change detection and "settle" waiting."""

from __future__ import annotations

import hashlib
import io
import time

from PIL import Image, ImageChops, ImageDraw, ImageGrab

# A classic arrow pointer, drawn on screenshots (Xvfb never renders the cursor).
_ARROW = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]


class Screen:
    def __init__(self, display: str):
        self.display = display

    def grab(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """Capture the screen (or an x, y, w, h region) as an RGB image."""
        img = ImageGrab.grab(xdisplay=self.display)
        if img.mode != "RGB":
            img = img.convert("RGB")
        if region:
            x, y, w, h = region
            img = img.crop((x, y, x + w, y + h))
        return img

    def size(self) -> tuple[int, int]:
        return self.grab().size


def draw_cursor(img: Image.Image, x: int, y: int, offset: tuple[int, int] = (0, 0),
                scale: float = 1.0) -> None:
    ox, oy = offset
    px, py = (x - ox) * scale, (y - oy) * scale
    if px < -20 or py < -20 or px > img.width or py > img.height:
        return
    s = max(0.6, min(1.5, scale * 1.15))
    pts = [(px + ax * s, py + ay * s) for ax, ay in _ARROW]
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))
    d.line(pts + [pts[0]], fill=(0, 0, 0), width=1)


def encode(img: Image.Image, fmt: str = "png", quality: int = 80) -> bytes:
    fmt = fmt.lower()
    buf = io.BytesIO()
    if fmt in ("jpg", "jpeg"):
        img.convert("RGB").save(buf, "JPEG", quality=int(quality), optimize=True)
    elif fmt == "webp":
        img.save(buf, "WEBP", quality=int(quality), method=4)
    elif fmt == "png":
        img.save(buf, "PNG", optimize=False, compress_level=6)
    else:
        raise ValueError(f"unsupported image format {fmt!r} (png, jpeg or webp)")
    return buf.getvalue()


def mime(fmt: str) -> str:
    fmt = fmt.lower()
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(fmt, "image/png")


def fit(img: Image.Image, max_width: int | None = None, max_height: int | None = None,
        max_pixels: int | None = None, scale: float | None = None) -> tuple[Image.Image, float]:
    """Downscale (never upscale) to fit the limits. Returns (image, scale factor)."""
    w, h = img.size
    f = 1.0
    if scale:
        f = min(f, float(scale))
    if max_width:
        f = min(f, max_width / w)
    if max_height:
        f = min(f, max_height / h)
    if max_pixels:
        f = min(f, (max_pixels / (w * h)) ** 0.5)
    if f >= 0.999:
        return img, 1.0
    nw, nh = max(1, round(w * f)), max(1, round(h * f))
    return img.resize((nw, nh), Image.Resampling.LANCZOS), nw / w


def thumb(img: Image.Image) -> Image.Image:
    """Small grayscale fingerprint used for change detection."""
    return img.convert("L").reduce(4)


def fingerprint(img: Image.Image) -> str:
    return hashlib.blake2b(thumb(img).tobytes(), digest_size=12).hexdigest()


def diff(a: Image.Image, b: Image.Image, threshold: int = 24) -> tuple[float, tuple | None]:
    """Compare two thumbs. Returns (changed fraction, bbox in thumb pixels or None)."""
    if a.size != b.size:
        return 1.0, (0, 0, b.width, b.height)
    d = ImageChops.difference(a, b).point(lambda v: 255 if v > threshold else 0)
    bbox = d.getbbox()
    if not bbox:
        return 0.0, None
    hist = d.histogram()
    changed = hist[255]
    return changed / (a.width * a.height), bbox


def describe_change(frac: float, bbox: tuple | None, factor: int = 4) -> dict:
    if not bbox or frac == 0:
        return {"changed": False, "fraction": 0.0}
    x0, y0, x1, y1 = bbox
    return {
        "changed": True,
        "fraction": round(frac, 4),
        "region": [x0 * factor, y0 * factor, (x1 - x0) * factor, (y1 - y0) * factor],
    }


def settle(screen: Screen, timeout: float = 3.0, quiet: float = 0.3, interval: float = 0.07,
           min_wait: float = 0.08, tolerance: float = 0.0004) -> tuple[bool, float, Image.Image]:
    """Wait until the screen stops changing.

    Returns (settled, elapsed seconds, last full frame). Tiny changes below
    ``tolerance`` (a blinking caret, a spinner) do not count as activity.
    """
    start = time.monotonic()
    time.sleep(min_wait)
    frame = screen.grab()
    prev = thumb(frame)
    stable_since = time.monotonic()
    while True:
        now = time.monotonic()
        if now - stable_since >= quiet:
            return True, now - start, frame
        if now - start >= timeout:
            return False, now - start, frame
        time.sleep(interval)
        frame = screen.grab()
        cur = thumb(frame)
        frac, _ = diff(prev, cur)
        if frac > tolerance:
            stable_since = time.monotonic()
        prev = cur
