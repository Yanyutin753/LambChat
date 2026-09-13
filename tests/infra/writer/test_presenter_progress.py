"""Presenter 进展时间戳契约（stall watchdog 的外部进展探针）。

事件有两条入口（executor 循环、AgentEventProcessor 缓冲 flush 的 emit 直连），
都汇聚到 save_event——看门狗据此判定「流仍在推进」。直连事件也必须刷新
last_progress_monotonic，否则深跑会被 stall watchdog 误杀
（2026-09-12/13 生产事故：生成器静默 >1h，直连事件持续产出，run 被判死）。
"""

from __future__ import annotations

import asyncio
import time

from src.infra.writer.present import Presenter, PresenterConfig


def _presenter() -> Presenter:
    # enable_storage=False：只验证追踪契约本身，不触达 dual writer
    return Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="fast",
            run_id="run-1",
            enable_storage=False,
        )
    )


async def test_last_progress_starts_at_init() -> None:
    presenter = _presenter()

    assert presenter.last_progress_monotonic() <= time.monotonic()


async def test_save_event_refreshes_last_progress() -> None:
    presenter = _presenter()
    before = presenter.last_progress_monotonic()
    await asyncio.sleep(0.01)

    await presenter.save_event({"event": "thinking", "data": {"content": "长篇思考"}})

    assert presenter.last_progress_monotonic() > before


async def test_emit_direct_path_refreshes_last_progress() -> None:
    presenter = _presenter()
    before = presenter.last_progress_monotonic()
    await asyncio.sleep(0.01)

    await presenter.emit(
        {"event": "message:chunk", "data": {"content": "直连路径输出", "depth": 1}}
    )

    assert presenter.last_progress_monotonic() > before


async def test_storage_disabled_still_refreshes_last_progress() -> None:
    """enable_storage=False 的 save_event 提前返回，也必须先刷新进展时间戳。"""
    presenter = _presenter()
    before = presenter.last_progress_monotonic()
    await asyncio.sleep(0.01)

    await presenter.save_event({"event": "tool:start", "data": {"tool": "web_search"}})

    assert presenter.last_progress_monotonic() > before
