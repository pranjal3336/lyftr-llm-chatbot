"""Session/message persistence. All writes happen atomically after a successful LLM reply."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.db.database import Database
from app.exceptions import SessionNotFoundError


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def load_context(self, session_id: str) -> tuple[str | None, list[dict[str, str]]]:
        """Stored system prompt (or None) and ordered history as LLM messages."""
        async with self.db.connect() as conn:
            cur = await conn.execute(
                "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = await cur.fetchone()
            system_prompt = row["system_prompt"] if row else None
            cur = await conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            history = [{"role": r["role"], "content": r["content"]} for r in await cur.fetchall()]
        return system_prompt, history

    async def save_turn(
        self,
        session_id: str,
        system_prompt: str | None,
        user_content: str,
        assistant_content: str,
        metadata: dict[str, Any],
    ) -> None:
        now = _now()
        async with self.db.connect() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                await conn.execute(
                    "INSERT INTO sessions (session_id, system_prompt, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                    "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt), "
                    "updated_at = excluded.updated_at",
                    (session_id, system_prompt, now, now),
                )
                await conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                    "VALUES (?, 'user', ?, NULL, ?)",
                    (session_id, user_content, now),
                )
                await conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                    "VALUES (?, 'assistant', ?, ?, ?)",
                    (session_id, assistant_content, json.dumps(metadata), now),
                )
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            cur = await conn.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
        if not rows:
            raise SessionNotFoundError(session_id)
        out: list[dict[str, Any]] = []
        for r in rows:
            item: dict[str, Any] = {"role": r["role"], "content": r["content"]}
            if r["role"] == "assistant" and r["metadata"]:
                item["metadata"] = json.loads(r["metadata"])
            out.append(item)
        return out
