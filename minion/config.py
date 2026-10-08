"""Runtime configuration.

All settings come from environment variables (see ``.env.example``). Most use the
``MINION_`` prefix; a few well-known names (``ANTHROPIC_API_KEY``,
``GITHUB_TOKEN``, ``TELEGRAM_BOT_TOKEN``) are read without the prefix.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _default_data_dir() -> Path:
    # Inside the official image /data is a named volume; elsewhere use ./data.
    return Path("/data") if Path("/.dockerenv").exists() else Path.cwd() / "data"


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MINION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Claude / Anthropic -------------------------------------------------
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "MINION_ANTHROPIC_API_KEY")
    )
    anthropic_base_url: str | None = Field(
        default=None, validation_alias=AliasChoices("MINION_ANTHROPIC_BASE_URL")
    )
    model: str = "claude-opus-5-5"
    fast_model: str = "claude-haiku-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    max_tokens: int = 64000
    max_turn_iterations: int = 80
    max_parallel_agents: int = 16  # concurrent brain runs / sub-agents / harness delegations
    max_subagent_depth: int = 3
    tool_result_max_chars: int = 60000
    refusal_fallback: bool = True
    thinking_display: Literal["updates", "summarized", "omitted"] = "updates"
    compaction: bool = True
    web_tools: bool = True  # Anthropic server-side web_search / web_fetch
    tool_search_threshold: int = 60  # above this many tools, MCP tools are deferred behind tool search

    # --- Persona / approvals ------------------------------------------------
    persona_name: str = "Minion"
    persona_style: str = ""  # extra personality instructions (also editable from the UI)
    language: str = ""  # preferred reply language; empty = mirror the user
    approvals: Literal["smart", "strict", "off"] = "smart"
    approval_timeout_s: int = 600

    # --- Budget / autonomy --------------------------------------------------
    monthly_budget_usd: float = 0.0  # 0 = unknown / unlimited
    autonomy: Literal["off", "low", "medium", "high"] = "medium"
    improve_interval_hours: float = 24.0  # 0 disables the self-improvement job
    scout_interval_hours: float = 72.0  # 0 disables the frontier-scout job

    # --- Server -------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8700
    api_token: str | None = None  # admin token; generated on first boot if unset
    gateway_token: str | None = None  # token agents use for /mcp; generated if unset
    public_url: str | None = None
    log_level: str = "INFO"
    cors_origins: CsvList = Field(default_factory=list)

    # --- Paths --------------------------------------------------------------
    data_dir: Path = Field(default_factory=_default_data_dir)
    src_dir: Path | None = None  # running source tree (git); default <data_dir>/src or repo root
    image_src_dir: Path = Path("/app")  # pristine source baked into the image

    # --- Docker / satellites ------------------------------------------------
    docker_network: str = "minion-net"
    self_hostname: str = "minion"  # how satellites reach the core on the docker network
    autostart: CsvList = Field(default_factory=lambda: ["desktop"])  # desktop,openclaw,hermes
    desktop_image: str = "minion-desktop:latest"
    desktop_resolution: str = "1280x800"
    desktop_vnc_password: str | None = None
    chat_ui_port: int = 3000  # host port for the Open WebUI front-end (when deployed)
    agent_upgrade_cron: str = "17 4 * * 0"  # weekly: rebuild harness images on their latest versions

    # --- Self-evolution / update / sharing ----------------------------------
    evolve_mode: Literal["auto", "approve", "off"] = "auto"
    check_timeout_s: int = 900
    health_timeout_s: int = 120
    update_mode: Literal["auto", "notify", "off"] = "auto"
    update_interval_minutes: int = 30
    repo_url: str | None = None  # upstream git repo (https://github.com/<owner>/<repo>.git)
    repo_branch: str = "main"
    github_token: str | None = Field(
        default=None, validation_alias=AliasChoices("GITHUB_TOKEN", "MINION_GITHUB_TOKEN")
    )
    github_webhook_secret: str | None = None
    contribute_mode: Literal["pr", "push", "off"] = "pr"
    install_id: str | None = None  # stable id of this installation; generated if unset
    host_dir: str | None = None  # absolute host path of the install dir (for the update helper)
    host_uid: int | None = None
    host_gid: int | None = None
    docker_gid: int | None = None
    compose_project: str = "minion"

    # --- Channels -----------------------------------------------------------
    telegram_bot_token: str | None = Field(
        default=None, validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "MINION_TELEGRAM_BOT_TOKEN")
    )
    telegram_allowed_users: CsvList = Field(default_factory=list)

    @field_validator("autostart", "telegram_allowed_users", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    # --- Derived paths ------------------------------------------------------
    @property
    def source_dir(self) -> Path:
        """The source tree the running process was loaded from (a git repo)."""
        if self.src_dir:
            return self.src_dir
        candidate = self.data_dir / "src"
        if (candidate / "minion").is_dir():
            return candidate
        return Path(__file__).resolve().parent.parent

    @property
    def catalog_dir(self) -> Path:
        """Shared catalog (tools, servers, agents, skills) - lives in the repo and is shared upstream."""
        return self.source_dir / "catalog"

    @property
    def local_dir(self) -> Path:
        """Private, never-shared items (tools/skills that embed personal details)."""
        return self.data_dir / "local"

    @property
    def run_dir(self) -> Path:
        """Coordination files shared with the supervisor (restart requests, last-good commit...)."""
        return self.data_dir / "run"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "minion.db"

    @property
    def core_url(self) -> str:
        """URL satellites (agents, desktop) use to reach the core over the docker network."""
        return f"http://{self.self_hostname}:{self.port}"

    @property
    def gateway_url(self) -> str:
        return f"{self.core_url}/mcp"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.run_dir, self.local_dir / "tools", self.local_dir / "skills",
                  self.local_dir / "agents", self.data_dir / "workshop", self.data_dir / "logs"):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("MINION_IN_DOCKER") == "1"
