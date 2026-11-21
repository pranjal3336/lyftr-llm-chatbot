"""Test harness: real FastAPI app + real LiteLLM Router/Cache, with a fake upstream *provider*.

The fake provider is registered through LiteLLM's custom_provider_map, so routing, failover and
caching all run through genuine LiteLLM code; only the network call is replaced.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import httpx
import litellm
import pytest
import pytest_asyncio
from litellm import CustomLLM

from app.config import Settings
from app.main import create_app

MODEL = "fake/test-model"


class FakeProvider(CustomLLM):
    """Behaviour per api_key: 'ok' (default), 429, 'quota', 500, 503, 'empty'."""

    def __init__(self) -> None:
        super().__init__()
        self.behaviors: dict[str, object] = {}
        self.calls: list[tuple[str, list[dict]]] = []

    def reset(self) -> None:
        self.behaviors.clear()
        self.calls.clear()

    def calls_for(self, api_key: str) -> int:
        return sum(1 for k, _ in self.calls if k == api_key)

    async def acompletion(
        self, model, messages, api_base, custom_prompt_dict, model_response, print_verbose,
        encoding, api_key, logging_obj, optional_params, acompletion=None, litellm_params=None,
        logger_fn=None, headers=None, timeout=None, client=None,
    ):
        self.calls.append((api_key, [dict(m) for m in messages]))
        behavior = self.behaviors.get(api_key, "ok")
        if behavior == 429:
            raise litellm.RateLimitError("rate limited", llm_provider="fake", model=model)
        if behavior == "quota":
            raise litellm.RateLimitError(
                "RESOURCE_EXHAUSTED: quota exceeded", llm_provider="fake", model=model
            )
        if behavior == 500:
            raise litellm.InternalServerError("upstream error", llm_provider="fake", model=model)
        if behavior == 503:
            raise litellm.ServiceUnavailableError("unavailable", llm_provider="fake", model=model)

        convo = " | ".join(m["content"] for m in messages if m["role"] != "system")
        text = "" if behavior == "empty" else f"reply to: {convo}"
        model_response.choices[0].message.content = text
        prompt_tokens = sum(len(m["content"]) for m in messages) // 4 + 1
        completion_tokens = len(text) // 4 + 1
        model_response.usage = litellm.Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        model_response.model = "test-model"  # provider-style name without the "fake/" prefix
        return model_response


_provider = FakeProvider()
litellm.custom_provider_map = [{"provider": "fake", "custom_handler": _provider}]


@pytest.fixture
def provider() -> FakeProvider:
    _provider.reset()
    return _provider


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "llm_api_keys": "k1,k2",
        "llm_model": MODEL,
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "allowed_origins": "http://localhost:3000",
        "enable_failure_simulation": True,
        "cache_enabled": True,
        "cache_type": "local",
        "llm_timeout_seconds": 5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@asynccontextmanager
async def running_app(settings: Settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.app = app  # type: ignore[attr-defined]
            yield client


@pytest.fixture
def tmp_settings(tmp_path):
    return lambda **kw: make_settings(tmp_path, **kw)


@pytest_asyncio.fixture
async def client(tmp_path, provider):
    async with running_app(make_settings(tmp_path)) as c:
        yield c


def chat_body(session_id: str, message: str, **extra) -> dict:
    return {"session_id": session_id, "message": message, **extra}
