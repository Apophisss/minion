import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own config/state directory."""
    monkeypatch.setenv("MINION_HOME", str(tmp_path / "minion-home"))
    yield


def docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    import subprocess

    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def x11_ready() -> bool:
    from minion.backends.local import missing_tools

    return sys.platform.startswith("linux") and not missing_tools()
