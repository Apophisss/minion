"""Prepare a desktop for the everyday-work scenarios (see README.md in this folder).

    python scripts/scenarios/setup.py web       # a browser desktop with the scenario site (web1, web2)
    python scripts/scenarios/setup.py office    # an office desktop with the documents and pictures
    python scripts/scenarios/setup.py dev       # a developer desktop with a small project to fix
    python scripts/scenarios/setup.py windows   # a Windows-apps desktop

It creates the desktop (or reuses one with --name), copies the scenario site in and starts it on
http://localhost:8765/, and copies the files each batch needs. The site logs what each page reports to
/tmp/gym-results.jsonl inside the desktop: the scenarios' checks read it.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from minion.desktop import Desktop  # noqa: E402
from minion.errors import NotFound  # noqa: E402

PROFILE = {
    "web": "browser",
    "office": "office",
    "everyday": "office",
    "workflows": "office",
    "media": "office",
    "dev": "dev",
    "windows": "windows",
}
DOCUMENTS = ["report.docx", "sales.csv", "people.csv", "invoice.pdf", "chapter1.pdf", "chapter2.pdf", "notes.txt"]
PICTURES = [
    "photo.png",
    "logo.png",
    "vacation1.jpeg",
    "vacation2.jpeg",
    "vacation3.jpeg",
    "receipt.jpg",
    "wifi-sign.png",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=sorted(PROFILE))
    ap.add_argument("--name", help="desktop name (default: scenarios-KIND); an existing desktop is reused")
    args = ap.parse_args()
    name = args.name or f"scenarios-{args.kind}"
    try:
        d = Desktop.attach(name)
    except NotFound:
        d = Desktop.create(PROFILE[args.kind], name=name)
    files = HERE / "files"
    d.upload(str(HERE / "site"), "/home/agent/site")
    d.run("mkdir -p ~/Documents ~/Pictures ~/Downloads ~/Videos", timeout=20)
    d.run("cd ~/site && exec python3 serve.py 8765", background=True)
    if args.kind in ("office", "everyday", "workflows", "media"):
        for f in DOCUMENTS:
            d.upload(str(files / f), "~/Documents/")
        for f in PICTURES:
            d.upload(str(files / f), "~/Pictures/")
        d.upload(str(files / "clip.mp4"), "~/Videos/")
        d.run(
            "cd ~/Downloads && head -c 1200000 /dev/urandom > old-installer.bin && head -c 340000 /dev/urandom > "
            "photos-backup.tar && head -c 52000 /dev/urandom > invoice-copy.pdf && echo hi > readme.txt && "
            "mkdir -p ~/Documents/project/src && echo 'print(1)' > ~/Documents/project/src/main.py && "
            "echo '# Project' > ~/Documents/project/README.md",
            timeout=30,
        )
    elif args.kind == "dev":
        for f in ["proj", "notes.txt", "config.ini", "hog.py"]:
            d.upload(str(files / f), f"/home/agent/{f}" if f == "proj" else "~/")
        d.run("cd ~ && exec python3 hog.py", background=True)
        d.run("mkdir -p ~/site2 && echo '<h1>Hello from site2</h1>' > ~/site2/index.html", timeout=20)
    else:
        d.upload(str(files / "notes.txt"), "~/Documents/")
    time.sleep(1)
    res = d.run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8765/index.html", timeout=20)
    print(f"{d.name}: {args.kind} scenarios ready (site: HTTP {res.stdout.strip()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
