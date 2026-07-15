from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from src.agent.schemas import ChatRequest, ChatResponse
from src.agent.service import AgentService
from src.core.logging import get_logger


router = APIRouter()
logger = get_logger()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, client_id: Annotated[UUID, Header(alias="X-Client-Id")], session_id: Annotated[UUID, Header(alias="X-Session-Id")]) -> ChatResponse:
    service: AgentService | None = getattr(request.app.state, "agent_service", None)
    
    if service is None or not service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent is not configured. Set OPENAI_API_KEY and OPENAI_MODEL."
        )
    try:
        return await service.chat(payload, str(client_id), str(session_id))
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("AI agent request failed [%s]", request_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI agent request failed."
        ) from exc
