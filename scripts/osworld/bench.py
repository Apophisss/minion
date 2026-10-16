"""OSWorld tasks on Minion desktops, scored with OSWorld's own checkers.

    bench.py AGENT start           the next task in AGENT's batch, on a fresh desktop set up as OSWorld sets it up
    bench.py AGENT do ARGS...      one step through AGENT's interface (S: screenshots and coordinates; M: Minion)
    bench.py AGENT end [--fail]    OSWorld's post-steps (activate the window, ctrl+s) and checker; --fail: "infeasible"
    bench.py plan AGENT COND ID... give AGENT a batch of task ids: condition S (screenshots), or a letter for
                                   the Minion in MINION_BIN (the published runs: M for 1.0.0, N for 1.1.0)
    bench.py bin AGENT             write AGENT's command ($OSWORLD_RUN/bin/AGENT), the only one it uses
    bench.py brief AGENT           print AGENT's instructions (briefs/), to give to the agent as its task

Every step is logged (logs/AGENT/TASK.jsonl), and each finished task adds a line to results/AGENT.jsonl.
The agent never sees the score.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("OSWORLD_RUN", "~/osworld-run")).expanduser()  # results, logs, caches (setup.sh)
OSW = Path(os.environ.get("OSWORLD_REPO", ROOT / "OSWorld")).expanduser()  # a clone of xlang-ai/OSWorld
MINION = os.environ.get("MINION_BIN", "minion")  # the Minion being measured (condition M; S uses it for input)
STATE, RESULTS, LOGS, SHOTS, CACHE = (ROOT / d for d in ("state", "results", "logs", "shots", "cache"))
MAX_STEPS = 50
W, H = 1280, 800
IMAGE_TOKENS = round(W * H / 750)  # Claude's estimate for one 1280x800 screenshot

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(OSW))


def _tokens(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("o200k_base").encode(text))
    except ImportError:
        return max(1, len(text) // 4)


# ---------------------------------------------------------------- tasks and state


def task_file(task_id: str) -> tuple[str, dict]:
    index = json.loads((OSW / "evaluation_examples" / "test_all.json").read_text())
    for domain, ids in index.items():
        if task_id in ids:
            return domain, json.loads(
                (OSW / "evaluation_examples" / "examples" / domain / f"{task_id}.json").read_text()
            )
    raise SystemExit(f"no OSWorld task {task_id}")


def load_state(agent: str) -> dict:
    path = STATE / f"{agent}.json"
    if not path.exists():
        raise SystemExit(f"no batch for {agent}")
    return json.loads(path.read_text())


def save_state(state: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{state['agent']}.json").write_text(json.dumps(state, indent=1))


def desktop(state: dict) -> str:
    return f"osw-{state['agent']}"


# ---------------------------------------------------------------- the desktop


def dexec(
    name: str, command: str, user: str = "agent", timeout: float = 120, detach: bool = False
) -> subprocess.CompletedProcess:
    args = [
        "docker",
        "exec",
        "-u",
        user,
        "-e",
        "DISPLAY=:0",
        "-e",
        "XAUTHORITY=/tmp/minion/Xauthority",
        "-e",
        "HOME=/home/agent",
    ]
    if detach:
        args.append("-d")
    return subprocess.run(
        [*args, f"minion-{name}", "bash", "-lc", command], capture_output=True, text=True, timeout=timeout
    )


def inside(path: str) -> str:
    """OSWorld's /home/user is the desktop's /home/agent (a symlink makes both work for the agent)."""
    return re.sub(r"^/home/user(?=/|$)", "/home/agent", path)


def cached(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + "-" + os.path.basename(url.split("?")[0]))
    if not path.exists():
        import requests

        for attempt in range(4):
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                path.write_bytes(r.content)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
    return path


def windows(name: str) -> list[tuple[str, str]]:
    out = dexec(
        name,
        "for w in $(xdotool search --onlyvisible --name . 2>/dev/null); do "
        'printf "%s\\t%s\\n" "$w" "$(xdotool getwindowname $w)"; done',
    ).stdout
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]


def norm(title: str) -> str:
    return re.sub(r"\s+[–—-]\s+", " - ", title).strip()


def step(name: str, s: dict) -> None:
    kind, p = s["type"], s.get("parameters", {})
    if kind == "download":
        for f in p["files"]:
            local, dest = cached(f["url"]), inside(f["path"])
            dexec(name, f"mkdir -p {shlex.quote(os.path.dirname(dest))}")
            subprocess.run(["docker", "cp", str(local), f"minion-{name}:{dest}"], check=True, capture_output=True)
            dexec(name, f"chown agent:agent {shlex.quote(dest)}", user="root")
    elif kind == "open":
        r = subprocess.run([MINION, "open", "-d", name, inside(p["path"])], capture_output=True, text=True, timeout=180)
        if r.returncode:
            print(f"(setup: open {p['path']}: {r.stdout.strip()[:200]} {r.stderr.strip()[:200]})", file=sys.stderr)
    elif kind in ("launch", "execute", "command"):
        cmd = p["command"]
        text = shlex.join(cmd) if isinstance(cmd, list) else str(cmd)
        for k, v in {
            "{SCREEN_WIDTH_HALF}": W // 2,
            "{SCREEN_HEIGHT_HALF}": H // 2,
            "{SCREEN_WIDTH}": W,
            "{SCREEN_HEIGHT}": H,
        }.items():
            text = text.replace(k, str(v))
        text = re.sub(r"^python(?=\s)", "python3", text)
        text = text.replace("/home/user", "/home/agent")
        if "pyautogui" in text:  # OSWorld's snippets, with the xdotool shim of the bits they use
            text = f"PYTHONPATH=/opt/osw {text}"
        if kind == "launch":
            dexec(name, f"nohup {text} >/dev/null 2>&1 &", detach=True)
            time.sleep(3)
        else:
            dexec(name, text, timeout=180)
    elif kind == "activate_window":
        want = norm(p["window_name"])
        found = [w for w, t in windows(name) if norm(t) == want] or (
            [] if p.get("strict") else [w for w, t in windows(name) if want in norm(t)]
        )
        if found:
            dexec(name, f"xdotool windowactivate --sync {found[0]} 2>/dev/null; sleep 0.3")
    elif kind == "sleep":
        time.sleep(float(p["seconds"]))
    else:
        raise RuntimeError(f"setup step {kind} isn't supported on Minion desktops")


def resave(name: str, path: str, tries: int = 3) -> bool:
    """Save the open document (ctrl+s) and check that its file was written again. Right after a big document's
    window appears, LibreOffice can still be loading and drop the keys, and a round trip whose save never happened
    looks clean when it isn't."""

    def stamp() -> str:
        return dexec(name, f"stat -c '%y %s' {shlex.quote(path)}").stdout.strip()

    before = stamp()
    for _ in range(tries):
        time.sleep(3)
        subprocess.run([MINION, "act", "-d", name, "key ctrl+s"], capture_output=True, text=True, timeout=120)
        time.sleep(3)
        if stamp() != before:
            return True
    return False


OFFICE = (".xlsx", ".xls", ".ods", ".docx", ".doc", ".odt", ".pptx", ".ppt", ".odp")


def gold_roundtrip(name: str, task: dict, cache_dir: Path) -> tuple[float | None, str]:
    """Can a perfect result pass here? Put OSWorld's expected file where the agent's result goes, open it, save it
    (and check that the file was written again), run the task's post-steps and score it with the task's checker.
    A task whose checkers compare one result with several expected files ("or") gets a round trip per expected
    file, and the best counts. None: nothing to try, or the save never happened."""
    ev = task["evaluator"]
    many = isinstance(ev["func"], list)
    results = ev.get("result") if many else [ev.get("result")]
    expected = (ev.get("expected") or []) if many else [ev.get("expected")]
    pairs = [
        (r, e)
        for r, e in zip(results, expected, strict=False)
        if r
        and e
        and r.get("type") == "vm_file"
        and e.get("type") == "cloud_file"
        and not r.get("multi")
        and not e.get("multi")
    ]
    if ev["func"] == "infeasible" or not pairs:
        return None, "no expected file to try"
    golds: dict[str, list[str]] = {}
    for r, e in pairs:
        golds.setdefault(inside(r["path"]), []).append(e["path"])
    best: tuple[float | None, str] = (None, "")
    for k in range(max(len(v) for v in golds.values())):
        fresh(name)
        opened = saved = False
        for dest, urls in golds.items():
            gold = cached(urls[min(k, len(urls) - 1)])
            dexec(name, f"mkdir -p \"$(dirname '{dest}')\"")
            subprocess.run(["docker", "cp", str(gold), f"minion-{name}:{dest}"], check=True, capture_output=True)
            dexec(name, f"chown agent:agent '{dest}'", user="root")
            if dest.lower().endswith(OFFICE) and not opened:
                subprocess.run([MINION, "open", "-d", name, dest], capture_output=True, timeout=180)
                opened = True
                saved = resave(name, dest)
        for s in ev.get("postconfig", []) if opened else []:
            try:
                step(name, s)
            except Exception as exc:  # noqa: BLE001
                print("post-step", s["type"], exc, file=sys.stderr)
        value, notes = score(task, name, False, cache_dir / str(k))
        if opened and not saved:
            value, notes = None, "this LibreOffice didn't save the file"
        if best[0] is None or (value is not None and value > best[0]):
            best = (value, notes)
    return best


def fresh(name: str) -> None:
    subprocess.run([MINION, "rm", name], capture_output=True, text=True)
    r = subprocess.run([MINION, "new", "office", "--name", name], capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise SystemExit(f"could not create the desktop: {r.stdout}{r.stderr}")
    dexec(
        name,
        "ln -sfn /home/agent /home/user; mkdir -p /home/agent/{Desktop,Documents,Downloads,Pictures,Music,Videos};"
        " chown -R agent:agent /home/agent; mkdir -p /opt/osw",
        user="root",
    )
    subprocess.run(
        ["docker", "cp", str(HERE / "pyautogui.py"), f"minion-{name}:/opt/osw/pyautogui.py"],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------- scoring (OSWorld's DesktopEnv.evaluate, on Minion)


class Controller:
    def __init__(self, name: str):
        self.name = name

    def get_file(self, path: str) -> bytes | None:
        r = subprocess.run(["docker", "exec", f"minion-{self.name}", "cat", inside(path)], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def execute_python_command(self, command: str) -> dict:
        r = dexec(self.name, f"python3 -c {shlex.quote(command)}")
        return {"output": r.stdout, "error": r.stderr}


class Env:
    def __init__(self, name: str, cache_dir: Path):
        self.controller, self.cache_dir, self.vm_ip, self.server_port = Controller(name), str(cache_dir), "", 0
        cache_dir.mkdir(parents=True, exist_ok=True)


def score(task: dict, name: str, failed: bool, cache_dir: Path) -> tuple[float, str]:
    import warnings

    warnings.filterwarnings("ignore")
    import contextlib
    import io

    import stubs  # noqa: F401

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from desktop_env.evaluators import getters, metrics  # (PyMuPDF prints a deprecation note)

    def vm_command_line(env, config):
        cmd = config["command"]
        r = dexec(name, cmd if isinstance(cmd, str) else shlex.join(cmd))
        return r.stdout

    getters.get_vm_command_line = vm_command_line
    ev = task["evaluator"]
    if ev["func"] == "infeasible":
        return (1.0 if failed else 0.0), "infeasible task"
    if failed:
        return 0.0, "the agent said it couldn't be done"
    env = Env(name, cache_dir)
    many = isinstance(ev["func"], list)
    funcs = ev["func"] if many else [ev["func"]]
    results = ev.get("result") if many else [ev.get("result")]
    expected = (ev.get("expected") or [None] * len(funcs)) if many else [ev.get("expected")]
    options = ev.get("options", [{}] * len(funcs)) if many else [ev.get("options", {})]
    if many and not isinstance(options, list):
        options = [options] * len(funcs)
    conj, scores, notes = ev.get("conj", "and"), [], []
    for f, res, exp, opt in zip(funcs, results, expected, options, strict=False):
        metric = getattr(metrics, f)
        try:
            got = getattr(getters, f"get_{res['type']}")(env, res) if res else None
        except FileNotFoundError:
            got = None
        try:
            if exp:
                want = getattr(getters, f"get_{exp['type']}")(env, exp)
                value = float(metric(got, want, **(opt or {})))
            else:
                value = float(metric(got, **(opt or {})))
        except Exception as e:  # a metric that crashes on a missing or broken file scores 0, as in OSWorld runs
            value = 0.0
            notes.append(f"{f}: {type(e).__name__}: {str(e)[:200]}")
        notes.append(f"{f} = {value}")
        if conj == "and" and value == 0.0:
            return 0.0, "; ".join(notes)
        if conj == "or" and value == 1.0:
            return 1.0, "; ".join(notes)
        scores.append(value)
    return (sum(scores) / len(scores) if conj == "and" else max(scores)), "; ".join(notes)


# ---------------------------------------------------------------- the agent's commands


def log(state: dict, entry: dict) -> None:
    folder = LOGS / state["agent"]
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{state['current']['id']}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_start(state: dict) -> int:
    if state.get("current"):
        print(f"Task {state['current']['id']} is still open: run `{state['agent']} end` (or `end --fail`) first.")
        return 1
    if state["i"] >= len(state["tasks"]):
        print("All tasks in your batch are done. Write your report.")
        return 0
    task_id = state["tasks"][state["i"]]
    domain, task = task_file(task_id)
    name = desktop(state)
    t0 = time.time()
    fresh(name)
    for s in task.get("config", []):
        step(name, s)
    time.sleep(1)
    state["current"] = {
        "id": task_id,
        "domain": domain,
        "start": time.time(),
        "setup_s": round(time.time() - t0, 1),
        "steps": 0,
        "shots": 0,
        "text_tokens": 0,
    }
    save_state(state)
    n, total = state["i"] + 1, len(state["tasks"])
    print(f"Task {n} of {total} ({task_id[:8]}). The desktop is ready, with the task's files open.\n")
    print(task["instruction"])
    print(
        f"\nYou have {MAX_STEPS} steps. When you're done, run `{state['agent']} end`; if the task can't be done, "
        f"`{state['agent']} end --fail`."
    )
    return 0


def screenshot(state: dict) -> str:
    cur = state["current"]
    folder = SHOTS / state["agent"] / cur["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{cur['steps']:03d}.png"
    subprocess.run([MINION, "screenshot", "-d", desktop(state), "-o", str(path)], capture_output=True, timeout=60)
    cur["shots"] += 1
    return str(path)


S_HELP = """Commands (coordinates are pixels on the 1280x800 screen):
  shot                         take a screenshot (open the PNG it prints with Read)
  click X Y | dclick X Y | rclick X Y | move X Y
  drag X1 Y1 X2 Y2
  type TEXT                    \\n is Enter, \\t is Tab
  key KEYS                     e.g. ctrl+s, Return, ctrl+shift+Home (several: key Tab Tab Return)
  scroll X Y up|down [N]
  wait SECONDS
Every command except wait prints the path of a screenshot taken after it."""


def do_s(state: dict, args: list[str]) -> tuple[int, str]:
    if not args or args[0] in ("help", "-h", "--help"):
        return 0, S_HELP
    verb, rest = args[0], args[1:]
    name = desktop(state)

    def xy(a, b):
        return f"{int(float(a))},{int(float(b))}"

    try:
        if verb == "shot":
            return 0, f"screenshot: {screenshot(state)}"
        if verb in ("click", "dclick", "rclick", "move"):
            action = f"{verb} {xy(*rest[:2])}"
        elif verb == "drag":
            action = f"drag {xy(*rest[:2])} {xy(*rest[2:4])}"
        elif verb == "type":
            action = "type " + " ".join(rest)
        elif verb == "key":
            action = "key " + " ".join(rest)
        elif verb == "scroll":
            n = rest[3] if len(rest) > 3 else "3"
            action = f"scroll {rest[2]} {n} {xy(*rest[:2])}"
        elif verb == "wait":
            time.sleep(min(30.0, float(rest[0])))
            return 0, "waited"
        else:
            return 2, f"unknown command {verb!r}\n{S_HELP}"
    except (ValueError, IndexError):
        return 2, f"bad arguments for {verb}\n{S_HELP}"
    r = subprocess.run(
        [MINION, "act", "-d", name, "--observe", "summary", action], capture_output=True, text=True, timeout=180
    )
    note = "" if r.returncode == 0 else "the action failed\n"  # Minion's message would describe the screen in text
    return (0 if r.returncode == 0 else 1), f"{note}screenshot: {screenshot(state)}"


M_FORBIDDEN = {
    "new",
    "up",
    "rm",
    "down",
    "fork",
    "snapshot",
    "restore",
    "list",
    "ls",
    "connect",
    "setup",
    "serve",
    "share",
    "mcp",
    "build",
    "pull",
    "skill",
}


def do_m(state: dict, args: list[str]) -> tuple[int, str]:
    if not args:
        return 2, "usage: m1 COMMAND [ARGS...]  (any `minion` command for this desktop: see, act, open, run, ...)"
    sub = args[0]
    if sub in M_FORBIDDEN:
        return 2, f"`{sub}` isn't available here: your desktop is already set up and is the only one you use."
    argv = [MINION, sub, "-d", desktop(state), *args[1:]]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    if sub == "screenshot":
        state["current"]["shots"] += 1
    return r.returncode, out


def cmd_do(state: dict, args: list[str]) -> int:
    cur = state.get("current")
    if not cur:
        print(f"No task is open: run `{state['agent']} start`.")
        return 1
    is_help = not args or args[0] in ("help", "-h", "--help")
    if cur["steps"] >= MAX_STEPS and not is_help:
        print(f"You have used all {MAX_STEPS} steps: run `{state['agent']} end`.")
        return 1
    t = time.time()
    code, out = (do_s if state["cond"] == "S" else do_m)(state, args)
    if not is_help:
        cur["steps"] += 1
        cur["text_tokens"] += _tokens(out)
        log(state, {"t": round(t, 2), "args": args, "secs": round(time.time() - t, 2), "code": code, "out": out})
    save_state(state)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return code


def cmd_end(state: dict, failed: bool) -> int:
    cur = state.get("current")
    if not cur:
        print(f"No task is open: run `{state['agent']} start`.")
        return 1
    _, task = task_file(cur["id"])
    name = desktop(state)
    seconds = round(time.time() - cur["start"], 1)
    for s in task["evaluator"].get("postconfig", []):
        try:
            step(name, s)
        except Exception as e:  # noqa: BLE001
            print(f"(post-step {s['type']}: {e})", file=sys.stderr)
    import contextlib
    import io
    import logging

    logging.disable(logging.CRITICAL)  # the checkers log their comparisons (file names, expected values)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        value, notes = score(task, name, failed, ROOT / "evalcache" / state["agent"] / cur["id"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    row = {
        "agent": state["agent"],
        "cond": state["cond"],
        "domain": cur["domain"],
        "id": cur["id"],
        "score": value,
        "failed_flag": failed,
        "steps": cur["steps"],
        "shots": cur["shots"],
        "text_tokens": cur["text_tokens"],
        "image_tokens": cur["shots"] * IMAGE_TOKENS,
        "seconds": seconds,
        "setup_s": cur["setup_s"],
        "notes": notes,
    }
    with open(RESULTS / f"{state['agent']}.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    subprocess.run([MINION, "rm", name], capture_output=True)
    state["current"], state["i"] = None, state["i"] + 1
    save_state(state)
    left = len(state["tasks"]) - state["i"]
    print(
        f"Recorded. {left} task{'s' if left != 1 else ''} left"
        + (f": run `{state['agent']} start`." if left else ". Write your report.")
    )
    return 0


def write_bin(agent: str) -> Path:
    folder = ROOT / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / agent
    py, me = shlex.quote(sys.executable), shlex.quote(str(Path(__file__).resolve()))
    path.write_text(
        f"#!/bin/sh\n# OSWorld on Minion: the only command agent {agent} uses.\n"
        f'case "$1" in\n  start|end) exec {py} {me} {agent} "$@" ;;\n  *) exec {py} {me} {agent} do "$@" ;;\nesac\n'
    )
    path.chmod(0o755)
    return path


def brief(agent: str) -> str:
    state = load_state(agent)
    parts = ["common_head.md", "S.md" if state["cond"] == "S" else "M.md", "common_tail.md"]
    text = "".join((HERE / "briefs" / p).read_text() for p in parts)
    skill = ROOT / "SKILL.md"  # Minion's guide for agents, as `minion skill` prints it
    skill.write_text(subprocess.run([MINION, "skill"], capture_output=True, text=True, check=True).stdout)
    values = {
        "{A}": agent,
        "{N}": str(len(state["tasks"])),
        "{STEPS}": str(MAX_STEPS),
        "{BIN}": str(ROOT / "bin"),
        "{SKILL}": str(skill),
        "{RUN}": str(ROOT),
    }
    for k, v in values.items():
        text = text.replace(k, v)
    return text


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "bin":
        print(write_bin(argv[1]))
        return 0
    if len(argv) == 2 and argv[0] == "brief":
        print(brief(argv[1]))
        return 0
    if len(argv) >= 3 and argv[0] == "plan":
        agent, cond, ids = argv[1], argv[2], argv[3:]
        save_state({"agent": agent, "cond": cond, "tasks": ids, "i": 0, "current": None})
        print(f"{agent}: {len(ids)} tasks, condition {cond}")
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    state = load_state(argv[0])
    if argv[1] == "start":
        return cmd_start(state)
    if argv[1] == "end":
        return cmd_end(state, "--fail" in argv[2:])
    if argv[1] == "do":
        return cmd_do(state, argv[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
