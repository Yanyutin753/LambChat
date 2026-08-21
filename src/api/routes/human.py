"""
Human Input 路由

用于 Agent 请求人工审批/输入的 API。

支持分布式部署：
- 审批数据存储在 MongoDB
- 使用 Redis Pub/Sub 实现跨进程响应唤醒
- 自动降级为 MongoDB 轮询（Redis 不可用时）
"""

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import require_permissions
from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.mongodb import (
    APPROVAL_TTL,
    ApprovalResponse,
    PendingApproval,
    get_approval_storage,
    notify_approval_response,
    wait_for_response_distributed,
)
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()

# ============================================================================
# 回调机制 - 用于通知前端有新的审批请求
# ============================================================================

# 当创建新审批时的回调函数列表
_approval_created_callbacks: List[Callable[[str], None]] = []


def register_approval_callback(callback: Callable[[str], None]) -> None:
    """注册审批创建回调"""
    _approval_created_callbacks.append(callback)


def unregister_approval_callback(callback: Callable[[str], None]) -> None:
    """注销审批创建回调"""
    if callback in _approval_created_callbacks:
        _approval_created_callbacks.remove(callback)


async def _notify_approval_created(session_id: str) -> None:
    """通知所有回调有新的审批创建"""
    for callback in _approval_created_callbacks:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(session_id)
            else:
                callback(session_id)
        except Exception as e:
            logger.warning(f"Approval callback error: {e}")


# ============================================================================
# 内存状态 (单进程优化)
# ============================================================================

# 单进程内使用 asyncio.Event 加速（可选优化）
# 分布式环境下会同时使用 Redis Pub/Sub + MongoDB 轮询作为备用
# 存储 (event, created_at) 以支持 TTL 清理
HUMAN_LOCAL_EVENT_CACHE_MAX_ENTRIES = 512
_local_events: OrderedDict[str, tuple[asyncio.Event, float]] = OrderedDict()

# MongoDB 存储实例
_approval_storage = get_approval_storage()


# ============================================================================
# 核心函数
# ============================================================================


def _touch_local_event(approval_id: str) -> tuple[asyncio.Event, float] | None:
    entry = _local_events.get(approval_id)
    if entry is None:
        return None
    _local_events.move_to_end(approval_id)
    return entry


def _store_local_event(approval_id: str, entry: tuple[asyncio.Event, float]) -> None:
    _local_events[approval_id] = entry
    _local_events.move_to_end(approval_id)
    while len(_local_events) > HUMAN_LOCAL_EVENT_CACHE_MAX_ENTRIES:
        _local_events.popitem(last=False)


async def create_approval(
    message: str,
    approval_type: str = "form",
    fields: Optional[List[dict]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    ttl: Optional[int] = APPROVAL_TTL,
) -> PendingApproval:
    """
    创建审批请求 (供 Agent 调用)

    Args:
        message: 提示消息
        approval_type: 类型 (form, confirm)
        fields: 表单字段列表
        session_id: 关联的会话 ID
        user_id: 关联的用户 ID
        metadata: 元数据（interrupt 模式记录 mode/run_id/thread_id）
        ttl: 过期时间（秒），interrupt 模式下与工具超时对齐

    Returns:
        PendingApproval 对象
    """
    approval_id = str(uuid.uuid4())
    approval = PendingApproval(
        id=approval_id,
        message=message,
        type=approval_type,
        fields=fields or [],
        status="pending",
        session_id=session_id,
        user_id=user_id,
        created_at=utc_now(),
        metadata=metadata,
    )

    # 存储到 MongoDB
    await _approval_storage.create(approval, ttl=ttl)
    logger.info(
        "[HITL] approval_id=%s Approval created (type=%s)",
        approval_id,
        approval_type,
    )

    # 创建本地 Event（单进程优化）
    _store_local_event(approval_id, (asyncio.Event(), time.time()))

    # 通知前端有新的审批请求
    await _notify_approval_created(session_id or "")

    return approval


async def wait_for_response(approval_id: str, timeout: float = 300) -> Optional[ApprovalResponse]:
    """
    等待审批响应 (供 Agent 调用)

    使用本地 asyncio.Event + MongoDB 轮询：
    1. 优先使用本地 Event（单进程内快速响应）
    2. 使用 MongoDB 轮询作为后备

    Args:
        approval_id: 审批 ID
        timeout: 超时时间 (秒)

    Returns:
        ApprovalResponse 或 None (超时)
    """
    logger.info(
        "[HITL] approval_id=%s Waiting for response (timeout=%ss)",
        approval_id,
        timeout,
    )
    local_event = _touch_local_event(approval_id)
    event = local_event[0] if local_event else None

    if event:
        # 单进程内：同时等待本地 Event 和 MongoDB 轮询
        wait_tasks: list[asyncio.Task] = []
        try:
            # 先检查是否已有响应
            response = await _approval_storage.get_response(approval_id)
            if response:
                logger.info(
                    "[HITL] approval_id=%s Response received (already present)",
                    approval_id,
                )
                return response

            # 创建两个任务：本地 Event 和 MongoDB 轮询
            local_wait = asyncio.wait_for(event.wait(), timeout=timeout)
            mongo_wait = wait_for_response_distributed(approval_id, timeout)

            wait_tasks = [
                asyncio.create_task(local_wait),
                asyncio.create_task(mongo_wait),
            ]
            done, pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 获取结果（local_event.wait() 返回 True，需要从 MongoDB 获取实际响应）
            for task in done:
                try:
                    # local_event.wait() 返回 True，表示事件被触发，但实际响应在 MongoDB 中
                    task.result()
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.warning(f"Wait task error: {e}")

            # 从 MongoDB 获取最终结果
            final_response = await _approval_storage.get_response(approval_id)
            if final_response:
                logger.info("[HITL] approval_id=%s Response received", approval_id)
            else:
                logger.info("[HITL] approval_id=%s Wait timed out", approval_id)
            return final_response
        finally:
            # Always cancel + retrieve the wait tasks, even when the outer
            # caller cancels this coroutine (e.g. MCPToolWithRetry wait_for).
            # Without this, asyncio.wait is interrupted by CancelledError and
            # the tasks are orphaned with unretrieved TimeoutError ("Task
            # exception was never retrieved", issue #197).
            for task in wait_tasks:
                if not task.done():
                    task.cancel()
            if wait_tasks:
                await asyncio.gather(*wait_tasks, return_exceptions=True)
            _local_events.pop(approval_id, None)
    else:
        # 跨进程：直接使用 MongoDB 轮询
        distributed_response = await wait_for_response_distributed(approval_id, timeout)
        if distributed_response:
            logger.info("[HITL] approval_id=%s Response received", approval_id)
        else:
            logger.info("[HITL] approval_id=%s Wait timed out", approval_id)
        return distributed_response


def _cleanup_approval(approval_id: str) -> None:
    """清理审批相关数据"""
    _local_events.pop(approval_id, None)


def _cleanup_stale_events(max_age: float = 3600) -> int:
    """清理超时的本地 Event（防止遗弃的审批泄漏内存）"""
    now = time.time()
    stale = [aid for aid, (_, created) in _local_events.items() if now - created > max_age]
    for aid in stale:
        _local_events.pop(aid, None)
    return len(stale)


# ============================================================================
# API 路由
# ============================================================================


@router.get("/pending")
async def get_pending_approvals(
    limit: int = Query(100, ge=1, le=100, description="最大返回审批数量"),
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    """
    获取待处理的审批列表

    前端轮询此接口获取待审批的请求。只返回当前用户的审批。
    """
    _cleanup_stale_events()
    pending = await _approval_storage.list_pending(user_id=user.sub, limit=limit)
    return {"approvals": [a.model_dump() for a in pending], "count": len(pending)}


@router.post("/{approval_id}/respond", dependencies=[Depends(require_permissions("chat:write"))])
async def respond_to_approval(
    approval_id: str,
    approved: bool = Query(..., description="是否批准"),
    response: str = Query("{}", description="响应数据（JSON 字符串）"),
):
    """
    响应审批请求

    前端调用此接口提交审批结果。
    """
    logger.info(
        "[HITL] approval_id=%s Responding approved=%s",
        approval_id,
        approved,
    )
    approval = await _approval_storage.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    if approval.status != "pending":
        logger.info(
            "[HITL] approval_id=%s Approval not pending (status=%s)",
            approval_id,
            approval.status,
        )
        raise HTTPException(status_code=400, detail="审批请求已处理")

    # 解析 JSON 响应数据
    try:
        response_data = await run_blocking_io(json.loads, response) if response else {}
    except json.JSONDecodeError:
        response_data = {}

    # 记录响应并更新状态
    approval_response = ApprovalResponse(approved=approved, response=response_data)
    status = "approved" if approved else "rejected"
    resume_result: dict | None = None
    from src.infra.task.hitl import (
        activate_hitl_resume_attempt,
        is_interrupt_approval,
        submit_hitl_resume_run,
    )

    # 审批 metadata 是该请求实际运行模式的权威来源；部署配置变更后，
    # 已挂起的 interrupt 仍必须沿原 checkpoint 恢复。
    interrupt_approval = is_interrupt_approval(approval)
    respond_with_metadata = getattr(_approval_storage, "respond_if_pending_with_metadata", None)
    distributed_prepare = (
        interrupt_approval and settings.TASK_BACKEND == "arq" and callable(respond_with_metadata)
    )

    if distributed_prepare:
        assert callable(respond_with_metadata)
        resume_attempt_id = f"hitl-resume:{approval_id}:{uuid.uuid4().hex}"
        resume_result = await submit_hitl_resume_run(
            approval,
            {"approved": approved, "values": response_data},
            resume_attempt_id=resume_attempt_id,
            prepare_only=True,
        )
        if not resume_result.get("submitted"):
            raise HTTPException(
                status_code=503,
                detail=resume_result.get("message") or "恢复任务提交失败，请重试",
            )
        updated_approval = await respond_with_metadata(
            approval_id,
            status,
            approval_response,
            {"resume_attempt_id": resume_attempt_id},
        )
        if updated_approval is None:
            raise HTTPException(status_code=400, detail="审批请求已处理")
        await activate_hitl_resume_attempt(approval_id, resume_attempt_id)
    else:
        respond_if_pending = getattr(_approval_storage, "respond_if_pending", None)
        if callable(respond_if_pending):
            updated_approval = await respond_if_pending(approval_id, status, approval_response)
            if updated_approval is None:
                raise HTTPException(status_code=400, detail="审批请求已处理")
        else:
            await _approval_storage.update_status(approval_id, status, approval_response)

        if interrupt_approval:
            resume_result = await submit_hitl_resume_run(
                approval,
                {"approved": approved, "values": response_data},
            )
            if not resume_result.get("submitted"):
                restore_pending = getattr(_approval_storage, "restore_pending_if_status", None)
                if callable(restore_pending):
                    await restore_pending(approval_id, status)
                raise HTTPException(
                    status_code=503,
                    detail=resume_result.get("message") or "恢复任务提交失败，请重试",
                )

    # interrupt 审批创建时不过期（无超时），响应成功后设置 GC 过期时间
    expire_after = getattr(_approval_storage, "expire_after", None)
    if callable(expire_after):
        await expire_after(approval_id)

    logger.info(
        "[HITL] approval_id=%s Approval response recorded, notifying waiters",
        approval_id,
    )

    # 通知阻塞模式的等待者（interrupt 模式已通过新运行恢复）
    if not interrupt_approval:
        await notify_approval_response(approval_id, approval_response)
        entry = _touch_local_event(approval_id)
        if entry:
            entry[0].set()

    result = {"status": "success", "approval_id": approval_id, "approved": approved}
    if resume_result is not None:
        result["hitl_resume"] = resume_result
    return result


@router.post("/{approval_id}/extend", dependencies=[Depends(require_permissions("chat:write"))])
async def extend_approval_timeout(
    approval_id: str,
    extra_seconds: int = Query(60, ge=10, le=300, description="延长的秒数"),
):
    """
    延长审批超时时间（用户交互时触发，支持分布式）

    interrupt 模式审批无超时、不过期，直接返回成功（前端倒计时逻辑
    对无截止时间的审批不生效）。
    """
    approval = await _approval_storage.get(approval_id)
    if approval and (getattr(approval, "metadata", None) or {}).get("mode") == "interrupt":
        return {"status": "success", "expires_at": None}

    new_expires = await _approval_storage.extend_expires_at(
        approval_id,
        extra_seconds=extra_seconds,
    )
    if new_expires is None:
        return {"status": "max_extensions_reached", "expires_at": None}

    return {
        "status": "success",
        "expires_at": new_expires.isoformat(),
    }


@router.get("/{approval_id}", dependencies=[Depends(require_permissions("chat:write"))])
async def get_approval(approval_id: str):
    """获取单个审批详情"""
    approval = await _approval_storage.get(approval_id)
    if not approval:
        # 返回 200 状态码，但用 status 字段表示不存在
        # 这样前端处理更简洁，不需要 catch 404 错误
        return {"id": approval_id, "status": "not_found"}

    return approval.model_dump()


@router.delete("/{approval_id}", dependencies=[Depends(require_permissions("chat:write"))])
async def cancel_approval(approval_id: str):
    """取消审批请求"""
    approval = await _approval_storage.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    # 删除 MongoDB 记录
    await _approval_storage.delete(approval_id)
    # 清理内存中的 Event
    _cleanup_approval(approval_id)
    return {"status": "cancelled"}
