"""Build the Claude Desktop extension, dist/minion.mcpb, from this repository.

    python scripts/build_mcpb.py                 # writes dist/minion.mcpb and prints its SHA-256
    python scripts/build_mcpb.py --smoke         # then starts it the way Claude Desktop does and checks it
    python scripts/build_mcpb.py --stage DIR     # also writes the bundle's files to DIR, for the official check:
    npx -y @anthropic-ai/mcpb@2.1.2 validate DIR

The bundle is an MCPB "uv" extension (packaging/mcpb/README.md explains why): packaging/mcpb/ plus the
`minion` package, exactly the files the wheel ships. The version comes from minion/agent/__init__.py. The
build is reproducible: sorted entries, fixed timestamps (SOURCE_DATE_EPOCH, else 1980-01-01) and
permissions, so the same commit gives the same bytes with the same Python. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import zipfile
from pathlib import Path
from typing import NoReturn

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "packaging" / "mcpb"
# Bundle path -> source. The minion package goes to server/minion, next to the launcher.
FILES = {
    "manifest.json": SRC / "manifest.json",
    "pyproject.toml": SRC / "pyproject.toml",
    "icon.png": SRC / "icon.png",
    "server/main.py": SRC / "server" / "main.py",
    "LICENSE": REPO / "LICENSE",
}


def fail(message: str) -> NoReturn:
    sys.exit(f"build_mcpb: {message}")


def version() -> str:
    text = (REPO / "minion" / "agent" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION = "([^"]+)"', text, re.M)
    if not m or not re.fullmatch(r"\d+\.\d+\.\d+([-+.][0-9A-Za-z.+-]+)?", m[1]):
        fail("no semantic VERSION in minion/agent/__init__.py")
    return m[1]


def live_tools() -> list[str]:
    """The tool names Minion's MCP server lists (all nine: the bundle runs without --compact)."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from minion.tools import TOOLS

    return sorted(t["name"] for t in TOOLS)


def in_package(folder: Path, top: Path) -> bool:
    """Whether setuptools ships the .py files in `folder`: it and each folder up to `top` has __init__.py."""
    while (folder / "__init__.py").is_file():
        if folder == top:
            return True
        folder = folder.parent
    return False


def package_files() -> list[Path]:
    """The minion package as the wheel has it: the .py files of its packages plus pyproject's package-data."""
    top = REPO / "minion"
    found = {p for p in top.rglob("*.py") if "__pycache__" not in p.parts and in_package(p.parent, top)}
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    for pattern in config["tool"]["setuptools"]["package-data"]["minion"]:
        folder, _, name = pattern.rpartition("/")
        base = top / folder
        if base.is_dir():
            found.update(p for p in base.iterdir() if p.is_file() and fnmatch.fnmatch(p.name, name))
    return sorted(found)


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        fail("packaging/mcpb/icon.png is not a PNG")
    return struct.unpack(">II", data[16:24])


def manifest(ver: str) -> bytes:
    data = json.loads(FILES["manifest.json"].read_text(encoding="utf-8"))
    data["version"] = ver
    if data.get("manifest_version") != "0.4" or data["server"].get("type") != "uv":
        fail('the manifest must say manifest_version "0.4" and server type "uv"')
    listed = sorted(t["name"] for t in data.get("tools", []))
    if listed != live_tools():
        fail(
            f"the manifest lists the tools {listed}, the server has {live_tools()}: update packaging/mcpb/manifest.json"
        )
    settings = data.get("user_config", {})
    for key, option in settings.items():
        if "default" not in option:  # Claude Desktop would pass the literal text "${user_config.KEY}"
            fail(f"user_config.{key} needs a default")
    unknown = set(re.findall(r"\$\{user_config\.([^}]+)\}", json.dumps(data["server"]))) - set(settings)
    if unknown:
        fail(f"mcp_config uses settings that user_config doesn't define: {sorted(unknown)}")
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()


def contents(ver: str) -> dict[str, bytes]:
    files = {name: path.read_bytes() for name, path in FILES.items()}
    files["manifest.json"] = manifest(ver)
    project = files["pyproject.toml"].decode()
    files["pyproject.toml"] = re.sub(r'^version = ".*"$', f'version = "{ver}"', project, count=1, flags=re.M).encode()
    for path in package_files():
        files["server/" + path.relative_to(REPO).as_posix()] = path.read_bytes()
    if png_size(files["icon.png"]) != (512, 512):
        fail("packaging/mcpb/icon.png must be 512x512")
    return dict(sorted(files.items()))


def zip_bytes(files: dict[str, bytes]) -> bytes:
    epoch = max(int(os.environ.get("SOURCE_DATE_EPOCH") or 0), 315532800)  # zip timestamps start in 1980
    stamp = time.gmtime(epoch)[:6]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, stamp)
            info.create_system = 3  # Unix, so that the permissions below mean the same on every OS
            info.external_attr = 0o100644 << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buf.getvalue()


# -- smoke test: start the bundle the way Claude Desktop does ---------------------------------------------------
def find_uv() -> str | None:
    exe = "uv.exe" if os.name == "nt" else "uv"
    for path in (shutil.which("uv"), Path.home() / ".local" / "bin" / exe, Path.home() / ".cargo" / "bin" / exe):
        if path and Path(path).is_file():
            return str(path)
    return None


def smoke(bundle: Path, ver: str) -> None:
    """Unpack the bundle, start its server with `uv run` (as the manifest says) and check the MCP handshake."""
    with tempfile.TemporaryDirectory(prefix="minion-mcpb-") as tmp:
        with zipfile.ZipFile(bundle) as zf:
            zf.extractall(tmp)
        uv = find_uv()
        if uv:
            command = [uv, "run", "--directory", tmp, "server/main.py", "mcp"]
        else:
            command = [sys.executable, str(Path(tmp) / "server" / "main.py"), "mcp"]
        note = "" if uv else "   (no uv found: using this Python)"
        print("smoke test: " + " ".join(command) + note, flush=True)
        # Settings as Claude Desktop may pass them: one never filled in, one default left unexpanded.
        env = {
            **os.environ,
            "MINION_DEFAULT_PROFILE": "${user_config.default_profile}",
            "MINION_FILES_ROOT": "${HOME}/Downloads",
        }
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True, encoding="utf-8"
        )
        lines: queue.Queue = queue.Queue()

        def pump() -> None:
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)  # the server exited

        threading.Thread(target=pump, daemon=True).start()
        hello = {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "build_mcpb", "version": ver},
        }
        for msg in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": hello},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ):
            proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        replies: dict = {}
        deadline = time.monotonic() + 300  # a first start may download Python
        try:
            while len(replies) < 2:
                line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
                if line is None:
                    break
                reply = json.loads(line)
                replies[reply.get("id")] = reply
        except queue.Empty:
            pass
        finally:
            proc.kill()
            proc.wait()
    info = replies.get(1, {}).get("result", {}).get("serverInfo", {})
    names = [t["name"] for t in replies.get(2, {}).get("result", {}).get("tools", [])]
    if info.get("version") != ver or sorted(names) != live_tools():
        fail(f"smoke test failed: serverInfo {info}, tools {names}")
    print(f"smoke test passed: {info['name']} {info['version']} lists {len(names)} tools ({', '.join(names)})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--output", type=Path, default=REPO / "dist" / "minion.mcpb", help="%(default)s")
    parser.add_argument("--stage", type=Path, help="also write the bundle's files to this new or empty folder")
    parser.add_argument("--smoke", action="store_true", help="start the built bundle as Claude Desktop does")
    args = parser.parse_args()

    ver = version()
    files = contents(ver)
    data = zip_bytes(files)
    if args.stage:
        if args.stage.exists() and any(args.stage.iterdir()):
            fail(f"--stage {args.stage} is not empty")
        for name, body in files.items():
            (args.stage / name).parent.mkdir(parents=True, exist_ok=True)
            (args.stage / name).write_bytes(body)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"{args.output}: Minion {ver}, {len(files)} files, {len(data) / 1024:.0f} KB")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}", flush=True)
    if args.smoke:
        smoke(args.output, ver)


if __name__ == "__main__":
    main()
