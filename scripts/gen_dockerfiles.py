"""Write a build context (Dockerfile + files) for every built-in profile, for CI image builds.

python scripts/gen_dockerfiles.py --registry ghcr.io/owner --tag 0.1 --out build/
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from minion import config, profiles  # noqa: E402
from minion.backends.docker import AGENT_DIR, BASE_DOCKERFILE  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--registry", default=config.REGISTRY)
ap.add_argument("--tag", default=config.IMAGE_TAG)
ap.add_argument("--out", default="build")
args = ap.parse_args()

out = Path(args.out)
shutil.rmtree(out, ignore_errors=True)
plan = []
reg = profiles.load_all()
for name in profiles.names(reg):
    p = reg[name]
    if not p.builtin:
        continue
    ctx = out / name
    ctx.mkdir(parents=True)
    if name == "base":
        shutil.copytree(AGENT_DIR, ctx / "agent", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        df = BASE_DOCKERFILE.read_text() + f'LABEL dev.minion.fingerprint="{p.fingerprint()}"\n'
    else:
        df = p.dockerfile(f"{args.registry}/minion-{p.extends}:{args.tag}")
        for path, content in p.files.items():
            target = ctx / "files" / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content.lstrip("\n"))
    (ctx / "Dockerfile").write_text(df)
    plan.append(
        {
            "profile": name,
            "parent": p.extends,
            "context": str(ctx),
            "image": f"{args.registry}/minion-{name}:{args.tag}",
        }
    )
print(json.dumps(plan, indent=2))
