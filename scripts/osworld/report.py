"""Add up the OSWorld-on-Minion runs: success, steps, screenshots, tokens and time per condition, paired by task.

    python report.py                 # every task that each condition did
    python report.py --feasible      # without the tasks this environment blocks (blocked.json)
    python report.py --json          # the numbers, for docs

Conditions are the letters given to `bench.py plan`: S = screenshots and coordinates only, M = Minion (and N, in
the published results, the Minion version with the fixes that the first run led to).
"""

import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("OSWORLD_RUN", "~/osworld-run")).expanduser()
NAMES = {"S": "Screenshots only", "M": "Minion", "N": "Minion (another version)"}


def load() -> dict:
    rows = []
    for f in sorted((ROOT / "results").glob("*.jsonl")):
        rows += [json.loads(line) for line in f.open()]
    by: dict = defaultdict(dict)
    for r in rows:
        by[r["id"]][r["cond"]] = r  # (the last run of a task in a condition)
    return by


def summary(by: dict, cond: str, tasks: list) -> dict:
    rs = [by[t][cond] for t in tasks]
    n = len(rs)
    tot = lambda key: sum(r[key] for r in rs)  # noqa: E731
    return {
        "tasks": n,
        "success": tot("score") / n,
        "solved": tot("score"),
        "steps": tot("steps") / n,
        "shots": tot("shots") / n,
        "text_tokens": tot("text_tokens") / n,
        "image_tokens": tot("image_tokens") / n,
        "tokens": (tot("text_tokens") + tot("image_tokens")) / n,
        "seconds": tot("seconds") / n,
    }


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n)


def main(argv: list[str]) -> int:
    by = load()
    blocked = set(json.loads((ROOT / "blocked.json").read_text())) if (ROOT / "blocked.json").exists() else set()
    conds = sorted({c for v in by.values() for c in v}, key=lambda c: ("SMN".find(c) % 9, c))
    tasks = sorted(t for t, v in by.items() if all(c in v for c in conds))
    if "--feasible" in argv:
        tasks = [t for t in tasks if t not in blocked]
    stats = {c: summary(by, c, tasks) for c in conds} if tasks else {}
    pairs = {}
    for a, b in (("M", "S"), ("N", "S"), ("N", "M")):
        if a in conds and b in conds:
            wins = sum(1 for t in tasks if by[t][a]["score"] > by[t][b]["score"])
            losses = sum(1 for t in tasks if by[t][a]["score"] < by[t][b]["score"])
            pairs[f"{a}-{b}"] = {"better": wins, "worse": losses, "p": sign_test(wins, losses)}
    if "--json" in argv:
        print(json.dumps({"tasks": tasks, "stats": stats, "pairs": pairs}, indent=1))
        return 0
    print(f"{len(tasks)} tasks done in every condition ({', '.join(NAMES.get(c, c) for c in conds)})\n")
    print("| | " + " | ".join(NAMES.get(c, c) for c in conds) + " |")
    print("|---|" + "---:|" * len(conds))
    for key, label, fmt in [
        ("success", "Success", "{:.1%}"),
        ("steps", "Steps per task", "{:.1f}"),
        ("shots", "Screenshots per task", "{:.1f}"),
        ("tokens", "Tokens the computer returned, per task", "{:,.0f}"),
        ("seconds", "Seconds per task", "{:.0f}"),
    ]:
        print(f"| {label} | " + " | ".join(fmt.format(stats[c][key]) for c in conds) + " |")
    print()
    for c in conds:
        lo, hi = wilson(stats[c]["solved"], len(tasks))
        print(f"{NAMES.get(c, c)}: {stats[c]['solved']:.1f}/{len(tasks)} solved, 95% interval {lo:.0%}-{hi:.0%}")
    for name, p in pairs.items():
        a, b = name.split("-")
        print(
            f"{NAMES.get(a, a)} vs {NAMES.get(b, b)}: better on {p['better']}, worse on {p['worse']} (sign test p = {p['p']:.3f})"
        )
    print("\n| Task | " + " | ".join(conds) + " |")
    print("|---|" + "---|" * len(conds))
    for t in tasks:
        row = by[t][conds[0]]
        cells = [f"{by[t][c]['score']:.2f} ({by[t][c]['steps']} steps)" for c in conds]
        print(f"| {row['domain'][12:]} {t[:8]} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
