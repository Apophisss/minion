"""Run one minion command for a scenario and log it: python scripts/scenarios/log.py SCENARIO_ID [minion args...]

Each call is appended to runs/logs/SCENARIO_ID.jsonl (the arguments, seconds, exit code and output), which
metrics.py turns into calls, output tokens and time per scenario.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

RUNS = Path(os.environ.get("MINION_SCENARIO_RUNS", Path(__file__).resolve().parent / "runs"))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    sid, args = sys.argv[1], sys.argv[2:]
    t = time.time()
    p = subprocess.run([sys.executable, "-m", "minion", *args], capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    (RUNS / "logs").mkdir(parents=True, exist_ok=True)
    entry = {"t": round(t, 2), "args": args, "secs": round(time.time() - t, 2), "code": p.returncode, "out": out}
    with open(RUNS / "logs" / f"{sid}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    sys.stdout.write(out)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
