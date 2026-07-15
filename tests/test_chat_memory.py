import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.agent.service import AgentService


async def _answer(state: MessagesState) -> dict[str, list[AIMessage]]:
    user_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
    return {"messages": [AIMessage(content=f"turn-{len(user_messages)}")]}


@pytest.mark.asyncio
async def test_in_memory_checkpointer_keeps_and_isolates_client_conversations() -> None:
    builder = StateGraph(MessagesState)
    builder.add_node("answer", _answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    first_client = {"configurable": {"thread_id": AgentService.conversation_thread_id("client-a", "session-a")}}
    second_client = {"configurable": {"thread_id": AgentService.conversation_thread_id("client-a", "session-b")}}

    await graph.ainvoke({"messages": [HumanMessage(content="첫 질문")]}, config=first_client)
    continued = await graph.ainvoke({"messages": [HumanMessage(content="후속 질문")]}, config=first_client)
    isolated = await graph.ainvoke({"messages": [HumanMessage(content="다른 사용자 질문")]}, config=second_client)

    assert continued["messages"][-1].content == "turn-2"
    assert isolated["messages"][-1].content == "turn-1"
    assert len((await graph.aget_state(first_client)).values["messages"]) == 4
    assert len((await graph.aget_state(second_client)).values["messages"]) == 2
