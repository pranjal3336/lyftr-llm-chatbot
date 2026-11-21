"""LiteLLM Router (key pool + ordered failover) and built-in response cache."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import litellm
from litellm import Router
from litellm.caching.caching import Cache

from app.config import Settings
from app.exceptions import AllProvidersUnavailableError
from app.gateway.failure_sim import simulated_exception

logger = logging.getLogger("app.gateway")

NO_CACHE = {"no-cache": True, "no-store": True}


@dataclass
class GatewayResult:
    reply: str
    input_tokens: int
    output_tokens: int
    model: str
    key_id: str | None
    fallback_attempts: int
    cache_hit: bool


class LLMGateway:
    """All LLM traffic goes through litellm.Router; caching is litellm's own Cache."""

    def __init__(self, settings: Settings) -> None:
        keys = settings.api_keys
        models = settings.per_key_models
        self.key_ids = [f"key_{i}" for i in range(1, len(keys) + 1)]
        self.model_map = dict(zip(self.key_ids, models, strict=True))
        self.cache_enabled = settings.cache_enabled
        self._configure_cache(settings)

        model_list = [
            {
                "model_name": key_id,  # logical alias; the secret never leaves the Router
                "litellm_params": {
                    "model": self.model_map[key_id],
                    "api_key": api_key,
                    "max_retries": 0,
                    "timeout": settings.llm_timeout_seconds,
                },
                "model_info": {"id": key_id},
            }
            for key_id, api_key in zip(self.key_ids, keys, strict=True)
        ]
        fallbacks = [
            {self.key_ids[i]: self.key_ids[i + 1 :]} for i in range(len(self.key_ids) - 1)
        ]
        common: dict[str, Any] = {"num_retries": 0, "cooldown_time": 0, "disable_cooldowns": True}
        # Normal path: Router performs the automatic 429 / quota / 5xx failover chain.
        self.router = Router(model_list=model_list, fallbacks=fallbacks, **common)
        # Request-scoped path (simulation / empty replies): one key per call, no Router fallbacks.
        self.direct_router = Router(model_list=model_list, **common)

    @staticmethod
    def _configure_cache(settings: Settings) -> None:
        if not settings.cache_enabled:
            litellm.cache = None
            return
        kwargs: dict[str, Any] = {
            "ttl": settings.cache_ttl_seconds, "supported_call_types": ["acompletion", "completion"]
        }
        if settings.cache_type == "disk":
            litellm.cache = Cache(type="disk", disk_cache_dir=settings.cache_disk_dir, **kwargs)
        else:
            litellm.cache = Cache(type="local", **kwargs)

    # ------------------------------------------------------------------ public
    async def complete(
        self, messages: list[dict[str, str]], sim_failures: dict[str, int] | None = None
    ) -> GatewayResult:
        if not self.key_ids:
            raise AllProvidersUnavailableError("no keys configured")
        if sim_failures:
            # Simulation bypasses the cache so failover always executes.
            return await self._walk(messages, sim_failures, start=0, failed=0)

        try:
            resp = await self.router.acompletion(
                model=self.key_ids[0], messages=messages, caching=self.cache_enabled
            )
        except Exception as exc:  # every key failed
            logger.error("all_providers_failed error=%s", type(exc).__name__)
            raise AllProvidersUnavailableError("all providers unavailable") from exc

        result = self._to_result(resp, messages)
        if result is None:  # empty reply counts as a provider failure -> try the remaining keys
            hidden = getattr(resp, "_hidden_params", None) or {}
            winner = hidden.get("model_id")
            start = self.key_ids.index(winner) + 1 if winner in self.key_ids else 0
            return await self._walk(messages, {}, start=start, failed=start)
        return result

    # ----------------------------------------------------------------- helpers
    async def _walk(
        self, messages: list[dict[str, str]], sim: dict[str, int], start: int, failed: int
    ) -> GatewayResult:
        for idx in range(start, len(self.key_ids)):
            key_id = self.key_ids[idx]
            try:
                if key_id in sim:
                    raise simulated_exception(sim[key_id], self.model_map[key_id])
                resp = await self.direct_router.acompletion(
                    model=key_id, messages=messages, cache=NO_CACHE
                )
                result = self._to_result(resp, messages, forced_key=key_id, failed=failed)
                if result is None:
                    raise RuntimeError("empty reply")
                return result
            except Exception as exc:
                failed += 1
                logger.warning("key_failed key_id=%s error=%s", key_id, type(exc).__name__)
        raise AllProvidersUnavailableError("all providers unavailable")

    def _to_result(
        self,
        resp: Any,
        messages: list[dict[str, str]],
        forced_key: str | None = None,
        failed: int = 0,
    ) -> GatewayResult | None:
        hidden = getattr(resp, "_hidden_params", None) or {}
        cache_hit = bool(hidden.get("cache_hit", False)) and forced_key is None
        reply = ((resp.choices[0].message.content) or "").strip()
        if not reply:
            return None

        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", None)
        out_tok = getattr(usage, "completion_tokens", None)
        if not isinstance(in_tok, int):
            in_tok = litellm.token_counter(model=self.model_map[self.key_ids[0]], messages=messages)
        if not isinstance(out_tok, int):
            out_tok = litellm.token_counter(model=self.model_map[self.key_ids[0]], text=reply)

        if cache_hit:
            key_id: str | None = None
            attempts = 0
            model_key = hidden.get("model_id")
            model = self.model_map.get(model_key, self.model_map[self.key_ids[0]])
        else:
            key_id = forced_key or hidden.get("model_id")
            if key_id not in self.key_ids:
                key_id = self.key_ids[0]
            attempts = failed if forced_key else self.key_ids.index(key_id)
            model = self.model_map[key_id]
        return GatewayResult(reply, int(in_tok), int(out_tok), model, key_id, attempts, cache_hit)
