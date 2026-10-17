"""Memory refreshes must preserve cached tools and append new navigation context."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.infra.agent.middleware import prompt_injection as pi
from src.kernel.config import settings


class Request(SimpleNamespace):
    def override(self, **updates):
        return Request(**(vars(self) | updates))


@pytest.mark.parametrize("updated_index", ["new navigation hint", ""])
async def test_memory_invalidation_appends_context_without_changing_parent_or_child_tools(
    monkeypatch, updated_index
):
    index = "original navigation hint"

    async def build(*args, **kwargs):
        return index

    async def no_project(*args):
        return None

    monkeypatch.setattr(pi, "_MEMORY_INDEX_SNAPSHOTS", {})
    monkeypatch.setattr(pi, "_MEMORY_INDEX_USER_SNAPSHOTS", {})
    monkeypatch.setattr(settings, "NATIVE_MEMORY_INDEX_ENABLED", True)
    monkeypatch.setattr(pi, "_build_memory_index_full", build)
    monkeypatch.setattr("src.infra.memory.scope.resolve_session_project_id", no_project)
    recall = StructuredTool.from_function(
        lambda query: query, name="memory_recall", description="Recall saved memories."
    )
    original_schema = convert_to_openai_tool(recall)
    states = {
        actor: {"messages": [HumanMessage(f"Review {actor}'s API contract")]}
        for actor in ("parent", "child-a", "child-b")
    }

    async def capture(request):
        assert convert_to_openai_tool(request.tools[0]) == original_schema
        return AIMessage("Reviewed")

    for turn in (1, 2, 3):
        if turn == 3:
            index = updated_index
            pi.invalidate_memory_index_snapshot("user")
        for state in states.values():
            # Persistent children and their parent rebuild middleware between executions.
            middleware = pi.MemoryRecallIndexMiddleware(
                user_id="user", session_id="session", recall_available=True
            )
            history = deepcopy(state["messages"])
            update = await middleware.abefore_agent(state, None)
            assert state["messages"] == history
            if update:
                state["messages"].extend(update["messages"])
            snapshots = [m for m in state["messages"] if m.name == "task_context"]
            assert len(snapshots) == (2 if turn == 3 else 1)
            assert "original navigation hint" in snapshots[0].text
            if turn == 3:
                assert "original navigation hint" not in snapshots[-1].text
                if updated_index:
                    assert updated_index in snapshots[-1].text
            await middleware.awrap_model_call(Request(tools=[recall], state=state), capture)
            assert state["messages"][: len(history)] == history
            state["messages"].append(AIMessage(f"Turn {turn} completed"))


async def test_disabled_recall_never_reads_or_injects_memory_index(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Disabled recall must not read memory navigation")

    monkeypatch.setattr(pi, "build_memory_recall_index_context", forbidden)
    middleware = pi.MemoryRecallIndexMiddleware(user_id="user", session_id="session")
    assert await middleware.abefore_agent({"messages": []}, None) is None
