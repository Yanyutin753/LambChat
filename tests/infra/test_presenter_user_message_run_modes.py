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
    event = _presenter().present_user_message("ok", run_modes=["auto", "goal"])

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
    assert derive_user_message_run_modes(auto_mode=False, goal={"objective": "win"}) == ["goal"]
    assert derive_user_message_run_modes(auto_mode=True, goal={"objective": "win"}) == [
        "auto",
        "goal",
    ]
    assert derive_user_message_run_modes(auto_mode=False, goal=None) == []


@pytest.mark.asyncio
async def test_user_event_persists_assistant_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    presenter = _presenter()
    saved: list[dict[str, Any]] = []

    async def save(event: dict[str, Any], **kwargs: Any) -> None:
        saved.append(event)

    monkeypatch.setattr(presenter, "save_event", save)
    identity = {"seed": "role-1", "name": "Reviewer", "avatar": "generated:role-1"}
    await presenter.emit_user_message("ok", assistant_identity=identity)
    assert saved[0]["data"]["assistant_identity"] == identity


@pytest.mark.asyncio
async def test_goal_continuation_is_internal_and_not_indexed_as_user_input(monkeypatch):
    presenter = _presenter()
    saved = []
    indexed = []

    async def save(event, **kwargs):
        saved.append(event)

    monkeypatch.setattr(presenter, "save_event", save)
    monkeypatch.setattr(
        "src.infra.writer.present.schedule_user_message_search_index",
        lambda *args: indexed.append(args),
    )
    await presenter.emit_user_message(
        "internal continuation prompt",
        goal_continuation={
            "goal_id": "g1",
            "turn": 2,
            "objective": "finish docs",
            "initial": False,
        },
    )
    assert saved[0]["event"] == "goal:continuation"
    assert saved[0]["data"]["turn"] == 2
    assert "content" not in saved[0]["data"]
    assert not indexed


@pytest.mark.asyncio
async def test_initial_goal_turn_preserves_actual_user_objective(monkeypatch):
    presenter = _presenter()
    saved = []

    async def save(event, **kwargs):
        saved.append(event)

    monkeypatch.setattr(presenter, "save_event", save)
    await presenter.emit_user_message(
        "internal continuation prompt",
        schedule_search_index=False,
        goal_continuation={"goal_id": "g1", "turn": 1, "objective": "finish docs", "initial": True},
    )
    assert saved[0]["event"] == "user:message"
    assert saved[0]["data"]["content"] == "finish docs"
    assert saved[0]["data"]["run_modes"] == ["goal"]
