"""Starts Minion's MCP server for Claude Desktop (the .mcpb extension).

Claude Desktop runs `uv run --directory <extension> server/main.py mcp`. uv supplies Python 3.11 or newer
(downloading it the first time if the computer has none), and Minion needs nothing else: its pure
standard-library source sits next to this file, in server/minion.

Any other arguments go to the `minion` command, which helps when checking an installed extension by hand:
`uv run --directory <extension> server/main.py doctor`.
"""

import os
import re
import sys

# uv guarantees 3.11+, but started some other way (`python3 server/main.py` on a stock Mac), say so plainly.
if sys.version_info < (3, 11):  # noqa: UP036
    sys.exit(f"Minion needs Python 3.11 or newer, not {sys.version.split()[0]} ({sys.executable}).")

HERE = os.path.dirname(os.path.abspath(__file__))

# Claude Desktop passes a setting that has no value as its literal placeholder, "${user_config.NAME}",
# and a default such as "${HOME}/Downloads" may arrive unexpanded.
PLACEHOLDER = re.compile(r"\$\{user_config\.[^}]*\}")
FOLDER = re.compile(r"\$\{(HOME|DESKTOP|DOCUMENTS|DOWNLOADS)\}")


def clean_settings(environ) -> None:
    """Drop MINION_* settings that came without a value, and expand ${HOME}-style folders in the rest."""
    home = os.path.expanduser("~")
    for name in [key for key in environ if key.startswith("MINION_")]:
        value = environ[name].strip()
        if not value or PLACEHOLDER.search(value):
            del environ[name]
        else:
            environ[name] = FOLDER.sub(lambda m: home if m[1] == "HOME" else os.path.join(home, m[1].title()), value)


def main() -> None:
    clean_settings(os.environ)
    # uv starts the server in the extension's folder. Move to the home folder, so that no relative path (a
    # download without a shared folder, say) ever points into the extension, which an update replaces.
    try:
        os.chdir(os.path.expanduser("~"))
    except OSError:
        pass
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from minion.cli import entry

    sys.argv = [sys.argv[0], *(sys.argv[1:] or ["mcp"])]
    entry()


if __name__ == "__main__":
    main()
