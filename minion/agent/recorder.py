"""Flight recorder: every action with a thumbnail, exportable as an HTML timeline or GIF."""

from __future__ import annotations

import base64
import html
import io
import threading
import time
from collections import deque
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont


@dataclass
class Step:
    t: float
    kind: str
    detail: str
    jpeg: bytes | None = None
    ok: bool = True


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


class Recorder:
    def __init__(self, max_steps: int = 400, enabled: bool = True, thumb_width: int = 800):
        self.enabled = enabled
        self.steps: deque[Step] = deque(maxlen=max_steps)
        self.thumb_width = thumb_width
        self.started = time.time()
        self.lock = threading.Lock()

    def add(self, kind: str, detail: str, frame: Image.Image | None = None, ok: bool = True) -> None:
        if not self.enabled:
            return
        jpeg = None
        if frame is not None:
            img = frame
            if img.width > self.thumb_width:
                h = round(img.height * self.thumb_width / img.width)
                img = img.resize((self.thumb_width, h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=62, optimize=True)
            jpeg = buf.getvalue()
        with self.lock:
            self.steps.append(Step(time.time(), kind, detail, jpeg, ok))

    def clear(self) -> None:
        with self.lock:
            self.steps.clear()
            self.started = time.time()

    def info(self) -> dict:
        with self.lock:
            steps = list(self.steps)
        return {
            "enabled": self.enabled,
            "steps": len(steps),
            "frames": sum(1 for s in steps if s.jpeg),
            "since": steps[0].t if steps else None,
            "last": steps[-1].t if steps else None,
        }

    # -- exports ------------------------------------------------------
    def export_html(self, title: str = "Minion session") -> str:
        with self.lock:
            steps = list(self.steps)
        t0 = steps[0].t if steps else time.time()
        cards = []
        for i, s in enumerate(steps, 1):
            img = ""
            if s.jpeg:
                b64 = base64.b64encode(s.jpeg).decode()
                img = f'<img loading="lazy" src="data:image/jpeg;base64,{b64}" alt="step {i}">'
            cls = "step" if s.ok else "step err"
            cards.append(
                f'<div class="{cls}"><div class="meta"><span class="n">#{i}</span>'
                f'<span class="t">+{s.t - t0:6.1f}s</span><span class="k">{html.escape(s.kind)}</span></div>'
                f'<div class="d">{html.escape(s.detail)}</div>{img}</div>'
            )
        dur = (steps[-1].t - t0) if steps else 0
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{margin:0;background:#0b1020;color:#e5e7eb;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{padding:28px 32px;background:linear-gradient(135deg,#1e1b4b,#312e81);}}
h1{{margin:0 0 6px;font-size:22px}} .sub{{color:#c7d2fe}}
main{{max-width:980px;margin:0 auto;padding:24px}}
.step{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px 16px;margin:0 0 16px}}
.step.err{{border-color:#b91c1c}}
.meta{{display:flex;gap:12px;color:#9ca3af;font-size:12px;margin-bottom:6px}}
.k{{color:#a5b4fc;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.d{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word}}
img{{display:block;width:100%;margin-top:10px;border-radius:8px;border:1px solid #1f2937}}
</style></head><body><header><h1>{html.escape(title)}</h1>
<div class="sub">{len(steps)} steps · {dur:.0f}s · recorded by Minion</div></header>
<main>{''.join(cards) or '<p>No steps recorded yet.</p>'}</main></body></html>"""

    def export_gif(self, width: int = 720, frame_ms: int = 900) -> bytes:
        with self.lock:
            steps = [s for s in self.steps if s.jpeg]
        if not steps:
            raise ValueError("no frames recorded yet")
        font = _font(15)
        frames = []
        for s in steps:
            img = Image.open(io.BytesIO(s.jpeg)).convert("RGB")
            h = round(img.height * width / img.width)
            img = img.resize((width, h), Image.Resampling.LANCZOS)
            bar = 30
            canvas = Image.new("RGB", (width, h + bar), (17, 24, 39))
            canvas.paste(img, (0, 0))
            d = ImageDraw.Draw(canvas)
            caption = f"{s.kind}: {s.detail}"
            if len(caption) > 90:
                caption = caption[:89] + "…"
            d.text((10, h + 7), caption, fill=(229, 231, 235), font=font)
            frames.append(canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
        buf = io.BytesIO()
        frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:],
                       duration=frame_ms, loop=0, optimize=True)
        return buf.getvalue()
