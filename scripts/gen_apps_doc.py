"""Write docs/apps.md: every app an agent can open by name, from minion/agent/catalog_data.py.

python scripts/gen_apps_doc.py           # rewrite docs/apps.md
python scripts/gen_apps_doc.py --check   # exit 1 if docs/apps.md is out of date (tests run this)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "minion" / "agent" / "catalog_data.py"
DOC = ROOT / "docs" / "apps.md"

HEADER = """\
# Apps an agent can open by name

`open NAME` works for every app below, on any profile. An app that isn't installed yet is installed the first time
(this takes from a few seconds to a few minutes, depending on its size), and the first open answers with a few tips
for it. Web apps open in the desktop's browser (a browser is installed first on the `base` profile). Apps that don't
run on Linux answer with the alternatives listed here.

Any other Debian package also works by name (`open galculator`), and `minion-install` takes `.deb`, `.AppImage` and
archive URLs, `pip:` and `npm:` packages. Inside an app, `see --menus` lists its commands with their shortcuts.

This page is generated from [`minion/agent/catalog_data.py`](../minion/agent/catalog_data.py) by
`scripts/gen_apps_doc.py`.
"""


def categories(source: str) -> dict[str, str]:
    """id -> the section heading it appears under in catalog_data.py."""
    out, current = {}, "Other"
    for line in source.splitlines():
        m = re.match(r"\s*#\s*-{5,}\s*(.+?)\s*$", line)
        if m:
            current = m.group(1)
            continue
        m = re.search(r'"id":\s*"([^"]+)"', line)
        if m:
            out[m.group(1)] = current
    return out


def how(app: dict, by_id: dict[str, dict]) -> str:
    size = f" (~{app['size_mb']} MB)" if app.get("size_mb") else ""
    if app.get("apt"):
        return f"Debian package{size}"
    if app.get("deb"):
        arch = " (x86-64 only)" if "arm64" not in app["deb"] else ""
        return f"official download{size}{arch}"
    if app.get("github"):
        arch = " (x86-64 only)" if "arm64" not in app["github"] else ""
        return f"newest GitHub release{size}{arch}"
    if app.get("url"):
        return f"web app: {app['url']}"
    alts = [by_id[a] for a in app.get("alternatives", ()) if a in by_id]
    return "not on Linux; instead: " + ", ".join(f"`open {a['id']}`" for a in alts)


def render() -> str:
    sys.path.insert(0, str(ROOT))
    from minion.agent.catalog_data import APPS

    by_id = {a["id"]: a for a in APPS}
    sections = categories(DATA.read_text())
    order: list[str] = []
    for app in APPS:
        if sections[app["id"]] not in order:
            order.append(sections[app["id"]])
    lines = [HEADER]
    for section in order:
        lines += [
            "",
            f"## {section[:1].upper()}{section[1:]}",
            "",
            "| App | Open with | How it gets there |",
            "|---|---|---|",
        ]
        for app in (a for a in APPS if sections[a["id"]] == section):
            names = ", ".join(f"`{n}`" for n in [app["id"], *app.get("aliases", [])][:4])
            lines.append(f"| {app.get('name', app['id'])} | {names} | {how(app, by_id)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not DOC.exists() or DOC.read_text() != text:
            print("docs/apps.md is out of date: run python scripts/gen_apps_doc.py")
            return 1
        return 0
    DOC.write_text(text)
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
