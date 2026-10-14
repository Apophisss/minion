"""Backends run desktops: Docker/Podman containers (default) or local Xvfb sessions (Linux)."""

from __future__ import annotations

import os
import shutil
import sys

from ..errors import MinionError
from .base import Backend, CreateOptions, DesktopInfo, Snapshot, check_name

_cache: dict[str, Backend] = {}


def get_backend(name: str | None = None) -> Backend:
    name = (name or os.environ.get("MINION_BACKEND") or "auto").lower()
    if name == "auto":
        if shutil.which(os.environ.get("MINION_DOCKER", "docker")) or shutil.which("podman"):
            name = "docker"
        elif sys.platform.startswith("linux") and shutil.which("Xvfb"):
            name = "local"
        else:
            name = "docker"
    if name in _cache:
        return _cache[name]
    if name in ("docker", "podman"):
        from .docker import DockerBackend

        backend: Backend = DockerBackend("podman" if name == "podman" else None)
    elif name == "local":
        from .local import LocalBackend

        backend = LocalBackend()
    else:
        raise MinionError(f"unknown backend {name!r} (use docker, podman or local)")
    _cache[name] = backend
    return backend


__all__ = ["Backend", "CreateOptions", "DesktopInfo", "Snapshot", "check_name", "get_backend"]
