"""Presenter 主代理正文追踪契约。

message:chunk 有两条入口（executor 循环的 save_event、AgentEventProcessor
缓冲 flush 的 emit 直连），必须都汇聚标记 produced_main_text——executor 的
零正文守卫依赖它判定 run 是否真的交付过答案（2026-09-05 生产事故：直发
路径绕过 executor 循环，导致交付过内容的 run 被误判失败）。
"""

from __future__ import annotations

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


async def test_emit_main_text_chunk_marks_produced() -> None:
    presenter = _presenter()

    assert presenter.produced_main_text is False
    await presenter.emit({"event": "message:chunk", "data": {"content": "最终回答"}})

    assert presenter.produced_main_text is True


async def test_save_event_main_text_chunk_marks_produced() -> None:
    presenter = _presenter()

    await presenter.save_event({"event": "message:chunk", "data": {"content": "最终回答"}})

    assert presenter.produced_main_text is True


async def test_subagent_chunk_does_not_mark() -> None:
    presenter = _presenter()

    await presenter.emit({"event": "message:chunk", "data": {"content": "子代理输出", "depth": 1}})

    assert presenter.produced_main_text is False


async def test_blank_chunk_does_not_mark() -> None:
    presenter = _presenter()

    await presenter.emit({"event": "message:chunk", "data": {"content": "   "}})

    assert presenter.produced_main_text is False


async def test_other_event_types_do_not_mark() -> None:
    presenter = _presenter()

    await presenter.emit({"event": "thinking", "data": {"content": "长篇思考"}})
    await presenter.emit({"event": "tool:start", "data": {"tool": "web_search"}})

    assert presenter.produced_main_text is False
