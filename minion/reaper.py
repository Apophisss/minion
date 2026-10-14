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
    from .desktop import Desktop

    while True:
        time.sleep(interval)
        try:
            for info in backend.list():
                if info.state != "running":
                    continue
                d = Desktop(info.name, backend)
                try:
                    st = d.call("status", timeout=15)
                    idle = min(float(st.get("idle", 0)), float(st.get("viewed", st.get("idle", 0))))
                    if idle >= threshold:
                        d.freeze()
                        sys.stderr.write(f"[minion] froze idle desktop {info.name!r} "
                                         f"(idle {idle:.0f}s; it wakes on the next call)\n")
                except Exception:
                    pass
                finally:
                    d.close()
        except Exception:
            pass


def start_reaper(backend, threshold: float, interval: float = 60.0) -> None:
    """Start (once per process) a background thread that freezes idle desktops."""
    global _started
    if threshold <= 0:
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(backend, threshold, min(interval, max(5.0, threshold / 2))),
                     daemon=True, name="minion-reaper").start()
