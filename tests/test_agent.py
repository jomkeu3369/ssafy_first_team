import json
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from src.agent import service as service_module
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.schemas import ChatRequest
from src.agent.service import AgentService
from src.core.config import Settings


def test_chat_request_defaults() -> None:
    request = ChatRequest(message="부산 여행지를 추천해 주세요")

    assert request.language == "ko"
    assert request.history == []


def test_system_prompt_contains_scope_gate() -> None:
    assert "Apply the scope gate before answering or calling any tool" in SYSTEM_PROMPT
    assert "do not call any tool" in SYSTEM_PROMPT
    assert "부산 지역 정보와 관련 질문만" in SYSTEM_PROMPT
    assert "you must automatically call" in SYSTEM_PROMPT
    assert "Do not ask the user for permission first" in SYSTEM_PROMPT
    assert "until web search has also been attempted" in SYSTEM_PROMPT
    assert "always call search_faiss" in SYSTEM_PROMPT
    assert "Response language contract" in SYSTEM_PROMPT
    assert "A newer turn's marker" in SYSTEM_PROMPT


def test_every_user_message_contains_the_requested_language_marker() -> None:
    korean = AgentService.localized_user_message(ChatRequest(message="부산 여행지를 추천해 주세요", language="ko"))
    english = AgentService.localized_user_message(ChatRequest(message="Recommend a place in Busan", language="en"))

    assert korean.content == "[LOCALHUB_RESPONSE_LANGUAGE=ko]\n부산 여행지를 추천해 주세요"
    assert english.content == "[LOCALHUB_RESPONSE_LANGUAGE=en]\nRecommend a place in Busan"


def test_mcp_connections_receive_only_required_environment() -> None:
    settings = Settings(database_url="sqlite+aiosqlite:///./data/test.db", openai_api_key="openai-test", openai_embedding_model="embedding-test", tavily_api_key="tavily-test", faiss_index_dir="data/test-faiss")
    connections = AgentService(settings)._mcp_connections()

    assert connections["database"]["env"] == {"DATABASE_URL": "sqlite+aiosqlite:///./data/test.db"}
    assert connections["vector"]["env"] == {"DATABASE_URL": "sqlite+aiosqlite:///./data/test.db", "OPENAI_EMBEDDING_MODEL": "embedding-test", "FAISS_INDEX_DIR": str(Path("data/test-faiss")), "OPENAI_API_KEY": "openai-test"}
    assert connections["web"]["env"] == {"TAVILY_API_KEY": "tavily-test"}
    assert "TAVILY_API_KEY" not in connections["vector"]["env"]
    assert "OPENAI_API_KEY" not in connections["web"]["env"]


def test_remote_vector_mcp_uses_http_and_bearer_auth() -> None:
    settings = Settings(vector_mcp_url="https://vector.example.com/mcp", vector_mcp_api_key="vector-secret", vector_mcp_timeout_seconds=3)
    connection = AgentService(settings)._mcp_connections()["vector"]

    assert connection == {"transport": "streamable_http", "url": "https://vector.example.com/mcp", "headers": {"Authorization": "Bearer vector-secret"}, "timeout": 3, "sse_read_timeout": 3}


@pytest.mark.asyncio
async def test_remote_vector_tool_returns_fallback_when_tunnel_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenSession:
        async def __aenter__(self):
            raise OSError("tunnel offline")

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    class BrokenClient:
        def __init__(self, _connections):
            pass

        def session(self, _server_name: str) -> BrokenSession:
            return BrokenSession()

    monkeypatch.setattr(service_module, "MultiServerMCPClient", BrokenClient)
    service = AgentService(Settings(vector_mcp_url="https://vector.example.com/mcp", vector_mcp_api_key="secret"))
    tool = service._remote_vector_tool(service._mcp_connections()["vector"])

    result = await tool.ainvoke({"query": "Busan beach", "limit": 5})

    assert result["items"] == []
    assert "SQL and web search" in result["notice"]


def test_conversation_thread_id_is_stable_and_isolated() -> None:
    first = AgentService.conversation_thread_id("client-a", "session-a")

    assert first == AgentService.conversation_thread_id("client-a", "session-a")
    assert first != AgentService.conversation_thread_id("client-a", "session-b")
    assert first != AgentService.conversation_thread_id("client-b", "session-a")
    assert "client-a" not in first
    assert "session-a" not in first


def test_reference_extraction_from_tool_message() -> None:
    payload = {
        "items": [
            {
                "sourceType": "regional_contents",
                "sourceId": "42",
                "title": "테스트 장소",
                "address": "부산광역시",
            }
        ],
        "citations": [{"title": "공식 페이지", "url": "https://example.com/source"}],
    }
    message = ToolMessage(
        content=json.dumps(payload),
        tool_call_id="tool-1",
        artifact={"structured_content": payload},
    )

    references = AgentService._extract_references([message])

    assert len(references) == 2
    assert references[0].id == "42"
    assert references[1].url == "https://example.com/source"
