"""Render packaging/mcpb/icon.png, 512x512 with a transparent background, from minion/web/logo.svg.

    python packaging/mcpb/render_icon.py                        # finds Chromium, Chrome or Edge
    python packaging/mcpb/render_icon.py --browser /path/to/chrome

Run it after the logo changes and commit the PNG: building the bundle needs no browser. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGO = HERE.parent.parent / "minion" / "web" / "logo.svg"
SIZE = 512
BROWSERS = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "msedge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
PAGE = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}
img {{ display: block; width: {SIZE}px; height: {SIZE}px; }}
</style></head><body><img src="logo.svg"></body></html>
"""


def find_browser(name: str | None) -> str:
    for candidate in [name] if name else BROWSERS:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    sys.exit("render_icon: no Chromium, Chrome or Edge found; pass --browser PATH")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--browser", help="a Chromium-based browser (default: the first one found)")
    parser.add_argument("-o", "--output", type=Path, default=HERE / "icon.png")
    args = parser.parse_args()
    browser = find_browser(args.browser)
    # A snap-packaged Chromium only reads non-hidden folders in the home directory, so render there.
    with tempfile.TemporaryDirectory(dir=Path.home(), prefix="minion-icon-") as tmp:
        work = Path(tmp)
        shutil.copyfile(LOGO, work / "logo.svg")
        (work / "icon.html").write_text(PAGE, encoding="utf-8")
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--default-background-color=00000000",
            f"--window-size={SIZE},{SIZE}",
            f"--screenshot={work / 'icon.png'}",
            (work / "icon.html").as_uri(),
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")  # Chromium refuses to run as root with its sandbox
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        data = (work / "icon.png").read_bytes()
    width, height, depth, color = struct.unpack(">IIBB", data[16:26])
    if data[:8] != b"\x89PNG\r\n\x1a\n" or (width, height, depth, color) != (SIZE, SIZE, 8, 6):
        sys.exit(f"render_icon: expected a {SIZE}x{SIZE} RGBA PNG, got {width}x{height} (depth {depth}, type {color})")
    args.output.write_bytes(data)
    print(f"{args.output}: {width}x{height} RGBA, {len(data)} bytes")


if __name__ == "__main__":
    main()
