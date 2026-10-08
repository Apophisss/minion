"""Shared data models (pydantic v2).

These are the contracts between services. Keep them backwards compatible:
specs are persisted as JSON in SQLite and in catalog YAML files.
"""

from __future__ import annotations

import re
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def slugify(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")
    return (s or "item")[:max_len]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# --------------------------------------------------------------------------- MCP


class ContainerSpec(_Model):
    """A container Minion runs via the Docker API."""

    name: str  # container name; Minion prefixes "minion-" when missing
    image: str
    build_context: str | None = None  # dir relative to the source tree (or absolute) to build `image` from
    dockerfile: str = "Dockerfile"
    build_args: dict[str, str] = Field(default_factory=dict)
    command: list[str] | str | None = None
    entrypoint: list[str] | str | None = None
    env: dict[str, str] = Field(default_factory=dict)  # values may contain ${secret:NAME} placeholders
    ports: dict[str, int | None] = Field(default_factory=dict)  # "8000/tcp" -> host port (None = not published)
    volumes: dict[str, dict[str, str]] = Field(default_factory=dict)  # volume-or-hostpath -> {bind, mode}
    network: str | None = None  # default: settings.docker_network
    network_aliases: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    restart: Literal["no", "always", "unless-stopped", "on-failure"] = "unless-stopped"
    kind: Literal["agent", "mcp", "desktop", "custom", "helper"] = "custom"
    mem_limit: str | None = None  # e.g. "2g"
    cpus: float | None = None
    shm_size: str | None = None
    user: str | None = None
    working_dir: str | None = None
    privileged: bool = False
    stdin_open: bool = False
    tty: bool = False
    healthcheck_url: str | None = None  # URL (reachable from the core) that returns 2xx when ready


class ServerSpec(_Model):
    """How to reach / launch one MCP server."""

    name: str
    transport: Literal["stdio", "http", "sse"] = "stdio"
    # stdio
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)  # may contain ${secret:NAME}
    cwd: str | None = None
    # http / sse
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)  # may contain ${secret:NAME}
    # optional container to start before connecting (long-running HTTP MCP servers)
    container: ContainerSpec | None = None
    # metadata
    description: str = ""
    enabled: bool = True
    source: Literal["manual", "registry", "catalog", "workshop", "builtin", "agent"] = "manual"
    tags: list[str] = Field(default_factory=list)
    required_secrets: list[str] = Field(default_factory=list)
    timeout_s: float = 120.0
    tool_allowlist: list[str] | None = None  # None = all tools
    expose_in_gateway: bool = True  # make tools available to agents through /mcp
    registry_name: str | None = None  # e.g. "io.github.owner/server"

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("server name must match [a-z0-9][a-z0-9_-]{0,47}")
        return v


ServerState = Literal["stopped", "starting", "running", "error", "disabled", "needs_secret"]


class ServerStatus(_Model):
    name: str
    state: ServerState = "stopped"
    error: str | None = None
    tool_count: int = 0
    started_at: float | None = None
    missing_secrets: list[str] = Field(default_factory=list)


class ToolInfo(_Model):
    server: str
    name: str  # original MCP tool name
    qualified_name: str  # "<server>__<tool>" sanitised to [a-zA-Z0-9_-]{1,64}
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    annotations: dict[str, Any] | None = None


class ToolCallResult(_Model):
    """Normalised MCP tool result.

    ``content`` items are dicts: ``{"type": "text", "text": ...}`` or
    ``{"type": "image", "data": <base64>, "mimeType": "image/png"}`` or
    ``{"type": "resource", "uri": ..., "text": ...}``.
    """

    content: list[dict[str, Any]] = Field(default_factory=list)
    structured: dict[str, Any] | None = None
    is_error: bool = False

    def text(self) -> str:
        parts = [c.get("text", "") for c in self.content if c.get("type") in ("text", "resource")]
        if not parts and self.structured is not None:
            import json

            return json.dumps(self.structured, ensure_ascii=False)
        return "\n".join(p for p in parts if p)


# ------------------------------------------------------------------------ Agents


class AgentConfigFile(_Model):
    path: str  # absolute path inside the container
    template: str  # template file, relative to the agent template dir (rendered with {{var}})
    mode: str = "0644"


class AgentInterface(_Model):
    """How Minion talks to a running agent."""

    type: Literal["openai_http", "exec_cli", "none"] = "openai_http"
    port: int | None = None
    path: str = "/v1/chat/completions"
    model: str = "default"
    auth_header: str | None = None  # e.g. "Bearer {{agent_token}}"
    extra_headers: dict[str, str] = Field(default_factory=dict)  # e.g. session headers "{{session}}"
    exec_cmd: list[str] = Field(default_factory=list)  # e.g. ["hermes", "chat", "-q", "{{message}}"]
    exec_cmd_continue: list[str] = Field(default_factory=list)  # variant used when continuing a session
    exec_user: str | None = None
    exec_workdir: str | None = None
    strip_ansi: bool = True
    timeout_s: float = 900.0


class AgentTemplate(_Model):
    """An agent harness / satellite (catalog/agents/<name>/template.yaml).

    Harnesses are existing open-source agents (OpenClaw, Hermes, opencode, Goose,
    Aider, ...) packaged so that rebuilding the image installs the latest upstream
    version (``upgrade``), configured to use Claude and Minion's MCP gateway.
    """

    name: str
    title: str = ""
    description: str = ""
    homepage: str = ""
    license: str = ""
    category: Literal["agent", "ui", "service"] = "agent"  # ui = chat front-end (e.g. Open WebUI)
    best_for: list[str] = Field(default_factory=list)  # routing hints for the brain
    optional: bool = False  # not deployed by "all"
    upgrade: Literal["rebuild", "pull", "none"] = "rebuild"  # how to move to the latest upstream version
    image: str  # image tag to run (built from `build_context` when set)
    build_context: str | None = None  # relative to the template dir, e.g. "." (Dockerfile next to template.yaml)
    dockerfile: str = "Dockerfile"
    build_args: dict[str, str] = Field(default_factory=dict)
    command: list[str] | str | None = None
    env: dict[str, str] = Field(default_factory=dict)  # {{var}} and ${secret:NAME} placeholders
    config_files: list[AgentConfigFile] = Field(default_factory=list)
    data_path: str | None = None  # container path persisted in a named volume
    ports: dict[str, int | None] = Field(default_factory=dict)
    interface: AgentInterface = Field(default_factory=AgentInterface)
    required_secrets: list[str] = Field(default_factory=list)
    mem_limit: str | None = None
    shm_size: str | None = None
    healthcheck_path: str | None = None  # HTTP path on interface.port
    dir: str | None = None  # filled at load time: absolute template dir


AgentState = Literal["stopped", "building", "starting", "running", "error"]


class AgentInstance(_Model):
    name: str
    template: str
    container: str
    state: AgentState = "stopped"
    error: str | None = None
    created_at: float = Field(default_factory=time.time)
    overrides: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None  # per-agent token for its own API (if any)


# ------------------------------------------------------------------------- Misc


class Notification(_Model):
    level: Literal["info", "success", "warning", "error"] = "info"
    title: str
    message: str = ""


class CheckResult(_Model):
    ok: bool
    output: str = ""
    duration_s: float = 0.0
