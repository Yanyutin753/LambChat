"""
Human Input 路由

用于 Agent 请求人工审批/输入的 API。

支持分布式部署：
- 审批数据存储在 MongoDB
- 使用 Redis Stream 实现跨进程通知
- 自动降级为 MongoDB 轮询（Redis 不可用时）
"""

import asyncio
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.infra.logging import get_logger
from src.infra.storage.mongodb import (
    ApprovalResponse,
    PendingApproval,
    get_approval_storage,
    notify_approval_response,
    wait_for_response_distributed,
)

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
# 分布式环境下会同时使用 Redis Stream 作为备用
_local_events: Dict[str, asyncio.Event] = {}

# MongoDB 存储实例
_approval_storage = get_approval_storage()


# ============================================================================
# 核心函数
# ============================================================================


async def create_approval(
    message: str,
    approval_type: str = "text",
    choices: Optional[List[str]] = None,
    default: Optional[str] = None,
    session_id: Optional[str] = None,
) -> PendingApproval:
    """
    创建审批请求 (供 Agent 调用)

    Args:
        message: 提示消息
        approval_type: 类型 (text, confirm, choice)
        choices: 选项列表 (choice 类型时使用)
        default: 默认值
        session_id: 关联的会话 ID

    Returns:
        PendingApproval 对象
    """
    approval_id = str(uuid.uuid4())
    approval = PendingApproval(
        id=approval_id,
        message=message,
        type=approval_type,
        choices=choices or [],
        default=default,
        status="pending",
        session_id=session_id,
    )

    # 存储到 MongoDB
    await _approval_storage.create(approval)

    # 创建本地 Event（单进程优化）
    _local_events[approval_id] = asyncio.Event()

    # 通知前端有新的审批请求
    await _notify_approval_created(session_id or "")

    return approval


async def wait_for_response(approval_id: str, timeout: float = 300) -> Optional[ApprovalResponse]:
    """
    等待审批响应 (供 Agent 调用)

    支持分布式部署：
    1. 优先使用本地 asyncio.Event（单进程内快速响应）
    2. 使用 Redis Stream 等待（跨进程通知）
    3. 降级为 MongoDB 轮询（Redis 不可用时）

    Args:
        approval_id: 审批 ID
        timeout: 超时时间 (秒)

    Returns:
        ApprovalResponse 或 None (超时)
    """
    local_event = _local_events.get(approval_id)

    if local_event:
        # 单进程内：同时等待本地 Event 和分布式通知
        try:
            # 创建两个任务：本地 Event 和分布式等待
            local_wait = asyncio.wait_for(local_event.wait(), timeout=timeout)
            distributed_wait = wait_for_response_distributed(approval_id, timeout)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(local_wait),
                    asyncio.create_task(distributed_wait),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()

            # 获取结果
            for task in done:
                try:
                    result: Any = task.result()
                    if result:
                        return result
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.warning(f"Wait task error: {e}")

            # 从 MongoDB 获取最终结果
            return await _approval_storage.get_response(approval_id)

        finally:
            _local_events.pop(approval_id, None)
    else:
        # 跨进程：直接使用分布式等待
        return await wait_for_response_distributed(approval_id, timeout)


def _cleanup_approval(approval_id: str) -> None:
    """清理审批相关数据"""
    _local_events.pop(approval_id, None)


# ============================================================================
# API 路由
# ============================================================================


@router.get("/pending")
async def get_pending_approvals():
    """
    获取待处理的审批列表

    前端轮询此接口获取待审批的请求。
    """
    pending = await _approval_storage.list_pending()
    return {"approvals": [a.model_dump() for a in pending], "count": len(pending)}


@router.post("/{approval_id}/respond")
async def respond_to_approval(
    approval_id: str,
    approved: bool = Query(..., description="是否批准"),
    response: str = Query("", description="响应内容"),
):
    """
    响应审批请求

    前端调用此接口提交审批结果。
    """
    approval = await _approval_storage.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="审批请求已处理")

    # 记录响应并更新状态
    approval_response = ApprovalResponse(approved=approved, response=response)
    status = "approved" if approved else "rejected"
    await _approval_storage.update_status(approval_id, status, approval_response)

    # 通知等待的 Agent（分布式支持）
    # 1. 通过 Redis Stream 通知跨进程的 Agent
    await notify_approval_response(approval_id, approval_response)

    # 2. 触发本地 Event（单进程内快速响应）
    if approval_id in _local_events:
        _local_events[approval_id].set()

    return {"status": "success", "approval_id": approval_id, "approved": approved}


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    """获取单个审批详情"""
    approval = await _approval_storage.get(approval_id)
    if not approval:
        # 返回 200 状态码，但用 status 字段表示不存在
        # 这样前端处理更简洁，不需要 catch 404 错误
        return {"id": approval_id, "status": "not_found"}

    return approval.model_dump()


@router.delete("/{approval_id}")
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
