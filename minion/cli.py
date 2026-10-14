"""The `minion` command line. Built for people and for agents with a shell."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, config, profiles
from .backends import get_backend
from .desktop import ActResult, Desktop, normalize_size
from .errors import MinionError, NotFound

# -- output helpers ----------------------------------------------------------
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def ok(text: str) -> None:
    print(c("✓ ", "32") + text)


def info(text: str) -> None:
    print(c(text, "2"))


def err(text: str) -> None:
    print(c("✗ ", "31") + text, file=sys.stderr)


def progress_printer(line: str) -> None:
    line = line.strip()
    if not line:
        return
    if len(line) > 160:
        line = line[:157] + "..."
    sys.stderr.write(c("  " + line, "2") + "\n")
    sys.stderr.flush()


def human_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit in ("B", "KB") else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def human_age(seconds: float) -> str:
    if seconds <= 0:
        return "-"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return f"{int(seconds)}s"


def emit_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


# -- desktop resolution --------------------------------------------------------
def desktop(args) -> Desktop:
    name = getattr(args, "desktop", None) or os.environ.get("MINION_DESKTOP")
    d = Desktop.attach(name)
    if name:
        config.update_state(current=d.name)
    return d


def act_and_print(args, *actions, **kw) -> int:
    d = desktop(args)
    res: ActResult = d.act(*actions, check=False, screenshot=bool(getattr(args, "shot", None)), **kw)
    if args.json:
        emit_json({k: v for k, v in res.__dict__.items() if k not in ("screenshot", "observation")})
    else:
        print(res.summary)
    if res.screenshot is not None:
        path = args.shot
        res.screenshot.save(path)
        info(f"screenshot → {path}")
    return 0 if res.ok else 1


REMOTE_RE = re.compile(r"^([a-z0-9][a-z0-9_-]*)?:([^\\].*)$")


def split_remote(path: str) -> tuple[str | None, str] | None:
    """'office-1:~/a.txt' -> ('office-1', '~/a.txt'); ':~/a.txt' -> (None, '~/a.txt')."""
    if re.match(r"^[A-Za-z]:\\", path):  # a Windows drive path
        return None
    m = REMOTE_RE.match(path)
    if not m:
        return None
    return m.group(1), m.group(2)


# -- commands ------------------------------------------------------------------
def cmd_up(args) -> int:
    profile = args.profile or config.DEFAULT_PROFILE
    t0 = time.time()
    d = Desktop.create(
        profile, name=args.name, size=args.size, memory=args.memory or "", cpus=args.cpus or "",
        network=not args.offline, mounts=args.mount or [], env=dict(kv.split("=", 1) for kv in args.env or []),
        ports=args.port or [], progress=None if args.quiet else progress_printer,
    )
    hello = d.hello()
    if args.json:
        emit_json({**d.to_dict(), "apps": hello.get("apps", []), "ready_in": round(time.time() - t0, 2)})
        return 0
    ok(f"{c(d.name, '1')} is ready  ({profile} · {'x'.join(map(str, hello['screen']))} · "
       f"{time.time() - t0:.1f}s)")
    if hello.get("apps"):
        info(f"  Apps: {', '.join(hello['apps'])}")
    info(f"  Next: minion see · minion open {(hello.get('apps') or ['<url>'])[-1].lower().split()[0]}"
         " · minion view")
    if args.view:
        return cmd_view(argparse.Namespace(desktop=d.name, json=False, no_open=False))
    return 0


def cmd_ls(args) -> int:
    desks = Desktop.list(stats=not args.fast)
    if args.json:
        emit_json([d.to_dict() for d in desks])
        return 0
    if not desks:
        info("No desktops yet. Create one:  minion up browser   (profiles: minion profiles)")
        return 0
    current = config.load_state().get("current")
    rows = [("NAME", "PROFILE", "STATE", "SIZE", "MEMORY", "CPU", "AGE")]
    for d in desks:
        mark = "*" if d.name == current else " "
        cpu = f"{d.cpu:.1f}%" if d.cpu is not None else "-"
        rows.append((mark + d.name, d.profile, d.state, d.size, human_bytes(d.memory), cpu, human_age(d.age)))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for i, r in enumerate(rows):
        line = "  ".join(col.ljust(w) for col, w in zip(r, widths)).rstrip()
        if i == 0:
            line = c(" " + line, "2")
        elif "paused" in r[2]:
            line = line.replace("paused", c("frozen", "36"))
        elif "running" in r[2]:
            line = line.replace("running", c("running", "32"))
        print(line)
    return 0


def cmd_rm(args) -> int:
    be = get_backend()
    names = [d.name for d in be.list()] if args.all else args.names
    if not names:
        name = getattr(args, "desktop", None)
        names = [name] if name else [Desktop.attach().name]
    code = 0
    for n in names:
        try:
            Desktop(n, be).remove()
            ok(f"removed {n}")
        except MinionError as e:
            err(str(e))
            code = 1
    return code


def _named(args) -> Desktop:
    name = getattr(args, "name", None) or getattr(args, "desktop", None)
    return Desktop.attach(name)


def cmd_simple(method: str, verb: str):
    def run(args) -> int:
        d = _named(args)
        getattr(d, method)()
        ok(f"{verb} {d.name}")
        return 0
    return run


def cmd_use(args) -> int:
    d = Desktop.attach(args.name)
    config.update_state(current=d.name)
    ok(f"current desktop: {d.name}")
    return 0


def cmd_fork(args) -> int:
    d = _named(args)
    new = d.fork(args.new, progress=progress_printer)
    ok(f"forked {d.name} → {c(new.name, '1')}")
    return 0


def cmd_snapshot(args) -> int:
    d = _named(args)
    tag = d.snapshot(args.tag)
    ok(f"snapshot {c(tag, '1')} of {d.name} saved (restore: minion restore {tag} -d {d.name})")
    return 0


def cmd_snapshots(args) -> int:
    be = get_backend()
    snaps = be.snapshots(args.name)
    if args.json:
        emit_json([s.to_dict() for s in snaps])
        return 0
    if not snaps:
        info("No snapshots yet:  minion snapshot [NAME] [TAG]")
        return 0
    for s in snaps:
        print(f"{s.desktop:20} {s.tag:28} {s.created:16} {s.size}")
    return 0


def cmd_restore(args) -> int:
    d = desktop(args)
    d.restore(args.tag)
    ok(f"{d.name} restored to {args.tag}")
    return 0


def cmd_profiles(args) -> int:
    reg = profiles.load_all()
    if args.show:
        p = profiles.get(args.show)
        if args.json:
            emit_json({**p.summary(), "packages": p.packages, "tips": p.tips})
        else:
            print(c(f"{p.icon} {p.title or p.name}", "1") + c(f"  ({p.name}, extends {p.extends})", "2"))
            print(p.description)
            print(c("Apps: ", "2") + ", ".join(a.name for a in p.merged("apps")))
            if p.packages:
                print(c("Packages: ", "2") + " ".join(p.packages))
            print(c("Image: ", "2") + p.image)
            if p.tips:
                print(c("Tips for agents:", "2"))
                print(p.tips)
        return 0
    items = [reg[n].summary() for n in profiles.names(reg)]
    if args.json:
        emit_json(items)
        return 0
    for s in items:
        tag = "" if s["builtin"] else c(" (custom)", "36")
        print(f"{s['icon'] or '•'} {c(s['name'], '1'):<22}{tag} {s['description']}")
    info(f"\nCreate one: minion up <profile>   ·   Custom profiles: {config.user_profiles_dir()}/*.toml")
    return 0


def cmd_build(args) -> int:
    be = get_backend()
    names = profiles.names() if args.all else (args.profiles or [config.DEFAULT_PROFILE])
    for n in names:
        p = profiles.get(n)
        t0 = time.time()
        if hasattr(be, "build"):
            ref = be.build(p, progress=None if args.quiet else progress_printer, pull="never")
            ok(f"built {ref} in {time.time() - t0:.0f}s")
            if args.push:
                be._stream(["push", ref], progress_printer)
        else:
            info(f"{be.name} backend needs no images")
    return 0


def cmd_pull(args) -> int:
    be = get_backend()
    for n in args.profiles or [config.DEFAULT_PROFILE]:
        ref = be.prepare(profiles.get(n), progress=progress_printer)
        if ref:
            ok(f"{n} ready ({ref})")
    return 0


def cmd_see(args) -> int:
    d = desktop(args)
    ocr = True if args.ocr else ("auto" if not args.no_ocr else False)
    obs = d.see(ocr=ocr, window=args.window)
    if args.json:
        emit_json(obs.__dict__)
    else:
        print(obs.text)
    return 0


def cmd_shot(args) -> int:
    d = desktop(args)
    region = [int(v) for v in re.split(r"[,\s]+", args.region.strip())] if args.region else None
    fmt = "jpeg" if (args.output or "").lower().endswith((".jpg", ".jpeg")) else (
        "webp" if (args.output or "").lower().endswith(".webp") else "png")
    shot = d.screenshot(region=region, max_width=args.max_width, format=fmt, marks=args.marks,
                        grid=args.grid, cursor=not args.no_cursor)
    if args.output == "-":
        sys.stdout.buffer.write(shot.data)
        return 0
    path = Path(args.output or f"{d.name}-{time.strftime('%H%M%S')}.{'jpg' if fmt == 'jpeg' else fmt}")
    shot.save(path)
    if args.json:
        emit_json({"path": str(path), "width": shot.width, "height": shot.height, "scale": shot.scale})
    else:
        print(path)
    return 0


def _target(parts: list[str]):
    """`click 640 400`, `click 640,400`, `click @3`, `click Sign in`."""
    if len(parts) == 2 and all(re.fullmatch(r"-?\d+", p) for p in parts):
        return [int(parts[0]), int(parts[1])]
    return " ".join(parts) if parts else None


def cmd_click(args) -> int:
    count = 2 if args.double else 3 if args.triple else 1
    button = "right" if args.right else "middle" if args.middle else "left"
    return act_and_print(args, {"action": "click", "target": _target(args.target), "button": button,
                                "count": count, "modifiers": args.mod})


def cmd_dclick(args) -> int:
    return act_and_print(args, {"action": "click", "target": _target(args.target), "count": 2})


def cmd_rclick(args) -> int:
    return act_and_print(args, {"action": "click", "target": _target(args.target), "button": "right"})


def cmd_move(args) -> int:
    return act_and_print(args, {"action": "move", "target": _target(args.target)})


def cmd_type(args) -> int:
    text = " ".join(args.text)
    if text == "-":
        text = sys.stdin.read()
    if args.enter:
        text += "\n"
    return act_and_print(args, {"action": "paste" if args.paste else "type", "text": text})


def cmd_key(args) -> int:
    return act_and_print(args, *[{"action": "key", "keys": k, "repeat": args.repeat} for k in args.keys])


def cmd_scroll(args) -> int:
    return act_and_print(args, {"action": "scroll", "direction": args.direction, "amount": args.amount,
                                "target": _target(args.at.split()) if args.at else None})


def cmd_drag(args) -> int:
    return act_and_print(args, {"action": "drag", "from": args.start, "to": args.end})


def cmd_fill(args) -> int:
    return act_and_print(args, {"action": "fill", "target": args.target, "text": " ".join(args.text)})


def cmd_wait_for(args) -> int:
    return act_and_print(args, {"action": "wait_for", "text": " ".join(args.text), "timeout": args.timeout,
                                "gone": args.gone}, settle=False)


def cmd_act(args) -> int:
    steps = []
    for s in args.steps:
        s = s.strip()
        if s == "-":
            data = json.loads(sys.stdin.read())
            steps.extend(data if isinstance(data, list) else [data])
        elif s.startswith(("{", "[")):
            data = json.loads(s)
            steps.extend(data if isinstance(data, list) else [data])
        else:
            steps.append(s)
    return act_and_print(args, *steps)


def cmd_open(args) -> int:
    d = desktop(args)
    res = d.open(" ".join(args.target), wait=args.wait)
    if args.json:
        emit_json(res)
        return 0 if "error" not in res else 1
    w = res.get("window")
    if w:
        ok(f"opened {res['command']} → \"{w['title']}\"")
    elif "error" in res:
        err(f"{res['command']}: {res['error']}")
        return 1
    else:
        ok(f"launched {res['command']} (no new window yet)")
    return 0


def cmd_run(args) -> int:
    d = desktop(args)
    cmd = args.command
    command = cmd[0] if len(cmd) == 1 else " ".join(cmd)
    res = d.run(command, timeout=args.timeout, background=args.background)
    if args.json:
        emit_json(res.__dict__)
        return 0
    if args.background:
        ok(f"started in the background (pid {res.pid})")
        return 0
    if res.stdout:
        sys.stdout.write(res.stdout if res.stdout.endswith("\n") else res.stdout + "\n")
    if res.stderr:
        sys.stderr.write(res.stderr if res.stderr.endswith("\n") else res.stderr + "\n")
    if res.timed_out:
        err(f"timed out after {args.timeout:g}s")
        return 124
    return res.code or 0


def cmd_cp(args) -> int:
    src_r, dst_r = split_remote(args.src), split_remote(args.dst)
    if bool(src_r) == bool(dst_r):
        raise MinionError("exactly one side must be in the desktop, written as NAME:path or :path "
                          "(e.g. minion cp report.pdf :~/Documents/  or  minion cp office-1:~/out.png .)")
    if src_r:
        name, path = src_r
        d = Desktop.attach(name or getattr(args, "desktop", None))
        out = d.download(path, args.dst)
        ok(f"{d.name}:{path} → {out}")
    else:
        name, path = dst_r
        d = Desktop.attach(name or getattr(args, "desktop", None))
        d.upload(args.src, path or "~/")
        ok(f"{args.src} → {d.name}:{path}")
    return 0


def cmd_clip(args) -> int:
    d = desktop(args)
    if args.text:
        d.clipboard = " ".join(args.text)
        ok("clipboard set")
    else:
        print(d.clipboard)
    return 0


def cmd_windows(args) -> int:
    d = desktop(args)
    wins = d.windows()
    if args.json:
        emit_json(wins)
        return 0
    if not wins:
        info("No windows open.")
    for i, w in enumerate(wins, 1):
        flags = ", ".join(([c("focused", "32")] if w["focused"] else []) + w.get("states", []))
        print(f"[{i}] {w['title']!r:50} {w['app']:16} {w['x']},{w['y']} {w['w']}x{w['h']}  {flags}")
    return 0


def cmd_focus(args) -> int:
    d = desktop(args)
    res = d.window(args.action, " ".join(args.window) if args.window else None)
    ok(f"{args.action} \"{res['window']['title']}\"")
    return 0


def cmd_replay(args) -> int:
    d = desktop(args)
    out = args.output or f"{d.name}-replay.html"
    if out.endswith(".gif"):
        d.recording("gif", out)
    else:
        d.recording("html", out)
    ok(f"flight recorder → {out}")
    if args.open and not out.endswith(".gif"):
        webbrowser.open(Path(out).resolve().as_uri())
    return 0


def cmd_view(args) -> int:
    from .server import ensure_server

    d = desktop(args) if (getattr(args, "desktop", None) or Desktop.list()) else None
    base, token = ensure_server()
    url = f"{base}/view/{d.name}?token={token}" if d else f"{base}/?token={token}"
    if args.json:
        emit_json({"url": url})
        return 0
    ok(f"live view: {url}")
    if not getattr(args, "no_open", False):
        webbrowser.open(url)
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    serve(host=args.host, port=args.port, token=None if args.no_auth else (args.token or ""),
          idle_freeze=args.idle_freeze, quiet=args.quiet)
    return 0


def cmd_mcp(args) -> int:
    from .mcp import main as mcp_main

    mcp_main(preload=args.preload, idle_freeze=args.idle_freeze)
    return 0


def cmd_logs(args) -> int:
    d = desktop(args)
    print(d.logs(args.tail))
    return 0


def cmd_doctor(args) -> int:
    from .doctor import run_checks

    return run_checks(json_out=args.json)


def cmd_version(args) -> int:
    print(f"minion {__version__}")
    return 0


# -- parser --------------------------------------------------------------------
HELP = """\
minion — instant, featherweight Linux desktops for AI agents.

Start:     minion up [office|dev|research|browser|data|base]    then: minion see · minion view
Look:      see · shot · windows
Act:       click · type · key · scroll · drag · fill · open · run · act (batch) · wait-for
Manage:    ls · rm · stop · start · freeze · thaw · fork · snapshot · restore · use · cp · clip
Connect:   mcp (Claude Code, Claude Desktop, Cursor...) · serve (HTTP API + dashboard) · view (live)

Targets for click/move/fill: @12 (an id from `minion see`), "Sign in" (visible text), or 640,400.
Docs: https://github.com/apophisss/minion
"""


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-d", "--desktop", default=argparse.SUPPRESS, help="desktop name (default: current)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON output")

    p = argparse.ArgumentParser(prog="minion", description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-d", "--desktop", help="desktop name (default: the current one)")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument("-V", "--version", action="version", version=f"minion {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    def add(name, fn, help, aliases=()):
        help = help.replace("%", "%%")  # argparse formats help strings with %
        sp = sub.add_parser(name, help=help, parents=[common], aliases=list(aliases), description=help)
        sp.set_defaults(fn=fn)
        return sp

    sp = add("up", cmd_up, "create and start a desktop", aliases=["new", "create"])
    sp.add_argument("profile", nargs="?", help="profile (default: browser); see `minion profiles`")
    sp.add_argument("--name", "-n", help="desktop name (default: <profile>-N)")
    sp.add_argument("--size", "-s", help="screen size, e.g. 1280x800 (default) or 1024x768")
    sp.add_argument("--memory", "-m", help="memory limit, e.g. 2g")
    sp.add_argument("--cpus", help="CPU limit, e.g. 1.5")
    sp.add_argument("--offline", action="store_true", help="no network access")
    sp.add_argument("--mount", "-v", action="append", help="bind mount HOST:DESKTOP[:ro] (repeatable)")
    sp.add_argument("--env", "-e", action="append", help="environment variable KEY=VALUE (repeatable)")
    sp.add_argument("--port", "-p", action="append", help="publish a desktop port on 127.0.0.1 (repeatable)")
    sp.add_argument("--view", action="store_true", help="open the live view when ready")
    sp.add_argument("--quiet", "-q", action="store_true", help="no progress output")

    sp = add("ls", cmd_ls, "list desktops", aliases=["list", "ps"])
    sp.add_argument("--fast", action="store_true", help="skip live memory/CPU stats")

    sp = add("rm", cmd_rm, "remove desktops", aliases=["remove", "delete"])
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true", help="remove every desktop")

    for name, method, verb, help in (
        ("stop", "stop", "stopped", "stop a desktop (keeps its files)"),
        ("start", "start", "started", "start a stopped desktop"),
        ("freeze", "freeze", "froze", "pause every process: 0% CPU, instant resume"),
        ("thaw", "thaw", "thawed", "resume a frozen desktop (any command also does this)"),
    ):
        sp = add(name, cmd_simple(method, verb), help)
        sp.add_argument("name", nargs="?")

    sp = add("use", cmd_use, "set the current desktop")
    sp.add_argument("name")

    sp = add("fork", cmd_fork, "clone a desktop (disk state) into a new one")
    sp.add_argument("name", nargs="?")
    sp.add_argument("new", nargs="?")

    sp = add("snapshot", cmd_snapshot, "save a desktop's disk state", aliases=["snap"])
    sp.add_argument("name", nargs="?")
    sp.add_argument("tag", nargs="?")

    sp = add("snapshots", cmd_snapshots, "list snapshots")
    sp.add_argument("name", nargs="?")

    sp = add("restore", cmd_restore, "restore a snapshot (replaces the desktop's state)")
    sp.add_argument("tag")

    sp = add("profiles", cmd_profiles, "list desktop profiles")
    sp.add_argument("show", nargs="?", help="show one profile in detail")

    sp = add("build", cmd_build, "build profile images locally")
    sp.add_argument("profiles", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--push", action="store_true", help="push to the registry after building")
    sp.add_argument("--quiet", "-q", action="store_true")

    sp = add("pull", cmd_pull, "download (or build) profile images ahead of time")
    sp.add_argument("profiles", nargs="*")

    sp = add("see", cmd_see, "describe the screen as text: windows and UI elements with @ids")
    sp.add_argument("--ocr", action="store_true", help="always add OCR text")
    sp.add_argument("--no-ocr", action="store_true", help="never run OCR")
    sp.add_argument("--window", "-w", help="describe this window instead of the focused one")

    sp = add("shot", cmd_shot, "take a screenshot", aliases=["screenshot"])
    sp.add_argument("-o", "--output", help="file (.png/.jpg/.webp) or - for stdout")
    sp.add_argument("--region", help="x,y,w,h")
    sp.add_argument("--max-width", type=int)
    sp.add_argument("--marks", action="store_true", help="label clickable elements with their @ids")
    sp.add_argument("--grid", action="store_true", help="overlay a coordinate grid")
    sp.add_argument("--no-cursor", action="store_true")

    sp = add("click", cmd_click, "click a target: @id, visible text or x,y")
    sp.add_argument("target", nargs="*")
    sp.add_argument("--right", action="store_true")
    sp.add_argument("--middle", action="store_true")
    sp.add_argument("--double", action="store_true")
    sp.add_argument("--triple", action="store_true")
    sp.add_argument("--mod", help="hold modifiers, e.g. ctrl or ctrl+shift")
    sp.add_argument("--shot", metavar="FILE", help="save a screenshot after the action")
    for name, fn, help in (("dclick", cmd_dclick, "double-click a target"),
                           ("rclick", cmd_rclick, "right-click a target"),
                           ("move", cmd_move, "move the mouse to a target (hover)")):
        sp = add(name, fn, help)
        sp.add_argument("target", nargs="+")
        sp.add_argument("--shot", metavar="FILE")

    sp = add("type", cmd_type, "type text into the focused element")
    sp.add_argument("text", nargs="+", help="text to type (- reads stdin)")
    sp.add_argument("--enter", action="store_true", help="press Return afterwards")
    sp.add_argument("--paste", action="store_true", help="paste through the clipboard (fast for long text)")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("key", cmd_key, "press keys, e.g. ctrl+s, Return, alt+Tab", aliases=["press"])
    sp.add_argument("keys", nargs="+")
    sp.add_argument("--repeat", "-n", type=int, default=1)
    sp.add_argument("--shot", metavar="FILE")

    sp = add("scroll", cmd_scroll, "scroll up/down/left/right")
    sp.add_argument("direction", nargs="?", default="down", choices=["up", "down", "left", "right"])
    sp.add_argument("amount", nargs="?", type=int, default=3)
    sp.add_argument("--at", help="target to scroll at (@id, text or x,y)")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("drag", cmd_drag, "drag from one target to another")
    sp.add_argument("start")
    sp.add_argument("end")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("fill", cmd_fill, "replace the text of a field: minion fill @4 hello")
    sp.add_argument("target")
    sp.add_argument("text", nargs="+")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("wait-for", cmd_wait_for, "wait until text appears (or --gone)")
    sp.add_argument("text", nargs="+")
    sp.add_argument("--timeout", type=float, default=15)
    sp.add_argument("--gone", action="store_true")

    sp = add("act", cmd_act, 'run several actions: minion act "click @3" "type hello" "key Return"')
    sp.add_argument("steps", nargs="+", help="action strings, JSON objects/lists, or - for JSON on stdin")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("open", cmd_open, "open an app, URL, file or command")
    sp.add_argument("target", nargs="+")
    sp.add_argument("--wait", type=float, default=12.0, help="seconds to wait for a window")

    sp = add("run", cmd_run, "run a shell command inside the desktop", aliases=["exec"])
    sp.add_argument("command", nargs="+")
    sp.add_argument("--timeout", "-t", type=float, default=120.0)
    sp.add_argument("--background", "-b", action="store_true")

    sp = add("cp", cmd_cp, "copy files in/out: minion cp a.pdf :~/Documents/ · minion cp :~/b.png .")
    sp.add_argument("src")
    sp.add_argument("dst")

    sp = add("clip", cmd_clip, "read or set the clipboard", aliases=["clipboard"])
    sp.add_argument("text", nargs="*")

    add("windows", cmd_windows, "list windows")

    sp = add("focus", cmd_focus, "focus (or close/maximize/minimize) a window by title, app or index")
    sp.add_argument("window", nargs="*")
    sp.add_argument("--action", default="focus",
                    choices=["focus", "close", "maximize", "restore", "minimize"])

    sp = add("view", cmd_view, "open the live view in your browser (watch and take over)")
    sp.add_argument("--no-open", action="store_true", help="just print the URL")

    sp = add("replay", cmd_replay, "export the flight recorder (HTML timeline or GIF)")
    sp.add_argument("-o", "--output", help="file.html (default) or file.gif")
    sp.add_argument("--open", action="store_true")

    sp = add("logs", cmd_logs, "show the desktop's session log")
    sp.add_argument("--tail", type=int, default=200)

    sp = add("serve", cmd_serve, "run the HTTP API, dashboard and live view")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=int(os.environ.get("MINION_PORT", "4747")))
    sp.add_argument("--token", help="access token (default: random, printed at start)")
    sp.add_argument("--no-auth", action="store_true", help="no token (only on trusted networks)")
    sp.add_argument("--idle-freeze", type=float, default=config.env_float("MINION_IDLE_FREEZE", 600),
                    help="freeze desktops idle for this many seconds (0 = never)")
    sp.add_argument("--quiet", "-q", action="store_true")

    sp = add("mcp", cmd_mcp, "run the MCP server on stdio (for Claude Code, Claude Desktop, Cursor, ...)")
    sp.add_argument("--preload", help="comma-separated profiles to prepare in the background")
    sp.add_argument("--idle-freeze", type=float, default=config.env_float("MINION_IDLE_FREEZE", 600))

    add("doctor", cmd_doctor, "check that everything is set up")
    add("version", cmd_version, "print the version")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    if not hasattr(args, "json"):
        args.json = False
    try:
        return args.fn(args) or 0
    except KeyboardInterrupt:
        err("interrupted")
        return 130
    except MinionError as e:
        if args.json:
            emit_json({"error": str(e), "type": type(e).__name__})
        else:
            err(str(e))
        return 2 if isinstance(e, NotFound) else 1


def entry() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entry()
