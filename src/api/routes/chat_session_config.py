"""会话配置后台写入调度：fire-and-forget、同会话串行、池满降级内联。

抽自 chat.py（1000 行门禁）；_update_session_config 仍留在 chat.py，
由调度器在执行期延迟导入，避免循环依赖。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.logging import get_logger
from src.kernel.schemas.agent import AgentRequest

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

_SESSION_CONFIG_MAX_TASKS = 64
_session_config_tasks = BestEffortTaskLimiter(
    "session config update", max_tasks=_SESSION_CONFIG_MAX_TASKS
)
# 同一会话的后台写串行链：防止背靠背请求的两个后台写并发在飞导致
# 旧写后落覆盖新写（metadata.current_run_id 回退到旧 run）
_session_config_chains: dict[str, "asyncio.Task[None]"] = {}


async def drain_session_config_tasks() -> None:
    """进程退出前等未完成的会话配置写入落库，避免丢数据。"""
    await _session_config_tasks.drain()


async def _schedule_session_config_update(
    session_id: str,
    run_id: str,
    agent_id: str,
    request: AgentRequest,
    language: str,
    trace_id: str | None = None,
    prompt_state: dict | None = None,
) -> None:
    """会话配置写入调度：默认 fire-and-forget（同会话串行），任务池满时降级为内联等待（绝不静默丢写）。"""
    previous_task = _session_config_chains.get(session_id)

    async def _chained_write() -> None:
        if previous_task is not None:
            try:
                await previous_task
            except (Exception, asyncio.CancelledError):
                # 前一个写失败不影响本次；limiter 本身也会记录异常日志
                pass
        from src.api.routes.chat import _update_session_config

        await _update_session_config(
            session_id,
            run_id,
            agent_id,
            request,
            language,
            trace_id=trace_id,
            prompt_state=prompt_state,
        )

    # 检查与 create_task 之间无 await，单事件循环下原子；满时内联等待保证写入
    # （内联路径同样先等前一个写完成，保持同会话串行）
    if _session_config_tasks.active_count >= _SESSION_CONFIG_MAX_TASKS:
        await _chained_write()
        return
    task = _session_config_tasks.create_task(_chained_write())
    _session_config_chains[session_id] = task

    def _cleanup_chain(done_task: "asyncio.Task[None]") -> None:
        if _session_config_chains.get(session_id) is done_task:
            _session_config_chains.pop(session_id, None)

    task.add_done_callback(_cleanup_chain)
