#!/usr/bin/env python3
"""Minion supervisor - PID 1 of the core container (under tini).

Standard library only, and always executed from the image (``/app``), so that
nothing Minion does to its own source tree can break this safety net.

Responsibilities:

1. Bootstrap the running source tree ``<data>/src`` (a git clone of ``/app``),
   pointing ``origin`` at the upstream repository, and fold in newer image code
   after a manual image rebuild.
2. Keep ``<data>/venv`` (``--system-site-packages``) in sync with the source's
   ``requirements.txt`` + ``requirements-extra.txt`` so code-level updates may add
   dependencies without an image rebuild.
3. Run ``python -m minion.server`` from the source tree; restart it when it asks
   (exit code 75) or crashes (with backoff).
4. Health-check every new commit. A commit that crashes or never becomes healthy is
   rolled back to the last good commit (``git reset --hard``), and the failure is
   written to ``<data>/run/rollback.json`` so the brain can learn from it.
5. After repeated failures fall back to "safe mode" (run the image's pristine code)
   so the system stays reachable and can repair itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

RESTART_EXIT_CODE = 75

APP_DIR = Path(os.environ.get("MINION_IMAGE_SRC_DIR", "/app"))
DATA_DIR = Path(os.environ.get("MINION_DATA_DIR", "/data"))
SRC_DIR = Path(os.environ.get("MINION_SRC_DIR", str(DATA_DIR / "src")))
RUN_DIR = DATA_DIR / "run"
VENV_DIR = DATA_DIR / "venv"
LOG_DIR = DATA_DIR / "logs"
PORT = int(os.environ.get("MINION_PORT", "8700"))
HEALTH_URL = os.environ.get("MINION_HEALTH_URL", f"http://127.0.0.1:{PORT}/health")
HEALTH_TIMEOUT = float(os.environ.get("MINION_HEALTH_TIMEOUT_S", "120"))
MAX_ROLLBACKS_BEFORE_SAFE_MODE = 3
GOOD_TAG = "minion-last-good"


def log(msg: str) -> None:
    print(f"[supervisor] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def git(*args: str, cwd: Path = SRC_DIR, check: bool = True, timeout: float = 300) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip() or None
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------- bootstrap


def configure_git_identity(repo: Path) -> None:
    git("config", "user.name", os.environ.get("MINION_GIT_NAME", "Minion"), cwd=repo)
    git("config", "user.email", os.environ.get("MINION_GIT_EMAIL", "minion@localhost"), cwd=repo)
    # Several uids may touch the volume (helper containers); trust it.
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True)


def upstream_url() -> str | None:
    url = os.environ.get("MINION_REPO_URL")
    if url:
        return url
    if (APP_DIR / ".git").exists():
        try:
            return git("remote", "get-url", "origin", cwd=APP_DIR) or None
        except RuntimeError:
            return None
    return None


def bootstrap_source() -> None:
    """Create ``SRC_DIR`` on first boot; fold in a newer image afterwards."""
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True)
    if (SRC_DIR / ".git").exists() and (SRC_DIR / "minion").is_dir():
        configure_git_identity(SRC_DIR)
        merge_image_into_source()
        return

    if SRC_DIR.exists():
        # Half-initialised tree (e.g. interrupted first boot): keep a copy, start over.
        backup = SRC_DIR.with_name(f"src.broken-{int(time.time())}")
        log(f"source dir is incomplete, moving it to {backup}")
        SRC_DIR.rename(backup)

    SRC_DIR.parent.mkdir(parents=True, exist_ok=True)
    if (APP_DIR / ".git").exists():
        log(f"cloning {APP_DIR} -> {SRC_DIR}")
        subprocess.run(["git", "clone", "--no-hardlinks", str(APP_DIR), str(SRC_DIR)], check=True)
    else:
        log(f"copying {APP_DIR} -> {SRC_DIR} (image has no git metadata)")
        shutil.copytree(APP_DIR, SRC_DIR, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data"))
        git("init", "-q", "-b", os.environ.get("MINION_REPO_BRANCH", "main"))
        configure_git_identity(SRC_DIR)
        git("add", "-A")
        git("commit", "-q", "-m", "Baseline from image")

    configure_git_identity(SRC_DIR)
    url = upstream_url()
    remotes = git("remote").split()
    if url:
        if "origin" in remotes:
            git("remote", "set-url", "origin", url)
        else:
            git("remote", "add", "origin", url)
    if "image" not in remotes:
        git("remote", "add", "image", str(APP_DIR), check=False)
    head = git("rev-parse", "HEAD")
    mark_good(head)
    log(f"source ready at {head[:10]} (origin={url or 'none'})")


def merge_image_into_source() -> None:
    """If the image carries commits the source tree lacks (manual rebuild), merge them in."""
    if not (APP_DIR / ".git").exists():
        return
    try:
        image_head = git("rev-parse", "HEAD", cwd=APP_DIR)
    except RuntimeError:
        return
    if read_text(RUN_DIR / "image_head") == image_head:
        return
    try:
        if "image" not in git("remote").split():
            git("remote", "add", "image", str(APP_DIR))
        git("fetch", "-q", "image", "HEAD:refs/remotes/image/head")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", image_head, "HEAD"], cwd=str(SRC_DIR)
        ).returncode == 0
        if not ancestor:
            dirty = git("status", "--porcelain")
            if dirty:
                git("stash", "push", "-u", "-m", "supervisor: before image merge", check=False)
            result = subprocess.run(
                ["git", "merge", "--no-edit", "-m", "Merge newer image code", image_head],
                cwd=str(SRC_DIR), capture_output=True, text=True,
            )
            if result.returncode != 0:
                git("merge", "--abort", check=False)
                log(f"could not merge image {image_head[:10]} into source (conflict) - keeping source as is")
                write_json(RUN_DIR / "image_merge_conflict.json",
                           {"image_head": image_head, "output": result.stdout[-4000:] + result.stderr[-4000:],
                            "ts": time.time()})
            else:
                log(f"merged image {image_head[:10]} into source")
        (RUN_DIR / "image_head").write_text(image_head)
    except Exception as exc:  # never block startup on this
        log(f"image merge skipped: {exc}")


# --------------------------------------------------------------------------- deps


def requirements_hash() -> str:
    h = hashlib.sha256()
    for name in ("requirements.txt", "requirements-extra.txt"):
        p = SRC_DIR / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def ensure_venv() -> Path:
    """Return the python to run the server with; install changed requirements into the overlay venv."""
    py = VENV_DIR / "bin" / "python"
    wanted = requirements_hash()
    stamp = RUN_DIR / "requirements.sha256"
    image_reqs = APP_DIR / "requirements.txt"
    src_reqs = SRC_DIR / "requirements.txt"
    extra = SRC_DIR / "requirements-extra.txt"
    needs_overlay = extra.exists() or (
        src_reqs.exists() and image_reqs.exists() and src_reqs.read_bytes() != image_reqs.read_bytes()
    )
    if not needs_overlay and not py.exists():
        return Path(sys.executable)
    if not py.exists():
        log("creating overlay venv")
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)], check=True)
    if read_text(stamp) != wanted:
        cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q"]
        for p in (src_reqs, extra):
            if p.exists():
                cmd += ["-r", str(p)]
        log("installing requirements into overlay venv")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            log(f"pip install failed (continuing with what is installed): {proc.stderr[-2000:]}")
        else:
            stamp.write_text(wanted)
    return py


# --------------------------------------------------------------------------- good / rollback


def current_head() -> str | None:
    try:
        return git("rev-parse", "HEAD")
    except Exception:
        return None


def mark_good(commit: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "last_good").write_text(commit)
    git("tag", "-f", GOOD_TAG, commit, check=False)


def rollback(failed: str, reason: str, log_tail: str) -> bool:
    good = read_text(RUN_DIR / "last_good")
    record = {"failed_commit": failed, "last_good": good, "reason": reason, "log_tail": log_tail[-8000:],
              "ts": time.time()}
    history = RUN_DIR / "rollbacks.jsonl"
    with history.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    write_json(RUN_DIR / "rollback.json", record)
    if not good or good == failed:
        log(f"cannot roll back ({reason}): no different last-good commit")
        return False
    log(f"rolling back {failed[:10]} -> {good[:10]}: {reason}")
    try:
        # Keep the failed attempt reachable for post-mortems.
        git("branch", "-f", f"failed/{failed[:12]}", failed, check=False)
        git("reset", "--hard", good)
        return True
    except Exception as exc:
        log(f"rollback failed: {exc}")
        return False


# --------------------------------------------------------------------------- child process


class Child:
    def __init__(self, python: Path, safe_mode: bool):
        self.python = python
        self.safe_mode = safe_mode
        self.proc: subprocess.Popen[str] | None = None
        self.tail: deque[str] = deque(maxlen=400)
        self._reader: threading.Thread | None = None

    def start(self) -> None:
        code_dir = APP_DIR if self.safe_mode else SRC_DIR
        env = {
            **os.environ,
            "PYTHONPATH": str(code_dir),
            "MINION_SRC_DIR": str(SRC_DIR),
            "MINION_SUPERVISED": "1",
            "MINION_SAFE_MODE": "1" if self.safe_mode else "0",
            "PYTHONUNBUFFERED": "1",
        }
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [str(self.python), "-m", "minion.server"], cwd=str(code_dir), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        log(f"started core pid={self.proc.pid} ({'SAFE MODE from image' if self.safe_mode else 'source'})")

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        logfile = LOG_DIR / "core.log"
        fh = logfile.open("a")
        for line in self.proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            self.tail.append(line)
            fh.write(line)
            fh.flush()
            if fh.tell() > 20 * 1024 * 1024:
                fh.close()
                logfile.replace(logfile.with_suffix(".log.1"))
                fh = logfile.open("a")
        fh.close()

    def poll(self) -> int | None:
        return self.proc.poll() if self.proc else 0

    def stop(self, timeout: float = 30) -> None:
        if not self.proc or self.proc.poll() is not None:
            return
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def log_tail(self) -> str:
        return "".join(self.tail)


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


# --------------------------------------------------------------------------- main loop


class Supervisor:
    def __init__(self) -> None:
        self.stopping = False
        self.safe_mode = os.environ.get("MINION_FORCE_SAFE_MODE") == "1"
        self.consecutive_rollbacks = 0
        self.crashes: deque[float] = deque(maxlen=10)
        self.child: Child | None = None

    def status(self, **extra: object) -> None:
        write_json(RUN_DIR / "supervisor.json", {
            "mode": "safe" if self.safe_mode else "normal",
            "head": current_head(),
            "last_good": read_text(RUN_DIR / "last_good"),
            "consecutive_rollbacks": self.consecutive_rollbacks,
            "child_pid": self.child.proc.pid if self.child and self.child.proc else None,
            "updated_at": time.time(),
            **extra,
        })

    def handle_signal(self, signum: int, _frame: object) -> None:
        log(f"signal {signum}: stopping")
        self.stopping = True
        if self.child:
            threading.Thread(target=self.child.stop, daemon=True).start()

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            bootstrap_source()
        except Exception as exc:
            log(f"bootstrap failed, entering safe mode: {exc}")
            self.safe_mode = True

        backoff = 1.0
        while not self.stopping:
            python = Path(sys.executable)
            if not self.safe_mode:
                try:
                    python = ensure_venv()
                except Exception as exc:
                    log(f"venv setup failed: {exc}")
            head = None if self.safe_mode else current_head()
            last_good = read_text(RUN_DIR / "last_good")
            on_probation = head is not None and head != last_good

            self.child = Child(python, self.safe_mode)
            self.child.start()
            (RUN_DIR / "restart_request.json").unlink(missing_ok=True)
            self.status(probation=on_probation)

            # Probation: a new commit must become healthy in time.
            became_healthy = False
            deadline = time.time() + HEALTH_TIMEOUT
            while not self.stopping and time.time() < deadline:
                if self.child.poll() is not None:
                    break
                if healthy():
                    became_healthy = True
                    break
                time.sleep(1)

            if self.stopping:
                break

            if not became_healthy:
                code = self.child.poll()
                reason = (f"exited with code {code} before becoming healthy" if code is not None
                          else f"not healthy within {HEALTH_TIMEOUT:.0f}s")
                self.child.stop()
                if on_probation and head:
                    if rollback(head, reason, self.child.log_tail()):
                        self.consecutive_rollbacks += 1
                        if self.consecutive_rollbacks >= MAX_ROLLBACKS_BEFORE_SAFE_MODE:
                            log("too many consecutive rollbacks - entering safe mode")
                            self.safe_mode = True
                        continue
                self.crashes.append(time.time())
                if not self.safe_mode and len([t for t in self.crashes if time.time() - t < 600]) >= 5:
                    log("core keeps failing - entering safe mode (image code)")
                    self.safe_mode = True
                    self.crashes.clear()
                    continue
                log(f"core failed ({reason}); retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # Healthy.
            backoff = 1.0
            if on_probation and head:
                mark_good(head)
                log(f"commit {head[:10]} is healthy - marked as last good")
            self.consecutive_rollbacks = 0
            self.status(probation=False)

            code = None
            while not self.stopping:
                code = self.child.poll()
                if code is not None:
                    break
                time.sleep(1)
            if self.stopping:
                break

            if code == RESTART_EXIT_CODE:
                log("restart requested by core")
                if self.safe_mode:
                    log("leaving safe mode to try the source tree again")
                    self.safe_mode = False
                continue
            self.crashes.append(time.time())
            recent = [t for t in self.crashes if time.time() - t < 600]
            log(f"core exited with code {code}; restarting in {backoff:.0f}s")
            if len(recent) >= 5 and not self.safe_mode:
                log("core keeps crashing - entering safe mode (image code)")
                self.safe_mode = True
                self.crashes.clear()
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

        if self.child:
            self.child.stop()
        self.status(stopped=True)
        log("stopped")
        return 0


def main() -> int:
    return Supervisor().run()


if __name__ == "__main__":
    sys.exit(main())
