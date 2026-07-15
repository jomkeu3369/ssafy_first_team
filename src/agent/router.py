from fastapi import APIRouter, HTTPException, Request, status

from src.agent.schemas import ChatRequest, ChatResponse
from src.agent.service import AgentService


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    service: AgentService | None = getattr(request.app.state, "agent_service", None)
    if service is None or not service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent is not configured. Set OPENAI_API_KEY and OPENAI_MODEL.",
        )
    try:
        return await service.chat(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI agent request failed.",
        ) from exc
