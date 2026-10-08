"""Secret storage and placeholder resolution.

Secrets (API keys, tokens) are stored in SQLite and never shown to the model:
specs reference them as ``${secret:NAME}`` and are resolved only at launch time.
``${env:NAME}`` reads the process environment. ``get`` falls back to the
environment variable of the same name so ``.env`` values work out of the box.
"""

from __future__ import annotations

import os
import re
import secrets as _secrets
import time
from typing import Any

from .db import Database

PLACEHOLDER_RE = re.compile(r"\$\{(secret|env):([A-Za-z_][A-Za-z0-9_]*)\}")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class MissingSecret(KeyError):
    def __init__(self, names: list[str]):
        super().__init__(", ".join(names))
        self.names = names


class SecretStore:
    def __init__(self, db: Database):
        self.db = db

    async def set(self, name: str, value: str, description: str = "") -> None:
        if not NAME_RE.match(name):
            raise ValueError(f"invalid secret name: {name!r}")
        await self.db.execute(
            "INSERT INTO secrets(name, value, description, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value, "
            "description = CASE WHEN excluded.description = '' THEN secrets.description ELSE excluded.description END, "
            "updated_at = excluded.updated_at",
            (name, value, description, time.time()),
        )

    async def get(self, name: str) -> str | None:
        row = await self.db.fetchone("SELECT value FROM secrets WHERE name = ?", (name,))
        if row:
            return row["value"]
        return os.environ.get(name) or None

    async def has(self, name: str) -> bool:
        return (await self.get(name)) is not None

    async def delete(self, name: str) -> None:
        await self.db.execute("DELETE FROM secrets WHERE name = ?", (name,))

    async def list(self) -> list[dict[str, Any]]:
        """Names and descriptions only - never values."""
        rows = await self.db.fetchall("SELECT name, description, updated_at FROM secrets ORDER BY name")
        return rows

    async def ensure_generated(self, name: str, nbytes: int = 24) -> str:
        """Return the secret, generating a random token on first use."""
        value = await self.get(name)
        if not value:
            value = _secrets.token_urlsafe(nbytes)
            await self.set(name, value, "auto-generated")
        return value

    # --- placeholders -------------------------------------------------------
    @staticmethod
    def referenced(value: Any) -> list[str]:
        """Secret names referenced by ``${secret:NAME}`` anywhere inside value (str/list/dict)."""
        found: list[str] = []

        def walk(v: Any) -> None:
            if isinstance(v, str):
                found.extend(m.group(2) for m in PLACEHOLDER_RE.finditer(v) if m.group(1) == "secret")
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    walk(x)

        walk(value)
        return sorted(set(found))

    async def missing(self, value: Any) -> list[str]:
        return [n for n in self.referenced(value) if not await self.has(n)]

    async def resolve(self, value: Any, strict: bool = True) -> Any:
        """Replace placeholders recursively. Raises MissingSecret when strict and a value is absent."""
        missing: list[str] = []

        async def sub(s: str) -> str:
            out, pos = [], 0
            for m in PLACEHOLDER_RE.finditer(s):
                out.append(s[pos : m.start()])
                kind, name = m.group(1), m.group(2)
                val = await self.get(name) if kind == "secret" else os.environ.get(name)
                if val is None:
                    missing.append(name)
                    val = ""
                out.append(val)
                pos = m.end()
            out.append(s[pos:])
            return "".join(out)

        async def walk(v: Any) -> Any:
            if isinstance(v, str):
                return await sub(v) if "${" in v else v
            if isinstance(v, dict):
                return {k: await walk(x) for k, x in v.items()}
            if isinstance(v, list):
                return [await walk(x) for x in v]
            return v

        result = await walk(value)
        if strict and missing:
            raise MissingSecret(sorted(set(missing)))
        return result

    async def redact(self, text: str) -> str:
        """Remove any stored secret value from text (e.g. logs shown to the model)."""
        rows = await self.db.fetchall("SELECT value FROM secrets")
        for r in rows:
            v = r["value"]
            if v and len(v) >= 6:
                text = text.replace(v, "***")
        return text
