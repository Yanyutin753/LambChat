"""HITL（ask_human）interrupt 模式的恢复处理（issue #218）。

interrupt 模式下，ask_human 通过 LangGraph interrupt() 挂起并持久化
checkpoint，进程重启后状态不丢。对齐 deepagents 官方 HITL 语义：
无超时、无限期等待，用户响应（POST /human/{id}/respond）通过提交一个
携带 hitl_resume 载荷的新运行来恢复：新运行重新进入 fast_agent_node，
以 Command(resume=...) 从断点继续执行。

跨副本重复恢复由 Redis 分布式锁 + 审批状态原子流转双重防护。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings

from .status import TaskStatus

logger = get_logger(__name__)

HITL_RESUME_LOCK_PREFIX = "hitl:resume:"
HITL_RESUME_LOCK_TTL_SECONDS = 300


def hitl_interrupt_mode_enabled() -> bool:
    """当前是否启用 interrupt 模式的 ask_human。"""
    return getattr(settings, "HITL_MODE", "blocking") == "interrupt"


def is_interrupt_approval(approval: Any) -> bool:
    """审批是否由 interrupt 模式的 ask_human 创建。"""
    metadata = getattr(approval, "metadata", None) or {}
    return metadata.get("mode") == "interrupt"


def extract_ask_human_interrupts(snapshot: Any) -> List[Dict[str, Any]]:
    """从挂起的图状态快照中提取 ask_human interrupt payload。"""
    payloads: List[Dict[str, Any]] = []
    tasks = getattr(snapshot, "tasks", None) or ()
    if isinstance(tasks, dict):
        tasks = [t for group in tasks.values() for t in (
            group if isinstance(group, (list, tuple)) else [group]
        )]
    for task in tasks:
        for intr in getattr(task, "interrupts", None) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and value.get("kind") == "ask_human":
                payloads.append(value)
    return payloads


async def _send_approval_sse(
    approval: Any,
    fields: List[dict],
    session_id: str,
    run_id: Optional[str],
) -> None:
    """挂起后发送 approval_required 事件到 SSE 流。"""
    try:
        from src.infra.session.dual_writer import get_dual_writer

        await get_dual_writer().write_event(
            session_id=session_id,
            event_type="approval_required",
            data={
                "id": approval.id,
                "message": approval.message,
                "type": approval.type,
                "fields": fields,
            },
            run_id=run_id,
        )
    except Exception as e:
        logger.error(
            "[HITL] approval_id=%s Failed to send approval_required event: %s",
            approval.id,
            e,
            exc_info=True,
        )


async def materialize_ask_human_approvals(
    snapshot: Any,
    *,
    session_id: Optional[str],
    run_id: Optional[str],
    user_id: Optional[str],
) -> int:
    """图挂起后，将 ask_human interrupt payload 物化为审批记录 + SSE 事件。

    工具内部零副作用（对齐 deepagents 官方 HITL），审批在此处创建，
    且仅在挂起发生时执行一次；按 message 对会话内已有 pending 审批
    去重，避免重复挂起/重放时重复创建。
    """
    payloads = extract_ask_human_interrupts(snapshot)
    if not payloads:
        return 0

    from src.api.routes.human import create_approval
    from src.infra.storage.mongodb import get_approval_storage

    existing: List[str] = []
    if session_id:
        try:
            existing = [
                a.message for a in await get_approval_storage().list_pending(
                    session_id=session_id, limit=100
                )
            ]
        except Exception as e:
            logger.warning("[HITL] Failed to list pending approvals: %s", e)

    created = 0
    for payload in payloads:
        message = str(payload.get("message", ""))
        fields = payload.get("fields") or []
        if message and message in existing:
            continue
        approval = await create_approval(
            message=message,
            approval_type="form",
            fields=fields,
            session_id=session_id,
            user_id=user_id,
            metadata={
                "mode": "interrupt",
                "run_id": run_id,
                "thread_id": session_id,
            },
            ttl=None,  # 无超时：审批不过期，响应后再 GC
        )
        existing.append(message)
        created += 1
        if session_id:
            await _send_approval_sse(approval, fields, session_id, run_id)
        logger.info(
            "[HITL] approval_id=%s Materialized from interrupt: session=%s run_id=%s",
            approval.id,
            session_id,
            run_id,
        )
    return created


async def _acquire_resume_lock(approval_id: str) -> str | None:
    """获取恢复锁，返回 token；获取失败返回 None（其他副本处理中）。"""
    token = uuid.uuid4().hex
    acquired = await get_redis_client().set(
        f"{HITL_RESUME_LOCK_PREFIX}{approval_id}",
        token,
        ex=HITL_RESUME_LOCK_TTL_SECONDS,
        nx=True,
    )
    return token if acquired else None


async def _release_resume_lock(approval_id: str, token: str) -> None:
    try:
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = get_redis_client().eval(lua, 1, f"{HITL_RESUME_LOCK_PREFIX}{approval_id}", token)
        if hasattr(result, "__await__"):
            await result
    except Exception as e:
        logger.warning("Failed to release HITL resume lock %s: %s", approval_id, e)


async def submit_hitl_resume_run(approval: Any, resume_value: Dict[str, Any]) -> Dict[str, Any]:
    """为挂起的 interrupt 审批提交恢复运行。

    Args:
        approval: 已记录响应的审批对象（需含 session_id）
        resume_value: 传给 interrupt() 的恢复值，
            用户响应形如 {"approved": bool, "values": {...}}，
            超时为 {"hitl_timeout": True}

    Returns:
        {"submitted": bool, "run_id": str | None, "message": str}
    """
    session_id = getattr(approval, "session_id", None)
    if not session_id:
        return {"submitted": False, "run_id": None, "message": "审批未关联会话，无法恢复"}

    token = await _acquire_resume_lock(approval.id)
    if token is None:
        return {"submitted": False, "run_id": None, "message": "恢复已在其他实例中启动"}

    try:
        from src.infra.session.storage import SessionStorage

        session = await SessionStorage().get_by_session_id(session_id)
        if session is None:
            return {"submitted": False, "run_id": None, "message": "会话不存在"}
        if not getattr(session, "user_id", None):
            return {"submitted": False, "run_id": None, "message": "会话缺少用户信息"}
        metadata = getattr(session, "metadata", None) or {}
        if metadata.get("task_status") != TaskStatus.WAITING_HUMAN.value:
            return {
                "submitted": False,
                "run_id": None,
                "message": "会话不在等待人工输入状态，跳过恢复",
            }

        from .concurrency import get_registered_executor

        executor_key = str(metadata.get("executor_key") or "agent_stream")
        executor_fn = get_registered_executor(executor_key)
        if executor_fn is None and executor_key == "agent_stream":
            from importlib import import_module

            import_module("src.api.routes.chat")
            executor_fn = get_registered_executor(executor_key)
        if executor_fn is None:
            return {
                "submitted": False,
                "run_id": None,
                "message": f"未找到执行器 {executor_key}",
            }

        from .manager import get_task_manager

        run_id, _ = await get_task_manager().submit(
            session_id,
            str(metadata.get("agent_id") or "fast"),
            "",
            str(session.user_id),
            executor_fn,
            disabled_tools=metadata.get("disabled_tools") or None,
            agent_options=metadata.get("agent_options") or None,
            disabled_skills=metadata.get("disabled_skills") or None,
            enabled_skills=metadata.get("enabled_skills") or None,
            persona_system_prompt=(
                (metadata.get("persona_snapshot") or {}).get("system_prompt")
                if isinstance(metadata.get("persona_snapshot"), dict)
                else None
            ),
            disabled_mcp_tools=metadata.get("disabled_mcp_tools") or None,
            session_name=getattr(session, "name", None),
            user_message_written=True,
            hitl_resume={
                "approval_id": approval.id,
                "resume_value": resume_value,
            },
        )
        logger.info(
            "[HITL] approval_id=%s Resume run submitted: session=%s run_id=%s",
            approval.id,
            session_id,
            run_id,
        )
        return {"submitted": True, "run_id": run_id, "message": "恢复运行已提交"}
    except Exception as e:
        logger.error(
            "[HITL] approval_id=%s Failed to submit resume run: %s",
            approval.id,
            e,
            exc_info=True,
        )
        return {"submitted": False, "run_id": None, "message": f"恢复任务失败: {e}"}
    finally:
        if token is not None:
            await _release_resume_lock(approval.id, token)
