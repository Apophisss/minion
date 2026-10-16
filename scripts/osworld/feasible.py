"""Replacements for sampled tasks this environment blocks: draw tasks from the same app (seeded) until one passes
both checks: OSWorld's expected file still passes its checker after this LibreOffice opens and saves it, and (Impress)
saving the original keeps the slide backgrounds the expected file has on slides the task leaves alone."""

import contextlib
import io
import json
import logging
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import stubs  # noqa: E402,F401

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from pptx import Presentation

NAME = "osw-fid"


def parts(task):
    ev = task["evaluator"]
    many = isinstance(ev["func"], list)
    results = ev.get("result") if many else [ev.get("result")]
    expected = (ev.get("expected") or []) if many else [ev.get("expected")]
    opts = (ev.get("options") or [{}] * len(results)) if many else [ev.get("options") or {}]
    opts = opts if isinstance(opts, list) else [opts]
    return ev, results, expected, opts


def gold_roundtrip(tid, task):
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        value, _ = bench.gold_roundtrip(NAME, task, bench.ROOT / "evalcache" / "feas" / tid)
    return value


def colors(path):
    out = []
    for slide in Presentation(path).slides:
        fill = slide.background.fill
        if fill.type == 1:
            out.append(str(fill.fore_color.rgb))
        elif fill.type == 5:
            master = slide.slide_layout.slide_master.background.fill
            out.append(str(master.fore_color.rgb) if master.type == 1 else None)
        else:
            out.append(None)
    return out


def background_ok(tid, task):
    ev, results, expected, opts = parts(task)
    golds = [e for e in expected if e and e.get("type") == "cloud_file" and str(e.get("path", "")).endswith(".pptx")]
    if not golds or not any((o or {}).get("examine_background_color", True) for o in opts):
        return True
    bench.fresh(NAME)
    for s in task.get("config", []):
        bench.step(NAME, s)
    bench.resave(NAME, bench.inside(results[0]["path"]))  # this LibreOffice's save of the task's own file
    for s in ev.get("postconfig", []):
        try:
            bench.step(NAME, s)
        except Exception:  # noqa: BLE001
            pass
    local = bench.ROOT / "evalcache" / "feas" / (tid + ".orig.pptx")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(bench.Controller(NAME).get_file(results[0]["path"]) or b"")
    try:
        mine, gold = colors(local), colors(bench.cached(golds[0]["path"]))
    except Exception:  # noqa: BLE001
        return False
    # Blocked: a slide whose expected background is white (left as it was) that this LibreOffice saves with none.
    return not any(g == "FFFFFF" and m is None for m, g in zip(mine, gold, strict=False))


def feasible(tid):
    domain, task = bench.task_file(tid)
    if task["evaluator"]["func"] == "infeasible":
        return True, "infeasible task"
    rt = gold_roundtrip(tid, task)
    if rt == 0.0:
        return False, "expected file fails its checker after a save here"
    if domain == "libreoffice_impress" and not background_ok(tid, task):
        return False, "white slide backgrounds saved as none here"
    return True, "ok" if rt is not None else "no expected file to try"


if __name__ == "__main__":
    idx = json.load(open(bench.OSW / "evaluation_examples" / "test_all.json"))
    sample = json.load(open(bench.ROOT / "sample30.json"))
    need = {"libreoffice_impress": 7, "libreoffice_writer": 1}
    found = {}
    log = open(bench.ROOT / "feasible.jsonl", "a")
    for domain, n in need.items():
        pool = [i for i in idx[domain] if i not in sample]
        random.Random(2027).shuffle(pool)
        found[domain] = []
        for tid in pool:
            if len(found[domain]) >= n:
                break
            ok, why = feasible(tid)
            log.write(json.dumps({"id": tid, "domain": domain, "feasible": ok, "why": why}) + "\n")
            log.flush()
            if ok:
                found[domain].append(tid)
    subprocess.run([bench.MINION, "rm", NAME], capture_output=True)
    json.dump(found, open(bench.ROOT / "replacements.json", "w"), indent=1)
    print("FEASIBLE-DONE", {d: len(v) for d, v in found.items()})
