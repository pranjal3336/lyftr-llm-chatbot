"""SQLite connection handling and schema bootstrap (aiosqlite)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages (session_id, id ASC);
"""


def parse_database_url(url: str) -> str:
    """sqlite:////data/app.db -> /data/app.db ; sqlite:///./data/app.db -> ./data/app.db."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("DATABASE_URL must start with sqlite:///")
    path = url[len(prefix):]
    if not path:
        raise ValueError("DATABASE_URL has an empty path")
    return path


class Database:
    def __init__(self, database_url: str) -> None:
        self.path = parse_database_url(database_url)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self.path, timeout=5)
        try:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            await conn.close()

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.executescript(SCHEMA)
            await conn.commit()

    async def check(self) -> None:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT 1")
            await cur.fetchone()
