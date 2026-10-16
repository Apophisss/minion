"""Record docs/assets/demo.mp4: an agent plans a weekend in Lisbon with a browser, a spreadsheet and a document.

Every step is one Minion tool call, made through the same toolkit an MCP client uses. The budget figures are part of
the task; the facts and the total the agent types are checked against what earlier calls returned. ffmpeg records
the desktop's screen from inside it. The video shows each call next to the desktop, with the text the agent got back
and what the same steps would cost in screenshots (priced as in docs/benchmarks.md).

    python scripts/demo_video.py              # record a new run, then make docs/assets/demo.mp4
    python scripts/demo_video.py --compose    # make the video again from the last run (build/demo/)

Needs Docker, Pillow and ffmpeg on the host (`pip install imageio-ffmpeg` is enough). No model is called.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from bench_tasks import CLAUDE_IMAGE, tokens  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from minion.desktop import Desktop  # noqa: E402
from minion.tools import Toolkit  # noqa: E402

DESKTOP = "demo-video"
WORK = ROOT / "build" / "demo"
OUT = ROOT / "docs" / "assets" / "demo.mp4"
POSTER = ROOT / "docs" / "assets" / "demo-poster.png"  # with a play button, for links to the video
THUMB = ROOT / "docs" / "assets" / "demo-thumbnail.jpg"  # 1280x720, for YouTube
FPS = 25
TITLE, LAST, END = 4.2, 1.5, 6.5  # seconds on the title card, on the last result, and on the end card
W, H = 1280, 800  # the desktop
VW, VH = 1920, 1080  # the video
DX, DY = 40, 116  # where the desktop sits in the video
PX, PW = DX + W + 32, VW - (DX + W + 32) - 40  # the side panel

BG, CARD, LINE = (7, 10, 24), (13, 18, 38), (40, 48, 86)
TEXT, MUTED, ACCENT = (232, 234, 246), (142, 149, 181), (165, 180, 252)
INDIGO, VIOLET, PINK, GREEN = (99, 102, 241), (124, 58, 237), (244, 114, 182), (74, 222, 128)

# What the agent does: (tool, arguments, caption, seconds to pause after it, screenshots a pixel-based agent needs
# for the same step: one per GUI action, as in docs/benchmarks.md). "{...}" in a text is filled in from what
# earlier calls returned.
SCENES = [
    (
        "Research on the web",
        [
            (
                "open",
                {"target": "https://www.wikipedia.org"},
                "The agent opens Wikipedia in its desktop's browser.",
                1.6,
                2,
            ),
            (
                "act",
                {
                    "actions": [
                        {"action": "fill", "target": "Search Wikipedia", "text": "Lisbon"},
                        {"action": "key", "keys": "Return"},
                        {"action": "wait_for", "text": "Portugal"},
                    ]
                },
                "It finds the search box by its label, types, presses Return and waits for the article.",
                1.6,
                3,
            ),
            ("see", {}, "Then it reads the page as text: the facts, and every control with an @id.", 3.6, 1),
        ],
    ),
    (
        "A budget in a spreadsheet",
        [
            ("open", {"target": "calc"}, "Next, a spreadsheet.", 1.2, 1),
            (
                "act",
                {
                    "actions": [
                        {
                            "action": "type",
                            "text": "Budget\tEUR\nFlights\t180\nHotel\t270\nFood\t120\nMuseums\t45\nTransport\t30\n"
                            "Total\t=SUM(B2:B6)\n",
                        }
                    ]
                },
                "It types the budget. Tab moves right, Return goes down, and the total is a formula.",
                1.6,
                1,
            ),
            (
                "act",
                {
                    "actions": [
                        {"action": "drag", "from": "A1", "to": "B6"},
                        {"action": "menu", "item": "Insert > Chart"},
                        {"action": "click", "target": "Finish"},
                        {"action": "key", "keys": "Escape Escape"},
                    ]
                },
                "It selects the cells, picks Insert › Chart… from the menu and clicks Finish.",
                2.2,
                5,
            ),
            (
                "act",
                {
                    "actions": [
                        {"action": "key", "keys": "ctrl+s"},
                        {"action": "path", "path": "~/Documents/lisbon-budget.xlsx", "overwrite": True},
                    ]
                },
                "It saves an Excel file by typing the full path into the Save dialog.",
                1.6,
                3,
            ),
            (
                "files",
                {"action": "read", "path": "~/Documents/lisbon-budget.xlsx"},
                "Then it checks the file as text, values and formulas, without opening it.",
                3.0,
                1,
            ),
        ],
    ),
    (
        "A plan as PDF",
        [
            ("open", {"target": "writer"}, "Last, a document.", 1.2, 1),
            (
                "act",
                {
                    "actions": [
                        {"action": "key", "keys": "ctrl+1"},
                        {
                            "action": "type",
                            "text": "Lisbon weekend\n{intro}\n\nBudget: {total} EUR (flights 180, hotel 270, food 120, "
                            "museums 45, transport 30).\n\nDay 1: Alfama and the Tagus riverfront.\nDay 2: Belém Tower."
                            "\nDay 3: Rua Augusta Arch and Lisbon Cathedral.\n",
                        },
                    ]
                },
                "It writes the plan from what it read on the web, with the total from the spreadsheet.",
                2.0,
                2,
            ),
            (
                "act",
                {
                    "actions": [
                        {"action": "menu", "item": "File > Export As > Export Directly as PDF"},
                        {"action": "path", "path": "~/Documents/lisbon-weekend.pdf", "overwrite": True},
                    ]
                },
                "It exports a PDF with the menu and the file dialog.",
                1.6,
                5,
            ),
            (
                "files",
                {"action": "read", "path": "~/Documents/lisbon-weekend.pdf"},
                "And it reads the PDF back to check it. Done.",
                3.6,
                2,
            ),
        ],
    ),
]
# Facts the plan uses; each must be in what `see` returned from the article.
FACTS = [
    "capital",
    "oldest cities in the world",
    "Alfama",
    "Tagus",
    "Belém Tower",
    "Rua Augusta Arch",
    "Lisbon Cathedral",
]
SHOW = {"see": r"^Screen|^\s+\[\d+\]|paragraph"}  # the lines of a long result to show (the rest is elided)


# -- recording --------------------------------------------------------------------------------------------------


def record() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tk = Toolkit()
    tk.call("desktop", {"action": "remove", "desktop": DESKTOP})
    made = tk.call("desktop", {"action": "create", "profile": "office", "name": DESKTOP})
    if made.is_error:
        raise SystemExit(made.text)
    d = Desktop.attach(DESKTOP)
    try:
        res = d.run("command -v ffmpeg >/dev/null || minion-install ffmpeg", timeout=900, record=False)
        if not res.ok:
            raise SystemExit(f"could not install ffmpeg in the desktop: {res.stderr[-500:]}")
        d.run(
            f"ffmpeg -nostdin -y -f x11grab -framerate {FPS} -video_size {W}x{H} -i $DISPLAY -c:v libx264 "
            "-preset ultrafast -crf 12 -pix_fmt yuv420p /tmp/demo-raw.mp4 2>/tmp/demo-ffmpeg.log",
            background=True,
            record=False,
        )
        time.sleep(2.0)
        events, found = [], {}
        for scene, (title, steps) in enumerate(SCENES):
            for tool, args, caption, hold, shots in steps:
                args = json.loads(json.dumps(args))
                for action in args.get("actions", []):
                    if "{" in action.get("text", ""):
                        action["text"] = action["text"].format(**found)
                t0 = time.time()
                res = tk.call(tool, {**args, "desktop": DESKTOP})
                t1 = time.time()
                print(f"{t1 - t0:5.1f}s {tool:<5} {'ERROR ' if res.is_error else ''}{res.text[:90]!r}")
                if res.is_error:
                    raise SystemExit(f"{tool} failed:\n{res.text}")
                learn(tool, args, res.text, found)
                events.append(
                    {
                        "scene": scene,
                        "title": title,
                        "tool": tool,
                        "args": args,
                        "caption": caption,
                        "shots": shots,
                        "t0": t0,
                        "t1": t1,
                        "hold": hold,
                        "text": res.text,
                        "tokens": tokens(res.text),
                    }
                )
                time.sleep(hold)
        d.run(
            "pkill -INT -x ffmpeg; for i in $(seq 50); do pgrep -x ffmpeg >/dev/null || break; sleep 0.2; done",
            record=False,
        )
        d.download("/tmp/demo-raw.mp4", WORK / "raw.mp4")
        log = d.run("cat /tmp/demo-ffmpeg.log", record=False).stdout
        m = re.search(r"x11grab.*?start: ([\d.]+)", log, re.S)
        if not m:
            raise SystemExit(f"no start time in the ffmpeg log:\n{log[-2000:]}")
        (WORK / "run.json").write_text(json.dumps({"start": float(m.group(1)), "events": events}, indent=1))
    finally:
        if "--keep" not in sys.argv:
            tk.call("desktop", {"action": "remove", "desktop": DESKTOP})


def learn(tool: str, args: dict, text: str, found: dict) -> None:
    """Take what later steps type from what the agent just read."""
    if tool == "see" and "Wikipedia" in text:
        missing = [f for f in FACTS if f not in text]
        if missing:
            raise SystemExit(f"the article no longer says: {missing}")
        found["intro"] = "Lisbon is the capital of Portugal and one of the oldest cities in the world."
    if tool == "files" and args["path"].endswith(".xlsx"):
        m = re.search(r"B7: (\d+)", text)
        if not m:
            raise SystemExit(f"no total in the spreadsheet:\n{text}")
        found["total"] = m.group(1)


# -- the video --------------------------------------------------------------------------------------------------


def font(size: int, weight: str = "Regular", mono: bool = False):
    paths = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
        ]
        if mono
        else [
            f"/usr/share/fonts/opentype/inter/Inter-{weight}.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if weight in ("Bold", "SemiBold", "ExtraBold")
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def gradient(w: int, h: int, colors=((165, 180, 252), (196, 181, 253), (249, 168, 212))) -> Image.Image:
    img = Image.new("RGB", (w, 1))
    for x in range(w):
        f = x / max(1, w - 1) * (len(colors) - 1)
        i = min(int(f), len(colors) - 2)
        a, b, t = colors[i], colors[i + 1], f - i
        img.putpixel((x, 0), tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    return img.resize((w, h))


def gradient_text(img: Image.Image, xy, text: str, fnt, anchor="la") -> None:
    mask = Image.new("L", img.size)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255, anchor=anchor)
    box = mask.getbbox()
    if box:
        img.paste(gradient(box[2] - box[0], box[3] - box[1]), box[:2], mask.crop(box))


def diagonal(size: int, colors) -> Image.Image:
    """A square gradient from the top-left corner to the bottom-right one."""
    strip = gradient(2 * size - 1, 1, colors)
    img = Image.new("RGB", (size, size))
    img.putdata([strip.getpixel((x + y, 0)) for y in range(size) for x in range(size)])
    return img


def logo(size: int) -> Image.Image:
    """The Minion logo (docs/assets/logo.svg), drawn at 4x and scaled down."""
    s = size * 4 / 64
    big = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    mask = Image.new("L", big.size)
    ImageDraw.Draw(mask).rounded_rectangle([4 * s, 8 * s, 60 * s, 50 * s], 10 * s, fill=255)
    big.paste(diagonal(big.width, ((129, 140, 248), (99, 102, 241), (124, 58, 237))), (0, 0), mask)
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([9 * s, 13 * s, 55 * s, 45 * s], 6 * s, fill=(14, 18, 34))
    cursor = [(27, 20), (27, 39), (32, 34.5), (35.5, 42), (39, 40.4), (35.6, 33), (42, 33)]
    d.polygon([(x * s, y * s) for x, y in cursor], fill="white")
    spark = [(47, 18.5), (48.4, 21.6), (51.5, 23), (48.4, 24.4), (47, 27.5), (45.6, 24.4), (42.5, 23), (45.6, 21.6)]
    d.polygon([(x * s, y * s) for x, y in spark], fill=ACCENT)
    d.rounded_rectangle([24 * s, 52 * s, 40 * s, 56 * s], 2 * s, fill=(85, 88, 200))
    return big.resize((size, size), Image.LANCZOS)


def wrap(text: str, fnt, width: int) -> list[str]:
    words, lines = text.split(), [""]
    for w in words:
        trial = f"{lines[-1]} {w}".strip()
        if fnt.getlength(trial) <= width or not lines[-1]:
            lines[-1] = trial
        else:
            lines.append(w)
    return lines


def fit(text: str, fnt, width: int, rows: int = 2) -> list[str]:
    """A line as at most `rows` rows that fit `width`, broken at a space where possible; the last row is cut."""
    out: list[str] = []
    while text:
        if fnt.getlength(text) <= width:
            return out + [text]
        cut = len(text)
        while cut > 1 and fnt.getlength(text[:cut]) > width:
            cut -= 1
        if len(out) == rows - 1:
            return out + [text[: cut - 1] + "…"]
        space = text.rfind(" ", 0, cut)
        cut = space if space > cut // 2 else cut
        out.append(text[:cut])
        text = "  " + text[cut:].lstrip()
    return out


def call_lines(tool: str, args: dict) -> list[str]:
    """A call as the compact one-line steps an agent can also send (`act ["fill ...", "key Return"]`)."""

    def q(s: str, n: int = 44) -> str:
        s = s.replace("\t", "\\t").replace("\n", "\\n")
        return f'"{s[:n].rstrip(chr(92))}…"' if len(s) > n + 1 else f'"{s}"'

    if tool == "open":
        return [args["target"]]
    if tool == "see":
        return ["(the whole screen)"]
    if tool == "files":
        return [f"{args['action']} {args['path']}"]
    out = []
    for a in args["actions"]:
        kind = a["action"]
        if kind == "fill":
            out.append(f"fill {q(a['target'])} {q(a['text'])}")
        elif kind == "type":
            out.append(f"type {q(a['text'], 33)}")
        elif kind == "key":
            out.append(f"key {a['keys']}")
        elif kind == "wait_for":
            out.append(f"wait_for {q(a['text'])}")
        elif kind == "drag":
            out.append(f"drag {a['from']} → {a['to']}")
        elif kind == "menu":
            out.append(f"menu {a['item']}")
        elif kind == "click":
            out.append(f"click {a['target']}")
        elif kind == "path":
            out.append(f"path {a['path']}")
        else:
            out.append(kind)
    return out


def result_lines(e: dict, cols: int, rows: int) -> list[str]:
    lines = e["text"].splitlines()
    pattern = SHOW.get(e["tool"])
    if pattern and len(lines) > rows:
        keep, last = [], -1
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                if last >= 0 and i > last + 1:
                    keep.append("…")
                keep.append(line)
                last = i
        lines = keep + ["…"]
    out = []
    for line in lines:
        indent = len(line) - len(line.lstrip())
        parts = textwrap.wrap(line, cols, subsequent_indent=" " * (indent + 2), drop_whitespace=False) or [""]
        out += parts[:3] if len(parts) <= 3 else parts[:2] + [parts[2][: cols - 1] + "…"]
    return out[: rows - 1] + ["…"] if len(out) > rows else out


class Painter:
    def __init__(self, events: list[dict]):
        self.events = events
        self.f = {
            "brand": font(34, "Bold"),
            "chip": font(22, "SemiBold"),
            "caption": font(34, "SemiBold"),
            "label": font(15, "Bold"),
            "call": font(19, mono=True),
            "result": font(15, mono=True),
            "meter": font(17, "Medium"),
            "meterb": font(17, "Bold"),
            "badge": font(24, "Bold"),
        }
        self.logo = logo(46)
        self.total_shots = sum(e["shots"] for e in events) * CLAUDE_IMAGE
        self.cache: dict = {}
        self.base = Image.new("RGB", (VW, VH), BG)
        d = ImageDraw.Draw(self.base)
        self.base.paste(self.logo, (DX, 30), self.logo)
        d.text((DX + 58, 52), "minion", font=self.f["brand"], fill=TEXT, anchor="lm")
        d.rounded_rectangle([DX - 2, DY - 2, DX + W + 1, DY + H + 1], 10, outline=LINE, width=2)
        self.mask = Image.new("L", (W, H))
        ImageDraw.Draw(self.mask).rounded_rectangle([0, 0, W - 1, H - 1], 9, fill=255)

    def header(self, e: dict) -> Image.Image:
        key = ("header", e["scene"])
        if key not in self.cache:
            img = Image.new("RGB", (VW - 300, 80), BG)
            d = ImageDraw.Draw(img)
            label = f"{e['scene'] + 1} · {e['title']}"
            w = int(self.f["chip"].getlength(label)) + 36
            d.rounded_rectangle([0, 12, w, 60], 24, fill=CARD, outline=LINE, width=2)
            d.text((18, 36), label, font=self.f["chip"], fill=ACCENT, anchor="lm")
            self.cache[key] = img
        return self.cache[key]

    def caption(self, e: dict) -> Image.Image:
        key = ("caption", id(e))
        if key not in self.cache:
            img = Image.new("RGB", (VW, VH - (DY + H + 10)), BG)
            d = ImageDraw.Draw(img)
            lines = wrap(e["caption"], self.f["caption"], VW - 160)
            y = img.height // 2 - (len(lines) - 1) * 22
            for line in lines:
                d.text((VW // 2, y), line, font=self.f["caption"], fill=TEXT, anchor="mm")
                y += 44
            self.cache[key] = img
        return self.cache[key]

    def panel(self, i: int, done: bool) -> Image.Image:
        key = ("panel", i, done)
        if key in self.cache:
            return self.cache[key]
        e = self.events[i]
        img = Image.new("RGB", (PW, H), BG)
        d = ImageDraw.Draw(img)
        d.text((0, 4), f"THE AGENT CALLS  ·  {i + 1} OF {len(self.events)}", font=self.f["label"], fill=MUTED)
        lines = [row for line in call_lines(e["tool"], e["args"]) for row in fit(line, self.f["call"], PW - 40)]
        box_h = 62 + 30 * len(lines)
        d.rounded_rectangle([0, 30, PW - 1, 30 + box_h], 12, fill=CARD, outline=LINE, width=2)
        tool_w = int(self.f["call"].getlength(e["tool"])) + 20
        d.rounded_rectangle([16, 44, 16 + tool_w, 74], 8, fill=INDIGO)
        d.text((26, 59), e["tool"], font=self.f["call"], fill="white", anchor="lm")
        y = 88
        for line in lines:
            d.text((20, y), line, font=self.f["call"], fill=ACCENT)
            y += 30
        y = 30 + box_h + 26
        d.text((0, y), "MINION RETURNS", font=self.f["label"], fill=MUTED)
        if done:
            tok = f"{e['tokens']:,} tokens of text"
            d.text((PW, y), tok, font=self.f["label"], fill=GREEN, anchor="ra")
        top = y + 26
        bottom = H - 150
        d.rounded_rectangle([0, top, PW - 1, bottom], 12, fill=CARD, outline=LINE, width=2)
        if done:
            rows = (bottom - top - 24) // 20
            cols = int((PW - 32) // self.f["result"].getlength("m"))
            for n, line in enumerate(result_lines(e, cols, rows)):
                color = GREEN if line.startswith("✓") else TEXT if n < 1 else (200, 204, 228)
                d.text((16, top + 12 + 20 * n), line, font=self.f["result"], fill=color)
        else:
            d.text((16, top + 14), "working…", font=self.f["result"], fill=MUTED)
        # The meter: the text the agent has read so far, and what the same steps cost as screenshots.
        upto = self.events[: i + 1] if done else self.events[:i]
        mine = sum(x["tokens"] for x in upto)
        shots = sum(x["shots"] for x in upto) * CLAUDE_IMAGE
        y = H - 124
        for label, value, color in (
            ("Minion, so far", mine, INDIGO),
            ("Screenshots, same steps", shots, (100, 107, 147)),
        ):
            d.text((0, y), label, font=self.f["meter"], fill=MUTED)
            d.text((PW, y), f"{value:,} tokens", font=self.f["meterb"], fill=TEXT, anchor="ra")
            d.rounded_rectangle([0, y + 28, PW - 1, y + 40], 6, fill=CARD)
            if value:
                d.rounded_rectangle(
                    [0, y + 28, max(12, round((PW - 1) * value / self.total_shots)), y + 40], 6, fill=color
                )
            y += 62
        self.cache[key] = img
        return img

    def badge(self, speed: float) -> Image.Image:
        key = ("badge", speed)
        if key not in self.cache:
            label = f"{speed:g}× speed"
            img = Image.new("RGBA", (int(self.f["badge"].getlength(label)) + 44, 50), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, img.width - 1, 49], 25, fill=(*VIOLET, 235))
            d.text((img.width // 2, 25), label, font=self.f["badge"], fill="white", anchor="mm")
            self.cache[key] = img
        return self.cache[key]

    def frame(self, desk: Image.Image, i: int, done: bool, speed: float) -> Image.Image:
        e = self.events[i]
        img = self.base.copy()
        img.paste(self.header(e), (300, 16))
        img.paste(desk, (DX, DY), self.mask)
        img.paste(self.panel(i, done), (PX, DY))
        img.paste(self.caption(e), (0, DY + H + 10))
        if speed > 1:
            b = self.badge(speed)
            img.paste(b, (DX + W - b.width, 27), b)
        return img

    def title(self) -> Image.Image:
        img = Image.new("RGB", (VW, VH), BG)
        d = ImageDraw.Draw(img)
        big = logo(150)
        img.paste(big, (VW // 2 - 75, 250), big)
        gradient_text(img, (VW // 2, 500), "minion", font(120, "ExtraBold"), anchor="mm")
        d.text(
            (VW // 2, 610), "Give every AI agent its own computer.", font=font(52, "SemiBold"), fill=TEXT, anchor="mm"
        )
        sub = "Watch an agent plan a weekend with a browser, a spreadsheet and a word processor."
        d.text((VW // 2, 700), sub, font=font(32), fill=MUTED, anchor="mm")
        d.text((VW // 2, 748), "It sees every screen as text.", font=font(32), fill=MUTED, anchor="mm")
        return img

    def end(self) -> Image.Image:
        img = Image.new("RGB", (VW, VH), BG)
        d = ImageDraw.Draw(img)
        mine = sum(e["tokens"] for e in self.events)
        shots = sum(e["shots"] for e in self.events)
        gradient_text(
            img, (VW // 2, 200), f"{len(self.events)} tool calls · {mine:,} tokens", font(84, "ExtraBold"), "mm"
        )
        d.text(
            (VW // 2, 295),
            f"The same steps with screenshots: {shots} × {CLAUDE_IMAGE:,} = {shots * CLAUDE_IMAGE:,} tokens "
            f"({shots * CLAUDE_IMAGE / mine:.0f}× more)",
            font=font(34, "Medium"),
            fill=MUTED,
            anchor="mm",
        )
        small = logo(96)
        img.paste(small, (VW // 2 - 48, 420), small)
        d.text(
            (VW // 2, 590), "Give every AI agent its own computer.", font=font(56, "SemiBold"), fill=TEXT, anchor="mm"
        )
        d.text((VW // 2, 680), "github.com/apophisss/minion", font=font(52, "Bold"), fill=ACCENT, anchor="mm")
        d.text(
            (VW // 2, 770),
            "MCP · function calling · HTTP · CLI   —   Claude, ChatGPT, Gemini, Cursor, VS Code and more",
            font=font(30, "Medium"),
            fill=MUTED,
            anchor="mm",
        )
        d.text((VW // 2, 830), "Free and open source (MIT)", font=font(30), fill=MUTED, anchor="mm")
        return img


def poster(frame: Image.Image) -> Image.Image:
    """The frame with a play button on the desktop, for links to the video (GitHub shows no player in a README)."""
    img = frame.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy, r = VW // 2, VH // 2, 74
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*BG, 200), outline=(*ACCENT, 255), width=4)
    d.polygon([(cx - 22, cy - 34), (cx - 22, cy + 34), (cx + 36, cy)], fill="white")
    return Image.alpha_composite(img, layer).convert("RGB")


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("needs ffmpeg: install it, or pip install imageio-ffmpeg") from None


def timeline(run: dict) -> list[tuple[float, float, float, int, bool]]:
    """(source start, source end, speed, event, done) pieces: long calls play faster, and waiting (for an app to
    start or a page to load) fastest."""
    ev = run["events"]
    pieces, t = [], ev[0]["t0"] - 1.0
    pieces.append((t, ev[0]["t0"], 1.0, 0, False))
    for i, e in enumerate(ev):
        took = e["t1"] - e["t0"]
        waiting = e["tool"] == "open" or any(a["action"] == "wait_for" for a in e["args"].get("actions", []))
        speed = 1.0 if took <= 3.5 else 4.0 if waiting and took > 7 else 2.0
        pieces.append((e["t0"], e["t1"], speed, i, False))
        end = ev[i + 1]["t0"] if i + 1 < len(ev) else e["t1"] + e["hold"]
        pieces.append((e["t1"], end, 1.0, i, True))
    return pieces


def compose() -> None:
    run = json.loads((WORK / "run.json").read_text())
    events, start = run["events"], run["start"]
    paint = Painter(events)
    ff = ffmpeg()
    src = subprocess.Popen(
        [
            ff,
            "-v",
            "error",
            "-i",
            str(WORK / "raw.mp4"),
            "-vf",
            f"fps={FPS}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = subprocess.Popen(
        [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-"]
        + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "libx264", "-preset", "medium"]
        + ["-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(OUT)],
        stdin=subprocess.PIPE,
    )
    size = W * H * 3
    index, desk = -1, None

    def desktop_at(t: float) -> Image.Image:
        nonlocal index, desk
        want = max(0, round((t - start) * FPS))
        while index < want:
            raw = src.stdout.read(size)
            if len(raw) < size:
                break
            index, desk = index + 1, raw
        return Image.frombytes("RGB", (W, H), desk)

    def emit(img: Image.Image, n: int = 1) -> None:
        data = img.tobytes()
        for _ in range(n):
            out.stdin.write(data)

    title, end = paint.title(), paint.end()
    emit(title, int(TITLE * FPS))
    first = None
    count = 0
    poster_at = next(i for i, e in enumerate(events) if e["tool"] == "act" and "menu" in json.dumps(e["args"]))
    for s0, s1, speed, i, done in timeline(run):
        t = s0
        while t < s1:
            img = paint.frame(desktop_at(t), i, done, speed)
            if first is None:  # cross-fade from the title
                first = img
                for k in range(1, 13):
                    emit(Image.blend(title, img, k / 12))
            if i == poster_at and done and t >= s0 + 1.0 and not POSTER.exists():
                poster(img).save(POSTER)
                img.resize((1280, 720), Image.LANCZOS).save(THUMB, quality=90)
            emit(img)
            count += 1
            last = img
            t += speed / FPS
    emit(last, int(LAST * FPS))
    for k in range(1, 13):
        emit(Image.blend(last, end, k / 12))
    emit(end, int(END * FPS))
    out.stdin.close()
    out.wait()
    src.kill()
    seconds = (int(TITLE * FPS) + 12 + count + int(LAST * FPS) + 12 + int(END * FPS)) / FPS
    print(
        f"wrote {OUT.relative_to(ROOT)} ({seconds:.0f}s, {OUT.stat().st_size / 1e6:.1f} MB), {POSTER.name}, {THUMB.name}"
    )


def main(argv: list[str]) -> int:
    if "--compose" not in argv:
        record()
    POSTER.unlink(missing_ok=True)
    compose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
