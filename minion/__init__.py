"""Minion: instant, featherweight Linux desktops for AI agents.

    from minion import Desktop

    with Desktop.create("office") as desk:
        desk.open("writer")
        desk.type("Hello from an agent!")
        print(desk.see())

Everything here is pure standard-library Python; desktops run in Docker
(or natively on Linux with the "local" backend).
"""

from .agent import VERSION as __version__
from .desktop import Desktop, Observation, RunResult, Screenshot
from .errors import MinionError

__all__ = ["Desktop", "Observation", "RunResult", "Screenshot", "MinionError", "__version__"]
