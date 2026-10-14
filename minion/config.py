"""Settings (environment variables) and on-disk locations."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .agent import VERSION

REGISTRY = os.environ.get("MINION_REGISTRY", "ghcr.io/apophisss")
# Desktop images are tagged major.minor: patch releases reuse them.
IMAGE_TAG = os.environ.get("MINION_IMAGE_TAG", ".".join(VERSION.split(".")[:2]))
DEFAULT_PROFILE = os.environ.get("MINION_DEFAULT_PROFILE", "browser")
DEFAULT_SIZE = os.environ.get("MINION_SIZE", "1280x800")
LABEL = "dev.minion"
CONTAINER_PREFIX = "minion-"


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def config_dir() -> Path:
    if os.environ.get("MINION_HOME"):
        return Path(os.environ["MINION_HOME"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "minion"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "minion"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "minion"


def data_dir() -> Path:
    if os.environ.get("MINION_HOME"):
        return Path(os.environ["MINION_HOME"]).expanduser() / "data"
    if sys.platform in ("win32", "darwin"):
        return config_dir() / "data"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "minion"


def user_profiles_dir() -> Path:
    return config_dir() / "profiles"


_state_lock = threading.Lock()


def _state_path() -> Path:
    return config_dir() / "state.json"


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def update_state(**changes) -> dict:
    """Merge changes into state.json (None deletes a key)."""
    with _state_lock:
        state = load_state()
        for k, v in changes.items():
            if v is None:
                state.pop(k, None)
            else:
                state[k] = v
        path = _state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            tmp.replace(path)
        except OSError:
            pass
        return state
