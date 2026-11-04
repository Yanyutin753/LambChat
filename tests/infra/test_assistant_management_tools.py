from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.infra.test_assistant_service import assistant, user


@pytest.mark.parametrize("kind,child", [("assistant", False), ("group", False), ("chief", True)])
async def test_management_rejects_non_chief_or_child_context(monkeypatch, kind, child):
    from src.infra.assistant.store import AssistantStore
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "resolve_tool_user", AsyncMock(return_value=user()))
    monkeypatch.setattr(
        AssistantStore,
        "for_session",
        AsyncMock(return_value=assistant().model_copy(update={"kind": kind})),
    )
    runtime = SimpleNamespace(
        config={
            "configurable": {"context": SimpleNamespace(user_id="owner", session_id="s")},
            "metadata": {"lambchat_subagent_id": "child"} if child else {},
        },
        tool_call_id="call",
    )
    with pytest.raises(Exception):
        await module.chief_context(runtime, "chat:write")


async def test_create_tool_reuses_call_identity_and_returns_navigation(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    create = AsyncMock(return_value=assistant())
    monkeypatch.setattr(module, "AssistantService", lambda: SimpleNamespace(create=create))
    runtime = SimpleNamespace(
        config={"configurable": {"thread_id": "thread", "run_id": "run"}}, tool_call_id="call"
    )
    result = await module.create_assistant.coroutine(
        name="Writer", instructions="Write clearly", runtime=runtime
    )
    assert result["url"] == "/assistants/assistant"
    first = create.call_args.kwargs["identity"]
    await module.create_assistant.coroutine(
        name="Writer", instructions="Write clearly", runtime=runtime
    )
    assert create.call_args.kwargs["identity"] == first


async def test_update_preserves_execution_settings_and_expected_revision(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant(model_id="model", project_id="project", instructions="original")
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    await module.update_assistant.coroutine(assistant_id="assistant", revision=7, name="Renamed")
    draft = update.call_args.args[2]
    assert draft.revision == 7
    assert draft.model_id == "model" and draft.project_id == "project"
    assert draft.instructions == "original" and draft.name == "Renamed"


async def test_management_rechecks_revoked_permissions(monkeypatch):
    from src.infra.tool import assistant_tool as module
    from src.kernel.errors import AppError

    monkeypatch.setattr(
        module,
        "resolve_tool_user",
        AsyncMock(return_value=user().model_copy(update={"permissions": []})),
    )
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="owner")}}, tool_call_id="call"
    )
    with pytest.raises(AppError):
        await module.chief_context(runtime, "chat:write")


async def test_chief_allows_root_tool_node_but_rejects_nested_namespace(monkeypatch):
    from src.infra.assistant.store import AssistantStore
    from src.infra.tool import assistant_tool as module
    from src.kernel.errors import AppError

    owner = user()
    monkeypatch.setattr(module, "resolve_tool_user", AsyncMock(return_value=owner))
    chief = assistant().model_copy(update={"kind": "chief"})
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=chief))
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "context": SimpleNamespace(user_id="owner", session_id=chief.session_id),
                "thread_id": chief.session_id,
                "checkpoint_ns": "tools:root",
            }
        }
    )
    assert await module.chief_context(runtime, "chat:write") == owner
    runtime.config["configurable"]["checkpoint_ns"] = "tools:root|tools:child"
    with pytest.raises(AppError):
        await module.chief_context(runtime, "chat:write")
