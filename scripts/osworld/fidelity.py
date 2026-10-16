"""Can a perfect result pass in this environment? For each task, OSWorld's expected file goes where the agent's
result goes, this LibreOffice opens and saves it, and the task's own checker scores it (bench.gold_roundtrip).

    fidelity.py [TASK_ID...]        default: the tasks in tasks.json; results in $OSWORLD_RUN/fidelity.jsonl
"""

import contextlib
import io
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

name = "osw-fid"
ids = sys.argv[1:] or json.load(open(bench.HERE / "tasks.json"))["tasks"]
out = open(bench.ROOT / "fidelity.jsonl", "a")
for tid in ids:
    domain, task = bench.task_file(tid)
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()):
        value, notes = bench.gold_roundtrip(name, task, bench.ROOT / "evalcache" / "fid" / tid)
    out.write(json.dumps({"id": tid, "domain": domain, "fidelity": value, "notes": notes}) + "\n")
    out.flush()
subprocess.run([bench.MINION, "rm", name], capture_output=True)
print("FIDELITY-DONE")
