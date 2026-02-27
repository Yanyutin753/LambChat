# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.infra.session.dual_writer import get_dual_writer
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.session import SessionUpdate

logger = logging.getLogger(__name__)

# Redis keys and channels
CANCEL_CHANNEL = "task:cancel"
HEARTBEAT_PREFIX = "task:heartbeat:"
INTERRUPT_PREFIX = "task:interrupt:"  # 中断信号前缀
HEARTBEAT_INTERVAL = 10  # 心跳间隔（秒）
HEARTBEAT_TIMEOUT = 60  # 心跳超时阈值（秒）

# 内存中的中断标志集合（用于快速检查）
_interrupted_runs: set = set()


class TaskInterruptedError(Exception):
    """任务被中断异常"""

    pass


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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
        self._statuses: Dict[str, TaskStatus] = {}  # run_id -> status
        self._errors: Dict[str, str] = {}  # run_id -> error
        self._run_info: Dict[str, Dict[str, str]] = {}  # run_id -> {session_id, trace_id, agent_id}
        self._lock = asyncio.Lock()
        self._storage = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._running = False
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}  # run_id -> heartbeat Task

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

        Returns:
            (run_id, trace_id) 元组
        """
        # 生成 run_id
        run_id = _generate_run_id()

        async with self._lock:
            # 设置初始状态（使用 run_id 作为 key）
            self._statuses[run_id] = TaskStatus.PENDING

            # 确保 session 记录存在
            await self._ensure_session(session_id, agent_id, user_id)

            # 更新 MongoDB session 状态（包含 current_run_id）
            await self._update_session_status(session_id, TaskStatus.PENDING, run_id=run_id)

            # 创建后台任务
            task = asyncio.create_task(
                self._run_task(
                    session_id,
                    run_id,
                    agent_id,
                    message,
                    user_id,
                    executor,
                    disabled_tools,
                    agent_options,
                )
            )
            self._tasks[run_id] = task

            # 添加完成回调
            task.add_done_callback(lambda t: self._on_task_done(run_id, t))

        logger.info(f"Task submitted: session={session_id}, run_id={run_id}, agent={agent_id}")
        # 返回 run_id，trace_id 将在 _run_task 中创建
        return run_id, ""  # trace_id 由 Presenter 生成，这里先返回空

    async def _start_heartbeat(self, run_id: str) -> None:
        """启动任务心跳"""

        async def heartbeat_loop():
            try:
                redis_client = get_redis_client()
                while True:
                    # 设置心跳，带 TTL（超时时间的 2 倍）
                    await redis_client.set(
                        f"{HEARTBEAT_PREFIX}{run_id}",
                        datetime.now().isoformat(),
                        ex=HEARTBEAT_TIMEOUT * 2,
                    )
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Heartbeat error for run_id={run_id}: {e}")

        self._heartbeat_tasks[run_id] = asyncio.create_task(heartbeat_loop())

    async def _stop_heartbeat(self, run_id: str) -> None:
        """停止任务心跳"""
        # 取消心跳任务
        if run_id in self._heartbeat_tasks:
            task = self._heartbeat_tasks.pop(run_id)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 删除 Redis 中的心跳 key
        try:
            redis_client = get_redis_client()
            await redis_client.delete(f"{HEARTBEAT_PREFIX}{run_id}")
        except Exception as e:
            logger.warning(f"Failed to delete heartbeat for run_id={run_id}: {e}")

    async def _run_task(
        self,
        session_id: str,
        run_id: str,
        agent_id: str,
        message: str,
        user_id: str,
        executor: Callable,
        disabled_tools: Optional[List[str]] = None,
        agent_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """执行任务"""
        from src.infra.writer.present import Presenter, PresenterConfig

        presenter = None
        dual_writer = None

        try:
            self._statuses[run_id] = TaskStatus.RUNNING
            await self._update_session_status(session_id, TaskStatus.RUNNING, run_id=run_id)

            # 启动心跳
            await self._start_heartbeat(run_id)

            # 创建 Presenter 并传递给 agent
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    run_id=run_id,  # 传递 run_id
                    enable_storage=True,
                )
            )

            # 设置请求上下文（供工具使用，如 ask_human）
            from src.infra.logging.context import TraceContext

            logger.info(
                f"[TaskManager] Setting TraceContext: session_id={session_id}, run_id={run_id}"
            )
            TraceContext.set_request_context(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
            )

            await presenter._ensure_trace()

            # 保存 trace_id 和 agent_id 到 run_info
            self._run_info[run_id] = {
                "session_id": session_id,
                "trace_id": presenter.trace_id,
                "agent_id": agent_id,
            }

            dual_writer = get_dual_writer()

            # 注意: 不再清除 Redis Stream，因为：
            # 1. 每个 run_id 都是唯一的，不会与之前的 events 冲突
            # 2. 清除可能导致与 SSE 连接的竞争条件
            # 3. Redis Stream 有 TTL 自动过期

            # 执行 agent，统一保存所有事件
            async for event in executor(
                session_id,
                agent_id,
                message,
                user_id,
                presenter,
                disabled_tools,
                agent_options,
            ):
                await presenter.save_event(event)

            # 完成 trace（更新 MongoDB trace 状态为 completed）
            await presenter.complete("completed")

            # 标记完成
            self._statuses[run_id] = TaskStatus.COMPLETED
            await self._update_session_status(session_id, TaskStatus.COMPLETED, run_id=run_id)
            logger.info(f"Task completed: session={session_id}, run_id={run_id}")

        except asyncio.CancelledError:
            self._statuses[run_id] = TaskStatus.FAILED
            self._errors[run_id] = "Task cancelled"
            await self._update_session_status(
                session_id, TaskStatus.FAILED, "Task cancelled", run_id=run_id
            )
            # 先刷新所有缓冲，确保已产生的事件不丢失
            if dual_writer is not None:
                try:
                    await dual_writer._flush_redis_buffer()
                    await dual_writer.flush_mongo_buffer()
                except Exception:
                    pass
            # 完成 trace（如果已创建）
            if presenter is not None:
                await presenter.complete("error")
            # 写入错误事件（包含 trace_id 以写入 MongoDB）
            trace_id = presenter.trace_id if presenter else None
            if dual_writer is not None:
                await dual_writer.write_event(
                    session_id=session_id,
                    event_type="error",
                    data={
                        "error": "Task cancelled",
                        "type": "CancelledError",
                        "run_id": run_id,
                    },
                    trace_id=trace_id,
                    run_id=run_id,
                )
            logger.warning(f"Task cancelled: session={session_id}, run_id={run_id}")
            raise

        except TaskInterruptedError as e:
            # 任务被中断
            self._statuses[run_id] = TaskStatus.FAILED
            self._errors[run_id] = str(e)
            await self._update_session_status(session_id, TaskStatus.FAILED, str(e), run_id=run_id)
            # 先刷新所有缓冲，确保已产生的事件不丢失
            if dual_writer is not None:
                try:
                    await dual_writer._flush_redis_buffer()
                    await dual_writer.flush_mongo_buffer()
                except Exception:
                    pass
            # 完成 trace
            if presenter is not None:
                await presenter.complete("error")
            # 写入错误事件（包含 trace_id 以写入 MongoDB）
            trace_id = presenter.trace_id if presenter else None
            if dual_writer is not None:
                await dual_writer.write_event(
                    session_id=session_id,
                    event_type="error",
                    data={
                        "error": str(e),
                        "type": "TaskInterruptedError",
                        "run_id": run_id,
                    },
                    trace_id=trace_id,
                    run_id=run_id,
                )
            logger.info(f"Task interrupted: session={session_id}, run_id={run_id}")
            raise

        except Exception as e:
            self._statuses[run_id] = TaskStatus.FAILED
            self._errors[run_id] = str(e)
            await self._update_session_status(session_id, TaskStatus.FAILED, str(e), run_id=run_id)
            logger.error(f"Task failed: session={session_id}, run_id={run_id}, error={e}")

            # 先刷新所有缓冲，确保已产生的事件不丢失
            if dual_writer is not None:
                try:
                    await dual_writer._flush_redis_buffer()
                    await dual_writer.flush_mongo_buffer()
                except Exception:
                    pass

            # 完成 trace（如果已创建）
            if presenter is not None:
                await presenter.complete("error")

            # 写入错误事件（包含 trace_id 以写入 MongoDB）
            trace_id = presenter.trace_id if presenter else None
            if dual_writer is not None:
                await dual_writer.write_event(
                    session_id=session_id,
                    event_type="error",
                    data={"error": str(e), "type": type(e).__name__, "run_id": run_id},
                    trace_id=trace_id,
                    run_id=run_id,
                )

        finally:
            # 无论成功、取消还是失败，都停止心跳并清除中断信号
            await self._stop_heartbeat(run_id)
            await self.clear_interrupt(run_id)

    def _on_task_done(self, run_id: str, task: asyncio.Task) -> None:
        """任务完成回调"""
        # 清理任务引用
        if run_id in self._tasks:
            del self._tasks[run_id]

    async def _update_session_status(
        self,
        session_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """更新 session 状态"""
        try:
            metadata = {"task_status": status.value}
            if error:
                metadata["task_error"] = error
            if run_id:
                metadata["current_run_id"] = run_id
            if status == TaskStatus.COMPLETED:
                metadata["completed_at"] = datetime.now().isoformat()

            await self.storage.update(
                session_id,
                SessionUpdate(metadata=metadata),
            )
        except Exception as e:
            logger.warning(f"Failed to update session status: {e}")

    async def _ensure_session(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
    ) -> None:
        """确保 session 记录存在，不存在则创建

        Raises:
            PermissionError: 如果 session 存在但不属于当前用户
        """
        from src.kernel.schemas.session import SessionCreate

        try:
            # 检查 session 是否存在
            existing = await self.storage.get_by_session_id(session_id)
            if existing:
                # 验证用户所有权
                if existing.user_id and existing.user_id != user_id:
                    logger.warning(
                        f"User {user_id} attempted to access session {session_id} owned by {existing.user_id}"
                    )
                    raise PermissionError("无权访问此会话")
                logger.debug(f"Session {session_id} already exists")
                return

            # 创建新的 session
            await self.storage.create(
                SessionCreate(
                    name="新对话",
                    metadata={"agent_id": agent_id},
                ),
                user_id=user_id,
                session_id=session_id,
            )
            logger.info(f"Created session {session_id} for user {user_id}")
        except PermissionError:
            raise  # 重新抛出权限错误
        except Exception as e:
            logger.warning(f"Failed to ensure session: {e}")

    async def get_status(self, session_id: str) -> TaskStatus:
        """获取 session 当前 run 的任务状态（向后兼容）"""
        # 尝试从 session metadata 获取 current_run_id
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if run_id and run_id in self._statuses:
                    return self._statuses[run_id]
        except Exception:
            pass
        return TaskStatus.PENDING

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        """获取特定 run 的任务状态"""
        # 先检查内存
        if run_id in self._statuses:
            return self._statuses[run_id]

        # 从 trace storage 获取状态（最可靠）
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

        # 如果 trace storage 没有，从 session metadata 获取
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                # 检查 current_run_id 是否匹配
                current_run_id = session.metadata.get("current_run_id")
                if current_run_id == run_id:
                    task_status = session.metadata.get("task_status")
                    if task_status:
                        return TaskStatus(task_status)
        except Exception as e:
            logger.warning(f"Failed to get run status from session storage: {e}")

        return TaskStatus.PENDING

    async def get_error(self, session_id: str) -> Optional[str]:
        """获取任务错误信息（向后兼容）"""
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if run_id and run_id in self._errors:
                    return self._errors[run_id]
        except Exception:
            pass
        return None

    async def get_run_error(self, run_id: str) -> Optional[str]:
        """获取特定 run 的错误信息"""
        # 先检查内存
        if run_id in self._errors:
            return self._errors[run_id]

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

        # 如果 trace storage 没有，从 session metadata 获取
        run_info = self._run_info.get(run_id)
        if run_info:
            session_id = run_info.get("session_id")
            if session_id:
                try:
                    session = await self.storage.get_by_session_id(session_id)
                    if session and session.metadata:
                        current_run_id = session.metadata.get("current_run_id")
                        if current_run_id == run_id:
                            return session.metadata.get("task_error")
                except Exception as e:
                    logger.warning(f"Failed to get run error from session storage: {e}")

        return None

    def get_trace_id(self, run_id: str) -> Optional[str]:
        """获取 run 对应的 trace_id"""
        info = self._run_info.get(run_id)
        return info.get("trace_id") if info else None

    async def cancel(self, session_id: str) -> bool:
        """取消任务（支持分布式）"""
        # 获取 current_run_id
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if run_id:
                    return await self.cancel_run(run_id)
        except Exception:
            pass
        return False

    async def cancel_run(self, run_id: str, publish: bool = True) -> bool:
        """
        取消特定 run 的任务（支持分布式）

        Args:
            run_id: 运行 ID
            publish: 是否通过 Redis pub/sub 广播取消信号（用于分布式场景）

        Returns:
            是否成功取消
        """
        cancelled_locally = False

        # 1. 立即设置内存中的中断标志（最快）
        global _interrupted_runs
        _interrupted_runs.add(run_id)
        logger.info(f"Memory interrupt flag set for run_id={run_id}")

        # 2. 设置 Redis 中断信号（用于分布式场景）
        try:
            redis_client = get_redis_client()
            await redis_client.set(
                f"{INTERRUPT_PREFIX}{run_id}",
                datetime.now().isoformat(),
                ex=300,  # 5 分钟过期
            )
            logger.info(f"Redis interrupt signal set for run_id={run_id}")
        except Exception as e:
            logger.warning(f"Failed to set interrupt signal: {e}")

        # 3. 调用 agent.close(run_id) 取消 graph 执行
        run_info = self._run_info.get(run_id)
        if run_info:
            agent_id = run_info.get("agent_id")
            if agent_id:
                try:
                    from src.agents.core.base import AgentFactory

                    agent = await AgentFactory.get(agent_id)
                    await agent.close(run_id)
                    logger.info(f"Agent.close({run_id}) called for agent={agent_id}")
                except Exception as e:
                    logger.warning(f"Failed to call agent.close: {e}")

        async with self._lock:
            if run_id in self._tasks:
                task = self._tasks[run_id]
                if not task.done():
                    task.cancel()
                    cancelled_locally = True
                    logger.info(f"Task cancelled locally: run_id={run_id}")

        # 如果本地没有这个任务，或者需要广播给其他实例
        if publish:
            try:
                redis_client = get_redis_client()
                agent_id = run_info.get("agent_id") if run_info else None
                await redis_client.publish(
                    CANCEL_CHANNEL,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "timestamp": datetime.now().isoformat(),
                        }
                    ),
                )
                logger.info(f"Published cancel signal for run_id={run_id}, agent_id={agent_id}")
            except Exception as e:
                logger.warning(f"Failed to publish cancel signal: {e}")

        return cancelled_locally

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
        global _interrupted_runs

        # 1. 首先检查内存标志（最快，无 IO）
        if run_id in _interrupted_runs:
            logger.info(f"Memory interrupt detected for run_id={run_id}")
            raise TaskInterruptedError(f"Task interrupted: run_id={run_id}")

        # 2. 检查 Redis（分布式场景）
        try:
            redis_client = get_redis_client()
            interrupted = await redis_client.get(f"{INTERRUPT_PREFIX}{run_id}")
            if interrupted:
                logger.info(f"Redis interrupt detected for run_id={run_id}")
                raise TaskInterruptedError(f"Task interrupted: run_id={run_id}")
        except TaskInterruptedError:
            raise
        except Exception as e:
            logger.warning(f"Failed to check Redis interrupt signal: {e}")

    @staticmethod
    async def clear_interrupt(run_id: str) -> None:
        """
        清除中断信号

        Args:
            run_id: 运行 ID
        """
        global _interrupted_runs

        # 1. 清除内存标志
        _interrupted_runs.discard(run_id)

        # 2. 清除 Redis 标志
        try:
            redis_client = get_redis_client()
            await redis_client.delete(f"{INTERRUPT_PREFIX}{run_id}")
        except Exception as e:
            logger.warning(f"Failed to clear interrupt signal: {e}")

    async def start_pubsub_listener(self) -> None:
        """
        启动 Redis pub/sub 监听器，用于接收分布式取消信号

        应在应用启动时调用
        """
        if self._running:
            return

        self._running = True

        async def listener():
            try:
                redis_client = get_redis_client()
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(CANCEL_CHANNEL)
                logger.info(f"Started listening on Redis channel: {CANCEL_CHANNEL}")

                async for message in pubsub.listen():
                    if not self._running:
                        break

                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            run_id = data.get("run_id")
                            agent_id = data.get("agent_id")
                            if run_id:
                                logger.info(
                                    f"Received cancel signal for run_id={run_id}, agent_id={agent_id}"
                                )

                                # 调用 agent.close(run_id) 取消 graph
                                if agent_id:
                                    try:
                                        from src.agents.core.base import AgentFactory

                                        agent = await AgentFactory.get(agent_id)
                                        await agent.close(run_id)
                                        logger.info(
                                            f"Agent.close({run_id}) called via pub/sub for agent={agent_id}"
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to call agent.close via pub/sub: {e}"
                                        )

                                # 尝试本地取消 asyncio Task
                                async with self._lock:
                                    if run_id in self._tasks:
                                        task = self._tasks[run_id]
                                        if not task.done():
                                            task.cancel()
                                            logger.info(
                                                f"Task cancelled via pub/sub: run_id={run_id}"
                                            )
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid cancel message format: {message['data']}")
                        except Exception as e:
                            logger.error(f"Error processing cancel message: {e}")

            except asyncio.CancelledError:
                logger.info("Pub/sub listener cancelled")
            except Exception as e:
                logger.error(f"Pub/sub listener error: {e}")
            finally:
                self._running = False
                logger.info("Pub/sub listener stopped")

        self._pubsub_task = asyncio.create_task(listener())

    async def stop_pubsub_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        self._running = False
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        logger.info("Pub/sub listener stopped")

    async def cleanup_stale_tasks(self) -> None:
        """
        清理残留的运行中任务（服务启动时调用）

        只清理心跳超时的任务，说明任务所在的实例已经下线或卡死。
        心跳还在的任务说明其他实例正在运行，不应清理。
        """
        try:
            redis_client = get_redis_client()

            # 查找所有 task_status=running 的 session
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.RUNNING.value}
            )
            running_sessions = await cursor.to_list(length=1000)

            cleaned_count = 0
            for session in running_sessions:
                session_id = session.get("_id")
                run_id = session.get("metadata", {}).get("current_run_id")

                if not run_id:
                    continue

                # 检查心跳是否存在
                heartbeat_key = f"{HEARTBEAT_PREFIX}{run_id}"
                heartbeat = await redis_client.get(heartbeat_key)

                if heartbeat:
                    # 心跳存在，说明其他实例正在运行此任务，跳过
                    logger.debug(
                        f"Task still running on another instance: session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳不存在，说明任务所在的实例已下线，清理此任务
                logger.warning(
                    f"Cleaning up stale task (no heartbeat): session={session_id}, run_id={run_id}"
                )
                await self._update_session_status(
                    session_id,
                    TaskStatus.FAILED,
                    "Task interrupted (instance unavailable)",
                    run_id=run_id,
                )
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale tasks without heartbeat")
        except Exception as e:
            logger.error(f"Failed to cleanup stale tasks: {e}")

    async def shutdown(self) -> None:
        """
        服务关闭时调用

        标记所有运行中的任务为失败，清理心跳
        """
        async with self._lock:
            # 停止所有心跳任务
            for run_id in list(self._heartbeat_tasks.keys()):
                await self._stop_heartbeat(run_id)

            for run_id, task in self._tasks.items():
                if not task.done():
                    task.cancel()
                    self._statuses[run_id] = TaskStatus.FAILED
                    self._errors[run_id] = "Server shutdown"

                    # 获取 session_id 并更新状态
                    info = self._run_info.get(run_id)
                    if info:
                        session_id = info.get("session_id")
                        if session_id:
                            await self._update_session_status(
                                session_id,
                                TaskStatus.FAILED,
                                "Server shutdown",
                                run_id=run_id,
                            )
                    logger.warning(f"Task marked as failed (shutdown): run_id={run_id}")

            self._tasks.clear()
            self._heartbeat_tasks.clear()
            logger.info("Task manager shutdown complete")


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
