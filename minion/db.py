"""SQLite persistence (single file, WAL mode) shared by all services.

Every table used anywhere in Minion is declared in ``SCHEMA`` so there is one
place to look. Services talk to the database through the small generic helpers
below (``execute`` / ``fetchone`` / ``fetchall`` / ``kv_*``) and JSON-encode
structured columns themselves (``dumps`` / ``loads``).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

-- Secrets (API keys, tokens). Values are never shown to the model.
CREATE TABLE IF NOT EXISTS secrets (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL
);

-- MCP servers registered at runtime (catalog/builtin servers are loaded from files).
CREATE TABLE IF NOT EXISTS servers (
    name TEXT PRIMARY KEY,
    spec TEXT NOT NULL,              -- ServerSpec JSON
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Agent instances (containers created from agent templates).
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    spec TEXT NOT NULL,              -- AgentInstance JSON
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Conversations with the brain (web, cli, telegram, openai-compatible, automations).
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'web',
    meta TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Append-only transcript in Anthropic Messages format (content is a JSON list of blocks
-- or a string). NEVER edit earlier rows: thinking blocks are bound to the exact history.
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,              -- user | assistant | system
    content TEXT NOT NULL,           -- JSON
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

-- User feedback on brain answers (feeds self-improvement).
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    rating INTEGER NOT NULL,         -- +1 / -1
    comment TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

-- Long-term memory: facts, lessons, preferences, notes.
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- fact | lesson | preference | note
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags, content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.id, old.content, old.tags);
END;

-- Every tool call the brain makes (success rate / latency feed self-improvement).
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool TEXT NOT NULL,
    ok INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool, created_at);

-- Token usage per API request (budget tracking).
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    purpose TEXT NOT NULL DEFAULT 'chat',   -- chat | automation | improve | scout | ...
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_time ON usage(created_at);

-- Scheduled automations (cron) - user-defined and built-in jobs.
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cron TEXT NOT NULL,              -- 5-field cron, server local time (UTC in docker)
    prompt TEXT NOT NULL,            -- what the brain should do
    kind TEXT NOT NULL DEFAULT 'prompt',  -- prompt | builtin
    enabled INTEGER NOT NULL DEFAULT 1,
    session_id TEXT,                 -- reuse one session per schedule (keeps context)
    last_run_at REAL,
    last_status TEXT NOT NULL DEFAULT '',
    next_run_at REAL,
    created_at REAL NOT NULL
);

-- Self-improvement backlog (goals the user or the brain wants to achieve).
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',   -- open | in_progress | done | dropped
    source TEXT NOT NULL DEFAULT 'user',
    result TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Code-change proposals (self-evolution in approve mode, or updates needing a decision).
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- evolve | update
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    diff TEXT NOT NULL DEFAULT '',
    checks TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected | applied | failed
    created_at REAL NOT NULL,
    decided_at REAL
);

-- History of everything that changed the system (evolve, update, rollback, contribute, install).
CREATE TABLE IF NOT EXISTS evolve_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- evolve | update | rollback | contribute | catalog | restart
    status TEXT NOT NULL,            -- ok | failed | pending | info
    summary TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

-- Brain runs. A run continues in the background even when the client disconnects;
-- clients re-attach to its event stream (events are kept in memory + summarised here).
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'web',
    purpose TEXT NOT NULL DEFAULT 'chat',
    status TEXT NOT NULL DEFAULT 'running',  -- running | waiting_approval | done | error | cancelled
    prompt TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);

-- Approval gates for risky tool calls (sending, deleting, paying, pushing...).
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    session_id TEXT,
    tool TEXT NOT NULL,
    input TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | denied | expired
    decided_by TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    decided_at REAL
);

-- Per-tool permission rules chosen by the user ("always allow X", "always ask for Y").
CREATE TABLE IF NOT EXISTS tool_policies (
    pattern TEXT PRIMARY KEY,        -- fnmatch pattern over tool names, e.g. "gmail__send_*"
    decision TEXT NOT NULL,          -- allow | ask | deny
    created_at REAL NOT NULL
);

-- Proactive capability suggestions (from the scout, the improver or the brain).
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'capability',   -- capability | mcp_server | tool | agent | skill | automation | improvement
    payload TEXT NOT NULL DEFAULT '{}',        -- e.g. registry entry / draft spec
    source TEXT NOT NULL DEFAULT 'brain',
    status TEXT NOT NULL DEFAULT 'new',        -- new | accepted | building | built | dismissed | failed
    result TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Contributions shared to the upstream repo.
CREATE TABLE IF NOT EXISTS contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    paths TEXT NOT NULL DEFAULT '[]',
    commit_sha TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,              -- pr | push | local
    status TEXT NOT NULL,            -- shared | pending | failed | local
    url TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
"""


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class Database:
    """Thin async wrapper around one aiosqlite connection.

    aiosqlite serialises statements on its own worker thread, so a single
    connection is safe to share between tasks. ``transaction()`` gives atomic
    multi-statement writes.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path) if str(path) != ":memory:" else path
        self._conn: aiosqlite.Connection | None = None
        self._tx_lock = asyncio.Lock()

    async def connect(self) -> None:
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(SCHEMA)
        await self._conn.execute(
            "INSERT OR IGNORE INTO kv(key, value, updated_at) VALUES ('schema_version', ?, ?)",
            (str(SCHEMA_VERSION), time.time()),
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run a write statement and commit. Returns lastrowid (or rowcount for updates)."""
        async with self._tx_lock:
            cur = await self.conn.execute(sql, tuple(params))
            await self.conn.commit()
            return cur.lastrowid if cur.lastrowid else cur.rowcount

    async def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        async with self._tx_lock:
            await self.conn.executemany(sql, [tuple(p) for p in seq])
            await self.conn.commit()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        cur = await self.conn.execute(sql, tuple(params))
        row = await cur.fetchone()
        return dict(row) if row is not None else None

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cur = await self.conn.execute(sql, tuple(params))
        return [dict(r) for r in await cur.fetchall()]

    async def fetchval(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(sql, params)
        if not row:
            return default
        return next(iter(row.values()))

    # --- key/value -----------------------------------------------------------
    async def kv_get(self, key: str, default: Any = None) -> Any:
        row = await self.fetchone("SELECT value FROM kv WHERE key = ?", (key,))
        return loads(row["value"], default) if row else default

    async def kv_set(self, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, dumps(value), time.time()),
        )

    async def kv_delete(self, key: str) -> None:
        await self.execute("DELETE FROM kv WHERE key = ?", (key,))

    # --- shared helpers --------------------------------------------------------
    async def log_change(self, kind: str, status: str, summary: str, detail: Any = None) -> int:
        """Append to ``evolve_log`` - the system's change history."""
        return await self.execute(
            "INSERT INTO evolve_log(kind, status, summary, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (kind, status, summary, dumps(detail or {}), time.time()),
        )
