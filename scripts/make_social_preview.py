"""Render docs/assets/social-preview.png, the 1280x640 Open Graph image for the site and the repository.

    pip install playwright && playwright install chromium   # once
    python scripts/make_social_preview.py [--out PATH] [--chromium PATH]

The image is the HTML template below, rendered with Playwright. It embeds docs/assets/office.png and the
logo, uses Inter when it is installed (the system sans-serif otherwise), and only shows real output of
`minion see` from the README. Upload the result in the repository settings as the social preview.
"""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W, H = 1280, 640

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0 }
html, body { width: 1280px; height: 640px; overflow: hidden }
body {
  position: relative; background: #070a18; color: #fff;
  font-family: Inter, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.mono { font-family: "SF Mono", Menlo, "Cascadia Code", "DejaVu Sans Mono", monospace }
.glow {
  position: absolute; inset: 0;
  background:
    radial-gradient(48% 70% at 92% 0%, rgba(99, 102, 241, .5), transparent 70%),
    radial-gradient(42% 60% at 0% 100%, rgba(14, 165, 233, .2), transparent 70%),
    radial-gradient(40% 50% at 70% 100%, rgba(124, 58, 237, .28), transparent 70%);
}
.grid {
  position: absolute; inset: 0;
  background-image: linear-gradient(rgba(165, 180, 252, .07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(165, 180, 252, .07) 1px, transparent 1px);
  background-size: 40px 40px;
  -webkit-mask-image: radial-gradient(ellipse 70% 90% at 25% 30%, #000 20%, transparent 75%);
}
.left { position: absolute; left: 72px; top: 74px; width: 610px }
.brand { display: flex; align-items: center; gap: 14px; font-size: 36px; font-weight: 700; letter-spacing: -.03em }
.brand svg { width: 54px; height: 54px }
h1 { margin-top: 44px; font-size: 64px; line-height: 1.04; letter-spacing: -.045em; font-weight: 700 }
.grad {
  background: linear-gradient(100deg, #a5b4fc 5%, #c4b5fd 50%, #f9a8d4 95%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.sub { margin-top: 24px; width: 540px; font-size: 23px; line-height: 1.45; color: #b8bdd6 }
.chips { display: flex; gap: 10px; margin-top: 34px }
.chips span {
  padding: 10px 14px; border-radius: 10px; border: 1px solid #283056; background: rgba(13, 18, 38, .85);
  font-size: 17px; font-weight: 600; color: #e0e7ff;
}
.chips b { color: #f472b6 }
.win {
  position: absolute; left: 706px; top: 70px; width: 700px; border-radius: 14px; overflow: hidden;
  border: 1px solid #343d6b; box-shadow: 0 40px 80px -24px rgba(0, 0, 0, .75);
}
.win img { display: block; width: 700px }
.term {
  position: absolute; left: 640px; top: 338px; width: 510px; border-radius: 16px; overflow: hidden;
  background: #0b1020; border: 1px solid #2a3258;
  box-shadow: 0 0 0 1px rgba(99, 102, 241, .15), 0 30px 70px -20px rgba(0, 0, 0, .85);
}
.term .h {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #1c2342;
  font-size: 15px; color: #c7cbe6;
}
.term .h .badge {
  margin-left: auto; padding: 5px 9px; border-radius: 7px; background: linear-gradient(135deg, #4f46e5, #7c3aed);
  font-size: 13px; font-weight: 700; color: #fff;
}
.term pre { padding: 14px 18px 16px; font-size: 15px; line-height: 1.7; color: #d7dbf0 }
.id { color: #f472b6; font-weight: 700 } .r { color: #a5b4fc } .s { color: #9be3c3 } .c { color: #7d86a8 }
.p { color: #646b93 }
</style></head><body>
<div class="glow"></div><div class="grid"></div>
<div class="left">
  <div class="brand">{{LOGO}}minion</div>
  <h1>Give every AI agent<br><span class="grad">its own computer.</span></h1>
  <p class="sub">Featherweight Linux desktops for any agent, over MCP, function calling, HTTP, a CLI, Python or
  TypeScript.</p>
  <div class="chips mono"><span><b>~1.5 s</b> ready</span><span><b>54–105 MB</b> idle</span><span><b>0%</b> CPU frozen</span></div>
</div>
<div class="win"><img src="data:image/png;base64,{{SHOT}}" alt=""></div>
<div class="term">
  <div class="h mono"><span class="p">$</span> minion see<span class="badge">@ids</span></div>
<pre class="mono"><span class="id">@1</span> <span class="r">menu</span> <span class="s">"File"</span> <span class="c">(22,38)</span>
<span class="id">@2</span> <span class="r">menu</span> <span class="s">"Edit"</span> <span class="c">(62,38)</span>
<span class="c">…</span>
<span class="id">@13</span> <span class="r">heading</span> <span class="s">"Q3 Market Brief"</span> <span class="c">(603,247)</span>
<span class="id">@14</span> <span class="r">paragraph</span> <span class="s">"Prepared by an AI agent</span>
<span class="s">    on a Minion desktop. No human touched</span>
<span class="s">    the keyboard."</span> <span class="c">(603,282)</span></pre>
</div>
</body></html>
"""


def render_html() -> str:
    shot = base64.b64encode((ROOT / "docs/assets/office.png").read_bytes()).decode()
    logo = (ROOT / "minion/web/logo.svg").read_text(encoding="utf-8")
    return TEMPLATE.replace("{{SHOT}}", shot).replace("{{LOGO}}", logo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the 1280x640 social preview image.")
    parser.add_argument("--out", default=str(ROOT / "docs/assets/social-preview.png"), help="output PNG")
    parser.add_argument(
        "--chromium",
        default=os.environ.get("MINION_CHROMIUM"),
        help="a Chromium or Chrome binary to use instead of Playwright's own (or set MINION_CHROMIUM)",
    )
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # imported here so --help works without Playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium) if args.chromium else p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.set_content(render_html(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=args.out, type="png")
        browser.close()
    print(args.out)


if __name__ == "__main__":
    main()
