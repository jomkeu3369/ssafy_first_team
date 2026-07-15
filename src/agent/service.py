from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from contextlib import AsyncExitStack
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client
from langsmith.run_helpers import tracing_context

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.schemas import ChatRequest, ChatResponse, Reference
from src.core.config import PROJECT_ROOT, Settings


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._exit_stack: AsyncExitStack | None = None
        self._agent: Any = None
        self._langsmith_client: Client | None = None
        self._checkpointer = InMemorySaver()

    @property
    def is_ready(self) -> bool:
        return self._agent is not None

    async def start(self) -> None:
        if self.is_ready:
            return
        if not self.settings.openai_api_key or not self.settings.openai_model:
            msg = "OPENAI_API_KEY and OPENAI_MODEL must be configured"
            raise RuntimeError(msg)

        connections = self._mcp_connections()
        client = MultiServerMCPClient(connections)
        stack = AsyncExitStack()
        try:
            tools = []
            for server_name in connections:
                session = await stack.enter_async_context(client.session(server_name))
                tools.extend(await load_mcp_tools(session, server_name=server_name))

            model = ChatOpenAI(
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                temperature=0,
            )
            self._agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
                checkpointer=self._checkpointer
            )
            if self.settings.langsmith_tracing and self.settings.langsmith_api_key:
                self._langsmith_client = Client(api_key=self.settings.langsmith_api_key)
            self._exit_stack = stack
        except Exception:
            await stack.aclose()
            raise

    async def close(self) -> None:
        self._agent = None

        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None

        if self._langsmith_client is not None:
            await asyncio.to_thread(self._langsmith_client.close, timeout=5)
            self._langsmith_client = None

    async def chat(self, request: ChatRequest, client_id: str, session_id: str) -> ChatResponse:
        if not self.is_ready:
            raise RuntimeError("Agent is not ready")

        thread_id = self.conversation_thread_id(client_id, session_id)
        config = {"recursion_limit": self.settings.agent_recursion_limit, "configurable": {"thread_id": thread_id}}
        state = await self._agent.aget_state(config)
        messages: list[HumanMessage | AIMessage | SystemMessage] = []
        
        if not state.values.get("messages"):
            messages.append(SystemMessage(content=f"The requested answer language is {request.language}."))
            for item in request.history:
                message_class = HumanMessage if item.role == "user" else AIMessage
                messages.append(message_class(content=item.content))
        
        messages.append(HumanMessage(content=request.message))

        with tracing_context(
            enabled=self._langsmith_client is not None,
            client=self._langsmith_client,
            project_name=self.settings.langsmith_project,
            metadata={"language": request.language, "thread_id": thread_id}
        ):
            result = await self._agent.ainvoke(
                {"messages": messages},
                config=config
            )
        result_messages = result.get("messages", [])
        answer = next(
            (
                self._message_text(message)
                for message in reversed(result_messages)
                if isinstance(message, AIMessage)
            ),
            "",
        )
        references = self._extract_references(result_messages)
        return ChatResponse(
            answer=answer,
            language=request.language,
            references=references,
        )

    @staticmethod
    def conversation_thread_id(client_id: str, session_id: str) -> str:
        return hashlib.sha256(f"{client_id}:{session_id}".encode()).hexdigest()

    def _mcp_connections(self) -> dict[str, dict[str, Any]]:
        local_environment = {"DATABASE_URL": self.settings.database_url, "OPENAI_EMBEDDING_MODEL": self.settings.openai_embedding_model, "FAISS_INDEX_DIR": str(self.settings.faiss_index_dir)}
        if self.settings.openai_api_key:
            local_environment["OPENAI_API_KEY"] = self.settings.openai_api_key

        web_environment = {}
        if self.settings.tavily_api_key:
            web_environment["TAVILY_API_KEY"] = self.settings.tavily_api_key

        return {"local": self._stdio_connection("src.mcp_servers.local_search", local_environment), "web": self._stdio_connection("src.mcp_servers.web_search", web_environment)}

    @staticmethod
    def _stdio_connection(module: str, environment: dict[str, str]) -> dict[str, Any]:
        return {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", module],
            "cwd": str(PROJECT_ROOT),
            "env": environment
        }

    @staticmethod
    def _message_text(message: AIMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        
        return "".join(
            block.get("text", "")
            for block in message.content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    @classmethod
    def _extract_references(cls, messages: list[Any]) -> list[Reference]:
        references: list[Reference] = []
        seen: set[tuple[str, str]] = set()
        for message in messages:
            if not isinstance(message, ToolMessage):
                continue
            
            artifact = message.artifact
            payload = (
                artifact.get("structured_content")
                if isinstance(artifact, dict)
                else None
            )

            if payload is None:
                payload = cls._tool_payload(message.content)
            
            if not isinstance(payload, dict):
                continue
            
            for item in payload.get("items", []):
                source_type = str(item.get("sourceType", "document"))
                source_id = str(item.get("sourceId", ""))
                key = (source_type, source_id)

                if key in seen:
                    continue

                seen.add(key)
                references.append(
                    Reference(
                        type=source_type,
                        id=source_id or None,
                        title=item.get("title"),
                        address=item.get("address"),
                        image_url=item.get("imageUrl"),
                    )
                )

            for citation in payload.get("citations", []):
                url = citation.get("url")
                if not url or ("web", url) in seen:
                    continue

                seen.add(("web", url))
                references.append(Reference(type="web", title=citation.get("title"), url=url))
        return references

    @staticmethod
    def _tool_payload(content: Any) -> Any:
        if isinstance(content, dict):
            return content
        
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        
        if isinstance(content, list):
            text_blocks = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            
            if text_blocks:
                try:
                    return json.loads("".join(text_blocks))
                except json.JSONDecodeError:
                    return None
        return None
