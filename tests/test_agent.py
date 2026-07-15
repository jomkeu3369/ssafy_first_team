import json
from pathlib import Path

from langchain_core.messages import ToolMessage

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


def test_mcp_connections_receive_only_required_environment() -> None:
    settings = Settings(database_url="sqlite+aiosqlite:///./data/test.db", openai_api_key="openai-test", openai_embedding_model="embedding-test", tavily_api_key="tavily-test", faiss_index_dir="data/test-faiss")
    connections = AgentService(settings)._mcp_connections()

    assert connections["local"]["env"] == {"DATABASE_URL": "sqlite+aiosqlite:///./data/test.db", "OPENAI_EMBEDDING_MODEL": "embedding-test", "FAISS_INDEX_DIR": str(Path("data/test-faiss")), "OPENAI_API_KEY": "openai-test"}
    assert connections["web"]["env"] == {"TAVILY_API_KEY": "tavily-test"}
    assert "TAVILY_API_KEY" not in connections["local"]["env"]
    assert "OPENAI_API_KEY" not in connections["web"]["env"]


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
