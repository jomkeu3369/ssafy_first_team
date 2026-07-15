import json

from langchain_core.messages import ToolMessage

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.schemas import ChatRequest
from src.agent.service import AgentService


def test_chat_request_defaults() -> None:
    request = ChatRequest(message="부산 여행지를 추천해 주세요")

    assert request.language == "ko"
    assert request.history == []


def test_system_prompt_contains_scope_gate() -> None:
    assert "Apply the scope gate before answering or calling any tool" in SYSTEM_PROMPT
    assert "do not call any tool" in SYSTEM_PROMPT
    assert "부산 지역 정보와 LocalHub 관련 질문만" in SYSTEM_PROMPT


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
