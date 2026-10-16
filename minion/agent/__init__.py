"""The in-desktop agent.

This package is copied into every desktop (a container, or a local Xvfb session)
and runs there as ``python3 -m minion_agent.session``. It owns the X server, the
window manager and a small RPC daemon that the host talks to.

It must only depend on the standard library, Pillow and, optionally, PyGObject
with AT-SPI (for the accessibility tree). Never import host-side modules here.
"""

VERSION = "1.1.0"
PROTOCOL = 1
