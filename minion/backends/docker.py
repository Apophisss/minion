"""Docker (or Podman) backend: one container per desktop, driven through `docker exec`.

No ports are published and nothing listens on the network: the host talks to the
in-desktop agent over the stdin/stdout of `docker exec`. That also makes it work
the same with Docker Desktop (macOS/Windows), remote DOCKER_HOSTs and Podman.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from .. import config, profiles
from ..agent import VERSION
from ..channel import Channel, ProcessTransport
from ..errors import BackendError, MinionError, NotFound
from ..profiles import Profile
from .base import Backend, CreateOptions, DesktopInfo, Login, Snapshot, check_login, check_name

PKG_DIR = Path(__file__).resolve().parent.parent
AGENT_DIR = PKG_DIR / "agent"
BASE_DOCKERFILE = PKG_DIR / "images" / "base.Dockerfile"
BRIDGE = "/opt/minion/minion_agent/bridge.py"
HOME = "/home/agent"
SNAPSHOT_REPO = "minion-snapshot"
LOGIN_REPO = "minion-login"  # saved sign-ins: snapshots that new desktops start from
L = config.LABEL


def agent_tar(arc_prefix: str = "minion_agent") -> bytes:
    """The agent package as a tar stream (no caches), owned by root and world-readable."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:

        def add(info: tarfile.TarInfo):
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o755 if info.isdir() else 0o644
            return info

        top = tarfile.TarInfo(arc_prefix)
        top.type = tarfile.DIRTYPE
        tar.addfile(add(top))
        for path in sorted(AGENT_DIR.rglob("*")):
            rel = path.relative_to(AGENT_DIR)
            if "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo"):
                continue
            tar.add(path, arcname=f"{arc_prefix}/{rel.as_posix()}", recursive=False, filter=add)
    return buf.getvalue()


def expand_home(path: str) -> str:
    if path == "~":
        return HOME
    if path.startswith("~/"):
        return HOME + path[1:]
    if not path.startswith("/"):
        return f"{HOME}/{path}"
    return path


def _parse_size_bytes(text: str) -> int | None:
    text = text.strip()
    units = {
        "b": 1,
        "kib": 1024,
        "kb": 1000,
        "mib": 1024**2,
        "mb": 1000**2,
        "gib": 1024**3,
        "gb": 1000**3,
        "tib": 1024**4,
        "tb": 1000**4,
    }
    num = "".join(c for c in text if c.isdigit() or c == ".")
    unit = text[len(num) :].strip().lower()
    try:
        return int(float(num) * units.get(unit, 1))
    except ValueError:
        return None


def cli_dirs() -> list[str]:
    """Where Docker and Podman put their commands. Apps launched from the GUI (Claude Desktop on macOS)
    start MCP servers with a minimal PATH that often misses these folders."""
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
        return [os.path.join(program_files, "Docker", "Docker", "resources", "bin")]
    home = os.path.expanduser("~")
    return [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        os.path.join(home, ".docker", "bin"),
        "/Applications/Docker.app/Contents/Resources/bin",
        os.path.join(home, ".orbstack", "bin"),
        os.path.join(home, ".rd", "bin"),  # Rancher Desktop
        "/opt/podman/bin",
    ]


def find_cli(*names: str) -> str | None:
    """The first of `names` on PATH (returned as is), else the full path of the first one found in `cli_dirs()`.
    That folder is then added to PATH, so the CLI also finds its helpers (docker-credential-desktop, ...)."""
    for name in names:
        if shutil.which(name):
            return name
    for name in names:
        for folder in cli_dirs():
            found = shutil.which(name, path=folder)
            if found:
                path = os.environ.get("PATH", "")
                if folder not in path.split(os.pathsep):
                    os.environ["PATH"] = path + os.pathsep + folder if path else folder
                return found
    return None


class DockerBackend(Backend):
    name = "docker"

    def __init__(self, binary: str | None = None):
        wanted = binary or os.environ.get("MINION_DOCKER")
        if wanted:  # a bare name is looked up like docker itself; a path is used as is
            self.bin = wanted if os.path.dirname(wanted) else (find_cli(wanted) or wanted)
        else:
            self.bin = find_cli("docker", "podman") or "docker"
        self._awake: dict[str, float] = {}  # desktop -> when we last saw it running

    # -- plumbing ------------------------------------------------------
    def _run(
        self, *args: str, input: bytes | None = None, timeout: float = 300, check: bool = True
    ) -> subprocess.CompletedProcess:
        try:
            res = subprocess.run([self.bin, *args], input=input, capture_output=True, timeout=timeout)
        except FileNotFoundError as e:
            raise BackendError(
                f"`{self.bin}` was not found. Install Docker (https://docs.docker.com/get-docker/) "
                "or Podman, or on Linux use the local backend: MINION_BACKEND=local"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise BackendError(f"`{self.bin} {args[0]}` timed out after {timeout:.0f}s") from e
        if check and res.returncode != 0:
            err = (res.stderr or res.stdout).decode("utf-8", "replace").strip()
            raise BackendError(f"{self.bin} {args[0]} failed: {err[-1500:]}")
        return res

    def _stream(self, args: list[str], progress=None, cwd: str | None = None) -> tuple[int, str]:
        try:
            proc = subprocess.Popen(
                [self.bin, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=cwd,
                text=True,
                errors="replace",
            )
        except FileNotFoundError as e:
            raise BackendError(f"`{self.bin}` was not found") from e
        tail: list[str] = []
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail = (tail + [line])[-40:]
            if progress:
                progress(line)
        return proc.wait(), "\n".join(tail)

    def _has_buildx(self) -> bool:
        if not hasattr(self, "_buildx"):
            try:
                self._buildx = (
                    os.path.basename(self.bin).startswith("docker")
                    and self._run("buildx", "version", check=False, timeout=20).returncode == 0
                )
            except BackendError:
                self._buildx = False
        return self._buildx

    def cname(self, name: str) -> str:
        return config.CONTAINER_PREFIX + name

    def available(self) -> tuple[bool, str]:
        try:
            res = self._run("version", "--format", "{{.Server.Version}}", timeout=20, check=False)
        except BackendError as e:
            return False, str(e)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", "replace").strip().splitlines()
            return False, (err[-1] if err else "the Docker daemon is not reachable") + " — is Docker running?"
        return True, f"{self.bin} {res.stdout.decode().strip()}"

    # -- images --------------------------------------------------------
    def image_labels(self, ref: str) -> dict | None:
        res = self._run("image", "inspect", ref, "--format", "{{json .Config.Labels}}", check=False, timeout=30)
        if res.returncode != 0:
            return None
        try:
            return json.loads(res.stdout.decode()) or {}
        except json.JSONDecodeError:
            return {}

    def pull(self, ref: str, progress=None) -> bool:
        if progress:
            progress(f"Pulling {ref} ...")
        code, _ = self._stream(["pull", ref], progress)
        return code == 0

    def build(self, profile: Profile, progress=None, pull: str | None = None) -> str:
        ref = profile.image
        with tempfile.TemporaryDirectory(prefix="minion-build-") as ctx:
            ctxp = Path(ctx)
            if profile.name == "base":
                shutil.copytree(
                    AGENT_DIR, ctxp / "agent", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
                )
                shutil.copy(BASE_DOCKERFILE, ctxp / "Dockerfile")
                with open(ctxp / "Dockerfile", "a") as f:
                    f.write(f'LABEL dev.minion.fingerprint="{profile.fingerprint()}"\n')
            else:
                parent = profile.parent()
                parent_ref = self.prepare(parent, progress, pull)
                (ctxp / "Dockerfile").write_text(profile.dockerfile(parent_ref))
                for path, content in profile.files.items():
                    target = ctxp / "files" / path.lstrip("/")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content.lstrip("\n"))
            args = ["build", "-t", ref]
            if self._has_buildx():
                args.append("--progress=plain")
            args.append(str(ctxp))
            if progress:
                progress(f"Building {ref} (profile {profile.name!r}) — this can take a few minutes ...")
            code, tail = self._stream(args, progress)
            if code != 0:
                raise BackendError(f"building {ref} failed:\n{tail}")
        return ref

    def prepare(self, profile: Profile, progress=None, pull: str | None = None) -> str:
        """Pull or build the image for a profile (and its parents) if it is missing."""
        pull = (pull or os.environ.get("MINION_PULL", "auto")).lower()
        ref = profile.image
        labels = self.image_labels(ref)
        if labels is not None and pull != "always":
            if profile.builtin or labels.get("dev.minion.fingerprint") == profile.fingerprint():
                return ref
            if progress:
                progress(f"Profile {profile.name!r} changed; rebuilding {ref}")
            return self.build(profile, progress, pull)
        if profile.builtin and pull != "never":
            if self.pull(ref, progress):
                return ref
            if labels is not None:
                return ref
            if progress:
                progress(f"Could not pull {ref}; building it locally instead.")
        return self.build(profile, progress, pull)

    # -- desktops ------------------------------------------------------
    def _inspect(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        res = self._run("inspect", *ids, check=False, timeout=60)
        try:
            return json.loads(res.stdout.decode() or "[]")
        except json.JSONDecodeError:
            return []

    def _to_info(self, c: dict) -> DesktopInfo:
        labels = c.get("Config", {}).get("Labels") or {}
        status = c.get("State", {}).get("Status", "unknown")
        state = {"exited": "stopped", "dead": "stopped", "removing": "stopped", "restarting": "running"}.get(
            status, status
        )
        try:
            options = json.loads(labels.get(f"{L}.options") or "{}")
        except json.JSONDecodeError:
            options = {}
        ports = {}
        for key, binds in (c.get("NetworkSettings", {}).get("Ports") or {}).items():
            if binds:
                ports[key.split("/")[0]] = f"{binds[0].get('HostIp', '127.0.0.1')}:{binds[0].get('HostPort')}"
        return DesktopInfo(
            name=labels.get(f"{L}.name") or c.get("Name", "").lstrip("/").removeprefix(config.CONTAINER_PREFIX),
            profile=labels.get(f"{L}.profile", ""),
            state=state,
            backend=self.name,
            size=labels.get(f"{L}.size", ""),
            created=float(labels.get(f"{L}.created", 0) or 0),
            image=c.get("Config", {}).get("Image", ""),
            id=c.get("Id", "")[:12],
            options=options,
            ports=ports,
        )

    def list(self, stats: bool = False) -> list[DesktopInfo]:
        res = self._run("ps", "-a", "-q", "--filter", f"label={L}=1", timeout=30)
        ids = res.stdout.decode().split()
        infos = [self._to_info(c) for c in self._inspect(ids)]
        infos.sort(key=lambda d: d.created)
        if stats:
            running = [self.cname(d.name) for d in infos if d.state == "running"]
            if running:
                out = self._run("stats", "--no-stream", "--format", "{{json .}}", *running, check=False, timeout=60)
                by_name = {}
                for line in out.stdout.decode().splitlines():
                    try:
                        s = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    by_name[s.get("Name", "")] = s
                for d in infos:
                    s = by_name.get(self.cname(d.name))
                    if s:
                        d.memory = _parse_size_bytes(str(s.get("MemUsage", "")).split("/")[0])
                        try:
                            d.cpu = float(str(s.get("CPUPerc", "0")).rstrip("%"))
                        except ValueError:
                            d.cpu = None
        return infos

    def get(self, name: str) -> DesktopInfo:
        found = self._inspect([self.cname(name)])
        if not found or (found[0].get("Config", {}).get("Labels") or {}).get(L) != "1":
            raise NotFound(f"no desktop named {name!r} (see `minion ls`)")
        return self._to_info(found[0])

    def exists(self, name: str) -> bool:
        try:
            self.get(name)
            return True
        except NotFound:
            return False

    def create(
        self, name: str, profile: Profile, options: CreateOptions, progress=None, login: Login | None = None
    ) -> DesktopInfo:
        check_name(name)
        if self.exists(name):
            raise MinionError(f"a desktop named {name!r} already exists")
        if login is not None:  # start from the saved sign-in's snapshot, signed in as it was
            return self._create_from(
                name, login.ref, profile, options, progress, extra_labels={f"{L}.login": login.name}
            )
        image = self.prepare(profile, progress)
        return self._create_from(name, image, profile, options, progress)

    def _create_from(
        self,
        name: str,
        image: str,
        profile: Profile,
        options: CreateOptions,
        progress=None,
        extra_labels: dict | None = None,
    ) -> DesktopInfo:
        c = self.cname(name)
        apps = [a.to_dict() for a in profile.merged("apps")]
        env = {**profile.merged("env"), **options.env}
        opts = options.to_dict()
        args = [
            "create",
            "--name",
            c,
            "--hostname",
            name,
            "--label",
            f"{L}=1",
            "--label",
            f"{L}.name={name}",
            "--label",
            f"{L}.profile={profile.name}",
            "--label",
            f"{L}.size={options.size}",
            "--label",
            f"{L}.created={int(time.time())}",
            "--label",
            f"{L}.version={VERSION}",
            "--label",
            f"{L}.options={json.dumps(opts)}",
            "--shm-size",
            options.shm or profile.merged("shm") or "256m",
        ]
        for k, v in (extra_labels or {}).items():
            args += ["--label", f"{k}={v}"]
        memory = options.memory or profile.merged("memory")
        if memory:
            args += ["--memory", memory]
        cpus = options.cpus or profile.merged("cpus")
        if cpus:
            args += ["--cpus", cpus]
        if not options.network:
            args += ["--network", "none"]
        for m in options.mounts:
            args += ["-v", m]
        for p in options.ports:
            args += ["-p", f"127.0.0.1::{p}"]
        envs = {
            "MINION_SCREEN": options.size,
            "MINION_NAME": name,
            "MINION_PROFILE": profile.name,
            "MINION_APPS": json.dumps(apps),
            "MINION_AUTOSTART": json.dumps(profile.merged("autostart")),
            **env,
        }
        for k, v in envs.items():
            args += ["-e", f"{k}={v}"]
        args.append(image)
        if progress:
            progress(f"Starting desktop {name!r} ({profile.name}, {options.size}) ...")
        self._run(*args, timeout=120)
        try:
            self._sync_agent(c)
            self._run("start", c, timeout=120)
            self._wait_ready(name)
        except Exception as e:
            logs = self.logs(name, 30)
            self._run("rm", "-f", c, check=False, timeout=60)
            if logs:
                raise BackendError(f"desktop {name!r} failed to start:\n{logs}") from e
            raise
        return self.get(name)

    def _sync_agent(self, container: str) -> None:
        """Copy this host's agent code into the desktop, so host and agent always match."""
        self._run("cp", "-", f"{container}:/opt/minion/", input=agent_tar(), timeout=60)

    def _wait_ready(self, name: str, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            ch = self.channel(name)
            try:
                ch.call("hello", timeout=35)
                return
            except Exception as e:  # not up yet
                last = str(e)
            finally:
                ch.close()
            info = self.get(name)
            if info.state not in ("running", "created"):
                break
            time.sleep(0.3)
        raise BackendError(f"desktop {name!r} did not become ready: {last}")

    def remove(self, name: str) -> None:
        self.get(name)
        self._run("rm", "-f", self.cname(name), timeout=120)

    def start(self, name: str) -> None:
        info = self.get(name)
        if info.state == "paused":
            self.thaw(name)
            return
        if info.state != "running":
            self._sync_agent(self.cname(name))
            self._run("start", self.cname(name), timeout=120)
            self._wait_ready(name)

    def stop(self, name: str) -> None:
        self._awake.pop(name, None)
        info = self.get(name)
        if info.state == "paused":
            self._run("unpause", self.cname(name), check=False)
        self._run("stop", "-t", "5", self.cname(name), timeout=60)

    def freeze(self, name: str) -> None:
        self._awake.pop(name, None)
        info = self.get(name)
        if info.state == "running":
            self._run("pause", self.cname(name))
        elif info.state != "paused":
            raise MinionError(f"desktop {name!r} is {info.state}; only running desktops can be frozen")

    def thaw(self, name: str) -> None:
        info = self.get(name)
        if info.state == "paused":
            self._run("unpause", self.cname(name))

    def ensure_awake(self, name: str) -> None:
        """A paused container freezes our open `docker exec` bridge too: unpause before writing.
        The state is cached for a second so bursts of calls cost one `docker inspect`."""
        now = time.monotonic()
        cache = self._awake
        if now - cache.get(name, -10.0) < 1.0:
            return
        res = self._run("inspect", "-f", "{{.State.Status}}", self.cname(name), check=False, timeout=20)
        status = res.stdout.decode().strip()
        if status == "paused":
            self._run("unpause", self.cname(name), check=False, timeout=30)
        elif status in ("exited", "created", "dead"):
            self.start(name)
        cache[name] = time.monotonic()

    def channel(self, name: str) -> Channel:
        cmd = [self.bin, "exec", "-i", self.cname(name), "python3", "-S", BRIDGE]
        return Channel(lambda: ProcessTransport(cmd), label=f"desktop {name!r}")

    def copy_in(self, name: str, src: str, dst: str) -> None:
        if not os.path.exists(src):
            raise NotFound(f"{src} does not exist")
        c = self.cname(name)
        dst = expand_home(dst)
        into_dir = dst.endswith("/") or self._run("exec", c, "test", "-d", dst, check=False, timeout=30).returncode == 0
        target = f"{dst.rstrip('/')}/{os.path.basename(os.path.normpath(src))}" if into_dir else dst
        self._run("cp", src, f"{c}:{dst}", timeout=600)
        if target.startswith((HOME + "/", "/tmp/")):  # never chown system directories
            self._run("exec", "-u", "root", c, "chown", "-R", "agent:agent", target, check=False, timeout=120)

    def copy_out(self, name: str, src: str, dst: str) -> None:
        self._run("cp", f"{self.cname(name)}:{expand_home(src)}", dst, timeout=600)

    # -- snapshots -----------------------------------------------------
    @staticmethod
    def _check_tag(tag: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_.-]{0,60}$", tag or ""):
            raise MinionError(f"invalid snapshot tag {tag!r}: use lowercase letters, digits, '.', '-' and '_'")
        return tag

    def _commit(self, source: str, owner: str, tag: str) -> Snapshot:
        ref = f"{SNAPSHOT_REPO}:{owner}--{self._check_tag(tag)}"
        self._run("commit", "--change", f"LABEL {L}.snapshot={tag}", self.cname(source), ref, timeout=900)
        return Snapshot(owner, tag, ref, time.strftime("%Y-%m-%d %H:%M:%S"))

    def snapshot(self, name: str, tag: str) -> Snapshot:
        self._check_tag(tag)
        self.get(name)
        return self._commit(name, name, tag)

    def snapshots(self, name: str | None = None) -> list[Snapshot]:
        res = self._run("images", SNAPSHOT_REPO, "--format", "{{json .}}", check=False, timeout=60)
        out = []
        for line in res.stdout.decode().splitlines():
            try:
                img = json.loads(line)
            except json.JSONDecodeError:
                continue
            tag = img.get("Tag", "")
            if "--" not in tag:
                continue
            desk, snap = tag.split("--", 1)
            if name and desk != name:
                continue
            out.append(Snapshot(desk, snap, f"{SNAPSHOT_REPO}:{tag}", img.get("CreatedSince", ""), img.get("Size", "")))
        return out

    def delete_snapshot(self, name: str, tag: str) -> None:
        self._run("rmi", f"{SNAPSHOT_REPO}:{name}--{self._check_tag(tag)}", timeout=120)

    # -- saved sign-ins ------------------------------------------------
    supports_logins = True

    def save_login(self, name: str, login: str, site: str = "") -> Login:
        """Snapshot desktop `name` as the sign-in `login` (replacing one of that name). The desktop keeps
        running; new desktops made with it start as this one is now."""
        check_login(login)
        info = self.get(name)
        ref = f"{LOGIN_REPO}:{login}"
        # (a LABEL value is parsed: no quotes, backslashes or $variables in it)
        site = " ".join(re.sub(r'["\\$`]', "", str(site or "")).split())[:200]
        changes = [
            f"LABEL {L}.login={login}",
            f"LABEL {L}.login.profile={info.profile}",
            f'LABEL {L}.login.site="{site}"',
            f"LABEL {L}.login.from={name}",
        ]
        args = [a for ch in changes for a in ("--change", ch)]
        self._run("commit", *args, self.cname(name), ref, timeout=900)
        return Login(login, info.profile, ref, site, time.strftime("%Y-%m-%d %H:%M:%S"))

    def logins(self) -> list[Login]:
        res = self._run("images", LOGIN_REPO, "--format", "{{json .}}", check=False, timeout=60)
        out = []
        for line in res.stdout.decode().splitlines():
            try:
                img = json.loads(line)
            except json.JSONDecodeError:
                continue
            tag = img.get("Tag", "")
            if not tag or tag == "<none>":
                continue
            ref = f"{LOGIN_REPO}:{tag}"
            labels = self.image_labels(ref) or {}
            profile = labels.get(f"{L}.login.profile") or labels.get(f"{L}.profile", "")
            site = labels.get(f"{L}.login.site", "")
            out.append(Login(tag, profile, ref, site, img.get("CreatedSince", ""), img.get("Size", "")))
        return sorted(out, key=lambda x: x.name)

    def delete_login(self, login: str) -> None:
        check_login(login)
        if not any(x.name == login for x in self.logins()):
            raise NotFound(f"no saved sign-in {login!r} (see `minion login list`)")
        # -f: desktops started from it keep running; only the name goes
        self._run("rmi", "-f", f"{LOGIN_REPO}:{login}", timeout=120)

    def _profile_for(self, info: DesktopInfo) -> Profile:
        try:
            return profiles.get(info.profile)
        except NotFound:
            return Profile(name=info.profile or "custom", builtin=False)

    def restore(self, name: str, tag: str, progress=None) -> DesktopInfo:
        info = self.get(name)
        ref = f"{SNAPSHOT_REPO}:{name}--{self._check_tag(tag)}"
        if self.image_labels(ref) is None:
            raise NotFound(f"no snapshot {tag!r} for desktop {name!r} (see `minion snapshots {name}`)")
        options = CreateOptions.from_dict(info.options)
        self._run("rm", "-f", self.cname(name), timeout=120)
        return self._create_from(name, ref, self._profile_for(info), options, progress)

    def fork(self, name: str, new_name: str, progress=None) -> DesktopInfo:
        check_name(new_name)
        if self.exists(new_name):
            raise MinionError(f"a desktop named {new_name!r} already exists")
        info = self.get(name)
        if progress:
            progress(f"Snapshotting {name!r} ...")
        snap = self._commit(name, new_name, f"forked-from-{name}")
        options = CreateOptions.from_dict(info.options)
        return self._create_from(
            new_name, snap.ref, self._profile_for(info), options, progress, extra_labels={f"{L}.forked_from": name}
        )

    def logs(self, name: str, tail: int = 200) -> str:
        res = self._run("logs", "--tail", str(tail), self.cname(name), check=False, timeout=30)
        return (res.stdout + res.stderr).decode("utf-8", "replace").strip()
