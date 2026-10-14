"""`minion setup`: the first-run wizard. The installers end with it, and it is safe to run again at any time.

1. Checks that Docker or Podman is installed and running, and says exactly how to fix it if not.
2. Prepares the desktop images you pick (default: browser).
3. Connects the agent apps on this computer (`minion connect`).
4. Says what to try next.

Without a terminal (CI, a piped installer) it never waits for input: it uses the defaults and prints what it
would have asked.
"""

from __future__ import annotations

import os
import re
import sys
import time

from . import __version__, config, connect, profiles
from .backends import get_backend
from .errors import MinionError

DOCS = "https://github.com/apophisss/minion/blob/main/docs/install.md"
EXAMPLES = {
    "browser": "Use Minion to open a browser desktop, go to wikipedia.org and tell me today's featured article.",
    "office": "Use Minion to create an office desktop, write a one-page memo in Writer and save it as memo.docx.",
    "research": "Use Minion to open a research desktop and summarize the latest Python release notes.",
    "dev": "Use Minion to open a dev desktop, clone https://github.com/psf/requests and run its tests.",
}

INSTALL = {
    "darwin": """\
Minion runs each desktop in a container, so it needs Docker (or Podman). Install one, start it, then run
`minion setup` again:
  • Docker Desktop:  https://docs.docker.com/desktop/setup/install/mac-install/
  • OrbStack, a lighter alternative:  https://orbstack.dev   (or: brew install orbstack)""",
    "win32": """\
Minion runs each desktop in a container, so it needs Docker. Install Docker Desktop, start it, then run
`minion setup` again:
  • https://docs.docker.com/desktop/setup/install/windows-install/
    (or: winget install -e --id Docker.DockerDesktop). It uses WSL 2; restart Windows if it asks you to.""",
    "linux": """\
Minion runs each desktop in a container, so it needs Docker (or Podman). Install one, then run
`minion setup` again:
  • Docker:  curl -fsSL https://get.docker.com | sh
    then let your user run it:  sudo usermod -aG docker $USER   (log out and back in)
  • or your distribution's package:  sudo apt install docker.io  ·  sudo dnf install moby-engine
    ·  sudo pacman -S docker   (then: sudo systemctl enable --now docker)
  • or Podman:  sudo apt install podman  (dnf and pacman have it too)
Without containers, Linux can also run desktops natively: MINION_BACKEND=local (see docs/faq.md).""",
}


def runtime_help(backend, detail: str) -> str:
    """Exactly what to do, on this OS, when Docker or Podman is missing or not running."""
    if backend.name == "local":
        return f"The local backend is not ready: {detail}"
    if "was not found" in detail:  # what DockerBackend.available() says when the command doesn't exist
        return INSTALL.get(sys.platform, INSTALL["linux"])
    name = os.path.basename(getattr(backend, "bin", "docker"))
    lines = [f"{name} is installed but not answering: {detail}"]
    if name.startswith("podman"):
        start = (
            "podman machine start" if sys.platform in ("darwin", "win32") else "systemctl --user start podman.socket"
        )
        lines.append(f"Start it:  {start}")
    elif sys.platform == "darwin":
        lines.append("Start Docker Desktop (or OrbStack) and wait until it is running:  open -a Docker")
    elif sys.platform == "win32":
        lines.append('Start Docker Desktop from the Start menu and wait until it says "Engine running".')
    elif "permission denied" in detail.lower():
        lines.append("Let your user run Docker:  sudo usermod -aG docker $USER   then log out and back in")
    else:
        lines.append("Start it:  sudo systemctl start docker")
    lines.append("Then run `minion setup` again.")
    return "\n".join(lines)


class PullProgress:
    """Docker's pull output, condensed on a terminal into one line that counts layers."""

    def __init__(self, label: str, tty: bool | None = None):
        self.label = label
        self.tty = sys.stderr.isatty() if tty is None else tty
        self.layers: dict[str, bool] = {}  # layer -> done
        self.open = False  # the counting line has no newline yet

    def __call__(self, line: str) -> None:
        from .cli import progress_printer

        m = re.match(r"^([0-9a-f]{12}): (.*)$", line.strip())
        if not (self.tty and m):
            self.close()
            progress_printer(line)
            return
        layer, status = m.groups()
        if status in ("Pulling fs layer", "Waiting", "Already exists") or layer in self.layers:
            self.layers[layer] = self.layers.get(layer, False) or status in ("Pull complete", "Already exists")
            done = sum(self.layers.values())
            sys.stderr.write(f"\r  Downloading {self.label}: {done}/{len(self.layers)} layers")
            sys.stderr.flush()
            self.open = True

    def close(self) -> None:
        if self.open:
            sys.stderr.write("\n")
            self.open = False


def _short(text: str, width: int = 76) -> str:
    """The first sentence, cut at a word if it is still long."""
    text = " ".join(text.split()).split(". ")[0].rstrip(".")
    return text if len(text) <= width else text[:width].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def choose_profiles(yes: bool) -> list[str]:
    reg = profiles.load_all()
    names = profiles.names(reg)
    default = config.DEFAULT_PROFILE
    print("Desktop profiles (each downloads once; they share most of their layers):")
    for n in names:
        print(f"  {n:<10} {_short(reg[n].description)}")
    question = f"Which should be ready now? Several like office,dev, or none [{default}]: "
    for _ in range(3):
        answer = connect.ask(question, default, yes)
        chosen = [] if answer.strip().lower() in ("none", "-", "no", "n") else re.split(r"[,\s]+", answer.strip())
        unknown = [n for n in chosen if n and n not in reg]
        if not unknown:
            return [n for n in chosen if n]
        print(f"Unknown: {', '.join(unknown)}. Pick from: {', '.join(names)}")
        if not connect.interactive():
            break
    return [default]


def prepare(backend, names: list[str]) -> list[str]:
    """Pull (or build) each profile's image. Returns the ones that failed."""
    from .cli import err, info, ok

    failed = []
    for name in names:
        t0, progress = time.time(), PullProgress(name)
        try:
            ref = backend.prepare(profiles.get(name), progress=progress)
        except MinionError as e:
            progress.close()
            err(f"{name}: {e}")
            failed.append(name)
            continue
        progress.close()
        ok(f"{name} is ready" + (f" ({ref}, {time.time() - t0:.0f}s)" if ref else ""))
    if failed:
        info(f"Try again later with: minion pull {' '.join(failed)}")
    return failed


def next_steps(changes: list, names: list[str]) -> None:
    from .cli import c

    connected = [ch.app.name for ch in changes if ch.done or ch.action == "none"]
    profile = next((n for n in names if n in EXAMPLES), "browser")  # for the example prompt
    ready = names[0] if names else config.DEFAULT_PROFILE  # for `minion up`: one that is downloaded already
    print(c("\nYou're set." if connected else "\nAlmost there.", "1"))
    if connected:
        print(f"Ask your agent ({', '.join(connected)}):")
        print(f'  "{EXAMPLES[profile]}"')
    else:
        print("No agent app is connected yet: `minion connect --list` shows the apps Minion knows, and agents")
        print("with a shell can use the `minion` CLI directly (`minion skill --install` teaches them).")
    print(f"Watch a desktop live:  minion view       Try one yourself:  minion up {ready} && minion see")
    print(f"Docs: {DOCS}")


def setup(names: list[str] | None = None, *, yes: bool = False, compact: bool = False) -> int:
    from .cli import c, err, ok

    for n in names or []:
        profiles.get(n)  # unknown names fail now, before anything is downloaded
    print(c(f"Minion {__version__} setup", "1"))

    backend = get_backend()
    print(c("\n[1/3] " + ("Local desktops (no containers)" if backend.name == "local" else "Docker"), "1"))
    ready, detail = backend.available()
    if not ready:
        err("No container runtime is ready." if backend.name != "local" else "The local backend is not ready.")
        print(runtime_help(backend, detail))
        return 1
    ok(detail)

    print(c("\n[2/3] Desktops", "1"))
    if names is None:
        names = choose_profiles(yes)
    failed = prepare(backend, names) if names else []
    if not names:
        print("Skipped: each profile downloads the first time you use it (or: minion pull PROFILE).")

    print(c("\n[3/3] Agent apps", "1"))
    changes = connect.run(launch=connect.launcher(compact), yes=yes, each=True)

    next_steps(changes, names)
    return 1 if failed else 0
