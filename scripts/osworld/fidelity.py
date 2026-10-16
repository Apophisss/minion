"""Can a perfect result pass in this environment? Put OSWorld's expected file where the agent's result goes, open
and save it in the desktop's LibreOffice as the task's post-steps do, and score it with the task's own checker."""

import contextlib
import io
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

OFFICE = (".xlsx", ".xls", ".ods", ".docx", ".doc", ".odt", ".pptx", ".ppt", ".odp")
name = "osw-fid"
ids = json.load(open(bench.ROOT / "sample30.json"))
out = open(bench.ROOT / "fidelity.jsonl", "a")
for tid in ids:
    domain, task = bench.task_file(tid)
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
        out.write(json.dumps({"id": tid, "domain": domain, "fidelity": None, "why": "no expected file to try"}) + "\n")
        out.flush()
        continue
    bench.fresh(name)
    opened = False
    for r, e in pairs:
        gold, dest = bench.cached(e["path"]), bench.inside(r["path"])
        bench.dexec(name, f"mkdir -p \"$(dirname '{dest}')\"")
        subprocess.run(["docker", "cp", str(gold), f"minion-{name}:{dest}"], check=True, capture_output=True)
        bench.dexec(name, f"chown agent:agent '{dest}'", user="root")
        if dest.lower().endswith(OFFICE) and not opened:
            subprocess.run([bench.MINION, "open", "-d", name, dest], capture_output=True, timeout=180)
            opened = True
    if opened:
        for s in ev.get("postconfig", []):
            try:
                bench.step(name, s)
            except Exception as exc:  # noqa: BLE001
                print("post-step", s["type"], exc, file=sys.stderr)
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        value, notes = bench.score(task, name, False, bench.ROOT / "evalcache" / "fid" / tid)
    out.write(json.dumps({"id": tid, "domain": domain, "fidelity": value, "opened": opened, "notes": notes}) + "\n")
    out.flush()
    subprocess.run([bench.MINION, "rm", name], capture_output=True)
print("FIDELITY-DONE")
