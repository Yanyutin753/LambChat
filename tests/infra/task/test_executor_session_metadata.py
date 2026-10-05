"""Persist explicit run metadata before execution, preserving session ownership."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task.executor import TaskExecutor


def make_executor(existing=None):
    async def merge_metadata(_session_id, metadata):
        existing.metadata.update(metadata)
        return True

    storage = SimpleNamespace(
        get_by_session_id=AsyncMock(return_value=existing),
        create=AsyncMock(),
        update_metadata_only=AsyncMock(side_effect=merge_metadata),
    )
    return TaskExecutor(storage, {}, SimpleNamespace()), storage


async def test_existing_session_persists_new_runtime_and_clears_project_without_losing_other_metadata():
    session = SimpleNamespace(
        user_id="owner",
        metadata={
            "project_id": "previous-project",
            "agent_options": {"sandbox": "cloud"},
            "channel_delivery": {"chat_id": "chat"},
            "is_favorite": True,
        },
    )
    executor, storage = make_executor(session)
    runtime = {"sandbox": "local", "sandbox_machine_id": "machine"}
    metadata = {"agent_options": runtime, "project_id": None, "auto_mode": False}

    await executor.ensure_session("session", "search", "owner", session_metadata=metadata)

    storage.update_metadata_only.assert_awaited_once_with("session", metadata)
    storage.create.assert_not_awaited()
    assert session.metadata == {
        **metadata,
        "channel_delivery": {"chat_id": "chat"},
        "is_favorite": True,
    }


async def test_new_session_stores_explicit_runtime_metadata_with_its_project():
    executor, storage = make_executor()
    metadata = {
        "executor_key": "agent_stream",
        "agent_options": {"sandbox": "local"},
        "team_id": None,
    }

    await executor.ensure_session(
        "session", "search", "owner", project_id="project", session_metadata=metadata
    )

    storage.create.assert_awaited_once()
    create = storage.create.call_args
    assert create.args[0].metadata == {"agent_id": "search", "project_id": "project", **metadata}
    assert create.kwargs == {"user_id": "owner", "session_id": "session"}
    storage.update_metadata_only.assert_not_awaited()


async def test_foreign_session_metadata_cannot_be_changed():
    session = SimpleNamespace(user_id="another-owner", metadata={"project_id": "private"})
    executor, storage = make_executor(session)

    with pytest.raises(PermissionError):
        await executor.ensure_session(
            "session", "search", "attacker", session_metadata={"project_id": "foreign"}
        )

    storage.update_metadata_only.assert_not_awaited()
    storage.create.assert_not_awaited()
    assert session.metadata == {"project_id": "private"}


@pytest.mark.parametrize("metadata", [None, {}])
async def test_unspecified_metadata_does_not_rewrite_an_existing_session(metadata):
    executor, storage = make_executor(SimpleNamespace(user_id="owner", metadata={}))

    await executor.ensure_session("session", "search", "owner", session_metadata=metadata)

    storage.update_metadata_only.assert_not_awaited()
    storage.create.assert_not_awaited()


@pytest.mark.parametrize("failure", [False, RuntimeError("database unavailable")])
async def test_runtime_metadata_persistence_failure_prevents_starting_with_stale_options(failure):
    executor, storage = make_executor(SimpleNamespace(user_id="owner", metadata={}))
    storage.update_metadata_only = (
        AsyncMock(side_effect=failure)
        if isinstance(failure, Exception)
        else AsyncMock(return_value=failure)
    )

    with pytest.raises(RuntimeError):
        await executor.ensure_session(
            "session", "search", "owner", session_metadata={"agent_options": {"sandbox": "local"}}
        )


async def test_new_session_creation_failure_with_runtime_metadata_is_not_swallowed():
    executor, storage = make_executor()
    storage.create.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await executor.ensure_session(
            "session", "search", "owner", session_metadata={"agent_options": {"sandbox": "local"}}
        )


async def test_calls_without_runtime_metadata_keep_legacy_creation_failure_behavior():
    executor, storage = make_executor()
    storage.create.side_effect = RuntimeError("database unavailable")

    await executor.ensure_session("session", "search", "owner")
