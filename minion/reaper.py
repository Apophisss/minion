"""Idle freezing: desktops nobody has used (or watched) for a while are paused.

A frozen desktop costs 0% CPU; the next call to it thaws it in about a tenth of a
second, so agents never notice.
"""

from __future__ import annotations

import sys
import threading
import time

_started = False
_lock = threading.Lock()


def _loop(backend, threshold: float, interval: float) -> None:
    from . import config
    from .desktop import Desktop

    stop_after = config.env_float("MINION_IDLE_STOP", 0)  # seconds; 0 = never stop, only freeze
    frozen: dict[str, tuple[float, float]] = {}  # name -> (when we froze it, its idle time then)
    while True:
        time.sleep(interval)
        try:
            now = time.monotonic()
            for info in backend.list():
                if info.state == "paused":
                    # Never call into a frozen desktop (that would wake it); time it here instead.
                    if stop_after and info.name in frozen:
                        at, idle0 = frozen[info.name]
                        if idle0 + (now - at) >= stop_after:
                            backend.stop(info.name)
                            frozen.pop(info.name, None)
                            _say(f"stopped idle desktop {info.name!r} (files kept; it restarts on the next call)")
                    continue
                frozen.pop(info.name, None)
                if info.state != "running":
                    continue
                d = Desktop(info.name, backend)
                try:  # never wake a desktop from here: someone may have frozen it since list()
                    st = d.call("status", timeout=15, wake=False)
                    if st.get("inflight"):
                        continue
                    idle = min(float(st.get("idle", 0)), float(st.get("viewed", st.get("idle", 0))))
                    if idle >= threshold:
                        d.freeze()
                        frozen[info.name] = (time.monotonic(), idle)
                        _say(f"froze idle desktop {info.name!r} (idle {idle:.0f}s; it wakes on the next call)")
                except Exception:
                    pass
                finally:
                    d.close()
        except Exception:
            pass


def _say(text: str) -> None:
    sys.stderr.write(f"[minion] {text}\n")
    sys.stderr.flush()


def start_reaper(backend, threshold: float, interval: float = 60.0) -> None:
    """Start (once per process) a background thread that freezes idle desktops."""
    global _started
    if threshold <= 0:
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(
        target=_loop,
        args=(backend, threshold, min(interval, max(5.0, threshold / 2))),
        daemon=True,
        name="minion-reaper",
    ).start()
