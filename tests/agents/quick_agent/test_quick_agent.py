"""Quick Agent（快问快答）测试：直连 LLM、无工具、外层图维护历史。"""

from __future__ import annotations

from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult

from src.agents.core.base import GraphBuilder
from src.agents.quick_agent.nodes import quick_agent_node
from src.agents.quick_agent.state import QuickAgentState


class _FakeModel:
    def __init__(self, reply: str = "好的") -> None:
        self.calls: list[list[Any]] = []
        self.reply = reply

    async def ainvoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        return AIMessage(content=self.reply)


def _patch_model(monkeypatch, model: _FakeModel) -> None:
    class _FakeLLMClient:
        @staticmethod
        async def get_model(**_kwargs):
            return model

    monkeypatch.setattr("src.agents.quick_agent.nodes.LLMClient", _FakeLLMClient)

    async def no_fallback(*args, **kwargs):
        return None

    monkeypatch.setattr("src.agents.quick_agent.nodes.resolve_fallback_model", no_fallback)


class _RecordingBuilder:
    def __init__(self) -> None:
        self.nodes: list[tuple] = []
        self.edges: list[tuple] = []
        self.entry_point = None

    def add_node(self, name, func, description=""):
        self.nodes.append((name, func))
        return self

    def set_entry_point(self, node_name):
        self.entry_point = node_name
        return self

    def add_edge(self, from_node, to_node):
        self.edges.append((from_node, to_node))
        return self


def _state(text: str, history: list | None = None) -> dict:
    return {
        "input": text,
        "session_id": "session-1",
        "messages": history or [],
        "output": "",
        "attachments": None,
    }


def test_quick_agent_registered_with_catalog_metadata() -> None:
    from src.agents import AgentFactory, discover_agents

    discover_agents()
    agents = AgentFactory.list_agents()
    quick = next(a for a in agents if a["id"] == "quick")
    assert quick["supports_sandbox"] is False
    assert quick["icon"] == "Zap"
    assert quick["name"] == "agents.quick.name"
    assert quick["description"] == "agents.quick.description"


def test_quick_agent_builds_single_node_graph() -> None:
    from src.agents.quick_agent.graph import QuickAgent

    builder = _RecordingBuilder()
    QuickAgent().build_graph(builder)
    assert builder.entry_point == "agent"
    assert [name for name, _ in builder.nodes] == ["agent"]
    assert builder.edges == [("agent", "END")]


async def test_quick_agent_node_sends_system_history_and_human_to_llm(monkeypatch) -> None:
    model = _FakeModel(reply="答案")
    _patch_model(monkeypatch, model)

    history = [HumanMessage("早"), AIMessage("早呀")]
    result = await quick_agent_node(_state("你好", history), {"configurable": {}})

    assert len(model.calls) == 1
    sent = model.calls[0]
    assert isinstance(sent[0], SystemMessage)
    assert sent[0].content  # 非空系统提示
    assert sent[1:] == [*history, HumanMessage("你好")]

    assert [m.content for m in result["messages"]] == ["你好", "答案"]
    assert result["output"] == "答案"


async def test_quick_agent_node_injects_persona_and_language_sections(monkeypatch) -> None:
    model = _FakeModel()
    _patch_model(monkeypatch, model)

    config = {
        "configurable": {
            "persona_system_prompt": "你是猫娘助手",
            "agent_options": {"response_language": "zh"},
        }
    }
    await quick_agent_node(_state("在吗"), config)

    system_prompt = model.calls[0][0].content
    assert "猫娘助手" in system_prompt
    assert "Always respond in Simplified Chinese" in system_prompt


async def test_quick_agent_node_keeps_default_prompt_without_persona(monkeypatch) -> None:
    model = _FakeModel()
    _patch_model(monkeypatch, model)

    await quick_agent_node(_state("在吗"), {"configurable": {}})

    system_prompt = model.calls[0][0].content
    assert "quick" in system_prompt.lower()
    # 无 persona 时不注入 persona 标题段
    assert "## Persona" not in system_prompt


async def test_quick_agent_graph_accumulates_history_across_turns(monkeypatch) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.quick_agent.graph import QuickAgent

    model = _FakeModel(reply="收到")
    _patch_model(monkeypatch, model)

    builder = GraphBuilder(QuickAgentState)
    QuickAgent().build_graph(builder)
    graph = builder.compile(checkpointer=MemorySaver())

    config = {"configurable": {"thread_id": "session-1"}}
    await graph.ainvoke(_state("第一问"), config)
    await graph.ainvoke(_state("第二问"), config)

    assert len(model.calls) == 2
    second_turn = model.calls[1]
    assert [type(m) for m in second_turn] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        HumanMessage,
    ]
    assert second_turn[1].content == "第一问"
    assert second_turn[3].content == "第二问"


# ---------------------------------------------------------------------------
# 真实 deepagents 内层图（fast/search/team 同款 create_deep_agent）与 quick
# 双向切换：共享 checkpointer + thread_id，历史互通。
# ---------------------------------------------------------------------------


class _RecordingChatModel(BaseChatModel):
    calls: ClassVar[list] = []

    @property
    def _llm_type(self) -> str:
        return "recording-quick-agent"

    def bind_tools(self, tools=None, *, tool_choice=None, **kwargs):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        type(self).calls.append([(m.type, m.content) for m in messages])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="deep 答案"))])


def _compile_real_deepagents_graph(checkpointer):
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=_RecordingChatModel(),
        system_prompt="You are a deep agent.",
        checkpointer=checkpointer,
    )


async def test_quick_history_visible_to_real_deepagents_graph(monkeypatch) -> None:
    """quick 先答一轮，真实 deepagents 图（fast/search/team 内层）续跑同 thread 能读到。"""
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.quick_agent.graph import QuickAgent

    _RecordingChatModel.calls.clear()
    model = _FakeModel(reply="quick 答案")
    _patch_model(monkeypatch, model)

    checkpointer = MemorySaver()
    thread = {"configurable": {"thread_id": "session-switch-3"}}

    builder = GraphBuilder(QuickAgentState)
    QuickAgent().build_graph(builder)
    quick_graph = builder.compile(checkpointer=checkpointer)
    await quick_graph.ainvoke(_state("第一问"), thread)

    deep_graph = _compile_real_deepagents_graph(checkpointer)
    await deep_graph.ainvoke({"messages": [HumanMessage("第二问")]}, thread)

    assert len(_RecordingChatModel.calls) == 1
    contents = [content for _kind, content in _RecordingChatModel.calls[0]]
    assert "第一问" in contents
    assert "quick 答案" in contents
    assert "第二问" in contents


async def test_deepagents_history_visible_to_quick(monkeypatch) -> None:
    """真实 deepagents 图先答一轮，切 quick 续跑同 thread 也能读到。"""
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.quick_agent.graph import QuickAgent

    _RecordingChatModel.calls.clear()
    model = _FakeModel(reply="quick 接棒")
    _patch_model(monkeypatch, model)

    checkpointer = MemorySaver()
    thread = {"configurable": {"thread_id": "session-switch-4"}}

    deep_graph = _compile_real_deepagents_graph(checkpointer)
    await deep_graph.ainvoke({"messages": [HumanMessage("deep 的问题")]}, thread)

    builder = GraphBuilder(QuickAgentState)
    QuickAgent().build_graph(builder)
    quick_graph = builder.compile(checkpointer=checkpointer)
    await quick_graph.ainvoke(_state("quick 的问题"), thread)

    sent = model.calls[0]
    texts = [m.content for m in sent]
    assert "deep 的问题" in texts
    assert "deep 答案" in texts
    assert "quick 的问题" in texts


def test_all_deepagents_agents_share_session_thread_checkpoint_namespace() -> None:
    """fast/search/team 内层图必须继续走 thread_id=session 的共享 checkpoint
    命名空间（跨 agent 切换历史互通的前提），quick 与之对齐。"""
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    for rel in (
        "agents/fast_agent/nodes.py",
        "agents/search_agent/nodes.py",
        "agents/team_agent/nodes.py",
    ):
        source = (src_root / rel).read_text(encoding="utf-8")
        assert "get_async_checkpointer" in source, rel
        assert 'state.get("session_id")' in source, rel

    # quick 外层图由 BaseGraphAgent 注入 thread_id=session_id 的 checkpointer；
    # messages channel 必须与 deepagents 同款（DeepAgentState/DeltaChannel），
    # 否则读不了 fast/search/team 写的增量 checkpoint。
    quick_state = (src_root / "agents/quick_agent/state.py").read_text(encoding="utf-8")
    assert "DeepAgentState" in quick_state


def test_quick_agent_checkpointer_respects_checkpoint_backend() -> None:
    """quick 的 checkpointer 必须走 get_async_checkpointer（按 CHECKPOINT_BACKEND
    选 PG/Mongo），与 deepagents 系 agent 共用存储；基类默认只试 Mongo，
    生产 PG 环境会导致跨 agent 历史互通静默失效。"""
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    source = (src_root / "agents/quick_agent/graph.py").read_text(encoding="utf-8")
    assert "get_async_checkpointer" in source
    assert "get_mongo_checkpointer" not in source


def test_base_stream_initial_state_drops_unserializable_kwargs() -> None:
    """BaseGraphAgent._stream 的初始状态不得携带原始 kwargs（含 Presenter 等
    不可序列化对象）：外层图带 checkpointer 时输入写入触发 msgpack 序列化
    直接报错（staging quick agent 首轮实证 'Type is not msgpack serializable:
    Presenter'）。"""
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    source = (src_root / "agents/core/base.py").read_text(encoding="utf-8")
    assert '"context": kwargs' not in source


async def test_quick_agent_uses_configured_fallback_after_retry_exhaustion(monkeypatch):
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(settings, "LLM_RETRY_DELAY", 0)

    class FailingModel(_FakeModel):
        async def ainvoke(self, messages, **kwargs):
            self.calls.append(list(messages))
            raise TimeoutError()

    primary = FailingModel()
    backup = _FakeModel(reply="备用回答")

    async def get_model(**kwargs):
        return backup if kwargs.get("model") == "backup" else primary

    monkeypatch.setattr("src.agents.quick_agent.nodes.LLMClient.get_model", get_model)
    result = await quick_agent_node(
        _state("你好"), {"configurable": {"agent_options": {"_resolved_fallback_model": "backup"}}}
    )
    assert result["output"] == "备用回答"
    assert len(primary.calls) == 2
    assert len(backup.calls) == 1


async def test_real_quick_graph_does_not_replay_delivered_stream(monkeypatch):
    import pytest
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    from src.agents.quick_agent.graph import QuickAgent
    from src.kernel.config import settings

    class InterruptedModel(BaseChatModel):
        attempts: int = 0

        @property
        def _llm_type(self):
            return "interrupted-test"

        def _generate(self, *args, **kwargs):
            raise AssertionError("graph should stream")

        async def _astream(self, *args, **kwargs):
            self.attempts += 1
            yield ChatGenerationChunk(message=AIMessageChunk(content="已经交付的正文"))
            raise TimeoutError("stream interrupted")

    monkeypatch.setattr(settings, "LLM_RETRY_DELAY", 0)
    model = InterruptedModel()
    _patch_model(monkeypatch, model)
    builder = GraphBuilder(QuickAgentState)
    QuickAgent().build_graph(builder)
    graph = builder.compile()
    delivered = []
    with pytest.raises(TimeoutError):
        async for event in graph.astream_events(_state("你好"), version="v2"):
            if event["event"] == "on_chat_model_stream":
                delivered.append(event["data"]["chunk"].content)
    assert delivered == ["已经交付的正文"]
    assert model.attempts == 1
