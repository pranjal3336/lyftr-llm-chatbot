"""The three required endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.exceptions import ServiceUnhealthyError
from app.schemas import ChatRequest, ChatResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    state = request.app.state
    try:
        await state.db.check()
    except Exception as exc:
        raise ServiceUnhealthyError("service unhealthy: database unavailable") from exc
    keys = len(state.gateway.key_ids)
    if keys < 2:
        raise ServiceUnhealthyError("service unhealthy: at least 2 API keys are required")
    return HealthResponse(status="ok", keys_configured=keys, cache_enabled=state.settings.cache_enabled)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    x_simulate_failure: str | None = Header(default=None),
) -> ChatResponse:
    return await request.app.state.chat_service.chat(body, x_simulate_failure)


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, request: Request) -> JSONResponse:
    messages = await request.app.state.repo.get_messages(session_id)
    return JSONResponse({"session_id": session_id, "messages": messages})
