"""SQLite connection configuration and versioned migrations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import TypeVar

import aiosqlite

ResultT = TypeVar("ResultT")
DatabaseOperation = Callable[[aiosqlite.Connection], Awaitable[ResultT]]


class SqliteDatabase:
    """Own SQLite connection policy; each operation gets a short-lived connection."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive.")
        self.path = path
        self._busy_timeout_ms = busy_timeout_ms

    async def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        migrations = files("interview_app.adapters.sqlite.migrations")
        async with self._connect() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            cursor = await connection.execute("SELECT version FROM schema_migrations")
            applied = {int(row["version"]) for row in await cursor.fetchall()}
            for resource in sorted(
                (entry for entry in migrations.iterdir() if entry.name.endswith(".sql")),
                key=lambda entry: entry.name,
            ):
                version = int(resource.name.split("_", maxsplit=1)[0])
                if version in applied:
                    continue
                # Migrations run during process bootstrap, before room/audio ownership begins.
                script = resource.read_text(encoding="utf-8")
                applied_at = datetime.now(UTC).isoformat()
                try:
                    await connection.executescript("BEGIN IMMEDIATE;\n" + script)
                    await connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, applied_at),
                    )
                    await connection.commit()
                except BaseException:
                    await connection.rollback()
                    raise

    async def read(self, operation: DatabaseOperation[ResultT]) -> ResultT:
        async with self._connect() as connection:
            return await operation(connection)

    async def write(self, operation: DatabaseOperation[ResultT]) -> ResultT:
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                result = await operation(connection)
            except BaseException:
                await connection.rollback()
                raise
            await connection.commit()
            return result

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(
            self.path,
            timeout=self._busy_timeout_ms / 1_000,
            isolation_level=None,
        ) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            await connection.execute("PRAGMA journal_mode = WAL")
            yield connection
