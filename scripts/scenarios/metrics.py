"""Calls, screenshots, failed calls, output tokens and seconds per batch, from a run's logs and results.

    python scripts/scenarios/metrics.py [RUNS_DIR]      # default: scripts/scenarios/runs

RUNS_DIR/logs/<scenario>.jsonl comes from log.py, RUNS_DIR/results/<batch>.jsonl from the agents (one JSON object
per scenario with at least "id" and "success"). Tokens are counted with tiktoken's o200k_base when it is installed.
"""

import glob
import json
import os
import sys
from pathlib import Path

try:
    import tiktoken

    _enc = tiktoken.get_encoding("o200k_base")

    def tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:  # pragma: no cover

    def tokens(text: str) -> int:
        return max(1, len(text) // 4)


def objects(path: str) -> list[dict]:
    """JSON objects one after another (one per line, or pretty-printed over several lines)."""
    out, buf = [], ""
    for line in open(path, encoding="utf-8"):
        buf += line
        try:
            out.append(json.loads(buf))
            buf = ""
        except ValueError:
            continue
    return out


def main() -> int:
    runs = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "runs")
    results = {}
    for f in glob.glob(str(runs / "results" / "*.jsonl")):
        for r in objects(f):
            results[r["id"]] = (os.path.basename(f)[:-6], r)
    batches: dict[str, list] = {}
    for sid, (batch, r) in results.items():
        log = runs / "logs" / f"{sid}.jsonl"
        calls = objects(str(log)) if log.exists() else []
        row = batches.setdefault(batch, [0, 0, 0, 0, 0, 0, 0.0])
        row[0] += 1
        row[1] += r.get("success") == "yes"
        row[2] += len(calls)
        row[3] += sum(1 for c in calls if c["args"][2:3] in (["shot"], ["screenshot"]))
        row[4] += sum(1 for c in calls if c["code"] != 0)
        row[5] += sum(tokens(c["out"]) for c in calls)
        row[6] += sum(c["secs"] for c in calls)
    print(f"{'batch':10} {'tasks':>5} {'done':>4} {'calls':>5} {'shots':>5} {'failed':>6} {'tokens':>7} {'secs':>6}")
    total = [0, 0, 0, 0, 0, 0, 0.0]
    for batch, row in sorted(batches.items()):
        print(f"{batch:10} {row[0]:5} {row[1]:4} {row[2]:5} {row[3]:5} {row[4]:6} {row[5]:7} {row[6]:6.0f}")
        total = [a + b for a, b in zip(total, row, strict=True)]
    print(f"{'total':10} {total[0]:5} {total[1]:4} {total[2]:5} {total[3]:5} {total[4]:6} {total[5]:7} {total[6]:6.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
