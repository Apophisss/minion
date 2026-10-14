"""The backend interface: where desktops actually run."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

from ..channel import Channel
from ..errors import MinionError
from ..profiles import Profile

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def check_name(name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise MinionError(f"invalid desktop name {name!r}: use lowercase letters, digits, - and _ "
                          "(max 41 characters, starting with a letter or digit)")
    return name


@dataclass
class CreateOptions:
    size: str = "1280x800"
    memory: str = ""
    cpus: str = ""
    shm: str = ""
    network: bool = True
    mounts: list[str] = field(default_factory=list)   # "host_path:desktop_path[:ro]"
    env: dict[str, str] = field(default_factory=dict)
    ports: list[str] = field(default_factory=list)    # desktop ports to publish on 127.0.0.1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CreateOptions:
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class DesktopInfo:
    name: str
    profile: str
    state: str                  # running | paused | stopped | created | unknown
    backend: str
    size: str = ""
    created: float = 0.0
    image: str = ""
    id: str = ""
    memory: int | None = None   # bytes in use (live, when known)
    cpu: float | None = None    # percent (live, when known)
    options: dict = field(default_factory=dict)
    ports: dict = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def age(self) -> float:
        return time.time() - self.created if self.created else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("options", None)
        return d


@dataclass
class Snapshot:
    desktop: str
    tag: str
    ref: str
    created: str = ""
    size: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Backend(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """(ok, human-readable detail)."""

    @abstractmethod
    def create(self, name: str, profile: Profile, options: CreateOptions, progress=None) -> DesktopInfo: ...

    @abstractmethod
    def list(self, stats: bool = False) -> list[DesktopInfo]: ...

    def get(self, name: str) -> DesktopInfo:
        from ..errors import NotFound

        for d in self.list():
            if d.name == name:
                return d
        raise NotFound(f"no desktop named {name!r}")

    def exists(self, name: str) -> bool:
        return any(d.name == name for d in self.list())

    @abstractmethod
    def remove(self, name: str) -> None: ...

    @abstractmethod
    def start(self, name: str) -> None: ...

    @abstractmethod
    def stop(self, name: str) -> None: ...

    @abstractmethod
    def freeze(self, name: str) -> None: ...

    @abstractmethod
    def thaw(self, name: str) -> None: ...

    @abstractmethod
    def channel(self, name: str) -> Channel: ...

    @abstractmethod
    def copy_in(self, name: str, src: str, dst: str) -> None: ...

    @abstractmethod
    def copy_out(self, name: str, src: str, dst: str) -> None: ...

    @abstractmethod
    def snapshot(self, name: str, tag: str) -> Snapshot: ...

    @abstractmethod
    def snapshots(self, name: str | None = None) -> list[Snapshot]: ...

    @abstractmethod
    def restore(self, name: str, tag: str, progress=None) -> DesktopInfo: ...

    @abstractmethod
    def fork(self, name: str, new_name: str, progress=None) -> DesktopInfo: ...

    @abstractmethod
    def delete_snapshot(self, name: str, tag: str) -> None: ...

    def logs(self, name: str, tail: int = 200) -> str:
        return ""

    def prepare(self, profile: Profile, progress=None, pull: str | None = None) -> str:
        """Make sure everything needed to create `profile` desktops is ready (images...)."""
        return ""
