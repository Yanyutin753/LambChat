"""SteerMiddleware — 运行中插话注入（Codex 式 steer）。

用户在任务运行期间发送的消息（POST /chat/sessions/{id}/steer）先进入
``SteerQueue``；本中间件在每次主 agent 模型调用前取出该会话的排队消息，
在调用开始前写出 ``steer:message`` 事件（事件先于本次调用的输出进入
Redis/MongoDB，实时 SSE 与历史回放中插话都排在回答之前），再追加到本次
请求的消息末尾（模型在当前步骤后即可看到），并通过 ``Command(update)``
把它们持久化进图状态，落盘到 checkpoint，刷新/重载后历史不丢。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware

from src.agents.core.node_utils import build_human_message

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain.agents.middleware.types import (
        ContextT,
        ModelRequest,
        ModelResponse,
        ResponseT,
    )

logger = logging.getLogger(__name__)


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

    若注入的模型调用失败，消息带原 ID 回队重试，送达时会再次写出
    同 ``message_id`` 的事件，由前端按 ID 去重。
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
    """把会话插话队列中的用户消息注入下一次模型调用。"""

    def __init__(self, *, session_id: str, presenter: Any = None) -> None:
        super().__init__()
        self._session_id = session_id
        self._presenter = presenter

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | Any:
        from src.infra.task.steer import get_steer_queue

        queue = get_steer_queue()
        pending = await queue.drain_items(self._session_id)
        if not pending:
            return await handler(request)

        injected = [build_human_message(item.content, item.attachments) for item in pending]
        logger.info(
            "[Steer] session=%s injecting %d user message(s) into model call",
            self._session_id,
            len(injected),
        )

        # 注入时刻先写 steer:message 事件：事件先于本次调用的输出进入
        # Redis/MongoDB，插话在实时流与历史回放中均排在回答之前
        if self._session_id:
            await _persist_injected_steer_messages(
                self._session_id, pending, presenter=self._presenter
            )

        try:
            response = await handler(request.override(messages=[*request.messages, *injected]))
        except BaseException:
            # 整体失败（含取消）：放回队首，等重试或下次运行送达，不丢失。
            # 重试送达会再次写出同 message_id 事件，前端按 ID 去重。
            await queue.requeue_front_items(self._session_id, pending)
            raise

        await queue.ack_items(self._session_id)

        from langchain.agents.middleware.types import ExtendedModelResponse
        from langgraph.types import Command as LangCommand

        return ExtendedModelResponse(
            model_response=response,
            command=LangCommand(update={"messages": injected}),
        )
