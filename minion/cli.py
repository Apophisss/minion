"""The `minion` command line. Built for people and for agents with a shell."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

from . import __version__, config, profiles
from .backends import check_login, get_backend
from .desktop import ActResult, Desktop
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
    # Pretty for people; compact (often 5x smaller) when an agent or a pipe reads it.
    tty = sys.stdout.isatty()
    print(
        json.dumps(
            obj, indent=2 if tty else None, separators=None if tty else (",", ":"), ensure_ascii=False, default=str
        )
    )


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
        emit_json({k: v for k, v in res.__dict__.items() if k not in ("screenshot", "observation", "crop")})
    else:
        print(res.summary)
        if res.observation is not None:
            print(res.observation.text)
    if res.screenshot is not None:
        path = args.shot
        res.screenshot.save(path)
        info(f"screenshot → {path}")
    if getattr(res, "crop", None) is not None:  # --observe crop: just the region that changed
        path = getattr(args, "shot", None) or f"{d.name}-change-{time.strftime('%H%M%S')}.png"
        res.crop.save(path)
        info(f"changed region → {path}")
    return 0 if res.ok else 1


REMOTE_RE = re.compile(r"^([a-z0-9][a-z0-9_-]*)?:([^\\].*)$")


def split_remote(path: str) -> tuple[str | None, str] | None:
    """'office-1:~/a.txt' -> ('office-1', '~/a.txt'); ':~/a.txt' -> (None, '~/a.txt')."""
    if re.match(r"^[A-Za-z]:[\\/]", path):  # a Windows drive path (C:\x or c:/x)
        return None
    m = REMOTE_RE.match(path)
    if not m:
        return None
    return m.group(1), m.group(2)


# -- commands ------------------------------------------------------------------
def cmd_up(args) -> int:
    login = getattr(args, "login", None)
    profile = args.profile or (None if login else config.DEFAULT_PROFILE)  # a sign-in brings its profile
    t0 = time.time()
    if args.count and args.count > 1:
        desks = Desktop.create_many(
            profile,
            args.count,
            size=args.size,
            memory=args.memory or "",
            cpus=args.cpus or "",
            network=not args.offline,
            progress=None if args.quiet else progress_printer,
            **({"login": login} if login else {}),
        )
        if args.json:
            emit_json([d.to_dict() for d in desks])
        else:
            ok(f"{len(desks)} desktops ready in {time.time() - t0:.1f}s: {', '.join(d.name for d in desks)}")
            info("  Use one with -d NAME, e.g. minion -d " + desks[0].name + " see")
        return 0
    d = Desktop.create(
        profile,
        name=args.name or getattr(args, "desktop", None),  # `minion up office -d NAME` names it too
        size=args.size,
        memory=args.memory or "",
        cpus=args.cpus or "",
        network=not args.offline,
        mounts=args.mount or [],
        env=dict(kv.split("=", 1) for kv in args.env or []),
        ports=args.port or [],
        progress=None if args.quiet else progress_printer,
        login=login,
    )
    hello = d.hello()
    profile = hello.get("profile") or profile
    if args.json:
        emit_json({**d.to_dict(), "apps": hello.get("apps", []), "ready_in": round(time.time() - t0, 2)})
        return 0
    if args.quiet:  # just the name, for scripts: NAME=$(minion up -q office)
        print(d.name)
        return 0
    signed = f" · signed in as {login!r} was" if login else ""
    ok(
        f"{c(d.name, '1')} is ready  ({profile}{signed} · {'x'.join(map(str, hello['screen']))} · {time.time() - t0:.1f}s)"
    )
    if hello.get("apps"):
        info(f"  Apps: {', '.join(hello['apps'])}")
    info(f"  Next: minion see · minion open {(hello.get('apps') or ['<url>'])[-1].lower().split()[0]} · minion view")
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
        line = "  ".join(col.ljust(w) for col, w in zip(r, widths, strict=True)).rstrip()
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
    if args.all and names and not args.yes:
        # Every desktop on this machine, possibly other agents' too: confirm first.
        listing = ", ".join(names)
        if not sys.stdin.isatty():
            raise MinionError(f"rm --all would remove {len(names)} desktops ({listing}); add --yes to confirm")
        if input(f"Remove {len(names)} desktops ({listing})? [y/N] ").strip().lower() not in ("y", "yes"):
            return 1
    if not names:
        name = getattr(args, "desktop", None)
        names = [name] if name else [Desktop.attach().name]
    code = 0
    for n in names:
        try:
            Desktop(n, be).remove()
            ok(f"removed {n}")
        except NotFound as e:
            err(str(e))
            code = max(code, 2)
        except MinionError as e:
            err(str(e))
            code = max(code, 1)
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


def _site(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url if "://" in url else "https://" + url).hostname or url


def _login_list(args) -> int:
    saved = Desktop.logins()
    if args.json:
        emit_json([x.to_dict() for x in saved])
        return 0
    if not saved:
        info("No saved sign-ins yet:  minion login NAME URL   (e.g. minion login github https://github.com/login)")
        return 0
    for x in saved:  # (no size: docker's counts the image it shares with every desktop of the profile)
        print(f"{x.name:20} {x.profile:10} {x.site or '-':40} saved {x.created}")
    info("  Start a desktop signed in:  minion up --login NAME")
    return 0


def _login_by_hand(args, name: str, url: str) -> int:
    """A desktop opens at URL in the live view; the person signs in and presses Done; it's saved as NAME."""
    from .server import ensure_server, handoff_wait

    existing = next((x for x in Desktop.logins() if x.name == name), None)
    taken = {x.name for x in Desktop.list()}
    stem = "login-" + re.sub(r"[^a-z0-9_-]", "-", name)[:34]
    desk_name, n = stem, 2
    while desk_name in taken:
        desk_name, n = f"{stem}-{n}", n + 1
    if existing:
        info(
            f"Adding to the sign-in {name!r} ({existing.site or 'saved before'}): its desktop opens signed in as it was"
        )
        sys.stdout.flush()
    d = Desktop.create(
        args.profile or None,
        name=desk_name,
        login=name if existing else None,
        progress=progress_printer,
    )
    try:
        d.open(url or "about:home")
        base, token = ensure_server()
        link = f"{base}/view/{d.name}" + (f"?token={token}" if token else "")
        site = _site(url) if url else ""
        ok(f"Sign in{' to ' + site if site else ''} in the live view, then press Done there:  {link}")
        if not args.no_open:
            webbrowser.open(link)
        sys.stdout.flush()
        message = f"Sign in{' to ' + site if site else ''}, then press Done: Minion saves this desktop as the sign-in '{name}'."
        note = handoff_wait(d.name, message, args.timeout)
        if note is None:
            err(f"not saved: Done wasn't pressed within {args.timeout:.0f}s")
            return 1
        sites = [x for x in (existing.site.split(", ") if existing and existing.site else []) if x]
        if site and site not in sites:
            sites.append(site)
        saved = d.save_login(name, ", ".join(sites))
        what = f" ({saved.site})" if saved.site else ""
        ok(f"saved the sign-in {c(name, '1')}{what}. New desktops start signed in:  minion up --login {name}")
        info("  It is a snapshot of that desktop, kept in this computer's Docker. Remove it: minion login rm " + name)
        return 0
    finally:
        if args.keep:
            info(f"  {d.name} is still running (minion rm {d.name} when you're done)")
        else:
            d.remove()


def cmd_login(args) -> int:
    words = list(args.words or [])
    if getattr(args, "cmd", "") == "logins" and not words:
        words = ["list"]
    if not words:
        raise MinionError(
            "which sign-in? minion login NAME URL (sign in by hand, saved as NAME) · minion login list · "
            "minion login save NAME (this desktop, as it is) · minion login rm NAME"
        )
    action = words[0].lower()
    if action in ("list", "ls"):
        return _login_list(args)
    if action in ("rm", "remove", "delete"):
        if len(words) < 2:
            raise MinionError("which sign-in? minion login rm NAME (see minion login list)")
        for name in words[1:]:
            Desktop.remove_login(name)
            ok(f"removed the sign-in {name!r}")
        return 0
    if action == "save":
        if len(words) != 2:
            raise MinionError("minion login save NAME [-d DESKTOP]: saves that desktop as it is, signed in where it is")
        d = desktop(args)
        saved = d.save_login(words[1], args.site or "")
        ok(
            f"saved {d.name} as the sign-in {c(saved.name, '1')}. New desktops start signed in:  minion up --login {saved.name}"
        )
        return 0
    if len(words) > 2:
        raise MinionError("minion login NAME [URL]: e.g. minion login github https://github.com/login")
    check_login(words[0])
    return _login_by_hand(args, words[0], words[1] if len(words) == 2 else "")


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
    ocr = args.lang or (True if args.ocr else ("auto" if not args.no_ocr else False))
    obs = d.see(ocr=ocr, window=args.window, full_text=args.full, changes=args.changes, menus=args.menus)
    if args.json:
        emit_json(obs.__dict__)
    else:
        print(obs.text)
    return 0


def cmd_shot(args) -> int:
    d = desktop(args)
    region = [int(v) for v in re.split(r"[,\s]+", " ".join(args.region).strip()) if v] if args.region else None
    if region is not None and len(region) != 4:
        raise MinionError("--region takes x,y,w,h: 4 numbers, e.g. --region 0,0,640,400")
    fmt = (
        "jpeg"
        if (args.output or "").lower().endswith((".jpg", ".jpeg"))
        else ("webp" if (args.output or "").lower().endswith(".webp") else "png")
    )
    shot = d.screenshot(
        region=region,
        max_width=args.max_width,
        width=1024 if getattr(args, "zoom", False) and region else None,
        format=fmt,
        marks=args.marks,
        grid=args.grid,
        cursor=not args.no_cursor and not region,  # crops are for reading details: no pointer on top
    )
    if args.output == "-":
        sys.stdout.buffer.write(shot.data)
        return 0
    if (args.output or "").startswith(":"):  # :~/Pictures/page.png — a file inside the desktop (to put in a document)
        import tempfile

        inside = desktop_path(args.output[1:])
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / Path(inside).name
            shot.save(local)
            d.upload(str(local), inside)
        if args.json:
            emit_json({"path": inside, "width": shot.width, "height": shot.height, "scale": shot.scale})
        else:
            print(f"{d.name}:{inside}")
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
    return act_and_print(
        args,
        {"action": "click", "target": _target(args.target), "button": button, "count": count, "modifiers": args.mod},
    )


def cmd_dclick(args) -> int:
    return act_and_print(args, {"action": "click", "target": _target(args.target), "count": 2})


def cmd_rclick(args) -> int:
    return act_and_print(args, {"action": "click", "target": _target(args.target), "button": "right"})


def cmd_move(args) -> int:
    return act_and_print(args, {"action": "move", "target": _target(args.target)})


def cmd_type(args) -> int:
    from .tools import _escapes

    text = " ".join(args.text)
    if text == "-":
        text = sys.stdin.read()  # (stdin is typed exactly as it is)
    elif not args.raw:
        text = _escapes(text)  # \n is Return and \t is Tab, as in act strings; \\ is a backslash
    if args.paste:  # a pasted trailing newline is often dropped: press Return as its own step
        steps = [{"action": "paste", "text": text}] + ([{"action": "key", "keys": "Return"}] if args.enter else [])
        return act_and_print(args, *steps)
    if args.enter:
        text += "\n"
    return act_and_print(args, {"action": "type", "text": text})


def cmd_key(args) -> int:
    return act_and_print(args, *[{"action": "key", "keys": k, "repeat": args.repeat} for k in args.keys])


def cmd_scroll(args) -> int:
    return act_and_print(
        args,
        {
            "action": "scroll",
            "direction": args.direction,
            "amount": args.amount,
            "target": _target(args.at.split()) if args.at else None,
        },
    )


def cmd_drag(args) -> int:
    return act_and_print(args, {"action": "drag", "from": args.start, "to": args.end})


def cmd_fill(args) -> int:
    return act_and_print(args, {"action": "fill", "target": args.target, "text": " ".join(args.text)})


def cmd_select(args) -> int:
    return act_and_print(args, {"action": "select", "target": args.target, "option": " ".join(args.option)})


def desktop_path(path: str) -> str:
    """A path for the desktop: a shell expands ~ to *this* machine's home (/root/x.pdf, /Users/ada/x.pdf),
    which means the desktop's home (~/x.pdf) there."""
    home = os.path.expanduser("~").rstrip("/")
    if home and home != "/home/agent" and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home) :]
    return path


def cmd_menu(args) -> int:
    return act_and_print(args, {"action": "menu", "item": " ".join(args.item)})


def cmd_path(args) -> int:
    path = desktop_path(" ".join(args.path))
    return act_and_print(args, {"action": "path", "path": path, "overwrite": args.overwrite})


def cmd_read(args) -> int:
    d = desktop(args)
    text = d.read(desktop_path(args.file), details=args.details)
    if args.json:
        emit_json({"path": args.file, "text": text})
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def cmd_convert(args) -> int:
    d = desktop(args)
    to = desktop_path(args.format) if "/" in args.format else args.format
    if len(args.file) > 1 and ("/" in to or "." in to.strip(".")):
        raise MinionError("several files convert to a format (pdf, docx, ...), not to one file name")
    outs = []
    for f in args.file:
        outs.append(d.convert(desktop_path(f), to, desktop_path(args.outdir) if args.outdir else None))
        if not args.json:
            ok(f"{f} → {outs[-1]}")
    if args.json:
        emit_json({"path": outs[0]} if len(outs) == 1 else {"paths": outs})
    return 0


def cmd_wait_for(args) -> int:
    return act_and_print(
        args,
        {"action": "wait_for", "text": " ".join(args.text), "timeout": args.timeout, "gone": args.gone},
        settle=False,
    )


SCRIPT_API = """\
The script runs inside the desktop; only what it prints comes back. Preloaded (targets as in act: @12, "Save",
button:Save, x,y; a failed step raises MinionScriptError):
  look:   see(changes=False) -> str · look() -> dict · elements(role=None, name=None) -> list[dict]
          find(text) -> list[dict] · cells() -> {"A1": "Item", ...} · formulas() -> {"B7": "=SUM(B2:B6)"}
          windows() -> list[dict] · menus() -> list[str] · screenshot(path) -> path
  act:    click(target, button="left", count=1, modifiers=None) · double_click(target) · right_click(target)
          move(target) · drag(start, end) · scroll(direction="down", amount=3, target=None)
          write(text)  (\\n is Return, \\t is Tab) · paste(text) · key("ctrl+s", repeat=1) · hold_key(keys, seconds)
          fill(target, text) · select(target, option) · menu("File > Save As") · path("~/out.pdf", overwrite=False)
          scroll_to(text) · close(window=None) · copy(target) · focus(window) · act(*steps) -> summary
  wait:   wait(seconds) · wait_for(text, timeout=10, gone=False) -> bool
  apps:   launch("calc" | URL | FILE) -> dict · run(cmd, timeout=60) -> {"code", "stdout", "stderr"}
          read(file) -> text · convert(file, to) -> new path · clipboard(text=None) -> str
Example:
  launch("calc")
  for item, price in [("Coffee", 3.5), ("Bagel", 2.25)]:
      write(f"{item}\\t{price}\\n")
  print(cells())
"""


def cmd_scroll_to(args) -> int:
    return act_and_print(args, {"action": "scroll_to", "text": " ".join(args.text), "timeout": args.timeout})


def cmd_goto(args) -> int:
    return act_and_print(args, {"action": "goto", "target": args.url})


def cmd_close(args) -> int:
    return act_and_print(args, {"action": "close", **({"window": " ".join(args.window)} if args.window else {})})


def cmd_copy(args) -> int:
    return act_and_print(args, {"action": "copy", "target": args.target}, settle=False)


def cmd_act(args) -> int:
    steps = []
    for raw in args.steps:
        s = raw.strip()
        if s == "-":
            data = json.loads(sys.stdin.read())
            steps.extend(data if isinstance(data, list) else [data])
        elif s.startswith(("{", "[")):
            data = json.loads(s)
            steps.extend(data if isinstance(data, list) else [data])
        else:
            steps.append(raw.lstrip())  # (its end as given: "type hi " types the space)
    return act_and_print(args, *steps, observe=args.observe)


URLISH = re.compile(r"^([a-z][a-z0-9+.-]*://\S+|(www\.)?[\w-]+(\.[\w-]+)*\.[a-z]{2,}(:\d+)?(/\S*)?)$", re.I)


def cmd_open(args) -> int:
    targets = [desktop_path(t) for t in args.target]  # (~ expanded by this machine's shell means the desktop's)
    if len(targets) > 1 and all(URLISH.match(t) for t in targets):  # open a.com b.org: one tab each
        code = 0
        for t in targets:
            args.target = [t]
            code = cmd_open(args) or code
        return code
    d = desktop(args)
    if not args.no_install and not args.json:
        info(f"opening {' '.join(targets)} (an app that isn't installed yet is installed first)")
        sys.stdout.flush()
    res = d.open(" ".join(targets), wait=args.wait, install=not args.no_install)
    if args.json:
        emit_json(res)
        return 0 if "error" not in res else 1
    if res.get("installed"):
        ok(f"installed {res['installed']}")
    w = res.get("window")
    if "error" in res:  # (an app may have opened only to show an error: "it opened, but shows an error: …")
        if w:
            info(f'opened {res["command"]} → "{w["title"]}"')
        err(res["error"])
        return 1
    if w:
        ok(f'opened {res["command"]} → "{w["title"]}"')
        if res.get("also"):
            info(f"  also opened: {', '.join(repr(t) for t in res['also'])}")
    else:
        ok(f"launched {res['command']} (no new window yet)")
    if res.get("tips"):
        info(f"tips: {res['tips']}")
    if res.get("look"):  # it opened on a dialog: what it asks
        print(res["look"])
    return 0


def piped_stdin(force: bool = False) -> str | None:
    """Text piped or redirected into this command (`echo hi | minion run cat`, heredocs), else None.

    A terminal, /dev/null, or a pipe that a harness keeps open without writing is never waited on."""
    import stat

    try:
        if force:
            return sys.stdin.read()
        if sys.stdin is None or sys.stdin.isatty():
            return None
        mode = os.fstat(sys.stdin.fileno()).st_mode
        if stat.S_ISREG(mode):
            return sys.stdin.read()
        if stat.S_ISFIFO(mode) and os.name != "nt":
            import select

            ready, _, _ = select.select([sys.stdin], [], [], 0.05)  # data (or EOF) already waiting
            return sys.stdin.read() if ready else None
    except (OSError, ValueError, AttributeError):
        pass
    return None


def cmd_run(args) -> int:
    d = desktop(args)
    cmd = args.command
    command = cmd[0] if len(cmd) == 1 else " ".join(cmd)
    stdin = None if args.background else piped_stdin(force=getattr(args, "stdin", False))
    res = d.run(command, timeout=args.timeout, background=args.background, input=stdin or None)
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
    if res.code and not res.stdout and not res.stderr:  # (a silent failure would look like success)
        err(f"exited with code {res.code} and printed nothing")
    return res.code or 0


def cmd_cp(args) -> int:
    src_r, dst_r = split_remote(args.src), split_remote(args.dst)
    if bool(src_r) == bool(dst_r):
        raise MinionError(
            "exactly one side must be in the desktop, written as NAME:path or :path "
            "(e.g. minion cp report.pdf :~/Documents/  or  minion cp office-1:~/out.png .)"
        )
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
        title = '"' + w["title"] + '"'
        print(f"[{i}] {title:50} {w['app']:16} {w['x']},{w['y']} {w['w']}x{w['h']}  {flags}")
    return 0


def cmd_focus(args) -> int:
    d = desktop(args)
    res = d.window(args.action, " ".join(args.window) if args.window else None)
    if res.get("note"):  # e.g. closing: the app is asking something first
        info(res["note"])
        return 1
    ok(f'{args.action} "{res["window"]["title"]}"')
    return 0


def cmd_replay(args) -> int:
    d = desktop(args)
    out = args.output or f"{d.name}-replay.html"
    if out.endswith(".gif"):
        d.recording("gif", out)
    elif out.endswith(".py"):
        d.recording("script", out)
    else:
        d.recording("html", out)
    ok(f"flight recorder → {out}")
    if args.open and not out.endswith(".gif"):
        webbrowser.open(Path(out).resolve().as_uri())
    return 0


def cmd_view(args) -> int:
    from .server import ensure_server, handoff_wait

    ask = getattr(args, "ask", None)
    if getattr(args, "name", None):
        args.desktop = args.name
    d = desktop(args) if (ask or getattr(args, "desktop", None) or Desktop.list()) else None
    base, token = ensure_server()
    url = f"{base}/view/{d.name}?token={token}" if d else f"{base}/?token={token}"
    if not args.json:
        ok(f"live view: {url}")
        info("  (a background server keeps it available; `minion serve --stop` stops it)")
    if not getattr(args, "no_open", False):
        webbrowser.open(url)
    if not ask:
        if args.json:
            emit_json({"url": url})
        return 0
    if not args.json:
        info(f"waiting up to {args.timeout:.0f}s for the human to press Done…")
    sys.stdout.flush()  # agents read this through a pipe: the link must arrive before the wait
    note = handoff_wait(d.name, ask, args.timeout)
    if args.json:
        emit_json({"url": url, "done": note is not None, "note": note})
    elif note is None:
        err(f"the human did not finish within {args.timeout:.0f}s")
    else:
        ok("the human is done" + (f': "{note}"' if note else ""))
    return 0 if note is not None else 1


def _stop_server() -> int:
    """Stop the background server that `minion view` (or `view --ask`) started."""
    import signal
    import subprocess

    st = config.load_state().get("server") or {}
    pid = int(st.get("pid") or 0)
    if not pid:
        info("No background server is recorded.")
        return 0
    if os.name == "nt":
        query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
        ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command", query]
    else:
        ps = ["ps", "-o", "command=", "-p", str(pid)]
    try:  # only ever stop a `minion serve`: the state can also point at an MCP server hosting the view
        cmdline = subprocess.run(ps, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        cmdline = ""
    if not cmdline.strip():
        config.update_state(server=None)
        info(f"The background server (pid {pid}) is not running.")
        return 0
    if " serve" not in cmdline:
        raise MinionError(f"pid {pid} is not a `minion serve` ({cmdline.strip()[:80]}); leaving it alone")
    os.kill(pid, signal.SIGTERM)
    config.update_state(server=None)
    ok(f"stopped the background server (pid {pid})")
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    if getattr(args, "stop", False):
        return _stop_server()
    serve(
        host=args.host,
        port=args.port,
        token=None if args.no_auth else (args.token or ""),
        idle_freeze=args.idle_freeze,
        quiet=args.quiet,
    )
    return 0


def cmd_mcp(args) -> int:
    from .mcp import main as mcp_main

    mcp_main(preload=args.preload, idle_freeze=args.idle_freeze, compact=args.compact, images=not args.no_images)
    return 0


def cmd_share(args) -> int:
    from .share import run

    return run(args)


def cmd_script(args) -> int:
    d = desktop(args)
    src = args.code
    if src == "-":
        code = sys.stdin.read()
    elif os.path.isfile(src):
        code = Path(src).read_text(encoding="utf-8")
    else:
        code = src
    res = d.script(code, timeout=args.timeout)
    if args.json:
        emit_json(res.__dict__)
        return 0 if res.ok else 1
    if res.stdout:
        sys.stdout.write(res.stdout if res.stdout.endswith("\n") else res.stdout + "\n")
        sys.stdout.flush()  # its output first, then any error
    if res.stderr:
        sys.stderr.write(res.stderr if res.stderr.endswith("\n") else res.stderr + "\n")
    if res.timed_out:
        err(f"timed out after {args.timeout:g}s")
        return 124
    if res.ok and not res.stdout and not res.stderr:
        ok(f"script finished in {res.elapsed:.1f}s (it printed nothing; print() what you want back)")
    return res.code or 0


def cmd_tools(args) -> int:
    from .tools import Toolkit

    tk = Toolkit()
    if args.call:
        arguments = json.loads(args.arguments) if args.arguments else {}
        # Each `tools --call` is a new process: carry "the current desktop" between calls like the CLI does.
        tk.current = getattr(args, "desktop", None) or config.load_state().get("current")
        res = tk.call(args.call, arguments)
        if tk.current != config.load_state().get("current"):
            config.update_state(current=tk.current)
        if args.json:
            emit_json(res.to_mcp())
        else:
            print(res.text)
            for i, (mime, data) in enumerate(res.images, 1):
                path = (
                    Path(tempfile.gettempdir())
                    / f"minion-tool-image-{time.strftime('%H%M%S')}-{i}.{mime.split('/')[-1]}"
                )
                path.write_bytes(__import__("base64").b64decode(data))
                info(f"image → {path}")
        return 1 if res.is_error else 0
    emit_json(tk.definitions(args.format, compact=args.compact))
    return 0


def cmd_skill(args) -> int:
    from importlib.resources import files

    text = files("minion").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
    if args.install is None:
        sys.stdout.write(text)
        return 0
    dest = Path(os.path.expanduser(args.install or "~/.claude/skills")) / "minion" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    ok(f"skill installed: {dest}")
    return 0


def cmd_logs(args) -> int:
    d = desktop(args)
    print(d.logs(args.tail))
    return 0


def cmd_setup(args) -> int:
    from .onboard import setup

    names = [n for n in re.split(r"[,\s]+", args.profiles or "") if n] if args.profiles is not None else None
    return setup(names, yes=args.yes, compact=args.compact)


def cmd_connect(args) -> int:
    from .connect import main as connect_main

    return connect_main(
        args.apps,
        every=args.all,
        list_only=args.list,
        dry_run=args.dry_run,
        remove=args.remove,
        compact=args.compact,
        yes=args.yes,
        json_out=args.json,
    )


def cmd_doctor(args) -> int:
    from .doctor import run_checks

    return run_checks(json_out=args.json)


def cmd_version(args) -> int:
    print(f"minion {__version__}")
    return 0


# -- parser --------------------------------------------------------------------
HELP = """\
minion — instant, featherweight Linux desktops for AI agents.

First run: minion setup (checks Docker, prepares a desktop, connects your agent apps)
Start:     minion up [office|dev|research|browser|data|windows|base]    then: minion see · minion view
Look:      see (--menus lists every menu command) · shot · windows · read (any document as text)
Act:       click · type · key · scroll · drag · fill · select · menu · path · open · run · act (batch) · wait-for
Apps:      open gimp / vscode / chrome / figma ... (installed the first time) · convert (docx → pdf, ...)
Manage:    ls · rm · stop · start · freeze · thaw · fork · snapshot · restore · use · cp · clip
Sign in:   login NAME URL (once, by hand in the live view) · up --login NAME (start signed in) · login list
Connect:   connect (add Minion to Claude, Cursor, VS Code, Codex...) · mcp (the MCP server itself)
           serve (HTTP API + dashboard) · view (live) · share (a URL for ChatGPT, Claude.ai, Le Chat)
           tools (definitions for any LLM API) · skill (SKILL.md for agents with a shell)

Targets for click/move/fill: @12 (an id from `minion see`), "Sign in" (visible text), button:Save, or 640,400.
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
    sp.add_argument("--count", "-c", type=int, default=1, help="create N desktops in parallel")
    sp.add_argument("--quiet", "-q", action="store_true", help="print only the new desktop's name")
    sp.add_argument("--login", "-l", metavar="NAME", help="start signed in, from a sign-in saved with `minion login`")

    sp = add("ls", cmd_ls, "list desktops", aliases=["list", "ps"])
    sp.add_argument("--fast", action="store_true", help="skip live memory/CPU stats")

    sp = add("rm", cmd_rm, "remove desktops", aliases=["remove", "delete"])
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true", help="remove every desktop on this machine (asks first)")
    sp.add_argument("--yes", "-y", action="store_true", help="don't ask (needed for --all without a terminal)")

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

    sp = add(
        "login",
        cmd_login,
        "sign in to a site by hand once, and start desktops signed in: minion login github https://github.com/login "
        "· minion up --login github · login list · login save NAME · login rm NAME",
        aliases=["logins"],
    )
    sp.add_argument("words", nargs="*", metavar="NAME [URL] | list | save NAME | rm NAME")
    sp.add_argument("--profile", "-p", help="profile of the desktop to sign in on (default: browser)")
    sp.add_argument("--site", help="save: a note on what it is signed in to")
    sp.add_argument("--timeout", "-t", type=float, default=1800.0, help="seconds to wait for Done (default 1800)")
    sp.add_argument("--keep", action="store_true", help="keep the desktop you signed in on (it is removed after)")
    sp.add_argument("--no-open", action="store_true", help="print the live view's link instead of opening it")

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
    sp.add_argument("--ocr", action="store_true", help="also OCR small pictures, or the whole window")
    sp.add_argument("--lang", help="OCR language if not the screen's own: heb, ara+eng, jpn, ...")
    sp.add_argument("--no-ocr", action="store_true", help="never run OCR")
    sp.add_argument("--window", "-w", help="describe this window instead of the focused one")
    sp.add_argument("--full", action="store_true", help="keep paragraphs whole (for reading)")
    sp.add_argument("--changes", action="store_true", help="only what changed since the previous look")
    sp.add_argument("--menus", action="store_true", help="also list the app's menu commands and shortcuts")

    sp = add("shot", cmd_shot, "take a screenshot", aliases=["screenshot"])
    sp.add_argument("-o", "--output", help="file (.png/.jpg/.webp) or - for stdout")
    sp.add_argument("--region", nargs="+", help="only this part of the screen: x,y,w,h (or x y w h)")
    sp.add_argument("--zoom", action="store_true", help="magnify --region to 1024 px wide (small text, icons)")
    sp.add_argument("--max-width", type=int, help="scale down to at most this width (fewer image tokens)")
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
    for name, fn, help in (
        ("dclick", cmd_dclick, "double-click a target"),
        ("rclick", cmd_rclick, "right-click a target"),
        ("move", cmd_move, "move the mouse to a target (hover)"),
    ):
        sp = add(name, fn, help)
        sp.add_argument("target", nargs="+")
        sp.add_argument("--shot", metavar="FILE")

    sp = add("type", cmd_type, "type text into the focused element (\\n is Return, \\t is Tab)")
    sp.add_argument("text", nargs="+", help="text to type (- reads stdin)")
    sp.add_argument("--raw", action="store_true", help="type backslashes as they are (no \\n or \\t)")
    sp.add_argument("--enter", action="store_true", help="press Return afterwards")
    sp.add_argument("--paste", action="store_true", help="paste through the clipboard (fast for long text)")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("key", cmd_key, "press keys, e.g. ctrl+s, Return, alt+Tab", aliases=["press"])
    sp.add_argument("keys", nargs="+")
    sp.add_argument("--repeat", "-n", type=int, default=1)
    sp.add_argument("--shot", metavar="FILE")

    sp = add("scroll", cmd_scroll, "scroll up/down/left/right")
    sp.add_argument("direction", nargs="?", default="down", choices=["up", "down", "left", "right"])
    sp.add_argument("amount", nargs="?", type=int, default=3, help="wheel clicks (3)")
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

    sp = add("select", cmd_select, "pick a dropdown option by its text: minion select @12 Title")
    sp.add_argument("target")
    sp.add_argument("option", nargs="+")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("menu", cmd_menu, 'choose a menu command by its path: minion menu "File > Export as PDF"')
    sp.add_argument("item", nargs="+")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("path", cmd_path, "type a full path into the open file dialog and confirm: minion path ~/out.pdf")
    sp.add_argument("path", nargs="+")
    sp.add_argument("--overwrite", action="store_true", help="replace the file if it exists")
    sp.add_argument("--shot", metavar="FILE")

    sp = add("read", cmd_read, "print any file in the desktop as text (docx, xlsx, pptx, pdf, odt, epub, html, images)")
    sp.add_argument("file")
    sp.add_argument(
        "--details",
        action="store_true",
        help="formatting too: slide backgrounds and shapes' place and size (cm), bullets, paragraph spacing and "
        "indents, fonts and sizes (bold, subscript...), number formats",
    )
    sp.add_argument("--full", action="store_true", help=argparse.SUPPRESS)  # (`see --full`'s habit: read is whole)

    sp = add(
        "convert",
        cmd_convert,
        "convert documents in the desktop: minion convert ~/report.docx pdf · minion convert ~/a.csv ~/b.xlsx",
    )
    sp.add_argument("file", nargs="+")
    sp.add_argument(
        "format", help="pdf, docx, odt, xlsx, ods, csv, pptx, odp, html, txt, md, png, jpg, or the new file's name"
    )
    sp.add_argument("--outdir", help="folder for the result (default: next to the file)")

    sp = add("wait-for", cmd_wait_for, "wait until text is visible on screen (or --gone)")
    sp.add_argument("text", nargs="+")
    sp.add_argument("--timeout", "-t", type=float, default=15, help="seconds to wait (15)")
    sp.add_argument("--gone", action="store_true", help="wait until the text is no longer visible")

    sp = add(
        "scroll-to",
        cmd_scroll_to,
        'bring text into view wherever it is on a long page (loading more of a feed): minion scroll-to "Entry 87"',
        aliases=["find"],
    )
    sp.add_argument("text", nargs="+")
    sp.add_argument("--timeout", "-t", type=float, default=20, help="seconds to keep loading more (20)")

    sp = add("goto", cmd_goto, "load a URL in the browser's current tab (open URL makes a new tab)")
    sp.add_argument("url")

    sp = add("close", cmd_close, "close a window like its X button (the focused one, or by title or app)")
    sp.add_argument("window", nargs="*")

    sp = add("copy", cmd_copy, "copy an element's whole text to the clipboard: minion copy @12")
    sp.add_argument("target")

    sp = add(
        "act",
        cmd_act,
        'run several actions in one call: minion act "click @3" "fill @4 Ada" "type hi\\n" "key ctrl+s Return"',
    )
    sp.add_argument(
        "steps",
        nargs="+",
        help=(
            "action strings: click|dclick|rclick|move TARGET · type TEXT (\\n is Return, \\t is Tab) · "
            "paste TEXT · key KEYS [N] (or a sequence: key Tab Tab Return) · fill TARGET TEXT · select TARGET OPTION · "
            "menu File > Save As · path FILE [--overwrite] · "
            "scroll DIR [N] [TARGET] · drag FROM TO · wait SECONDS · wait_for TEXT [SECONDS] [--gone] · "
            "scroll_to TEXT · goto URL · close [WINDOW] · copy TARGET · focus WINDOW. "
            "The text of type/paste/fill is taken as is (one pair of outer quotes is removed), except that \\n is "
            "Return, \\t is Tab and \\\\ a backslash; a Windows path (C:\\users\\x.txt) keeps its backslashes. "
            "Also JSON objects/lists, or - for JSON on stdin"
        ),
    )
    sp.add_argument(
        "--observe",
        default="auto",
        choices=["auto", "summary", "changes", "see", "crop"],
        help="what to report after the actions: auto (what changed, when a page, window or dialog changed or the "
        "app finished working), summary, changes, see, crop (saves an image of the changed region)",
    )
    sp.add_argument("--shot", metavar="FILE", help="also save a screenshot (or the --observe crop image) here")

    sp = add("open", cmd_open, "open an app (installed first if needed: minion open gimp), a URL, a file or a command")
    sp.add_argument("target", nargs="+")
    sp.add_argument("--wait", type=float, default=12.0, help="seconds to wait for a window")
    sp.add_argument("--no-install", action="store_true", help="fail instead of installing a missing app")

    sp = add("run", cmd_run, "run a shell command inside the desktop (piped stdin is passed on)", aliases=["exec"])
    sp.add_argument("command", nargs="+")
    sp.add_argument("--timeout", "-t", type=float, default=120.0, help="seconds before the command is stopped (120)")
    sp.add_argument("--background", "-b", action="store_true", help="start it and return at once (for GUI apps)")
    sp.add_argument("--stdin", "-i", action="store_true", help="always read stdin and pass it to the command")

    sp = add("cp", cmd_cp, "copy files in/out: minion cp a.pdf :~/Documents/ · minion cp :~/b.png .")
    sp.add_argument("src")
    sp.add_argument("dst")

    sp = add("clip", cmd_clip, "read or set the clipboard", aliases=["clipboard"])
    sp.add_argument("text", nargs="*")

    add("windows", cmd_windows, "list windows")

    sp = add("focus", cmd_focus, "focus (or close/maximize/minimize) a window by title, app or index")
    sp.add_argument("window", nargs="*")
    sp.add_argument("--action", default="focus", choices=["focus", "close", "maximize", "restore", "minimize"])

    sp = add("view", cmd_view, "open the live view in your browser (watch and take over)")
    sp.add_argument("name", nargs="?", help="desktop (default: the current one)")
    sp.add_argument("--no-open", action="store_true", help="just print the URL")
    sp.add_argument("--ask", metavar="MESSAGE", help="hand off to the human with this message; wait for Done")
    sp.add_argument("--timeout", "-t", type=float, default=600.0, help="seconds to wait with --ask (default 600)")

    sp = add("replay", cmd_replay, "export the flight recorder: HTML timeline, GIF, or a replayable .py script")
    sp.add_argument("-o", "--output", help="file.html (default), file.gif, or file.py (replay with `minion script`)")
    sp.add_argument("--open", action="store_true")

    sp = add("script", cmd_script, "run Python inside the desktop with the GUI API (FILE, - or code)")
    sp.epilog = SCRIPT_API
    sp.formatter_class = argparse.RawDescriptionHelpFormatter
    sp.add_argument("code", help="a .py file, - for stdin, or Python code")
    sp.add_argument("--timeout", "-t", type=float, default=120.0)

    sp = add("tools", cmd_tools, "print tool definitions for any LLM API, or call a tool")
    sp.add_argument(
        "--format", "-f", default="openai", choices=["openai", "openai-responses", "anthropic", "gemini", "mcp"]
    )
    sp.add_argument("--compact", action="store_true", help="the single `computer` tool")
    sp.add_argument("--call", metavar="NAME", help="call a tool, e.g. --call see")
    sp.add_argument("arguments", nargs="?", help="JSON arguments for --call")

    sp = add("skill", cmd_skill, "print the Agent Skill (SKILL.md) that teaches agents this CLI, or install it")
    sp.add_argument(
        "--install",
        nargs="?",
        const="",
        metavar="DIR",
        help="write DIR/minion/SKILL.md (default DIR: ~/.claude/skills)",
    )

    sp = add("logs", cmd_logs, "show the desktop's session log")
    sp.add_argument("--tail", type=int, default=200)

    sp = add("serve", cmd_serve, "run the HTTP API, dashboard and live view")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=int(os.environ.get("MINION_PORT", "4747")))
    sp.add_argument("--token", help="access token (default: random, printed at start)")
    sp.add_argument("--no-auth", action="store_true", help="no token (only on trusted networks)")
    sp.add_argument(
        "--idle-freeze",
        type=float,
        default=config.env_float("MINION_IDLE_FREEZE", 600),
        help="freeze desktops idle for this many seconds (0 = never)",
    )
    sp.add_argument("--quiet", "-q", action="store_true")
    sp.add_argument("--stop", action="store_true", help="stop the background server that `minion view` started")

    sp = add("mcp", cmd_mcp, "run the MCP server on stdio (for Claude Code, Claude Desktop, Cursor, ...)")
    sp.add_argument("--preload", help="comma-separated profiles to prepare in the background")
    sp.add_argument("--compact", action="store_true", help="expose one `computer` tool (smallest context)")
    sp.add_argument(
        "--no-images",
        action="store_true",
        help="text only: no screenshot tool, no images in results (for clients "
        "that would pass images to the model as base64 text)",
    )
    sp.add_argument("--idle-freeze", type=float, default=config.env_float("MINION_IDLE_FREEZE", 600))

    sp = add("share", cmd_share, "a public HTTPS MCP URL for ChatGPT, Claude.ai, Le Chat… (Ctrl+C stops sharing)")
    sp.add_argument("--token", help="access token (default: a fresh random one each time)")
    sp.add_argument("--port", type=int, default=int(os.environ.get("MINION_SHARE_PORT", "4748")), help="local port")
    sp.add_argument("--bind", default="127.0.0.1", help="local address to listen on (default 127.0.0.1)")
    sp.add_argument(
        "--files",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="let `files` upload/download use this computer's disk, inside MINION_FILES_ROOT, and desktops start "
        "from your saved sign-ins (default: no)",
    )
    sp.add_argument("--docker", action="store_true", help="run cloudflared in Docker even if it is installed")
    sp.add_argument("--tailscale", action="store_true", help="publish with `tailscale funnel` instead of Cloudflare")
    sp.add_argument("--compact", action="store_true", help="hand out the URL of the single `computer` tool")
    sp.add_argument("--no-images", action="store_true", help="hand out a text-only URL (no screenshots)")

    sp = add("connect", cmd_connect, "add Minion's MCP server to your agent apps (Claude, Cursor, VS Code, ...)")
    sp.add_argument("apps", nargs="*", metavar="APP", help="apps to connect (default: the ones on this computer)")
    sp.add_argument("--all", action="store_true", help="every app found on this computer, without asking")
    sp.add_argument("--list", action="store_true", help="show the apps, their config and whether they're connected")
    sp.add_argument("--dry-run", action="store_true", help="show the changes (a diff) without making them")
    sp.add_argument("--remove", action="store_true", help="take Minion out of the apps' configs again")
    sp.add_argument("--compact", action="store_true", help="use `minion mcp --compact` (one tool, smallest context)")
    sp.add_argument("--yes", "-y", action="store_true", help="don't ask (connect every app found)")

    sp = add("setup", cmd_setup, "first-run wizard: check Docker, prepare desktops, connect your agent apps")
    sp.add_argument("--profiles", metavar="LIST", help="profiles to prepare, e.g. office,dev (default: browser; none)")
    sp.add_argument("--yes", "-y", action="store_true", help="don't ask; use the defaults")
    sp.add_argument("--compact", action="store_true", help="connect apps to `minion mcp --compact`")

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


def _utf8_streams() -> None:
    """Agents read this output through pipes, which on Windows default to the ANSI code page: it can't
    encode ✓ or most text on screen. Always speak UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # not a TextIOWrapper (e.g. replaced by a test harness)
            pass


def entry() -> None:
    _utf8_streams()
    sys.exit(main())


if __name__ == "__main__":
    entry()
