"""Render docs/assets/hero.png (README banner / social preview) from real desktop screenshots.

    python scripts/make_hero.py office.png research.png dev.png
"""

import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1280, 640
FONT_DIR = "/usr/share/fonts/opentype/inter/"


def font(name, size):
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except OSError:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)


def background():
    horiz = Image.linear_gradient("L").rotate(90).transpose(Image.Transpose.FLIP_LEFT_RIGHT).resize((W, H))
    grad = Image.blend(horiz, Image.linear_gradient("L").resize((W, H)), 0.35)
    img = Image.composite(Image.new("RGB", (W, H), (34, 29, 98)), Image.new("RGB", (W, H), (7, 10, 24)), grad)
    for cx, cy, r, color, strength in ((0.82, 0.2, 0.6, (99, 102, 241), 0.6), (0.05, 1.0, 0.5, (14, 165, 233), 0.35)):
        size = int(max(W, H) * r)
        mask = ImageOps.invert(Image.radial_gradient("L").resize((size * 2, size * 2)))
        mask = mask.point(lambda v, s=strength: int(max(0, v - 96) * 1.6 * s))  # 0 well before the edge
        img.paste(Image.new("RGB", mask.size, color), (int(W * cx) - size, int(H * cy) - size), mask)
    return img


def rounded(img, radius=14):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius, fill=255)
    out = Image.new("RGBA", img.size)
    out.paste(img, (0, 0), mask)
    return out


def card(path, width, angle):
    shot = Image.open(path).convert("RGB")
    shot = shot.resize((width, round(shot.height * width / shot.width)), Image.Resampling.LANCZOS)
    framed = Image.new("RGB", (shot.width + 8, shot.height + 8), (49, 46, 129))
    framed.paste(shot, (4, 4))
    c = rounded(framed, 16)
    pad = 40
    shadow = Image.new("RGBA", (c.width + pad * 2, c.height + pad * 2), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 170), (pad, pad + 14, pad + c.width, pad + c.height + 14), c.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    shadow.alpha_composite(c, (pad, pad))
    return shadow.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def logo(size):
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4 * s, 8 * s, 60 * s, 50 * s], 10 * s, fill=(99, 102, 241))
    d.rounded_rectangle([9 * s, 13 * s, 55 * s, 45 * s], 6 * s, fill=(11, 16, 32))
    arrow = [(27, 20), (27, 39), (32, 34.5), (35.5, 42), (39, 40.4), (35.6, 33), (42, 33)]
    d.polygon([(x * s, y * s) for x, y in arrow], fill="white")
    d.rounded_rectangle([24 * s, 52 * s, 40 * s, 56 * s], 2 * s, fill=(129, 140, 248))
    return img


def main(office, research, dev, out="docs/assets/hero.png"):
    img = background().convert("RGBA")
    for path, width, angle, x, y in ((dev, 470, -6, 600, 318), (research, 520, 4, 590, 18), (office, 520, -3, 800, 200)):
        c = card(path, width, angle)
        img.alpha_composite(c, (x, y))
    d = ImageDraw.Draw(img)
    img.alpha_composite(logo(84), (70, 150))
    d.text((170, 152), "minion", font=font("Inter-Bold.otf", 74), fill="white")
    d.text((72, 262), "Instant desktops", font=font("Inter-SemiBold.otf", 46), fill=(224, 231, 255))
    d.text((72, 316), "for AI agents.", font=font("Inter-SemiBold.otf", 46), fill=(165, 180, 252))
    body = font("Inter-Regular.otf", 21)
    lines = ["Office · Dev · Research · Browser · Data", "Ready in ~1.5 s · 0% CPU when frozen", "MCP · CLI · Python · HTTP · Claude computer use"]
    for i, line in enumerate(lines):
        d.text((74, 400 + i * 34), line, font=body, fill=(199, 210, 254))
    img.convert("RGB").save(out, optimize=True)
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
