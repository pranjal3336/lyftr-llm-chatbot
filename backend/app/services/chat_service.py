"""Orchestrates one chat turn: validate -> load context -> LLM -> persist (only on success)."""
from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.db.repository import Repository
from app.gateway.failure_sim import parse_failure_header
from app.gateway.litellm_gateway import LLMGateway
from app.schemas import ChatRequest, ChatResponse, Metadata

logger = logging.getLogger("app.chat")


class ChatService:
    def __init__(self, repo: Repository, gateway: LLMGateway, settings: Settings) -> None:
        self.repo = repo
        self.gateway = gateway
        self.settings = settings
        self._locks: dict[str, list] = {}  # session_id -> [lock, users]

    async def _acquire(self, session_id: str) -> asyncio.Lock:
        entry = self._locks.setdefault(session_id, [asyncio.Lock(), 0])
        entry[1] += 1
        await entry[0].acquire()
        return entry[0]

    def _release(self, session_id: str) -> None:
        entry = self._locks[session_id]
        entry[0].release()
        entry[1] -= 1
        if entry[1] == 0:
            del self._locks[session_id]

    async def chat(self, req: ChatRequest, simulate_header: str | None) -> ChatResponse:
        t0 = time.perf_counter()
        sim: dict[str, int] = {}
        if self.settings.enable_failure_simulation:
            sim = parse_failure_header(simulate_header, self.gateway.key_ids)

        await self._acquire(req.session_id)
        try:
            stored_prompt, history = await self.repo.load_context(req.session_id)
            effective = req.system_prompt or stored_prompt or self.settings.default_system_prompt
            messages = [
                {"role": "system", "content": effective},
                *history,
                {"role": "user", "content": req.message},
            ]

            result = await self.gateway.complete(messages, sim)  # raises -> nothing persisted

            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            metadata = Metadata(
                resolution_source="LLM_CACHE" if result.cache_hit else "LIVE_INFERENCE",
                model=result.model,
                latency_ms=latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                key_id=result.key_id,
                fallback_attempts=result.fallback_attempts,
            )
            await self.repo.save_turn(
                req.session_id, req.system_prompt, req.message, result.reply, metadata.model_dump()
            )
        finally:
            self._release(req.session_id)

        logger.info(
            "chat_ok source=%s key_id=%s fallbacks=%d latency_ms=%d",
            metadata.resolution_source, metadata.key_id, metadata.fallback_attempts, latency_ms,
        )
        return ChatResponse(session_id=req.session_id, reply=result.reply, metadata=metadata)
