"""agent 自建 presenter 的 trace 终结器。

从 ``base.py`` 抽出（该文件受 1000 行上限约束）。TaskExecutor 传入的
presenter 由 executor 负责终结；本模块只服务于 ``BaseGraphAgent._stream``
自建 presenter 的场景（直连 ``/api/{agent_id}/stream`` 路径）。
"""

import asyncio

from src.infra.logging import get_logger
from src.infra.writer.present import Presenter

logger = get_logger(__name__)

_OWNED_TRACE_FINALIZED_FLAG = "_lambchat_owned_trace_finalized"


async def complete_owned_presenter_trace(
    presenter: Presenter, terminal_error: BaseException | None
) -> None:
    """终结 agent 自建 presenter 的 trace（直连 ``/api/{agent_id}/stream`` 路径）。

    保证成功 / 报错 / 取消三种出口都不把 trace 留在 status="running"
    （否则 run 挂死后前端大纲永远显示进行中，且无任何清理路径能回收）。
    """
    if getattr(presenter, _OWNED_TRACE_FINALIZED_FLAG, False):
        return
    try:
        if terminal_error is None:
            await presenter.complete("completed")
        else:
            from src.infra.task.manager import TaskInterruptedError

            # 用户取消（CancelledError / TaskInterruptedError）是独立终态，
            # 与 executor 侧口径一致：写成 error 会让用量面板把主动停止显示为 Err
            is_user_cancel = isinstance(
                terminal_error, (asyncio.CancelledError, TaskInterruptedError)
            )
            if is_user_cancel:
                event = presenter.error(
                    "Task cancelled", error_type="CancelledError", code="task_cancelled"
                )
            else:
                event = presenter.error(
                    str(terminal_error) or type(terminal_error).__name__,
                    error_type=type(terminal_error).__name__,
                )
            await presenter.emit(event)
            await presenter.complete("cancelled" if is_user_cancel else "error")
        setattr(presenter, _OWNED_TRACE_FINALIZED_FLAG, True)
    except Exception:
        logger.warning(
            "[Agent] Failed to finalize owned presenter trace: run_id=%s",
            getattr(presenter, "run_id", None),
            exc_info=True,
        )
