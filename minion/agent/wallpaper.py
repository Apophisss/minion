"""A generated wallpaper, so desktops look good in screenshots and demos."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make(path: str, width: int, height: int, label: str = "") -> str:
    w, h = max(64, width), max(64, height)
    grad = Image.linear_gradient("L").rotate(-32, expand=True).resize((w, h))
    dark = Image.new("RGB", (w, h), (10, 14, 32))
    deep = Image.new("RGB", (w, h), (40, 33, 110))
    img = Image.composite(deep, dark, grad)

    # Two soft glows.
    for cx, cy, r, color, strength in (
        (0.78, 0.28, 0.55, (99, 102, 241), 0.55),
        (0.12, 0.92, 0.45, (14, 165, 233), 0.35),
    ):
        size = int(max(w, h) * r)
        mask = ImageOps.invert(Image.radial_gradient("L").resize((size * 2, size * 2)))
        mask = mask.point(lambda v, s=strength: int(v * s))
        glow = Image.new("RGB", mask.size, color)
        img.paste(glow, (int(w * cx) - size, int(h * cy) - size), mask)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    if label:
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        font = _font(max(14, h // 40))
        tw = d.textlength(label, font=font)
        d.text((w - tw - 28, h - max(14, h // 40) - 52), label, font=font, fill=(255, 255, 255, 70))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    img.save(path, "PNG")
    return path
