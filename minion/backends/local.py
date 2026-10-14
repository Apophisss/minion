"""Local backend (Linux): desktops are native Xvfb sessions on this machine. No Docker needed.

Lighter than containers (no image, nothing to download) but not isolated: apps run
as your user and use the programs installed on this host. Great for CI and servers.
Each desktop gets its own display, home directory and process group.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path

from .. import config, profiles
from ..channel import Channel, SocketTransport
from ..errors import BackendError, MinionError, NotFound
from ..profiles import Profile
from .base import Backend, CreateOptions, DesktopInfo, Snapshot, check_name

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
REQUIRED = {"Xvfb": "xvfb", "xdotool": "xdotool", "wmctrl": "wmctrl", "xwininfo": "x11-utils", "xprop": "x11-utils"}
OPTIONAL = {
    "jwm": "jwm",
    "dbus-daemon": "dbus-daemon",
    "tesseract": "tesseract-ocr",
    "xclip": "xclip",
    "xauth": "xauth",
}


def _python() -> str | None:
    from ..doctor import _which_python_with

    return _which_python_with(["PIL", "gi"]) or _which_python_with(["PIL"])


def missing_tools(optional: bool = False) -> list[str]:
    pkgs = []
    for binary, pkg in {**REQUIRED, **(OPTIONAL if optional else {})}.items():
        if not shutil.which(binary) and pkg not in pkgs:
            pkgs.append(pkg)
    if _python() is None:
        pkgs.append("python3-pil")
    return pkgs


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _proc_state(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return ""


class LocalBackend(Backend):
    name = "local"

    def __init__(self) -> None:
        self.root = config.data_dir() / "local"

    def available(self) -> tuple[bool, str]:
        if not sys.platform.startswith("linux"):
            return False, "the local backend only runs on Linux (use Docker on macOS and Windows)"
        missing = missing_tools()
        if missing:
            return False, "missing: " + " ".join(missing) + f" (sudo apt-get install -y {' '.join(missing)})"
        return True, "native Xvfb sessions"

    # -- helpers -------------------------------------------------------
    def _dir(self, name: str) -> Path:
        return self.root / name

    def _meta(self, name: str) -> dict:
        try:
            return json.loads((self._dir(name) / "meta.json").read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise NotFound(f"no desktop named {name!r} (see `minion ls`)") from e

    @staticmethod
    def _host_app(app: dict) -> dict:
        """Local desktops use this machine's programs: map the terminal to one that exists."""
        exe = (app.get("command") or "").split()[0] if app.get("command") else ""
        if exe and not shutil.which(exe) and app.get("id") == "terminal":
            for term in ("xterm", "lxterminal", "xfce4-terminal", "gnome-terminal", "konsole", "x-terminal-emulator"):
                if shutil.which(term):
                    return {**app, "command": term}
        return app

    def _runtime(self, name: str) -> Path:
        """Sockets live under a short /tmp path (UNIX socket paths are limited to ~108 bytes)."""
        meta = self._meta(name)
        base = Path(f"/tmp/minion-{os.getuid()}")
        base.mkdir(mode=0o700, exist_ok=True)
        return base / meta["id"][:12]

    def _save_meta(self, name: str, meta: dict) -> None:
        (self._dir(name) / "meta.json").write_text(json.dumps(meta, indent=2))

    def _procs(self, desktop_id: str) -> list[int]:
        """Every process started inside the desktop (they all inherit MINION_DESKTOP_ID)."""
        marker = f"MINION_DESKTOP_ID={desktop_id}".encode()
        pids = []
        me = os.getpid()
        for entry in os.listdir("/proc"):
            if not entry.isdigit() or int(entry) == me:
                continue
            try:
                with open(f"/proc/{entry}/environ", "rb") as f:
                    if marker in f.read().split(b"\0"):
                        pids.append(int(entry))
            except OSError:
                continue
        return pids

    def _signal_all(self, desktop_id: str, sig: int) -> int:
        n = 0
        for pid in self._procs(desktop_id):
            try:
                os.kill(pid, sig)
                n += 1
            except OSError:
                pass
        return n

    def _free_display(self) -> int:
        used = set()
        for m in self.root.glob("*/meta.json"):
            try:
                used.add(int(json.loads(m.read_text()).get("display", -1)))
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        n = 50
        while n in used or os.path.exists(f"/tmp/.X{n}-lock") or os.path.exists(f"/tmp/.X11-unix/X{n}"):
            n += 1
        return n

    def _info(self, meta: dict) -> DesktopInfo:
        pid = int(meta.get("pid") or 0)
        if pid and _alive(pid):
            state = "paused" if _proc_state(pid) == "T" else "running"
        else:
            state = "stopped"
        return DesktopInfo(
            name=meta["name"],
            profile=meta.get("profile", ""),
            state=state,
            backend=self.name,
            size=meta.get("size", ""),
            created=float(meta.get("created", 0)),
            image="(host)",
            id=meta.get("id", "")[:12],
            options=meta.get("options", {}),
        )

    # -- lifecycle -----------------------------------------------------
    def list(self, stats: bool = False) -> list[DesktopInfo]:
        out = []
        if not self.root.is_dir():
            return out
        for m in sorted(self.root.glob("*/meta.json")):
            try:
                info = self._info(json.loads(m.read_text()))
            except (OSError, json.JSONDecodeError, KeyError):
                continue
            if stats and info.state == "running":
                info.memory = self._rss(json.loads(m.read_text()).get("id", ""))
            out.append(info)
        out.sort(key=lambda d: d.created)
        return out

    def _rss(self, desktop_id: str) -> int:
        total = 0
        for pid in self._procs(desktop_id):
            try:
                with open(f"/proc/{pid}/statm") as f:
                    total += int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            except (OSError, ValueError, IndexError):
                pass
        return total

    def get(self, name: str) -> DesktopInfo:
        return self._info(self._meta(name))

    def exists(self, name: str) -> bool:
        return (self._dir(name) / "meta.json").exists()

    def create(self, name: str, profile: Profile, options: CreateOptions, progress=None) -> DesktopInfo:
        ok, detail = self.available()
        if not ok:
            raise BackendError(f"local backend unavailable: {detail}")
        check_name(name)
        if self.exists(name):
            raise MinionError(f"a desktop named {name!r} already exists")
        d = self._dir(name)
        (d / "home").mkdir(parents=True, exist_ok=True)
        (d / "lib").mkdir(exist_ok=True)
        link = d / "lib" / "minion_agent"
        if not link.exists():
            link.symlink_to(AGENT_DIR, target_is_directory=True)
        meta = {
            "name": name,
            "profile": profile.name,
            "size": options.size,
            "created": time.time(),
            "id": uuid.uuid4().hex,
            "options": options.to_dict(),
            "apps": [self._host_app(a.to_dict()) for a in profile.merged("apps")],
            "autostart": profile.merged("autostart"),
            "env": {**profile.merged("env"), **options.env},
        }
        self._save_meta(name, meta)
        self._spawn(name, progress)
        return self.get(name)

    def _spawn(self, name: str, progress=None) -> None:
        meta = self._meta(name)
        d = self._dir(name)
        py = _python()
        if py is None:
            raise BackendError("no python3 with Pillow found (sudo apt-get install -y python3-pil)")
        display = self._free_display()
        runtime = self._runtime(name)
        if runtime.exists():
            shutil.rmtree(runtime, ignore_errors=True)
        runtime.mkdir()
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("MINION_", "DISPLAY", "WAYLAND", "DBUS_SESSION", "XAUTHORITY"))
        }
        env.update(meta.get("env", {}))
        env.update(
            {
                "HOME": str(d / "home"),
                "PYTHONPATH": str(d / "lib"),
                "MINION_DISPLAY": f":{display}",
                "MINION_SCREEN": meta["size"],
                "MINION_RUNTIME_DIR": str(runtime),
                "MINION_NAME": name,
                "MINION_PROFILE": meta.get("profile", ""),
                "MINION_APPS": json.dumps(meta.get("apps", [])),
                "MINION_AUTOSTART": json.dumps(meta.get("autostart", [])),
                "MINION_DESKTOP_ID": meta["id"],
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        if progress:
            progress(f"Starting local desktop {name!r} on display :{display} ...")
        with open(runtime / "session.log", "ab") as log:
            proc = subprocess.Popen(
                [py, "-m", "minion_agent.session"],
                env=env,
                cwd=str(d / "home"),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        meta.update(pid=proc.pid, display=display)
        self._save_meta(name, meta)
        sock = runtime / "agent.sock"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                tail = (runtime / "session.log").read_text(errors="replace")[-1500:]
                raise BackendError(f"desktop {name!r} failed to start:\n{tail}")
            if sock.exists():
                try:
                    ch = self.channel(name)
                    ch.call("hello", timeout=10)
                    ch.close()
                    return
                except Exception:
                    pass
            time.sleep(0.1)
        raise BackendError(f"desktop {name!r} did not become ready (see {runtime / 'session.log'})")

    def remove(self, name: str) -> None:
        runtime = self._runtime(name)
        self.stop(name)
        shutil.rmtree(runtime, ignore_errors=True)
        shutil.rmtree(self._dir(name), ignore_errors=True)

    def start(self, name: str) -> None:
        info = self.get(name)
        if info.state == "paused":
            self.thaw(name)
        elif info.state != "running":
            self._spawn(name)

    def stop(self, name: str) -> None:
        meta = self._meta(name)
        did = meta.get("id", "")
        self._signal_all(did, signal.SIGCONT)
        pid = int(meta.get("pid") or 0)
        if pid and _alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self._procs(did):
            self._signal_all(did, signal.SIGTERM)
            time.sleep(0.2)
        self._signal_all(did, signal.SIGKILL)

    def freeze(self, name: str) -> None:
        info = self.get(name)
        if info.state != "running":
            if info.state == "paused":
                return
            raise MinionError(f"desktop {name!r} is {info.state}; only running desktops can be frozen")
        self._signal_all(self._meta(name)["id"], signal.SIGSTOP)

    def thaw(self, name: str) -> None:
        self._signal_all(self._meta(name)["id"], signal.SIGCONT)

    def ensure_awake(self, name: str) -> None:
        meta = self._meta(name)
        pid = int(meta.get("pid") or 0)
        if not pid or not _alive(pid):
            self._spawn(name)
        elif _proc_state(pid) == "T":
            self.thaw(name)

    def channel(self, name: str) -> Channel:
        sock = str(self._runtime(name) / "agent.sock")
        return Channel(lambda: SocketTransport(sock), label=f"desktop {name!r}")

    # -- files ---------------------------------------------------------
    def _path(self, name: str, path: str) -> Path:
        home = self._dir(name) / "home"
        if path in ("~", ""):
            return home
        if path.startswith("~/"):
            return home / path[2:]
        if not path.startswith("/"):
            return home / path
        return Path(path)

    def copy_in(self, name: str, src: str, dst: str) -> None:
        target = self._path(name, dst)
        srcp = Path(src)
        if not srcp.exists():
            raise NotFound(f"{src} does not exist")
        if target.is_dir() or dst.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            target = target / srcp.name
        if srcp.is_dir():
            shutil.copytree(srcp, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(srcp, target)

    def copy_out(self, name: str, src: str, dst: str) -> None:
        source = self._path(name, src)
        if not source.exists():
            raise NotFound(f"{src} does not exist in desktop {name!r}")
        target = Path(dst)
        if target.is_dir():
            target = target / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)

    # -- snapshots (home directory archives) ---------------------------
    def _snapdir(self) -> Path:
        p = config.data_dir() / "local-snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def snapshot(self, name: str, tag: str) -> Snapshot:
        self._meta(name)
        path = self._snapdir() / f"{name}--{tag}.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            tar.add(self._dir(name) / "home", arcname="home")
        return Snapshot(name, tag, str(path), time.strftime("%Y-%m-%d %H:%M:%S"))

    def snapshots(self, name: str | None = None) -> list[Snapshot]:
        out = []
        for p in sorted(self._snapdir().glob("*.tar.gz")):
            desk, _, tag = p.name[: -len(".tar.gz")].partition("--")
            if name and desk != name:
                continue
            out.append(
                Snapshot(
                    desk,
                    tag,
                    str(p),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                    f"{p.stat().st_size / 1e6:.1f}MB",
                )
            )
        return out

    def delete_snapshot(self, name: str, tag: str) -> None:
        p = self._snapdir() / f"{name}--{tag}.tar.gz"
        if not p.exists():
            raise NotFound(f"no snapshot {tag!r} for {name!r}")
        p.unlink()

    def _unpack_home(self, name: str, archive: Path) -> None:
        home = self._dir(name) / "home"
        shutil.rmtree(home, ignore_errors=True)
        with tarfile.open(archive) as tar:
            members = [m for m in tar.getmembers() if m.name == "home" or m.name.startswith("home/")]
            for m in members:
                if m.name.startswith("/") or ".." in Path(m.name).parts:
                    raise MinionError(f"unsafe path in snapshot: {m.name}")
            safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            tar.extractall(self._dir(name), members=members, **safe)

    def restore(self, name: str, tag: str, progress=None) -> DesktopInfo:
        archive = self._snapdir() / f"{name}--{tag}.tar.gz"
        if not archive.exists():
            raise NotFound(f"no snapshot {tag!r} for desktop {name!r}")
        self.stop(name)
        self._unpack_home(name, archive)
        self._spawn(name, progress)
        return self.get(name)

    def fork(self, name: str, new_name: str, progress=None) -> DesktopInfo:
        check_name(new_name)
        if self.exists(new_name):
            raise MinionError(f"a desktop named {new_name!r} already exists")
        meta = self._meta(name)
        try:
            prof = profiles.get(meta.get("profile", "base"))
        except NotFound:
            prof = profiles.get("base")
        opts = CreateOptions.from_dict(meta.get("options", {}))
        (self._dir(new_name)).mkdir(parents=True, exist_ok=True)
        shutil.copytree(self._dir(name) / "home", self._dir(new_name) / "home", symlinks=True)
        return self.create(new_name, prof, opts, progress)

    def logs(self, name: str, tail: int = 200) -> str:
        try:
            lines = (self._runtime(name) / "session.log").read_text(errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[-tail:])
