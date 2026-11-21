"""FastAPI application factory."""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # no network fetch at import

import litellm
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import Settings
from app.db.database import Database
from app.db.repository import Repository
from app.exceptions import (
    AllProvidersUnavailableError,
    ServiceUnhealthyError,
    SessionNotFoundError,
)
from app.gateway.litellm_gateway import LLMGateway
from app.services.chat_service import ChatService

logger = logging.getLogger("app")


class RedactingFilter(logging.Filter):
    """Removes configured API key values from every log record."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if self.secrets:
            msg = record.getMessage()
            for s in self.secrets:
                msg = msg.replace(s, "[redacted]")
            record.msg, record.args = msg, None
        return True


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    for handler in root.handlers:
        handler.addFilter(RedactingFilter(settings.api_keys))
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "httpx"):
        logging.getLogger(name).setLevel(logging.ERROR)


def _json(status: int, detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings)
        db = Database(settings.database_url)
        await db.init()
        gateway = LLMGateway(settings)
        if len(gateway.key_ids) < 2:
            logger.warning("fewer than 2 API keys configured; /health will report unhealthy")
        app.state.settings = settings
        app.state.db = db
        app.state.repo = Repository(db)
        app.state.gateway = gateway
        app.state.chat_service = ChatService(app.state.repo, gateway, settings)
        logger.info("startup ok keys=%d cache=%s", len(gateway.key_ids), settings.cache_enabled)
        yield

    app = FastAPI(title="Lyftr LLM Chatbot", lifespan=lifespan)

    origins = settings.origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if "*" in origins else origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Simulate-Failure"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"type": e.get("type"), "loc": list(e.get("loc", [])), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return _json(422, errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _json(exc.status_code, exc.detail)

    @app.exception_handler(SessionNotFoundError)
    async def _not_found(_: Request, __: SessionNotFoundError) -> JSONResponse:
        return _json(404, "session not found")

    @app.exception_handler(AllProvidersUnavailableError)
    async def _unavailable(_: Request, __: AllProvidersUnavailableError) -> JSONResponse:
        return _json(503, "all providers unavailable")

    @app.exception_handler(ServiceUnhealthyError)
    async def _unhealthy(_: Request, exc: ServiceUnhealthyError) -> JSONResponse:
        return _json(503, str(exc))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error error=%s", type(exc).__name__)
        return _json(500, "internal server error")

    app.include_router(router)
    return app


app = create_app()
