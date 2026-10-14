"""Measure Minion desktops: download size, time to ready, idle RAM, RAM with the main app open,
and the token cost of `see` vs a screenshot. Reproduce the README numbers with:

    python scripts/bench.py base browser office dev research data
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

sys.path.insert(0, ".")
from minion import Desktop, profiles  # noqa: E402

MAIN_APP = {"browser": "https://en.wikipedia.org/wiki/Computer", "office": "writer", "dev": "terminal",
            "research": "https://arxiv.org/list/cs.AI/recent", "data": "calc", "base": "terminal"}


def mem_mb(name: str) -> float:
    out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", f"minion-{name}"],
                         capture_output=True, text=True).stdout
    used = json.loads(out)["MemUsage"].split("/")[0].strip()
    num = float("".join(c for c in used if c.isdigit() or c == "."))
    return num * (1024 if used.endswith("GiB") else 1 / 1024 if used.endswith("KiB") else 1)


def image_mb(profile: str) -> float:
    ref = profiles.get(profile).image
    out = subprocess.run(["docker", "image", "inspect", ref, "--format", "{{.Size}}"], capture_output=True, text=True)
    return int(out.stdout.strip()) / 1e6


def tokens(w: int, h: int) -> int:  # Claude's image token estimate
    return round(w * h / 750)


rows = []
for profile in sys.argv[1:] or ["base", "browser", "office"]:
    name = f"bench-{profile}"
    t0 = time.time()
    desk = Desktop.create(profile, name=name)
    ready = time.time() - t0
    time.sleep(3)
    idle = mem_mb(name)
    t1 = time.time()
    desk.open(MAIN_APP[profile], wait=30)
    open_s = time.time() - t1
    time.sleep(4)
    busy = mem_mb(name)
    obs = desk.see()
    see_tokens = round(len(obs.text) / 3.6)
    w, h = desk.size
    desk.freeze()
    time.sleep(1)
    frozen_cpu = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", f"minion-{name}"],
                                capture_output=True, text=True).stdout.strip()
    rows.append({"profile": profile, "download_mb": round(image_mb(profile)), "ready_s": round(ready, 1),
                 "idle_mb": round(idle), "app": MAIN_APP[profile], "app_open_s": round(open_s, 1),
                 "with_app_mb": round(busy), "see_tokens": see_tokens, "screenshot_tokens": tokens(w, h),
                 "frozen_cpu": frozen_cpu})
    desk.remove()
    print(json.dumps(rows[-1]), flush=True)

print("\n| Profile | Download | Ready in | Idle RAM | RAM with app | `see` tokens | Screenshot tokens |")
print("|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r['profile']} | {r['download_mb']} MB | {r['ready_s']} s | {r['idle_mb']} MB | "
          f"{r['with_app_mb']} MB ({r['app']}) | ~{r['see_tokens']} | ~{r['screenshot_tokens']} |")
