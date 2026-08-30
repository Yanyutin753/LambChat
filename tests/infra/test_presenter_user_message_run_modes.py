"""user:message 事件应携带 run_modes，供前端历史还原运行模式 chip。"""

from __future__ import annotations

from typing import Any

import pytest

from src.infra.writer.present import Presenter, PresenterConfig
from src.infra.writer.presenter_events import derive_user_message_run_modes


def _presenter() -> Presenter:
    return Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="search",
            user_id="owner-1",
            run_id="run-1",
            trace_id="trace-1",
        )
    )


def test_present_user_message_includes_run_modes_when_present() -> None:
    event = _presenter().present_user_message(
        "ok", run_modes=["auto", "goal"]
    )

    data: dict[str, Any] = event["data"]
    assert data["run_modes"] == ["auto", "goal"]


def test_present_user_message_omits_run_modes_when_empty() -> None:
    event = _presenter().present_user_message("ok")

    assert "run_modes" not in event["data"]


@pytest.mark.asyncio
async def test_emit_user_message_persists_run_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = _presenter()
    saved: list[dict[str, Any]] = []

    async def _save_event(event: dict[str, Any], **kwargs: Any) -> None:
        saved.append(event)

    monkeypatch.setattr(presenter, "save_event", _save_event)

    await presenter.emit_user_message("ok", run_modes=["auto"])

    assert saved[0]["data"]["run_modes"] == ["auto"]


def test_derive_user_message_run_modes_reflects_auto_and_goal() -> None:
    assert derive_user_message_run_modes(auto_mode=True, goal=None) == ["auto"]
    assert derive_user_message_run_modes(
        auto_mode=False, goal={"objective": "win"}
    ) == ["goal"]
    assert derive_user_message_run_modes(
        auto_mode=True, goal={"objective": "win"}
    ) == ["auto", "goal"]
    assert derive_user_message_run_modes(auto_mode=False, goal=None) == []
