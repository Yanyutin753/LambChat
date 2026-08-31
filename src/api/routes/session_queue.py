"""会话排队状态查询路由（从 chat.py 拆出以控制单文件规模）。

挂载在 /api/chat 之下，与 chat.py 的 /sessions/{id}/... 路由同前缀；
前端轮询 `/api/chat/sessions/{id}/queue-position` 刷新"排队中（第 N 位）"。
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required
from src.api.routes.session import verify_session_ownership
from src.infra.logging import get_logger
from src.infra.session.manager import SessionManager
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()


@router.get("/sessions/{session_id}/queue-position")
async def get_session_queue_position(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """查询排队中任务的实时队列位置（前端轮询刷新"排队中（第 N 位）"）。"""
    session = await SessionManager().get_session(session_id)
    if not session:
        raise AppError(ErrorCode.SESSION_NOT_FOUND)
    verify_session_ownership(session, user)

    metadata = session.metadata or {}
    run_id = metadata.get("current_run_id")
    task_status = str(metadata.get("task_status") or "")
    position = 0
    # 排队侧状态（或缺失状态，保守起见同样查询）才查 Redis；running/终态必然不在队列
    if run_id and (
        not task_status or task_status in {TaskStatus.QUEUED.value, TaskStatus.PENDING.value}
    ):
        from src.infra.task.concurrency import get_concurrency_limiter

        position = await get_concurrency_limiter().get_queue_position(user.sub, str(run_id))

    return {
        "session_id": session_id,
        "run_id": run_id,
        "task_status": task_status,
        "position": position,
    }
