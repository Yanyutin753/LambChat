"""重放响应 id 防护测试（2026-08-25 生产 KeyError: 'model' 事故）。

事故链路（已在生产堆栈与本地复现证实）：

1. 上游中转（chat.oaifree.cn 反代）在同一会话的多次补全里返回重复的响应 id；
2. langgraph 的 ``add_messages`` 按 id 去重——同 id 的新 AIMessage 会**原位替换**
   历史消息而不是追加；
3. deepagents 的 model→tools 条件边发现"最后一条 AIMessage 的 tool_calls 已
   全部有 ToolMessage 回答"，走进"人工注入 tool 消息"分支并返回 ``"model"``；
4. deepagents 默认图没有 before_model/after_model 中间件也没有 response_format，
   该条件边的 destinations 不含 ``"model"`` → ``Branch._finish`` 抛
   ``KeyError: 'model'``，整个 run 失败。

``UniqueResponseIdMiddleware`` 在响应进入 state 前改写冲突/空 id，保证
add_messages 永远追加，毒状态无从形成。
"""

from types import SimpleNamespace
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.middleware.types import ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from src.infra.agent.middleware.retry import (
    UniqueResponseIdMiddleware,
    create_retry_middleware,
)


class ScriptedModel(GenericFakeChatModel):
    """按脚本顺序返回消息的假模型（支持 bind_tools）。"""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self


@tool
def noop(text: str) -> str:
    """No-op tool for exercising the tools loop."""
    return "ok"


def _tool_call(call_id: str) -> dict:
    return {"name": "noop", "args": {"text": "x"}, "id": call_id, "type": "tool_call"}


async def test_replayed_response_id_does_not_crash_deepagents_graph() -> None:
    """上游重放同一条响应（同 id 同 tool_call）时 run 必须照常完成。"""
    replayed = AIMessage(id="resp-dup", content="", tool_calls=[_tool_call("call-a")])
    model = ScriptedModel(messages=iter([replayed, replayed, AIMessage(content="done")]))
    graph = create_deep_agent(
        model=model,
        tools=[noop],
        checkpointer=InMemorySaver(),
        middleware=create_retry_middleware(),
    )
    config = {"configurable": {"thread_id": "t-replay"}}

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")]}, config)

    messages = result["messages"]
    contents = [m.content for m in messages if isinstance(m, AIMessage)]
    assert "done" in contents
    # 重放的 tool_call 被改写为未回答的新 id → 工具重新执行（两条 ToolMessage）
    tool_messages = [m for m in messages if type(m).__name__ == "ToolMessage"]
    assert len(tool_messages) == 2
    # 所有 AIMessage id 必须唯一
    ids = [m.id for m in messages if isinstance(m, AIMessage)]
    assert len(ids) == len(set(ids))


async def test_unique_response_id_rewrites_colliding_and_empty_ids() -> None:
    """与历史冲突或为空的响应 id 改写为新 uuid，正常 id 保持不变。"""
    middleware = UniqueResponseIdMiddleware()
    history = [
        HumanMessage(id="h1", content="hi"),
        AIMessage(id="resp-dup", content="old"),
        ToolMessage(id="t1", content="ok", tool_call_id="call-answered"),
    ]
    request = SimpleNamespace(state={"messages": history}, messages=history)
    colliding = AIMessage(id="resp-dup", content="replayed")
    empty_id = AIMessage(id="", content="empty id")
    fresh = AIMessage(id="resp-fresh", content="fresh")

    async def handler(_req: Any) -> ModelResponse:
        return ModelResponse(result=[colliding, empty_id, fresh])

    await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]

    assert colliding.id not in {"resp-dup", "", None}
    assert empty_id.id not in {"resp-dup", "", None}
    assert colliding.id != empty_id.id
    assert fresh.id == "resp-fresh"


async def test_unique_response_id_rewrites_replayed_tool_call_ids() -> None:
    """已被 ToolMessage 回答过的 tool_call id 改写为新 id，未回答的保持不变。"""
    middleware = UniqueResponseIdMiddleware()
    history = [
        HumanMessage(id="h1", content="hi"),
        ToolMessage(id="t1", content="ok", tool_call_id="call-answered"),
    ]
    request = SimpleNamespace(state={"messages": history}, messages=history)
    replayed_call = AIMessage(
        id="resp-new",
        content="",
        tool_calls=[
            {"name": "noop", "args": {}, "id": "call-answered", "type": "tool_call"},
            {"name": "noop", "args": {}, "id": "call-open", "type": "tool_call"},
        ],
    )

    async def handler(_req: Any) -> ModelResponse:
        return ModelResponse(result=[replayed_call])

    await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]

    call_ids = [c["id"] for c in replayed_call.tool_calls]
    assert call_ids[0] not in {"call-answered", "call-open", None}
    assert call_ids[1] == "call-open"
    assert len(set(call_ids)) == 2
