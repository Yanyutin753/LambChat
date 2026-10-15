"""Real agent graphs, virtual file storage, and repeatable request prefixes."""

import importlib
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.infra.llm.responses_cache import current_responses_prompt_cache_key
from src.infra.writer.present import Presenter, PresenterConfig


class _AnswerModel(BaseChatModel):
    calls: list[Any] = []
    schemas: list[str] = []
    cache_keys: list[str | None] = []
    tools: list[str] = []
    tool_schema: str = ""
    write_file: bool = False

    @property
    def _llm_type(self):
        return "no-sandbox-test"

    def bind_tools(self, tools, **kwargs):
        self.tools = [getattr(tool, "name", "") for tool in tools]
        self.tool_schema = json.dumps(
            [convert_to_openai_tool(tool) for tool in tools], sort_keys=True
        )
        return self

    def _generate(self, messages, **kwargs):
        self.calls.append(messages)
        self.schemas.append(self.tool_schema)
        self.cache_keys.append(current_responses_prompt_cache_key())
        if self.write_file and len(self.calls) == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "write-note",
                        "name": "write_file",
                        "args": {
                            "file_path": "/workflow/no-sandbox/note.txt",
                            "content": "persistent proof",
                        },
                    }
                ],
            )
        else:
            message = AIMessage(content="ready")
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, **kwargs):
        return self._generate(messages, **kwargs)


@pytest.mark.parametrize(
    ("agent_id", "write_file"),
    [
        ("search", False),
        ("search", True),
        ("team", False),
        ("team", True),
        ("quick", False),
    ],
)
async def test_agents_work_without_sandbox_and_keep_prefixes(monkeypatch, agent_id, write_file):
    from src.agents.core.base import AgentFactory
    from src.infra.llm.client import LLMClient
    from src.kernel.config import settings

    module = importlib.import_module(f"src.agents.{agent_id}_agent.nodes")
    model = _AnswerModel(write_file=write_file)
    monkeypatch.setattr(LLMClient, "get_model", AsyncMock(return_value=model))
    for flag in (
        "ENABLE_SANDBOX",
        "ENABLE_MCP",
        "ENABLE_MEMORY",
        "ENABLE_SKILLS",
        "ENABLE_RECOMMEND_QUESTIONS",
        "ENABLE_COMPUTER_USE",
        "ENABLE_CODE_INTERPRETER",
    ):
        monkeypatch.setattr(settings, flag, False)
    monkeypatch.setattr(AgentFactory, "_instances", {})
    agent = await AgentFactory.get(agent_id)
    store = InMemoryStore()
    if agent_id == "quick":
        agent._graph = agent._graph.builder.compile(checkpointer=MemorySaver())
    else:
        backend_module = getattr(module, "backend_setup", module)
        monkeypatch.setattr(backend_module, "acreate_store", AsyncMock(return_value=store))
        monkeypatch.setattr(module, "get_async_checkpointer", AsyncMock(return_value=MemorySaver()))
        monkeypatch.setattr(module, "emit_token_usage", AsyncMock())
        # Artifact publishing is an external service, outside this storage/LLM contract.
        monkeypatch.setattr(
            module, "ArtifactDeliveryMiddleware", lambda **kwargs: AgentMiddleware()
        )
        context_type = getattr(
            module, "SearchAgentContext" if agent_id == "search" else "TeamAgentContext"
        )
        monkeypatch.setattr(context_type, "setup", AsyncMock())
        monkeypatch.setattr(
            backend_module,
            "get_session_sandbox_manager",
            lambda: pytest.fail("disabled sandbox must not be initialized"),
        )
    for message in ("hello", "continue"):
        presenter = Presenter(
            PresenterConfig(
                session_id="no-sandbox",
                agent_id=agent_id,
                agent_name=agent.name,
                user_id="user",
                enable_storage=False,
            )
        )
        monkeypatch.setattr(presenter, "build_langsmith_metadata", AsyncMock(return_value={}))
        events = [
            event
            async for event in agent.stream(
                message,
                "no-sandbox",
                user_id="user",
                presenter=presenter,
                agent_options={
                    "_resolved_fallback_model": None,
                    "_resolved_supports_vision": False,
                    "_resolved_image_url_mode": "url",
                    "enable_code_interpreter": False,
                },
            )
        ]
        assert events[-1]["event"] == "done"
    assert len(model.calls) >= 2
    assert model.cache_keys == ["no-sandbox"] * len(model.calls)
    assert all(schema == model.schemas[0] for schema in model.schemas)
    first = [(message.type, message.content) for message in model.calls[0]]
    last_prefix = [(message.type, message.content) for message in model.calls[-1][: len(first)]]
    assert first == last_prefix
    assert "execute" not in model.tools
    if agent_id != "quick":
        prompt = str(model.calls[0][0].content)
        assert "no sandbox or operating-system shell" in prompt
        assert "/workflow/<session-id>" in prompt
        assert "Sandbox local:" not in prompt
    if write_file:
        items = await store.asearch(("assistant-user", "workflow", "no-sandbox"))
        assert any("persistent proof" in str(item.value) for item in items)
