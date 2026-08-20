"""SteerMiddleware — 运行中插话注入（Codex 式 steer）。

用户在任务运行期间发送的消息（POST /chat/sessions/{id}/steer）先进入
``SteerQueue``；本中间件在每次主 agent 模型调用前取出该会话的排队消息，
追加到本次请求的消息末尾（模型在当前步骤后即可看到），并通过
``Command(update)`` 把它们持久化进图状态，落盘到 checkpoint，
刷新/重载后历史不丢。
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


async def _persist_delivered_user_messages(
    session_id: str, texts: list[str], presenter: Any = None
) -> None:
    """把已注入的插话消息写入 user:message 事件（尽力而为）。

    优先复用当前 run 的 ``presenter.emit_user_message``：事件自动归属
    该 run 的 trace，MongoDB 历史（completed_only 聚合）刷新后可见。
    无 presenter 时回退 dual_writer 直写（仅 Redis SSE，不进历史，
    仅作实时展示兜底）。失败只记日志，不影响注入。
    """
    import uuid

    try:
        if presenter is not None:
            for text in texts:
                await presenter.emit_user_message(
                    text,
                    message_id=f"steer-{uuid.uuid4().hex[:12]}",
                )
            return

        from src.infra.session.dual_writer import get_dual_writer
        from src.infra.utils.datetime import utc_now_iso

        writer = get_dual_writer()
        for text in texts:
            await writer.write_event(
                session_id=session_id,
                event_type="user:message",
                data={
                    "content": text,
                    "timestamp": utc_now_iso(),
                    "message_id": f"steer-{uuid.uuid4().hex[:12]}",
                },
            )
    except Exception:
        logger.warning(
            "[Steer] session=%s failed to persist delivered steer message(s)",
            session_id,
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
        pending = await queue.drain(self._session_id)
        if not pending:
            return await handler(request)

        injected = [build_human_message(text, None) for text in pending]
        logger.info(
            "[Steer] session=%s injecting %d user message(s) into model call",
            self._session_id,
            len(injected),
        )
        try:
            response = await handler(request.override(messages=[*request.messages, *injected]))
        except BaseException:
            # 整体失败（含取消）：放回队首，等重试或下次运行送达，不丢失
            await queue.requeue_front(self._session_id, pending)
            raise

        # 注入成功：写 user:message 事件（SSE + 历史持久化），
        # 再把插话消息写入图状态，checkpoint 持久化
        if self._session_id:
            await _persist_delivered_user_messages(
                self._session_id, pending, presenter=self._presenter
            )

        from langchain.agents.middleware.types import ExtendedModelResponse
        from langgraph.types import Command as LangCommand

        return ExtendedModelResponse(
            model_response=response,
            command=LangCommand(update={"messages": injected}),
        )
