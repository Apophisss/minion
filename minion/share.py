"""`minion share`: give web chat apps (ChatGPT, Claude.ai, Le Chat) a computer, in one command.

It starts a Minion server on this machine with a fresh token and opens a Cloudflare quick tunnel to
it (no account needed): the `cloudflared` program if it is installed, otherwise its official Docker
image. It prints the HTTPS MCP URL to paste into the chat app, and stays in the foreground; Ctrl+C
closes the tunnel and the server, and the URL stops working.

    minion share                 # https://<random words>.trycloudflare.com/mcp?token=...
    minion share --tailscale     # the same server, published with `tailscale funnel` instead

Security model (docs/remote.md): the token is the only key, so the server is dedicated to the share
(its own token, not your `minion serve` one), files on this computer are not reachable unless you pass
--files, and it answers only to loopback names and the tunnel's hostname.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass

from .errors import MinionError

IMAGE = os.environ.get("MINION_CLOUDFLARED_IMAGE", "cloudflare/cloudflared:latest")
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
ORIGIN_DOWN = "Unable to reach the origin service"  # what cloudflared logs when it can't reach our server
DEFAULT_PORT = 4748
CHAT_WAIT = "45"  # seconds a tool may wait before replying "still working, call again": chat apps give up near 60
INSTALL_HELP = "https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/"
GUIDE = "https://github.com/apophisss/minion/blob/main/docs/remote.md"
NO_TUNNEL = (
    "minion share needs cloudflared or Docker. Install cloudflared (macOS: brew install cloudflared, "
    f"Windows: winget install --id Cloudflare.cloudflared, Linux: {INSTALL_HELP}) or Docker, "
    "or publish the server another way (minion share --tailscale)."
)


@dataclass
class TunnelPlan:
    """How cloudflared will run: its command line, and the address of our server as it sees it."""

    argv: list[str]
    origin: str
    via: str  # "cloudflared", or the container engine ("docker", "podman")
    container: str | None = None


def tunnel_plan(
    port: int,
    *,
    cloudflared: str | None = None,
    engine: str | None = None,
    engine_in_vm: bool = False,
    name: str | None = None,
) -> TunnelPlan:
    """Decide how to run a quick tunnel to 127.0.0.1:`port`.

    - cloudflared installed: run it directly; it reaches the server on 127.0.0.1.
    - Otherwise in a container. Docker Engine and Podman on Linux share this computer's network with
      `--network host`, so 127.0.0.1 works. Docker Desktop (macOS, Windows, and its Linux app) and Podman
      machines run containers in a VM, whose 127.0.0.1 is not ours; there the container calls
      host.docker.internal (host.containers.internal for Podman), which Docker Desktop forwards to this
      computer's loopback, so the server can stay on 127.0.0.1.
    The metrics server is kept on loopback: by default cloudflared opens it on every interface, and it
    would tell anyone on the network the tunnel's address."""
    tunnel = ["tunnel", "--metrics", "127.0.0.1:0", "--url"]  # the image's entrypoint adds --no-autoupdate
    if cloudflared:
        origin = f"http://127.0.0.1:{port}"
        return TunnelPlan([cloudflared, "tunnel", "--no-autoupdate", *tunnel[1:], origin], origin, "cloudflared")
    if not engine:
        raise MinionError(NO_TUNNEL)
    kind = "podman" if os.path.basename(engine).lower().startswith("podman") else "docker"
    name = name or f"minion-share-{secrets.token_hex(3)}"
    run = [engine, "run", "--rm", "--name", name, "--label", "dev.minion.share=1"]
    if engine_in_vm:
        host = "host.containers.internal" if kind == "podman" else "host.docker.internal"
        origin = f"http://{host}:{port}"
        return TunnelPlan([*run, IMAGE, *tunnel, origin], origin, kind, name)
    origin = f"http://127.0.0.1:{port}"
    return TunnelPlan([*run, "--network", "host", IMAGE, *tunnel, origin], origin, kind, name)


def find_tunnel_url(line: str) -> str | None:
    m = TUNNEL_URL.search(line)
    return m.group(0) if m and not m.group(0).startswith("https://api.") else None


def share_urls(public: str, token: str, *, compact: bool = False, images: bool = True) -> dict:
    """The URLs to hand out for a server reachable at `public`."""
    extra = ("&compact=1" if compact else "") + ("" if images else "&images=0")
    return {
        "public_url": public,
        "mcp_url": f"{public}/mcp?token={token}{extra}",
        "mcp_endpoint": f"{public}/mcp" + (f"?{extra[1:]}" if extra else ""),  # for clients that send the header
        "authorization": f"Bearer {token}",
        "dashboard_url": f"{public}/?token={token}",
    }


def check_token(token: str) -> str:
    """A token that will sit in a public URL: long, and only URL-safe characters."""
    if not re.fullmatch(r"[A-Za-z0-9._~-]{24,}", token):
        raise MinionError(
            "--token must be at least 24 characters of A-Z a-z 0-9 . _ ~ - (it goes in the URL). "
            'Make one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return token


def engine_in_vm(engine: str) -> bool:
    """Whether the container engine runs containers in a VM instead of on this computer's network."""
    if not sys.platform.startswith("linux"):
        return True  # Docker Desktop, Podman machine, Colima, OrbStack, ...
    try:
        out = subprocess.run(
            [engine, "info", "--format", "{{.OperatingSystem}}"], capture_output=True, text=True, timeout=30
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "docker desktop" in out.lower()


def tailscale_name(binary: str = "tailscale") -> str:
    """This machine's MagicDNS name (e.g. laptop.tail1234.ts.net), the hostname `tailscale funnel` serves."""
    try:
        out = subprocess.run([binary, "status", "--json"], capture_output=True, text=True, timeout=20)
        data = json.loads(out.stdout or "{}")
    except FileNotFoundError:
        raise MinionError("Tailscale is not installed: https://tailscale.com/download") from None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        raise MinionError(f"could not ask Tailscale for this machine's name: {e}") from e
    name = ((data.get("Self") or {}).get("DNSName") or "").rstrip(".")
    if data.get("BackendState") != "Running" or not name:
        raise MinionError("Tailscale is not connected on this machine: run `tailscale up` first")
    return name


def funnel_command(port: int) -> str:
    return f"tailscale funnel {port}"


def describe_call(tool, arguments) -> str:
    """One short line about a tool call, for the activity log in the terminal."""
    args = arguments if isinstance(arguments, dict) else {}
    if tool == "act":
        steps = [a.get("action", "?") for a in args.get("actions") or [] if isinstance(a, dict)]
        detail = ", ".join(steps)
    else:
        detail = args.get("action") or args.get("command") or args.get("target") or args.get("profile") or ""
    detail = " ".join(str(detail).split())
    return f"{tool} {detail[:60] + ('…' if len(detail) > 60 else '')}".rstrip()


class Tunnel:
    """A running cloudflared: its output is collected to find the public URL and to explain failures."""

    def __init__(self, plan: TunnelPlan):
        self.plan = plan
        self.url: str | None = None
        self.origin_down = False
        self.lines: deque = deque(maxlen=40)
        self._found = threading.Event()
        kwargs = (
            {"start_new_session": True}  # Ctrl+C reaches us, and we stop it in order
            if os.name != "nt"
            else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        )
        self.proc = subprocess.Popen(
            plan.argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        threading.Thread(target=self._read, daemon=True, name="minion-tunnel-log").start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())
            if ORIGIN_DOWN in line:
                self.origin_down = True
            if self.url is None and (url := find_tunnel_url(line)):
                self.url = url
                self._found.set()
        self._found.set()  # it exited

    def wait_url(self, timeout: float) -> str | None:
        self._found.wait(timeout)
        return self.url

    def alive(self) -> bool:
        return self.proc.poll() is None

    def log_tail(self, n: int = 12) -> str:
        return "\n".join(f"    {line}" for line in list(self.lines)[-n:])

    def stop(self) -> None:
        if self.plan.container:
            try:
                subprocess.run([self.plan.argv[0], "rm", "-f", self.plan.container], capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def check_public(url: str, token: str, tunnel: Tunnel | None = None, timeout: float = 45) -> tuple[bool, str]:
    """Call the server through its public URL until it answers (the tunnel's DNS name can take a moment)."""
    deadline = time.monotonic() + timeout
    last = "no answer"
    while time.monotonic() < deadline:
        req = urllib.request.Request(
            f"{url}/api/health", headers={"Authorization": f"Bearer {token}", "User-Agent": "minion-share"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return True, ""
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if tunnel is not None and tunnel.origin_down:
                return False, "origin"
        except (urllib.error.URLError, OSError) as e:
            last = str(getattr(e, "reason", e))
        if tunnel is not None and not tunnel.alive():
            return False, "the tunnel stopped"
        time.sleep(2)
    return False, last


def _stop_on_signals() -> dict:
    """Ctrl+C, `kill` and closing the terminal all end up in the same clean stop: the tunnel must not
    outlive the server. Returns the previous handlers, for _restore_signals."""

    def stop(signum, frame):
        raise KeyboardInterrupt

    old = {}
    for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:  # SIGINT may have been ignored (a background job): make it count again
            old[sig] = signal.signal(sig, signal.default_int_handler if name == "SIGINT" else stop)
        except (ValueError, OSError):  # not the main thread
            pass
    return old


def _restore_signals(old: dict) -> None:
    for sig, handler in old.items():
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, TypeError):
            pass


def _prepare_image(engine: str, say) -> None:
    if subprocess.run([engine, "image", "inspect", IMAGE], capture_output=True).returncode == 0:
        return
    say(f"Downloading {IMAGE} (once, about 30 MB)…")
    res = subprocess.run([engine, "pull", IMAGE], capture_output=True, text=True)
    if res.returncode != 0:
        raise MinionError(f"could not download {IMAGE}: {(res.stderr or res.stdout).strip()[-500:]}")


def _images_hint() -> str | None:
    """A warning when desktops can't start (no container engine running), or a tip when no desktop image is
    downloaded yet: the first desktop would take minutes, and chat apps stop waiting after about a minute."""
    try:
        from . import config, profiles
        from .backends import get_backend

        be = get_backend()
        ready, detail = be.available()
        if not ready:
            return f"Desktops can't start yet ({detail}): start Docker, and check with `minion doctor`."
        if be.name != "docker":
            return None
        if any(be.image_labels(profiles.get(n).image) is not None for n in profiles.names()):
            return None
        return (
            f"No desktop image is downloaded yet. Run `minion pull {config.DEFAULT_PROFILE}` (and any other profile "
            "you want) first: chat apps stop waiting for a tool after about a minute."
        )
    except Exception:
        return None


def run(args) -> int:
    from . import config
    from . import server as srv
    from .backends import get_backend
    from .cli import c, err, info, ok
    from .reaper import start_reaper

    for stream in (sys.stdout, sys.stderr):  # the URL must show up at once, even through a pipe or a log file
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass
    as_json = bool(getattr(args, "json", False))
    say = (lambda text: print(text, file=sys.stderr, flush=True)) if as_json else (lambda text: info(text))
    token = check_token(args.token) if args.token else secrets.token_urlsafe(32)
    os.environ.setdefault("MINION_MCP_CREATE_WAIT", CHAT_WAIT)  # reply "still preparing" before chat apps give up

    cloudflared = engine = ts_name = None
    in_vm = False
    if args.tailscale:
        ts_name = tailscale_name()
    else:
        cloudflared = None if args.docker else shutil.which("cloudflared")
        if not cloudflared:
            engine = os.environ.get("MINION_DOCKER") or shutil.which("docker") or shutil.which("podman")
            if not engine:
                raise MinionError(NO_TUNNEL)
            in_vm = engine_in_vm(engine)
            _prepare_image(engine, say)

    # Explicit Host names keep the Host check on whatever the bind address; the tunnel's name is added below.
    vm_names = ("host.docker.internal", "host.containers.internal")
    httpd, local, token = srv.make_server(
        args.bind, args.port, token, quiet=True, fallback=True, allowed_hosts=vm_names
    )
    handler = httpd.RequestHandlerClass
    port = httpd.server_address[1]
    handler.host_files = bool(args.files)
    handler.wait_cap = float(CHAT_WAIT)
    if not as_json:
        handler.activity = lambda tool, arguments, client: print(
            c(f"  {time.strftime('%H:%M:%S')}  {describe_call(tool, arguments)}  ({client})", "2"), flush=True
        )
    threading.Thread(target=httpd.serve_forever, daemon=True, name="minion-share-http").start()
    idle = float(os.environ.get("MINION_IDLE_FREEZE", "600") or 0)
    if idle > 0:
        start_reaper(get_backend(), idle)

    tunnel = None
    signals = _stop_on_signals()
    try:
        if ts_name:
            public = f"https://{ts_name}"
            how = "Tailscale Funnel"
        else:
            plan = tunnel_plan(port, cloudflared=cloudflared, engine=engine, engine_in_vm=in_vm)
            say(f"Opening a Cloudflare quick tunnel ({'cloudflared' if plan.via == 'cloudflared' else plan.via})…")
            tunnel = Tunnel(plan)
            public = tunnel.wait_url(90)
            if not public:
                raise MinionError("cloudflared did not get a tunnel URL. Its last output:\n" + tunnel.log_tail())
            how = "Cloudflare quick tunnel" + (f", cloudflared in {plan.via}" if plan.container else "")
        handler.extra_hosts = handler.extra_hosts | {public.split("://", 1)[1].lower()}
        handler.public_url = public
        urls = share_urls(public, token, compact=args.compact, images=not args.no_images)
        urls["local_url"] = f"{local}/?token={token}"

        if ts_name:
            reachable, why = True, ""
        else:
            say("Checking the public URL…")
            reachable, why = check_public(public, token, tunnel)
            if not reachable and why == "origin":
                raise MinionError(
                    f"cloudflared runs but cannot reach Minion at {plan.origin}. Install cloudflared on this "
                    f"computer instead of using {plan.via} ({INSTALL_HELP}), or run `minion share --bind 0.0.0.0` "
                    "(the server then also listens on your network; the token still protects it)."
                )

        if as_json:
            print(json.dumps({**urls, "via": how, "verified": reachable}), flush=True)
        else:
            print()
            if ts_name:
                ok(f"Minion is ready for {c(public, '1')}: publish it with the `tailscale funnel` command below")
            else:
                ok(f"Minion is online at {c(public, '1')}  ({how})")
            if not reachable:
                err(f"could not reach it from this computer yet ({why}); it may still work in a minute")
            print()
            print("  MCP server URL (ChatGPT, Claude.ai, Le Chat: add a custom connector, no sign-in):")
            print("    " + c(urls["mcp_url"], "36"))
            print("  Apps that send headers (Cursor, VS Code, Claude Code): URL " + urls["mcp_endpoint"])
            print("    with the header  Authorization: " + urls["authorization"])
            print("  Live view (watch and take over):")
            print("    " + urls["dashboard_url"])
            print("    " + urls["local_url"] + "  (this computer only)")
            print()
            print(c("  ! Anyone with this URL can use every Minion desktop on this computer: run programs in", "33"))
            print(c("    them, read their screens and files. Keep it private and press Ctrl+C when you're done.", "33"))
            if not args.files:
                print(c("    Files on this computer stay private (--files allows upload/download in", "2"))
                print(c(f"    {os.environ.get('MINION_FILES_ROOT') or config.data_dir() / 'files'}).", "2"))
            hint = _images_hint()
            if hint:
                print(c("  Tip: " + hint, "2"))
            if ts_name:
                print()
                print(f"  Now publish it, in another terminal:  {c(funnel_command(port), '1')}")
                print("  (Funnel must be allowed for your tailnet; the first run explains how.)")
                if not args.token:
                    print("  Tip: pass --token to keep the same URL next time (the Funnel hostname doesn't change).")
            print(f"  Guide: {GUIDE}")
            print()
            print(c("Sharing. Press Ctrl+C to stop; the URL stops working with it.", "1"))
        while tunnel is None or tunnel.alive():
            time.sleep(0.5)
        raise MinionError("the tunnel stopped. cloudflared said:\n" + tunnel.log_tail())
    except KeyboardInterrupt:
        if not as_json:
            print()
            ok("stopped sharing")
        return 0
    finally:
        if tunnel is not None:
            tunnel.stop()
        httpd.shutdown()
        httpd.server_close()
        _restore_signals(signals)
