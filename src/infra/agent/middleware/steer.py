"""SteerMiddleware — 运行中插话注入（Codex 式 steer）。

用户在任务运行期间发送的消息（POST /chat/sessions/{id}/steer）先进入
``SteerQueue``；本中间件在每次模型调用前（``before_model`` 钩子，独立图
节点）取出该会话的排队消息，在模型调用开始前写出 ``steer:message``
事件（事件先于本次调用的输出进入 Redis/MongoDB，实时 SSE 与历史回放中
插话都排在回答之前），再以 state 更新把消息注入图状态。

注入必须发生在模型响应之前：``before_model`` 节点的更新先于模型节点提交
checkpoint，插话因此落在本次模型响应之前（模型是对插话做出的响应）。
OpenAI 协议要求带 ``tool_calls`` 的 assistant 消息后紧跟对应 tool 消息；
若插话经 ``Command(update)`` 在模型节点完成后追加（旧实现），一旦该次
响应携带 tool_calls，tools 节点写回的 ToolMessage 会落在插话之后，下一
次模型调用即 400 "insufficient tool messages following tool_calls
message"（2026-09-08 生产实例）。注入时顺带把历史中已被写乱的消息重排
自愈，存量坏会话不再永久 400。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, AnyMessage, RemoveMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from src.agents.core.node_utils import build_human_message

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentState
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


def _reorder_tool_response_adjacency(messages: list[AnyMessage]) -> list[AnyMessage] | None:
    """把夹在 AIMessage(tool_calls) 与其 ToolMessage 之间的其他消息后移。

    返回重排后的完整列表；顺序本就合法时返回 ``None``（调用方免于整表
    重写）。悬空 tool_calls（始终没有 ToolMessage 回应）不在此处理——
    deepagents 的 PatchToolCallsMiddleware 负责在 AI 消息后补合成响应，
    与本函数的移动语义兼容。
    """
    result: list[AnyMessage] = []
    held: list[AnyMessage] = []
    pending_ids: set[str | None] = set()
    for message in messages:
        if isinstance(message, AIMessage):
            call_ids = {
                call["id"]
                for call in (*message.tool_calls, *message.invalid_tool_calls)
                if call.get("id") is not None
            }
            if call_ids:
                result.extend(held)
                held = []
                result.append(message)
                pending_ids = call_ids
                continue
        if isinstance(message, ToolMessage):
            result.append(message)
            pending_ids.discard(message.tool_call_id)
            if not pending_ids and held:
                result.extend(held)
                held = []
        elif pending_ids:
            held.append(message)
        else:
            result.append(message)
    result.extend(held)
    if len(result) == len(messages) and all(a is b for a, b in zip(result, messages)):
        return None
    return result


async def _persist_injected_steer_messages(
    session_id: str, items: list[Any], presenter: Any = None
) -> None:
    """在注入时刻把插话消息写入独立的 steer:message 事件（尽力而为）。

    插话与用户消息管线完全解耦：自有事件类型，不参与 user:message
    的语义（去重/轮次归属/回放）。事件在模型调用开始前写出，保证在
    Redis 实时流与 MongoDB 历史中都排在回答事件之前；``created_at``
    记录用户发送时刻，供前端作为消息时间戳。优先复用当前 run 的
    presenter（事件归属该 run 的 trace）；无 presenter 时回退
    dual_writer 直写（仅实时 SSE 兜底）。失败只记日志。
    """
    import uuid

    for item in items:
        try:
            data = {
                "content": item.content,
                "message_id": item.id or f"steer-{uuid.uuid4().hex[:12]}",
                "attachments": item.attachments,
            }
            if getattr(item, "created_at", None):
                data["created_at"] = item.created_at.isoformat()
            run_id = getattr(presenter, "run_id", None)
            if run_id:
                data["run_id"] = run_id
            if presenter is not None:
                await presenter.save_event({"event": "steer:message", "data": data})
                continue

            from src.infra.session.dual_writer import get_dual_writer

            await get_dual_writer().write_event(
                session_id=session_id,
                event_type="steer:message",
                data=data,
            )
        except Exception:
            logger.warning(
                "[Steer] session=%s failed to persist injected steer message %s",
                session_id,
                getattr(item, "id", "unknown"),
                exc_info=True,
            )


class SteerMiddleware(AgentMiddleware):
    """把会话插话队列中的用户消息在下一次模型调用前注入图状态。"""

    def __init__(self, *, session_id: str, presenter: Any = None) -> None:
        super().__init__()
        self._session_id = session_id
        self._presenter = presenter

    async def abefore_model(
        self, state: AgentState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:  # noqa: ARG002
        from src.infra.task.steer import get_steer_queue

        queue = get_steer_queue()
        pending = await queue.drain_items(self._session_id)
        if not pending:
            return None

        injected = [build_human_message(item.content, item.attachments) for item in pending]
        logger.info(
            "[Steer] session=%s injecting %d user message(s) before model call",
            self._session_id,
            len(injected),
        )

        # 注入时刻先写 steer:message 事件：事件先于本次调用的输出进入
        # Redis/MongoDB，插话在实时流与历史回放中均排在回答之前
        if self._session_id:
            await _persist_injected_steer_messages(
                self._session_id, pending, presenter=self._presenter
            )

        # drain 即送达，随之释放 Redis lease 并清 inflight：否则 run 终态的
        # emit_undelivered_steer_events（list_items 读 pending+inflight）会把
        # 已送达的插话误报 steer:undelivered，前端补发流程会重复投递。ack
        # 失败只记日志——注入语义已由下方 state 更新保证，不因清理失败而中断。
        try:
            await queue.ack_items(self._session_id)
        except Exception:
            logger.warning(
                "[Steer] session=%s failed to ack drained steer items after injection",
                self._session_id,
                exc_info=True,
            )

        # 更新经 before_model 节点提交 checkpoint（先于模型节点），插话即
        # 持久化送达；随后模型调用失败也不回队——新 run 从 state 续跑仍能
        # 看到插话，回队反而会重复注入。
        reordered = _reorder_tool_response_adjacency(state.get("messages") or [])
        if reordered is None:
            return {"messages": injected}
        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *reordered, *injected]}
