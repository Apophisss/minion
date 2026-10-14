"""Desktop session: Xvfb + D-Bus + AT-SPI + JWM + the agent daemon, in one supervisor.

Run as `python3 -m minion_agent.session` inside a container (the image entrypoint),
or by the local backend on a Linux host. Configuration comes from MINION_* variables.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import VERSION, jwm, server, wallpaper

GTK_SETTINGS = """[Settings]
gtk-enable-animations=false
gtk-cursor-blink=false
gtk-recent-files-enabled=false
gtk-overlay-scrolling=false
gtk-error-bell=false
gtk-font-name=DejaVu Sans 10
"""

ATSPI_LAUNCHERS = (
    "/usr/libexec/at-spi-bus-launcher",
    "/usr/lib/at-spi2-core/at-spi-bus-launcher",
    "/usr/lib/at-spi2/at-spi-bus-launcher",
)


def log(msg: str) -> None:
    sys.stderr.write(f"[minion {time.strftime('%H:%M:%S')}] {msg}\n")
    sys.stderr.flush()


def parse_size(spec: str) -> tuple[int, int]:
    parts = spec.lower().replace("×", "x").split("x")
    try:
        w, h = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        raise SystemExit(f"invalid MINION_SCREEN {spec!r}; expected WIDTHxHEIGHT such as 1280x800") from None
    if not (320 <= w <= 7680 and 240 <= h <= 4320):
        raise SystemExit(f"screen size {w}x{h} is out of range")
    return w, h


def _json_env(name: str, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log(f"ignoring invalid JSON in {name}")
        return default


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Session:
    def __init__(self) -> None:
        self.display = os.environ.get("MINION_DISPLAY", ":0")
        self.num = int(self.display.lstrip(":").split(".")[0])
        self.size = parse_size(os.environ.get("MINION_SCREEN", "1280x800"))
        self.runtime = Path(os.environ.get("MINION_RUNTIME_DIR", "/tmp/minion"))
        self.name = os.environ.get("MINION_NAME", socket.gethostname())
        self.profile = os.environ.get("MINION_PROFILE", "")
        self.apps = _json_env("MINION_APPS", [])
        self.autostart = _json_env("MINION_AUTOSTART", [])
        self.procs: dict[str, subprocess.Popen] = {}
        self.stopping = False
        self.wm_restarts = 0

    # -- helpers -------------------------------------------------------
    def spawn(self, name: str, cmd: list[str], **kw) -> subprocess.Popen:
        logf = open(self.runtime / f"{name}.log", "ab")
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=logf, stderr=logf, **kw)
        logf.close()
        self.procs[name] = proc
        return proc

    def wait_for(self, check, timeout: float, what: str, proc: subprocess.Popen | None = None) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if check():
                return
            if proc is not None and proc.poll() is not None:
                tail = ""
                try:
                    tail = (self.runtime / f"{what}.log").read_text(errors="replace")[-800:]
                except OSError:
                    pass
                raise RuntimeError(f"{what} exited with code {proc.returncode}: {tail}")
            time.sleep(0.05)
        raise RuntimeError(f"timed out waiting for {what}")

    # -- stages --------------------------------------------------------
    def prepare(self) -> None:
        self.runtime.mkdir(parents=True, exist_ok=True)
        os.chmod(self.runtime, 0o700)
        xdg = self.runtime / "xdg"
        xdg.mkdir(exist_ok=True)
        os.chmod(xdg, 0o700)
        home = Path(os.path.expanduser("~"))
        for d in ("Desktop", "Documents", "Downloads", "Pictures", ".config/gtk-3.0", ".config/gtk-4.0"):
            (home / d).mkdir(parents=True, exist_ok=True)
        for gtk in ("gtk-3.0", "gtk-4.0"):
            f = home / ".config" / gtk / "settings.ini"
            if not f.exists():
                f.write_text(GTK_SETTINGS)
        # `minion-install <anything>` inside the desktop (apt names, .deb/.AppImage/archive URLs, pip:, npm:).
        bin_dir = home / ".local" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        tool = bin_dir / "minion-install"
        if not tool.exists():
            tool.write_text('#!/bin/sh\nexec python3 -m minion_agent.install "$@"\n')
            tool.chmod(0o755)
        env = os.environ
        env["DISPLAY"] = self.display
        env["XDG_RUNTIME_DIR"] = str(xdg)
        env["MINION_RUNTIME_DIR"] = str(self.runtime)
        env.setdefault("LANG", "C.UTF-8")
        env.setdefault("XDG_SESSION_TYPE", "x11")
        env.setdefault("XDG_CURRENT_DESKTOP", "Minion")
        # Accessibility everywhere: GTK/ATK, Qt, Firefox, Chromium/Electron, LibreOffice.
        env["GNOME_ACCESSIBILITY"] = "1"
        env["QT_ACCESSIBILITY"] = "1"
        env["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"
        env["ACCESSIBILITY_ENABLED"] = "1"
        env.pop("NO_AT_BRIDGE", None)
        env.setdefault("SAL_USE_VCLPLUGIN", "gtk3")
        # Calm, deterministic pixels: no overlay scrollbars, no animations, software GL.
        env["GTK_OVERLAY_SCROLLING"] = "0"
        env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        env["MINION_SESSION"] = "1"
        local_bin = str(Path(os.path.expanduser("~")) / ".local" / "bin")
        if local_bin not in env.get("PATH", "").split(os.pathsep):
            env["PATH"] = local_bin + os.pathsep + env.get("PATH", "/usr/bin:/bin")

    def clean_stale(self) -> None:
        lock = Path(f"/tmp/.X{self.num}-lock")
        sock = Path(f"/tmp/.X11-unix/X{self.num}")
        if lock.exists():
            try:
                pid = int(lock.read_text().strip())
            except (OSError, ValueError):
                pid = 0
            if pid and _alive(pid):
                raise RuntimeError(f"display {self.display} is already in use (pid {pid})")
            for p in (lock, sock):
                try:
                    p.unlink()
                except OSError:
                    pass
        for stale in ("agent.sock", "bus"):
            try:
                (self.runtime / stale).unlink()
            except OSError:
                pass

    def start_x(self) -> None:
        w, h = self.size
        cmd = [
            "Xvfb",
            self.display,
            "-screen",
            "0",
            f"{w}x{h}x24",
            "-nolisten",
            "tcp",
            "-dpi",
            "96",
            "-noreset",
            "-s",
            "0",
            "+extension",
            "RANDR",
        ]
        if shutil.which("xauth"):
            auth = self.runtime / "Xauthority"
            auth.touch(mode=0o600)
            cookie = secrets.token_hex(16)
            subprocess.run(
                ["xauth", "-q", "-f", str(auth), "add", self.display, ".", cookie],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cmd += ["-auth", str(auth)]
            os.environ["XAUTHORITY"] = str(auth)
        else:
            cmd += ["-ac"]
        Path("/tmp/.X11-unix").mkdir(mode=0o1777, exist_ok=True)
        proc = self.spawn("xvfb", cmd)
        sock_path = f"/tmp/.X11-unix/X{self.num}"

        def ready() -> bool:
            if not os.path.exists(sock_path):
                return False
            s = socket.socket(socket.AF_UNIX)
            try:
                s.connect(sock_path)
                return True
            except OSError:
                return False
            finally:
                s.close()

        self.wait_for(ready, 15, "xvfb", proc)
        if shutil.which("xset"):
            subprocess.run(
                ["xset", "s", "off", "s", "noblank", "-dpms"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )

    def start_dbus(self) -> None:
        if not shutil.which("dbus-daemon"):
            log("dbus-daemon not found: accessibility tree disabled")
            return
        bus = self.runtime / "bus"
        proc = self.spawn("dbus", ["dbus-daemon", "--session", "--nofork", "--nopidfile", f"--address=unix:path={bus}"])
        self.wait_for(bus.exists, 10, "dbus", proc)
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"

    def start_atspi(self) -> None:
        if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
            return
        launcher = next((p for p in ATSPI_LAUNCHERS if os.path.exists(p)), None)
        if not launcher:
            log("at-spi-bus-launcher not found: accessibility tree disabled")
            return
        self.spawn("atspi", [launcher, "--launch-immediately"])
        if not shutil.which("dbus-send"):
            return
        for _ in range(60):
            r = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--print-reply",
                    "--dest=org.a11y.Bus",
                    "/org/a11y/bus",
                    "org.freedesktop.DBus.Properties.Set",
                    "string:org.a11y.Status",
                    "string:IsEnabled",
                    "variant:boolean:true",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            if r.returncode == 0:
                return
            time.sleep(0.1)
        log("could not enable the accessibility bus")

    def terminal(self) -> str:
        t = os.environ.get("MINION_TERMINAL")
        if t:
            return t
        for cand in ("lxterminal", "xfce4-terminal", "xterm", "x-terminal-emulator"):
            if shutil.which(cand):
                return cand
        return "xterm"

    def start_wm(self) -> None:
        wm = os.environ.get("MINION_WM", "jwm").lower()
        if wm == "none":
            return
        wp = None
        if os.environ.get("MINION_WALLPAPER", "1") != "0":
            custom = os.environ.get("MINION_WALLPAPER")
            if custom and custom not in ("1", "0") and os.path.exists(custom):
                wp = custom
            else:
                try:
                    wp = wallpaper.make(str(self.runtime / "wallpaper.png"), *self.size)
                except Exception as e:  # cosmetic only
                    log(f"wallpaper failed: {e}")
        if wm == "jwm" and shutil.which("jwm"):
            rc = self.runtime / "jwmrc"
            rc.write_text(
                jwm.config(
                    self.apps, wp, terminal=self.terminal(), maximize=os.environ.get("MINION_MAXIMIZE", "1") != "0"
                )
            )
            self.spawn("wm", ["jwm", "-f", str(rc)])
        elif shutil.which("openbox"):
            self.spawn("wm", ["openbox"])
            if wp and shutil.which("hsetroot"):
                subprocess.run(["hsetroot", "-fill", wp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            log("no window manager found (install jwm): windows will not be decorated")
            return
        time.sleep(0.3)

    def run_autostart(self) -> None:
        for cmd in self.autostart:
            if not cmd:
                continue
            logf = open(self.runtime / "apps.log", "ab")
            subprocess.Popen(
                ["bash", "-lc", cmd],
                cwd=os.path.expanduser("~"),
                stdin=subprocess.DEVNULL,
                stdout=logf,
                stderr=logf,
                start_new_session=True,
            )
            logf.close()

    # -- lifecycle -----------------------------------------------------
    def stop(self, *_args) -> None:
        if self.stopping:
            return
        self.stopping = True
        for name in ("wm", "atspi", "dbus", "xvfb"):
            p = self.procs.get(name)
            if p and p.poll() is None:
                p.terminate()
        deadline = time.monotonic() + 3
        for p in self.procs.values():
            try:
                p.wait(max(0.05, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                p.kill()
        os._exit(0)

    def supervise(self) -> None:
        while not self.stopping:
            time.sleep(2)
            x = self.procs.get("xvfb")
            if x and x.poll() is not None:
                log(f"X server exited with code {x.returncode}; shutting down")
                self.stop()
            wm = self.procs.get("wm")
            if wm and wm.poll() is not None and self.wm_restarts < 10:
                self.wm_restarts += 1
                log("window manager exited; restarting it")
                self.spawn("wm", wm.args)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        t0 = time.monotonic()
        self.prepare()
        self.clean_stale()
        self.start_x()
        self.start_dbus()
        self.start_atspi()
        self.start_wm()
        info = {"name": self.name, "profile": self.profile, "apps": self.apps}
        agent = server.Agent(self.display, self.size, info)
        ready = threading.Event()
        sock = str(self.runtime / "agent.sock")
        threading.Thread(target=server.serve, args=(agent, sock, ready), daemon=True).start()
        ready.wait(10)
        self.run_autostart()
        (self.runtime / "session.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "display": self.display,
                    "screen": list(self.size),
                    "socket": sock,
                    "version": VERSION,
                    "started": time.time(),
                }
            )
        )
        log(
            f"desktop {self.name!r} ready on {self.display} ({self.size[0]}x{self.size[1]}) "
            f"in {time.monotonic() - t0:.2f}s"
        )
        self.supervise()


def main() -> None:
    try:
        Session().run()
    except RuntimeError as e:
        log(f"failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
