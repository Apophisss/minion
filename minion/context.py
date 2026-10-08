"""The service container.

``Services`` holds every long-lived component. ``minion.app`` builds it in the
FastAPI lifespan (in dependency order), and every component receives the
``Services`` instance so it can reach its peers lazily (``services.hub`` ...).
Components must tolerate peers being ``None`` (e.g. Docker unavailable).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import Settings
from .db import Database
from .events import EventBus
from .secrets import SecretStore

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .brain.agent import Brain
    from .brain.memory import MemoryStore
    from .brain.policy import PolicyEngine
    from .brain.skills import SkillLibrary
    from .brain.suggestions import SuggestionBox
    from .brain.tools import ToolRegistry
    from .brain.usage import UsageTracker
    from .evolve.contrib import Contributor
    from .evolve.evolver import Evolver
    from .evolve.git import Git
    from .evolve.improver import Improver
    from .evolve.scheduler import Scheduler
    from .evolve.updater import Updater
    from .mcp_hub.gateway import MCPGateway
    from .mcp_hub.hub import MCPHub
    from .mcp_hub.registry_client import RegistryClient
    from .runtime.agents import AgentManager
    from .runtime.desktop import DesktopManager
    from .runtime.docker_manager import DockerManager
    from .workshop.manager import Workshop

log = logging.getLogger(__name__)

# Exit code the supervisor interprets as "restart me with the (possibly new) code".
RESTART_EXIT_CODE = 75


@dataclass
class Services:
    settings: Settings
    db: Database
    bus: EventBus
    secrets: SecretStore

    # Serialises every operation that mutates the source repo (evolve, update, catalog commits).
    git_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    git: "Git | None" = None
    docker: "DockerManager | None" = None
    hub: "MCPHub | None" = None
    registry: "RegistryClient | None" = None
    gateway: "MCPGateway | None" = None
    workshop: "Workshop | None" = None
    agents: "AgentManager | None" = None
    desktop: "DesktopManager | None" = None
    memory: "MemoryStore | None" = None
    skills: "SkillLibrary | None" = None
    usage: "UsageTracker | None" = None
    policy: "PolicyEngine | None" = None
    suggestions: "SuggestionBox | None" = None
    tools: "ToolRegistry | None" = None
    brain: "Brain | None" = None
    evolver: "Evolver | None" = None
    updater: "Updater | None" = None
    contrib: "Contributor | None" = None
    scheduler: "Scheduler | None" = None
    improver: "Improver | None" = None

    started_at: float = field(default_factory=time.time)
    background: set[asyncio.Task[Any]] = field(default_factory=set)

    def spawn(self, coro: Any, name: str | None = None) -> asyncio.Task[Any]:
        """Run a background task whose exceptions are logged instead of lost."""
        task = asyncio.create_task(coro, name=name)
        self.background.add(task)

        def _done(t: asyncio.Task[Any]) -> None:
            self.background.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("background task %s failed", t.get_name(), exc_info=t.exception())

        task.add_done_callback(_done)
        return task

    def request_restart(self, reason: str, delay_s: float = 1.0) -> None:
        """Ask the supervisor to restart the core process (it reloads code from the source dir).

        Writes ``<run_dir>/restart_request.json`` and then sends SIGTERM to this
        process; the server exits with ``RESTART_EXIT_CODE``. When not running
        under the supervisor the process simply exits and must be restarted by
        whatever launched it.
        """
        run_dir = self.settings.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "restart_request.json").write_text(
            json.dumps({"reason": reason, "ts": time.time(), "pid": os.getpid()})
        )
        self.bus.publish("system.restart", reason=reason)
        log.warning("restart requested: %s", reason)
        os.environ["MINION_EXIT_CODE"] = str(RESTART_EXIT_CODE)

        loop = asyncio.get_event_loop()
        loop.call_later(delay_s, os.kill, os.getpid(), signal.SIGTERM)
