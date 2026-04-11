# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage

from .cancellation import TaskCancellation
from .exceptions import TaskInterruptedError
from .executor import TaskExecutor
from .heartbeat import TaskHeartbeat
from .pubsub import TaskPubSub
from .status import TaskStatus

# 重导出供外部使用
__all__ = [
    "BackgroundTaskManager",
    "TaskStatus",
    "TaskInterruptedError",
    "TaskCancellation",
]

logger = get_logger(__name__)


def _generate_run_id() -> str:
    """生成运行 ID"""
    return f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


class BackgroundTaskManager:
    """
    后台任务管理器

    管理后台任务的生命周期：
    - 提交任务后立即返回 session_id 和 run_id
    - 任务在后台异步执行
    - 支持按 run_id 查询任务状态
    - 支持分布式取消任务（通过 Redis pub/sub）
    - 服务关闭时标记未完成任务为失败
    """

    def __init__(self):
        # 使用 run_id 作为 key 管理状态
        self._tasks: Dict[str, asyncio.Task] = {}  # run_id -> Task
        self._run_info: Dict[
            str, Dict[str, Any]
        ] = {}  # run_id -> {session_id, trace_id, agent_id, user_id, ...}
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}  # run_id -> task context (queued tasks)
        self._lock = asyncio.Lock()
        self._storage = None
        self._heartbeat = TaskHeartbeat()
        self._cancellation = TaskCancellation(self._lock, self._tasks)
        self._pubsub = TaskPubSub(self._lock, self._tasks)
        self._executor = None  # Lazy init in submit

    @property
    def storage(self) -> SessionStorage:
        """延迟加载存储"""
        if self._storage is None:
            self._storage = SessionStorage()
        return self._storage

    async def submit(
        self,
        session_id: str,
        agent_id: str,
        message: str,
        user_id: str,
        executor: Callable[[str, str, str, str], Any],
        disabled_tools: Optional[List[str]] = None,
        agent_options: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        disabled_skills: Optional[List[str]] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """
        提交后台任务

        Args:
            session_id: 会话 ID
            agent_id: Agent ID
            message: 用户消息
            user_id: 用户 ID
            executor: 执行函数 (session_id, agent_id, message, user_id) -> AsyncGenerator
            disabled_tools: 用户禁用的工具列表（可选）
            agent_options: Agent 选项（可选，如 enable_thinking）
            attachments: 文件附件列表（可选）

        Returns:
            (run_id, trace_id) 元组
        """
        # 确保 executor 已初始化
        if self._executor is None:
            self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)

        # 生成 run_id
        run_id = run_id or _generate_run_id()

        async with self._lock:
            # 确保 session 记录存在
            await self._executor.ensure_session(
                session_id, agent_id, user_id, project_id=project_id
            )

            # 更新 MongoDB session 状态（包含 current_run_id）
            await self._executor._update_session_status(
                session_id, TaskStatus.PENDING, run_id=run_id
            )

            # 创建后台任务
            task = asyncio.create_task(
                self._executor.run_task(
                    session_id,
                    run_id,
                    agent_id,
                    message,
                    user_id,
                    executor,
                    disabled_tools,
                    agent_options,
                    attachments,
                    disabled_skills=disabled_skills,
                    disabled_mcp_tools=disabled_mcp_tools,
                )
            )
            self._tasks[run_id] = task

            # 添加完成回调
            task.add_done_callback(lambda t: self._on_task_done(run_id, t))

        logger.info(f"Task submitted: session={session_id}, run_id={run_id}, agent={agent_id}")
        # 返回 run_id，trace_id 将在 _run_task 中创建
        return run_id, ""  # trace_id 由 Presenter 生成，这里先返回空

    def _on_task_done(self, run_id: str, task: asyncio.Task) -> None:
        """任务完成回调"""
        # 清理任务引用
        if run_id in self._tasks:
            del self._tasks[run_id]
        # 清理运行信息，防止内存泄漏
        run_info = self._run_info.pop(run_id, None)
        # 清理待处理任务上下文（如果存在）
        self._pending_tasks.pop(run_id, None)
        # 释放并发槽位
        user_id = run_info.get("user_id") if run_info else None
        if user_id:
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.ensure_future(self._release_concurrency(user_id, run_id))
            )

    def pop_pending_task(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Pop and return a pending task context (used by concurrency limiter to dispatch queued tasks)."""
        return self._pending_tasks.pop(run_id, None)

    async def _release_concurrency(self, user_id: str, run_id: str) -> None:
        """Release a concurrency slot for the user."""
        try:
            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            await limiter.release(user_id, run_id)
        except Exception as e:
            logger.warning(f"Failed to release concurrency slot: {e}")

    async def get_status(self, session_id: str) -> TaskStatus:
        """获取 session 当前 run 的任务状态（向后兼容）

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning(f"Failed to get status from session storage: {e}")
        return TaskStatus.PENDING

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        """获取特定 run 的任务状态

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        # 优先从 session metadata 获取（最权威，取消/失败时会更新）
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning(f"Failed to get run status from session storage: {e}")

        # 回退到 trace storage 获取状态
        try:
            trace_storage = get_trace_storage()
            # 查询该 run_id 的 trace
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"status": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace_status = traces[0].get("status")
                if trace_status:
                    # 映射 trace status 到 TaskStatus
                    status_map = {
                        "running": TaskStatus.RUNNING,
                        "completed": TaskStatus.COMPLETED,
                        "error": TaskStatus.FAILED,
                    }
                    return status_map.get(trace_status, TaskStatus.PENDING)
        except Exception as e:
            logger.warning(f"Failed to get run status from trace storage: {e}")

        return TaskStatus.PENDING

    async def get_error(self, session_id: str) -> Optional[str]:
        """获取任务错误信息（向后兼容）

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                return session.metadata.get("task_error")
        except Exception as e:
            logger.warning(f"Failed to get error from session storage: {e}")
        return None

    async def get_run_error(self, run_id: str) -> Optional[str]:
        """获取特定 run 的错误信息

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        # 从 trace storage 获取错误信息
        try:
            trace_storage = get_trace_storage()
            # 查询该 run_id 的 trace
            cursor = (
                trace_storage.collection.find(
                    {"run_id": run_id}, {"metadata": 1, "events": 1, "_id": 0}
                )
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace = traces[0]
                # 先检查 metadata 中的错误信息
                metadata = trace.get("metadata", {})
                if metadata.get("error"):
                    return metadata.get("error")
                # 再检查 events 中是否有 error 事件
                events = trace.get("events", [])
                for event in reversed(events):  # 从后往前找最新的 error
                    if event.get("event_type") == "error":
                        data = event.get("data", {})
                        return data.get("error")
        except Exception as e:
            logger.warning(f"Failed to get run error from trace storage: {e}")

        # 如果 trace storage 没有，尝试从 session metadata 获取
        run_info = self._run_info.get(run_id)
        if run_info:
            session_id = run_info.get("session_id")
            if session_id:
                try:
                    session = await self.storage.get_by_session_id(session_id)
                    if session and session.metadata:
                        return session.metadata.get("task_error")
                except Exception as e:
                    logger.warning(f"Failed to get run error from session storage: {e}")

        return None

    def get_trace_id(self, run_id: str) -> Optional[str]:
        """获取 run 对应的 trace_id"""
        info = self._run_info.get(run_id)
        return info.get("trace_id") if info else None

    async def cancel(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        取消任务（支持分布式）

        Args:
            session_id: 会话 ID
            user_id: 取消任务的用户 ID

        Returns:
            {
                "success": bool,  # 中断信号是否成功设置
                "cancelled_locally": bool,  # 是否在本地实例取消
                "run_id": str | None,  # 被取消的 run_id
                "message": str  # 状态信息
            }
        """
        # 获取 current_run_id
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if run_id:
                    return await self.cancel_run(run_id, user_id=user_id)
                else:
                    return {
                        "success": False,
                        "cancelled_locally": False,
                        "run_id": None,
                        "message": "没有正在运行的任务",
                    }
        except Exception as e:
            logger.warning(f"Failed to cancel session {session_id}: {e}")
        return {
            "success": False,
            "cancelled_locally": False,
            "run_id": None,
            "message": "取消失败",
        }

    async def cancel_run(
        self, run_id: str, publish: bool = True, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        取消特定 run 的任务（支持分布式）

        Args:
            run_id: 运行 ID
            publish: 是否通过 Redis pub/sub 广播取消信号（用于分布式场景）
            user_id: 取消任务的用户 ID

        Returns:
            {
                "success": bool,  # 中断信号是否成功设置
                "cancelled_locally": bool,  # 是否在本地实例取消
                "run_id": str,  # 被取消的 run_id
                "message": str  # 状态信息
            }
        """
        run_info = self._run_info.get(run_id)

        result = await self._cancellation.cancel_run(
            run_id=run_id,
            publish=publish,
            user_id=user_id,
            run_info=run_info,
        )

        # 更新 session 状态为 cancelled
        if result["success"] and run_info and self._executor is not None:
            session_id = run_info.get("session_id")
            if session_id:
                await self._executor._update_session_status(
                    session_id, TaskStatus.FAILED, "Task cancelled", run_id=run_id
                )

        return result

    @staticmethod
    def check_interrupt_fast(run_id: str) -> bool:
        """
        快速检查中断信号（仅内存，无 IO）

        用于高频调用的场景（如主循环），避免 Redis IO 开销。
        对于分布式场景，依赖 Redis pub/sub 将信号同步到本地内存。

        Args:
            run_id: 运行 ID

        Returns:
            True 如果任务被中断
        """
        return TaskCancellation.check_interrupt_fast(run_id)

    @staticmethod
    async def check_interrupt(run_id: str) -> None:
        """
        检查是否有中断信号，如果有则抛出 TaskInterruptedError

        供 agent 在执行过程中调用，实现优雅中断。
        优先检查内存标志（最快），其次检查 Redis（分布式场景）。

        Args:
            run_id: 运行 ID

        Raises:
            TaskInterruptedError: 如果任务被中断
        """
        await TaskCancellation.check_interrupt(run_id)

    @staticmethod
    async def clear_interrupt(run_id: str) -> None:
        """
        清除中断信号

        Args:
            run_id: 运行 ID
        """
        await TaskCancellation.clear_interrupt(run_id)

    async def start_pubsub_listener(self) -> None:
        """
        启动 Redis pub/sub 监听器，用于接收分布式取消信号

        应在应用启动时调用
        """
        await self._pubsub.start_listener()

    async def stop_pubsub_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        await self._pubsub.stop_listener()

    async def cleanup_stale_tasks(self) -> None:
        """
        清理残留的运行中任务（服务启动时调用）

        清理两类任务：
        1. task_status=RUNNING：心跳超时的任务（executor 崩溃）
        2. task_status=PENDING + 在 active set 中：心跳超时的任务
           （任务被分派后 executor 崩溃，但状态未更新为 RUNNING）
        心跳还在的任务说明其他实例正在运行，不应清理。
        """
        from .concurrency import get_concurrency_limiter

        limiter = get_concurrency_limiter()
        redis = limiter.redis

        try:
            # 清理 RUNNING 状态且心跳超时的任务
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.RUNNING.value}
            )
            running_sessions = await cursor.to_list(length=1000)

            cleaned_count = 0
            for session in running_sessions:
                session_id = session.get("_id")
                run_id = session.get("metadata", {}).get("current_run_id")
                user_id = session.get("user_id")

                if not run_id:
                    continue

                # 检查心跳是否存在
                heartbeat_exists = await self._heartbeat.check_exists(run_id)

                if heartbeat_exists:
                    logger.debug(
                        f"Task still running on another instance: session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳不存在，清理
                logger.warning(
                    f"Cleaning up stale RUNNING task (no heartbeat): session={session_id}, run_id={run_id}"
                )
                if self._executor is None:
                    self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)
                await self._executor._update_session_status(
                    session_id,
                    TaskStatus.FAILED,
                    "Task interrupted (instance unavailable)",
                    run_id=run_id,
                )
                if user_id:
                    try:
                        await limiter.release(user_id, run_id)
                    except Exception as e:
                        logger.warning(f"Failed to release concurrency slot for stale task: {e}")
                cleaned_count += 1

            # 清理 PENDING 状态但心跳超时的任务（被分派后 executor 崩溃，状态未更新）
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.PENDING.value}
            )
            pending_sessions = await cursor.to_list(length=1000)

            for session in pending_sessions:
                session_id = str(session.get("_id"))
                run_id = session.get("metadata", {}).get("current_run_id")
                user_id = session.get("user_id")

                if not run_id or not user_id:
                    continue

                # 检查是否在 active set 中
                active_key = f"chat:active:{user_id}"
                in_active = await redis.zscore(active_key, run_id) is not None
                if not in_active:
                    # 不在 active set 中，由 _replay_pending_queued_tasks 处理
                    continue

                # 在 active set 中，检查心跳是否超时
                heartbeat_exists = await self._heartbeat.check_exists(run_id)
                if heartbeat_exists:
                    # 有心跳，说明有 worker 在处理
                    logger.debug(
                        f"Pending task still in active set (running elsewhere): session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳超时，清理
                logger.warning(
                    f"Cleaning up stale PENDING task (in active set, no heartbeat): "
                    f"session={session_id}, run_id={run_id}"
                )
                if self._executor is None:
                    self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)
                await self._executor._update_session_status(
                    session_id,
                    TaskStatus.FAILED,
                    "Task interrupted (instance unavailable)",
                    run_id=run_id,
                )
                try:
                    await limiter.release(user_id, run_id)
                except Exception as e:
                    logger.warning(f"Failed to release concurrency slot for stale task: {e}")
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale tasks without heartbeat")

            # 重放 PENDING session 的排队任务（服务器重启后恢复）
            await self._replay_pending_queued_tasks()

            # 清理过期的排队条目
            await self._cleanup_stale_queues()
        except Exception as e:
            logger.error(f"Failed to cleanup stale tasks: {e}")

    async def _cleanup_stale_queues(self) -> None:
        """清理过期的排队条目（超过 QUEUE_TIMEOUT 的）"""
        try:
            from .concurrency import QUEUE_TIMEOUT, get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            import time

            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="chat:queue:*", count=100)
                for key in keys:
                    entries = await redis.lrange(key, 0, -1)
                    valid = []
                    expired = 0
                    for entry in entries:
                        data = json.loads(entry)
                        if time.time() - data.get("queued_at", 0) > QUEUE_TIMEOUT:
                            expired += 1
                        else:
                            valid.append(entry)
                    if expired:
                        await redis.delete(key)
                        if valid:
                            await redis.rpush(key, *valid)
                        logger.info(f"Cleaned {expired} expired queue entries from {key}")
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Failed to cleanup stale queues: {e}")

    async def _replay_pending_queued_tasks(self) -> None:
        """
        服务器重启后重放 PENDING 状态的排队任务。

        排队任务在 Redis 队列中持久化，但进程内存（_run_info 等）在重启后丢失。
        对每个 PENDING session：
        - 队列条目仍在 → 触发 release() 释放并发槽，触发 _try_dequeue_next 重新分派
        - 队列条目已消失 + 无心跳 → 任务被遗弃，标记为 FAILED
        """
        try:
            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            # 查找所有 task_status=pending 的 session
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.PENDING.value}
            )
            pending_sessions = await cursor.to_list(length=1000)

            replayed = 0
            abandoned = 0

            for session in pending_sessions:
                session_id = str(session.get("_id"))
                run_id = session.get("metadata", {}).get("current_run_id")
                user_id = session.get("user_id")

                if not run_id or not user_id:
                    continue

                # 检查 Redis 队列中是否还有这个任务的条目
                queue_key = f"chat:queue:{user_id}"
                entries = await redis.lrange(queue_key, 0, -1)
                queue_entry = None
                for entry in entries:
                    data = json.loads(entry)
                    if data.get("run_id") == run_id:
                        queue_entry = data
                        break

                if queue_entry:
                    # 队列条目存在，触发 release 释放并发槽 → 会触发 _try_dequeue_next
                    logger.info(
                        f"Replaying queued task on startup: session={session_id}, run_id={run_id}"
                    )
                    try:
                        await limiter.release(user_id, run_id)
                        replayed += 1
                    except Exception as e:
                        logger.warning(f"Failed to replay queued task {run_id}: {e}")
                else:
                    # 队列条目已消失：任务已被分派或被超时清理
                    # - in_active：cleanup_stale_tasks 已处理（心跳超时后标记 FAILED）
                    # - 有心跳：其他 worker 在处理，不动
                    # - 无心跳且不在 active：任务被遗弃，标记 FAILED
                    active_key = f"chat:active:{user_id}"
                    in_active = await redis.zscore(active_key, run_id) is not None
                    heartbeat_exists = await self._heartbeat.check_exists(run_id)

                    if in_active or heartbeat_exists:
                        # 任务正在被处理（in_active 或有心跳），cleanup_stale_tasks 会处理超时情况
                        logger.debug(
                            f"Pending task still active or running elsewhere: "
                            f"session={session_id}, run_id={run_id}"
                        )
                    else:
                        # 既不在 active set 也没有心跳 → 任务被遗弃
                        logger.warning(
                            f"Abandoned queued task (no queue entry, no active, no heartbeat): "
                            f"session={session_id}, run_id={run_id}"
                        )
                        if self._executor is None:
                            self._executor = TaskExecutor(
                                self.storage, self._run_info, self._heartbeat
                            )
                        await self._executor._update_session_status(
                            session_id,
                            TaskStatus.FAILED,
                            "Task abandoned (server restarted while queued)",
                            run_id=run_id,
                        )
                        abandoned += 1

            if replayed > 0:
                logger.info(f"Replayed {replayed} queued tasks on startup")
            if abandoned > 0:
                logger.warning(f"Marked {abandoned} abandoned queued tasks as FAILED")
        except Exception as e:
            logger.error(f"Failed to replay pending queued tasks: {e}")

    async def shutdown(self) -> None:
        """
        服务关闭时调用

        标记所有运行中的任务为失败，清理心跳
        """
        async with self._lock:
            # 停止所有心跳任务
            await self._heartbeat.stop_all()

            # 初始化 executor 如果还未初始化
            if self._executor is None:
                self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)

            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            for run_id, task in self._tasks.items():
                if not task.done():
                    task.cancel()

                    # 获取 session_id 并更新状态
                    info = self._run_info.get(run_id)
                    if info:
                        session_id = info.get("session_id")
                        if session_id:
                            await self._executor._update_session_status(
                                session_id,
                                TaskStatus.FAILED,
                                "Server shutdown",
                                run_id=run_id,
                            )
                        # 释放 Redis 并发槽位
                        user_id = info.get("user_id")
                        if user_id:
                            try:
                                await limiter.release(user_id, run_id)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to release concurrency slot on shutdown: {e}"
                                )
                    logger.warning(f"Task marked as failed (shutdown): run_id={run_id}")

            self._tasks.clear()
            self._run_info.clear()
            self._pending_tasks.clear()
            logger.info("Task manager shutdown complete")


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
