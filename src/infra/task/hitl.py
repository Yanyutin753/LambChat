"""HITL（ask_human）interrupt 模式的恢复处理（issue #218）。

interrupt 模式下，ask_human 通过 LangGraph interrupt() 挂起并持久化
checkpoint，进程重启后状态不丢。对齐 deepagents 官方 HITL 语义：
无超时、无限期等待，用户响应（POST /human/{id}/respond）通过提交一个
携带 hitl_resume 载荷的恢复尝试继续同一逻辑运行：重新进入 fast_agent_node，
以 Command(resume=...) 从断点继续执行。

跨副本重复恢复由 Redis 分布式锁 + 审批状态原子流转双重防护。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings

from .status import TaskStatus

logger = get_logger(__name__)

HITL_RESUME_LOCK_PREFIX = "hitl:resume:"
HITL_RESUME_LOCK_TTL_SECONDS = 300
HITL_SOURCE_RELEASE_PREFIX = "hitl:source-released:"
HITL_SOURCE_RELEASE_TTL_SECONDS = 300
HITL_RESUME_ACTIVATION_PREFIX = "hitl:resume-activated:"


def hitl_interrupt_mode_enabled() -> bool:
    """当前是否启用 interrupt 模式的 ask_human。"""
    return getattr(settings, "HITL_MODE", "interrupt") == "interrupt"


def is_interrupt_approval(approval: Any) -> bool:
    """审批是否由 interrupt 模式的 ask_human 创建。"""
    metadata = getattr(approval, "metadata", None) or {}
    return metadata.get("mode") == "interrupt"


def extract_ask_human_interrupts(snapshot: Any) -> List[Dict[str, Any]]:
    """从挂起的图状态快照中提取 ask_human interrupt payload。"""
    payloads: List[Dict[str, Any]] = []
    tasks = getattr(snapshot, "tasks", None) or ()
    if isinstance(tasks, dict):
        tasks = [
            t
            for group in tasks.values()
            for t in (group if isinstance(group, (list, tuple)) else [group])
        ]
    for task in tasks:
        for intr in getattr(task, "interrupts", None) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and value.get("kind") == "ask_human":
                payload = dict(value)
                interrupt_id = getattr(intr, "id", None)
                if interrupt_id:
                    payload["interrupt_id"] = str(interrupt_id)
                payloads.append(payload)
    return payloads


async def _send_approval_sse(
    approval: Any,
    fields: List[dict],
    session_id: str,
    run_id: Optional[str],
    trace_id: Optional[str] = None,
    origin: Optional[str] = None,
) -> None:
    """挂起后发送 approval_required 事件到 SSE 流。

    必须带 trace_id 双写：不传 trace_id 时 DualEventWriter 只写 Redis，
    流过期后历史回放将永久缺失审批卡片（线上 approval_required 0 落库事故）。
    """
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
                "tool_call_id": (getattr(approval, "metadata", None) or {}).get("tool_call_id"),
                "interrupt_id": (getattr(approval, "metadata", None) or {}).get("interrupt_id"),
                "origin": origin,
            },
            run_id=run_id,
            trace_id=trace_id,
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
    trace_id: Optional[str] = None,
    resume_context: Optional[Dict[str, Any]] = None,
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

    existing_interrupt_ids: set[str] = set()
    legacy_messages: dict[str, int] = {}
    existing_sandbox_messages: set[str] = set()
    if session_id:
        try:
            for approval in await get_approval_storage().list_pending(
                session_id=session_id, limit=100
            ):
                metadata = getattr(approval, "metadata", None) or {}
                interrupt_id = metadata.get("interrupt_id")
                if metadata.get("origin") == "sandbox_confirm":
                    existing_sandbox_messages.add(str(getattr(approval, "message", "")))
                if interrupt_id:
                    existing_interrupt_ids.add(str(interrupt_id))
                else:
                    message = str(getattr(approval, "message", ""))
                    legacy_messages[message] = legacy_messages.get(message, 0) + 1
        except Exception as e:
            logger.warning("[HITL] Failed to list pending approvals: %s", e)

    created = 0
    # 沙箱确认门整批：并行工具各自中断但携带同一批消息——同 origin+message
    # 只物化一张审批卡（恢复侧 expand_sandbox_confirm_resume 负责把批复值
    # 映射回全部同批中断）
    sandbox_seen_messages: set[str] = set()
    for payload in payloads:
        message = str(payload.get("message", ""))
        fields = payload.get("fields") or []
        interrupt_id = str(payload.get("interrupt_id") or "")
        if payload.get("origin") == "sandbox_confirm":
            if message in sandbox_seen_messages or message in existing_sandbox_messages:
                continue
            sandbox_seen_messages.add(message)
        if interrupt_id and interrupt_id in existing_interrupt_ids:
            continue
        if message and legacy_messages.get(message, 0) > 0:
            legacy_messages[message] -= 1
            continue
        metadata = {
            "mode": "interrupt",
            "run_id": run_id,
            "trace_id": trace_id,
            "thread_id": session_id,
        }
        if resume_context:
            metadata["resume_context"] = resume_context
        if interrupt_id:
            metadata["interrupt_id"] = interrupt_id
        tool_call_id = payload.get("tool_call_id")
        if tool_call_id:
            metadata["tool_call_id"] = str(tool_call_id)
        origin = payload.get("origin")
        if origin:
            metadata["origin"] = str(origin)
        approval = await create_approval(
            message=message,
            approval_type="form",
            fields=fields,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            ttl=None,  # 无超时：审批不过期，响应后再 GC
        )
        if interrupt_id:
            existing_interrupt_ids.add(interrupt_id)
        created += 1
        if session_id:
            await _send_approval_sse(
                approval, fields, session_id, run_id, trace_id, origin=origin
            )
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


async def mark_hitl_source_released(run_id: str) -> None:
    """Publish that the suspended source attempt finished distributed cleanup."""
    try:
        await get_redis_client().set(
            f"{HITL_SOURCE_RELEASE_PREFIX}{run_id}",
            "1",
            ex=HITL_SOURCE_RELEASE_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning("Failed to publish HITL source release for %s: %s", run_id, e)


async def wait_for_hitl_source_release(
    run_id: str,
    user_id: str | None = None,
    timeout: float = 2.0,
) -> bool:
    """Consume the source-release fence, falling back when its heartbeat is gone."""
    redis = get_redis_client()
    key = f"{HITL_SOURCE_RELEASE_PREFIX}{run_id}"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await redis.getdel(key) is not None:
            return True
        await asyncio.sleep(0.02)

    from .heartbeat import TaskHeartbeat

    if await TaskHeartbeat().check_exists(run_id):
        return False
    if user_id:
        from .concurrency import get_concurrency_limiter

        if await get_concurrency_limiter().is_active_run(user_id, run_id):
            return False
    return True


async def activate_hitl_resume_attempt(approval_id: str, attempt_id: str) -> None:
    """Release a prepared resume job after the approval CAS succeeds."""
    try:
        await get_redis_client().set(
            f"{HITL_RESUME_ACTIVATION_PREFIX}{attempt_id}",
            approval_id,
            ex=HITL_RESUME_LOCK_TTL_SECONDS,
        )
    except Exception as e:
        # Mongo 中的 terminal approval + exact attempt_id 是持久化激活凭据；
        # Redis 仅用于快速唤醒，失败时 worker 会走一次 Mongo 点查。
        logger.warning("Failed to publish HITL resume activation for %s: %s", approval_id, e)


async def wait_for_hitl_resume_activation(
    approval_id: str,
    attempt_id: str,
    timeout: float = 2.0,
) -> bool:
    """Wait for activation, then use one Mongo point read as crash fallback."""
    redis = get_redis_client()
    key = f"{HITL_RESUME_ACTIVATION_PREFIX}{attempt_id}"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await redis.get(key) is not None:
            await redis.delete(key)
            return True
        await asyncio.sleep(0.02)

    from src.infra.storage.mongodb import get_approval_storage

    approval = await get_approval_storage().get(approval_id)
    metadata = getattr(approval, "metadata", None) or {}
    return bool(
        approval
        and getattr(approval, "status", "pending") != "pending"
        and metadata.get("resume_attempt_id") == attempt_id
    )


async def submit_hitl_resume_run(
    approval: Any,
    resume_value: Dict[str, Any],
    *,
    resume_attempt_id: str | None = None,
    prepare_only: bool = False,
) -> Dict[str, Any]:
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

    session_storage: Any = None
    resume_slot_acquired = False
    resume_user_id: str | None = None
    source_run_id = ""
    try:
        from src.infra.session.storage import SessionStorage

        session_storage = SessionStorage()
        session = await session_storage.get_by_session_id(session_id)
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

        approval_metadata = getattr(approval, "metadata", None) or {}
        source_run_id = str(approval_metadata.get("run_id") or "")
        source_trace_id = str(approval_metadata.get("trace_id") or "")
        current_run_id = str(metadata.get("current_run_id") or "")
        if not source_run_id or (current_run_id and current_run_id != source_run_id):
            return {
                "submitted": False,
                "run_id": None,
                "message": "审批所属运行已不是当前运行，跳过恢复",
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

        interrupt_id = approval_metadata.get("interrupt_id")
        resume_context = approval_metadata.get("resume_context") or {}
        sandbox_confirm_message = (
            str(approval.message)
            if approval_metadata.get("origin") == "sandbox_confirm"
            else None
        )
        command_resume = {str(interrupt_id): resume_value} if interrupt_id else resume_value
        hitl_resume = {
            "approval_id": approval.id,
            "resume_attempt_id": resume_attempt_id,
            "resume_value": command_resume,
            **(
                {"sandbox_confirm_message": sandbox_confirm_message}
                if sandbox_confirm_message
                else {}
            ),
            "goal_started_at": resume_context.get("goal_started_at"),
            "approval_resolved": {
                "id": approval.id,
                "tool_call_id": approval_metadata.get("tool_call_id"),
                "interrupt_id": interrupt_id,
                "status": "approved" if resume_value.get("approved") else "rejected",
                "success": bool(resume_value.get("approved")),
                "result": {
                    "status": "success" if resume_value.get("approved") else "rejected",
                    "message": (
                        "用户已响应" if resume_value.get("approved") else "用户拒绝了此请求"
                    ),
                    "values": resume_value.get("values") or {},
                },
                "timestamp": utc_now_iso(),
            },
        }
        manager = get_task_manager()
        common_kwargs: dict[str, Any] = {
            "disabled_tools": metadata.get("disabled_tools") or None,
            "agent_options": metadata.get("agent_options") or None,
            "disabled_skills": metadata.get("disabled_skills") or None,
            "enabled_skills": metadata.get("enabled_skills") or None,
            "persona_system_prompt": (
                (metadata.get("persona_snapshot") or {}).get("system_prompt")
                if isinstance(metadata.get("persona_snapshot"), dict)
                else None
            ),
            "disabled_mcp_tools": metadata.get("disabled_mcp_tools") or None,
            "session_name": getattr(session, "name", None),
            "user_message_written": True,
            "run_id": source_run_id,
            "trace_id": source_trace_id or None,
            "hitl_resume": hitl_resume,
            "team_id": metadata.get("team_id") or None,
            "active_goal": resume_context.get("active_goal"),
            "recommendation_input": resume_context.get("recommendation_input"),
            "auto_mode": bool(metadata.get("auto_mode", False)),
        }
        if getattr(settings, "TASK_BACKEND", "local") == "arq":
            dispatch_id = resume_attempt_id or f"hitl-resume:{approval.id}:{uuid.uuid4().hex}"
            run_id, _ = await manager.submit_arq(
                session_id=session_id,
                agent_id=str(metadata.get("agent_id") or "fast"),
                message="",
                user_id=str(session.user_id),
                executor_key=executor_key,
                dispatch_id=dispatch_id,
                initial_status=None if prepare_only else TaskStatus.PENDING,
                **common_kwargs,
            )
        else:
            await manager.wait_for_task_completion(source_run_id)
            from .concurrency import get_concurrency_limiter

            resume_user_id = str(session.user_id)
            limiter = get_concurrency_limiter()
            resume_slot_acquired = await limiter.try_acquire_run_slot(resume_user_id, source_run_id)
            if not resume_slot_acquired:
                return {
                    "submitted": False,
                    "run_id": None,
                    "message": "当前并发任务已满，请稍后重试恢复",
                }
            run_id, _ = await manager.submit(
                session_id,
                str(metadata.get("agent_id") or "fast"),
                "",
                str(session.user_id),
                executor_fn,
                **common_kwargs,
            )
        logger.info(
            "[HITL] approval_id=%s Resume run submitted: session=%s run_id=%s",
            approval.id,
            session_id,
            run_id,
        )
        result = {
            "submitted": True,
            "run_id": run_id,
            "message": "恢复运行已提交",
        }
        if resume_attempt_id:
            result["resume_attempt_id"] = resume_attempt_id
        return result
    except Exception as e:
        logger.error(
            "[HITL] approval_id=%s Failed to submit resume run: %s",
            approval.id,
            e,
            exc_info=True,
        )
        try:
            approval_metadata = getattr(approval, "metadata", None) or {}
            restore_metadata: dict[str, Any] = {"task_status": TaskStatus.WAITING_HUMAN.value}
            restore_run_id = str(approval_metadata.get("run_id") or "")
            if restore_run_id:
                source_run_id = restore_run_id
                restore_metadata["current_run_id"] = restore_run_id
            if session_storage is not None:
                await session_storage.update_metadata_only(session_id, restore_metadata)
        except Exception as restore_error:
            logger.warning(
                "[HITL] approval_id=%s Failed to restore waiting session state: %s",
                approval.id,
                restore_error,
            )
        if resume_slot_acquired and resume_user_id and source_run_id:
            try:
                from .concurrency import get_concurrency_limiter

                await get_concurrency_limiter().release(resume_user_id, source_run_id)
            except Exception as release_error:
                logger.warning(
                    "[HITL] approval_id=%s Failed to release resume slot: %s",
                    approval.id,
                    release_error,
                )
        return {"submitted": False, "run_id": None, "message": f"恢复任务失败: {e}"}
    finally:
        if token is not None:
            await _release_resume_lock(approval.id, token)


async def expand_sandbox_confirm_resume(
    graph: Any,
    config: Any,
    resume_map: Dict[str, Any],
    *,
    message: str,
) -> Dict[str, Any]:
    """沙箱确认门整批恢复扩展：把批复值映射到同批（同 origin+message）全部中断。

    并行工具各自是独立图任务、各持一个同消息中断；审批卡只有一张（物化
    去重），respond 只带一个 interrupt_id。节点恢复前调用本函数把同一批复
    值扩散到全部同批中断 id——所有任务同时拿到决定，各执行恰好一次。
    ``resume_map`` 形如 ``{interrupt_id: resume_value}``（hitl.py 构建）。
    """
    if not isinstance(resume_map, dict) or not resume_map:
        return resume_map
    value = next(iter(resume_map.values()))
    try:
        snapshot = await graph.aget_state(config)
    except Exception as e:  # noqa: BLE001 - 扩展失败回退单点映射（保守降级）
        logger.warning("[HITL] sandbox_confirm resume expand failed: %s", e)
        return resume_map
    if snapshot is None:
        return resume_map
    tasks = getattr(snapshot, "tasks", None) or ()
    if isinstance(tasks, dict):
        tasks = [
            t
            for group in tasks.values()
            for t in (group if isinstance(group, (list, tuple)) else [group])
        ]
    expanded: Dict[str, Any] = {}
    for task in tasks:
        for intr in getattr(task, "interrupts", None) or ():
            payload = getattr(intr, "value", None)
            if (
                isinstance(payload, dict)
                and payload.get("origin") == "sandbox_confirm"
                and str(payload.get("message", "")) == message
                and getattr(intr, "id", None)
            ):
                expanded[str(intr.id)] = value
    return expanded or resume_map
