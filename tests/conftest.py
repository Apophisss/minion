"""Shared pytest fixtures.

* ``settings``  - Settings pointing at a temporary data dir (source dir = this repo)
* ``db``        - connected Database
* ``services``  - a minimal Services container (db, bus, secrets); tests attach the
                  components they need (``services.hub = FakeHub()`` ...)
* ``docker_ok`` - skips the test when no Docker daemon is reachable
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from minion.config import Settings
from minion.context import Services
from minion.db import Database
from minion.events import EventBus
from minion.secrets import SecretStore

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def settings(tmp_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    # Never let a developer's real .env / environment leak into tests.
    for key in list(os.environ):
        if key.startswith("MINION_") or key in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN"):
            monkeypatch.delenv(key, raising=False)
    s = Settings(
        _env_file=None,
        data_dir=tmp_data_dir,
        src_dir=REPO_ROOT,
        api_token="test-admin-token",
        gateway_token="test-gateway-token",
        autostart=[],
        update_mode="off",
        contribute_mode="off",
        improve_interval_hours=0,
        scout_interval_hours=0,
        anthropic_api_key="sk-ant-test",
    )
    s.ensure_dirs()
    return s


@pytest.fixture
async def db(settings: Settings):
    database = Database(settings.db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def services(settings: Settings, db: Database) -> Services:
    return Services(settings=settings, db=db, bus=EventBus(), secrets=SecretStore(db))


def _docker_reachable() -> bool:
    if not shutil.which("docker") and not Path("/var/run/docker.sock").exists():
        return False
    try:
        import docker

        client = docker.from_env(timeout=3)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def docker_ok() -> bool:
    if os.environ.get("MINION_SKIP_DOCKER_TESTS") == "1" or not _docker_reachable():
        pytest.skip("Docker daemon not reachable")
    return True
