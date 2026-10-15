"""Point the Homebrew formula, packaging/homebrew/minion-desktop.rb, at a release on PyPI.

    python scripts/update_homebrew_formula.py              # the VERSION in minion/agent/__init__.py
    python scripts/update_homebrew_formula.py 1.0.1        # another release
    python scripts/update_homebrew_formula.py --dry-run    # show the change as a diff, write nothing

It reads the release from PyPI's JSON API and writes its source distribution's exact URL (the long
files.pythonhosted.org one that Homebrew wants) and SHA-256 into the formula's `url` and `sha256`. Run it after
the PyPI release, then copy the formula into the tap (packaging/README.md). Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

REPO = Path(__file__).resolve().parent.parent
FORMULA = REPO / "packaging" / "homebrew" / "minion-desktop.rb"
PROJECT = "minion-desktop"


def fail(message: str) -> NoReturn:
    sys.exit(f"update_homebrew_formula: {message}")


def repo_version() -> str:
    text = (REPO / "minion" / "agent" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION = "([^"]+)"', text, re.M)
    if not m:
        fail("no VERSION in minion/agent/__init__.py")
    return m[1]


def sdist(version: str, index: str) -> tuple[str, str]:
    """The URL and SHA-256 of the release's source distribution, from PyPI's JSON API."""
    url = f"{index.rstrip('/')}/{PROJECT}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            release = json.load(response)
    except urllib.error.HTTPError as e:
        fail(f"{PROJECT} {version} is not on {index} (yet?)" if e.code == 404 else f"{url}: HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError) as e:
        fail(f"cannot reach {url}: {getattr(e, 'reason', e)}")
    for file in release["urls"]:
        if file["packagetype"] == "sdist":
            return file["url"], file["digests"]["sha256"]
    fail(f"{PROJECT} {version} has no source distribution on {index}")


def update(formula: str, url: str, sha256: str) -> str:
    """The formula with new values for its own `url` and `sha256`: the first of each, before any resource."""
    formula, urls = re.subn(r'^(  url )"[^"]*"', lambda m: f'{m[1]}"{url}"', formula, count=1, flags=re.M)
    formula, sums = re.subn(r'^(  sha256 )"[^"]*"', lambda m: f'{m[1]}"{sha256}"', formula, count=1, flags=re.M)
    if not (urls and sums):
        fail("the formula has no top-level `url` and `sha256` lines to update")
    return formula


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", nargs="?", help="the release on PyPI (default: VERSION in minion/agent/__init__.py)")
    parser.add_argument("--dry-run", action="store_true", help="print the change as a diff instead of writing it")
    parser.add_argument(
        "--index",
        default="https://pypi.org/pypi",
        help="the index's JSON API (default: %(default)s; TestPyPI: https://test.pypi.org/pypi)",
    )
    parser.add_argument("--formula", type=Path, default=FORMULA, help="the formula to update (default: %(default)s)")
    args = parser.parse_args()

    version = args.version or repo_version()
    url, sha256 = sdist(version, args.index)
    before = args.formula.read_text(encoding="utf-8")
    after = update(before, url, sha256)
    if after == before:
        print(f"{args.formula} is up to date for {PROJECT} {version}")
    elif args.dry_run:
        name = str(args.formula)
        sys.stdout.writelines(difflib.unified_diff(before.splitlines(True), after.splitlines(True), name, name))
    else:
        args.formula.write_text(after, encoding="utf-8")
        print(f"{args.formula}: {PROJECT} {version}\n  url {url}\n  sha256 {sha256}")


if __name__ == "__main__":
    main()
