from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService
from src.api.routes.chat import (
    CHAT_SSE_DATA_MAX_BYTES,
    apply_declared_plugin_session_options,
    apply_agent_team_plugin_session_option,
    apply_project_agent_team_default,
    apply_project_plugin_session_defaults,
    _execute_agent_stream,
    _format_sse_event,
    build_conversation_config,
    ensure_chat_agent_executable,
    ensure_agent_team_executable,
    ensure_plugin_agent_executable,
    resolve_goal_for_request,
    selected_agent_team_id_from_metadata,
    session_stream,
)
from src.kernel.extensions import PluginManifest, PluginRuntime
from src.kernel.extensions.builtin_plugins import build_agent_team_plugin_manifest
from src.kernel.schemas.agent import AgentRequest, GoalSpec


def test_build_conversation_config_does_not_persist_run_scoped_goal() -> None:
    request = AgentRequest(
        message="continue",
        goal=GoalSpec(objective="finish exports", rubric="- exports work"),
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
    )

    assert "active_goal" not in config


def test_build_conversation_config_persists_trace_id_for_cancellation_recovery() -> None:
    request = AgentRequest(message="continue")

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
        trace_id="trace-1",
    )

    assert config["trace_id"] == "trace-1"


def test_build_conversation_config_writes_agent_team_session_plugin_option() -> None:
    request = AgentRequest(message="team work", team_id="team-1")

    config = build_conversation_config(
        run_id="run-1",
        agent_id="team",
        request=request,
        language="en",
        session_id="session-1",
    )

    assert "team_id" not in config
    assert config["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }


def test_build_conversation_config_preserves_generic_plugin_session_options() -> None:
    request = AgentRequest(
        message="run workflow",
        plugin_options={
            "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"},
            "feedback": {"DRAFT_MODE": True},
        },
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
    )

    assert config["plugin_options"] == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"},
        "feedback": {"DRAFT_MODE": True},
    }


def test_build_conversation_config_filters_plugin_options_by_manifest_when_runtime_is_available() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        permissions=["workflow_runner:read"],
        settings=[
            {
                "key": "SELECTED_WORKFLOW_ID",
                "type": "string",
                "scope": "session",
            }
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])
    request = AgentRequest(
        message="run workflow",
        plugin_options={
            "workflow_runner": {
                "SELECTED_WORKFLOW_ID": "workflow-1",
                "UNDECLARED": "drop-me",
            },
            "missing_plugin": {"ANY": "drop-me"},
        },
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
        plugin_runtime=runtime,
    )

    assert config["plugin_options"] == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}
    }


def test_build_conversation_config_overlays_agent_team_legacy_selection() -> None:
    request = AgentRequest(
        message="team work",
        team_id="team-current",
        plugin_options={"agent_team": {"SELECTED_TEAM_ID": "team-stale"}},
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="team",
        request=request,
        language="en",
        session_id="session-1",
    )

    assert config["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-current"}
    }


def test_apply_agent_team_plugin_session_option_prefers_plugin_namespace() -> None:
    request = AgentRequest(
        message="team work",
        team_id="legacy-team",
        plugin_options={"agent_team": {"SELECTED_TEAM_ID": "plugin-team"}},
    )

    apply_agent_team_plugin_session_option(request, agent_id="team")

    assert request.team_id == "plugin-team"


def test_apply_declared_plugin_session_options_imports_manifest_legacy_payload() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                    "legacy_payload_keys": ["workflow_id"],
                }
            ]
        },
    )
    request = AgentRequest(
        message="run workflow",
        context={"note": "legacy field stays outside plugin state"},
    )
    request.context["workflow_id"] = "workflow-1"

    apply_declared_plugin_session_options(
        request,
        agent_id="search",
        plugin_runtime=PluginRuntime([manifest]),
    )

    assert request.plugin_options == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}
    }


def test_apply_declared_plugin_session_options_filters_disabled_plugins() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])
    runtime.disable_plugin("workflow_runner")
    request = AgentRequest(
        message="run workflow",
        plugin_options={"workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}},
    )

    apply_declared_plugin_session_options(
        request,
        agent_id="search",
        plugin_runtime=runtime,
    )

    assert request.plugin_options is None


def test_selected_agent_team_id_from_metadata_prefers_plugin_option_with_legacy_fallback() -> None:
    assert (
        selected_agent_team_id_from_metadata(
            {
                "team_id": "legacy-team",
                "plugin_options": {
                    "agent_team": {"SELECTED_TEAM_ID": "plugin-team"}
                },
            }
        )
        == "plugin-team"
    )
    assert selected_agent_team_id_from_metadata({"team_id": "legacy-team"}) == "legacy-team"
    assert selected_agent_team_id_from_metadata({"plugin_options": {}}) is None


def test_ensure_agent_team_executable_keeps_legacy_compat_without_runtime() -> None:
    ensure_agent_team_executable(
        "team",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
    )


def test_ensure_agent_team_executable_allows_other_agents_when_disabled() -> None:
    ensure_agent_team_executable(
        "search",
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(plugin_runtime=SimpleNamespace(is_enabled=lambda _plugin_id: False))
            )
        ),
    )


def test_ensure_agent_team_executable_rejects_disabled_agent_team() -> None:
    with pytest.raises(Exception) as exc_info:
        ensure_agent_team_executable(
            "team",
            SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(plugin_runtime=SimpleNamespace(is_enabled=lambda _plugin_id: False))
                )
            ),
        )

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 503
    assert exc.detail == {
        "error": "plugin_unavailable",
        "plugin_id": "agent_team",
        "message": "Agent Team plugin is not executable",
    }


def test_ensure_plugin_agent_executable_rejects_any_disabled_plugin_agent() -> None:
    runtime = PluginRuntime(
        [
            PluginManifest(
                id="workflow_runner",
                name="Workflow Runner",
                version="1.0.0",
                api_version="v1",
                permissions=["workflow_runner:read"],
                agents=[
                    {
                        "id": "workflow",
                        "module": "plugins.workflow.agent.WorkflowAgent",
                        "required_permissions": ["workflow_runner:read"],
                    }
                ],
            )
        ]
    )
    runtime.disable_plugin("workflow_runner")

    with pytest.raises(Exception) as exc_info:
        ensure_plugin_agent_executable(
            "workflow",
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=runtime))),
        )

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 503
    assert exc.detail["error"] == "plugin_unavailable"
    assert exc.detail["plugin_id"] == "workflow_runner"


def test_ensure_chat_agent_executable_rejects_any_manifest_declared_disabled_agent() -> None:
    runtime = SimpleNamespace(
        plugin_for_agent=lambda agent_id: "workflow_runner" if agent_id == "workflow" else None,
        is_enabled=lambda _plugin_id: False,
    )

    with pytest.raises(Exception) as exc_info:
        ensure_chat_agent_executable(
            "workflow",
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=runtime))),
        )

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 503
    assert exc.detail["error"] == "plugin_unavailable"
    assert exc.detail["plugin_id"] == "workflow_runner"


def test_chat_agent_team_guard_uses_shared_plugin_unavailable_helper() -> None:
    source = Path("src/api/routes/chat.py").read_text(encoding="utf-8")
    guard_body = source.split("def ensure_declared_plugin_agent_executable", 1)[1].split(
        "def ensure_agent_team_executable",
        1,
    )[0]

    assert "plugin_unavailable_http_error" in guard_body
    assert '"error": "plugin_unavailable"' not in guard_body


@pytest.mark.asyncio
async def test_apply_project_agent_team_default_uses_plugin_project_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AgentRequest(message="team work", project_id="project-1")
    project = SimpleNamespace(
        metadata={"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-project"}}}
    )
    storage = SimpleNamespace(get_by_id=lambda project_id, user_id: project)

    async def get_by_id(project_id, user_id):
        assert (project_id, user_id) == ("project-1", "user-1")
        return project

    storage.get_by_id = get_by_id
    monkeypatch.setattr("src.infra.folder.storage.get_project_storage", lambda: storage)

    await apply_project_agent_team_default(
        request,
        agent_id="team",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=SimpleNamespace(is_enabled=lambda plugin_id: plugin_id == "agent_team")
                )
            )
        ),
    )

    assert request.team_id == "team-project"


@pytest.mark.asyncio
async def test_apply_project_agent_team_default_prefers_project_scoped_plugin_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AgentRequest(message="team work", project_id="project-1")
    project = SimpleNamespace(
        metadata={"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-legacy"}}}
    )
    storage = SimpleNamespace()

    async def get_by_id(project_id, user_id):
        assert (project_id, user_id) == ("project-1", "user-1")
        return project

    manifest = build_agent_team_plugin_manifest()
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    await settings_service.set_setting(
        manifest,
        key="DEFAULT_TEAM_ID",
        value="team-settings",
        scope="project",
        subject_id="project-1",
        updated_by="user-1",
    )
    storage.get_by_id = get_by_id
    monkeypatch.setattr("src.infra.folder.storage.get_project_storage", lambda: storage)

    await apply_project_agent_team_default(
        request,
        agent_id="team",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=SimpleNamespace(
                        is_enabled=lambda plugin_id: plugin_id == "agent_team",
                        get_state=lambda _plugin_id: SimpleNamespace(manifest=manifest),
                    ),
                    plugin_settings_service=settings_service,
                )
            )
        ),
    )

    assert request.team_id == "team-settings"


@pytest.mark.asyncio
async def test_apply_project_plugin_session_defaults_respects_session_option_visible_when(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AgentRequest(message="search work", project_id="project-1")
    project = SimpleNamespace(metadata={})

    async def get_by_id(_project_id, _user_id):
        return project

    manifest = build_agent_team_plugin_manifest()
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    await settings_service.set_setting(
        manifest,
        key="DEFAULT_TEAM_ID",
        value="team-settings",
        scope="project",
        subject_id="project-1",
        updated_by="user-1",
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_id=get_by_id),
    )

    await apply_project_plugin_session_defaults(
        request,
        agent_id="search",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=PluginRuntime([manifest]),
                    plugin_settings_service=settings_service,
                )
            )
        ),
    )

    assert request.team_id is None
    assert request.plugin_options is None


@pytest.mark.asyncio
async def test_apply_project_agent_team_default_ignores_disabled_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AgentRequest(message="team work", project_id="project-1")
    called = False

    async def get_by_id(_project_id, _user_id):
        nonlocal called
        called = True
        return None

    storage = SimpleNamespace(get_by_id=get_by_id)
    monkeypatch.setattr("src.infra.folder.storage.get_project_storage", lambda: storage)

    await apply_project_agent_team_default(
        request,
        agent_id="team",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(plugin_runtime=SimpleNamespace(is_enabled=lambda _plugin_id: False))
            )
        ),
    )

    assert request.team_id is None
    assert called is False


@pytest.mark.asyncio
async def test_apply_project_agent_team_default_keeps_explicit_team_id() -> None:
    request = AgentRequest(message="team work", project_id="project-1", team_id="manual-team")

    await apply_project_agent_team_default(
        request,
        agent_id="team",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
    )

    assert request.team_id == "manual-team"


@pytest.mark.asyncio
async def test_apply_project_plugin_session_defaults_uses_manifest_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "DEFAULT_WORKFLOW_ID", "type": "string", "scope": "project"},
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.default",
                    "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                }
            ],
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ],
        },
    )
    runtime = PluginRuntime([manifest])
    request = AgentRequest(message="run workflow", project_id="project-1")
    project = SimpleNamespace(
        metadata={
            "plugin_options": {
                "workflow_runner": {"DEFAULT_WORKFLOW_ID": "workflow-project"}
            }
        }
    )

    async def get_by_id(project_id, user_id):
        assert (project_id, user_id) == ("project-1", "user-1")
        return project

    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_id=get_by_id),
    )

    await apply_project_plugin_session_defaults(
        request,
        agent_id="search",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=runtime))
        ),
    )

    assert request.plugin_options == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-project"}
    }


@pytest.mark.asyncio
async def test_apply_project_plugin_session_defaults_keeps_explicit_session_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "DEFAULT_WORKFLOW_ID", "type": "string", "scope": "project"},
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.default",
                    "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                }
            ],
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ],
        },
    )
    request = AgentRequest(
        message="run workflow",
        project_id="project-1",
        plugin_options={"workflow_runner": {"SELECTED_WORKFLOW_ID": "manual"}},
    )
    project = SimpleNamespace(
        metadata={
            "plugin_options": {
                "workflow_runner": {"DEFAULT_WORKFLOW_ID": "workflow-project"}
            }
        }
    )

    async def get_by_id(_project_id, _user_id):
        return project

    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_id=get_by_id),
    )

    await apply_project_plugin_session_defaults(
        request,
        agent_id="search",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=PluginRuntime([manifest])))
        ),
    )

    assert request.plugin_options == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "manual"}
    }


@pytest.mark.asyncio
async def test_apply_project_plugin_session_defaults_uses_generic_defaults_when_team_id_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "DEFAULT_WORKFLOW_ID", "type": "string", "scope": "project"},
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.default",
                    "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                }
            ],
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ],
        },
    )
    project = SimpleNamespace(
        metadata={
            "plugin_options": {
                "workflow_runner": {"DEFAULT_WORKFLOW_ID": "workflow-project"}
            }
        }
    )

    async def get_by_id(_project_id, _user_id):
        return project

    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_id=get_by_id),
    )
    request = AgentRequest(
        message="run workflow",
        project_id="project-1",
        team_id="manual-team",
    )

    await apply_project_plugin_session_defaults(
        request,
        agent_id="search",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=PluginRuntime([manifest])))
        ),
    )

    assert request.team_id == "manual-team"
    assert request.plugin_options == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-project"}
    }


@pytest.mark.asyncio
async def test_apply_project_agent_team_default_does_not_override_explicit_team_with_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(
        metadata={"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-project"}}}
    )

    async def get_by_id(_project_id, _user_id):
        return project

    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_id=get_by_id),
    )
    request = AgentRequest(
        message="team work",
        project_id="project-1",
        team_id="manual-team",
    )

    await apply_project_agent_team_default(
        request,
        agent_id="team",
        user=SimpleNamespace(sub="user-1"),
        http_request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=PluginRuntime([build_agent_team_plugin_manifest()])
                )
            )
        ),
    )

    assert request.team_id == "manual-team"
    assert request.plugin_options == {
        "agent_team": {"SELECTED_TEAM_ID": "manual-team"}
    }


def test_resolve_goal_for_request_uses_request_goal_without_rewriting_message() -> None:
    request = AgentRequest(
        message="continue",
        goal=GoalSpec(objective="finish docs", rubric="- docs finished"),
    )

    active_goal, agent_message = resolve_goal_for_request(request, existing_metadata={})

    assert active_goal is not None
    assert active_goal.objective == "finish docs"
    assert agent_message == "continue"
    assert request.goal == active_goal
    assert "goal_command_action" not in request.context


def test_resolve_goal_for_request_does_not_restore_session_goal_for_follow_up() -> None:
    request = AgentRequest(message="keep going")

    active_goal, agent_message = resolve_goal_for_request(
        request,
        existing_metadata={
            "active_goal": {
                "objective": "finish docs",
                "rubric": "- docs are updated",
                "max_iterations": 5,
            }
        },
    )

    assert active_goal is None
    assert agent_message == "keep going"
    assert request.goal is None


def test_format_sse_event_adds_timestamp_without_mutating_event_data() -> None:
    event = {
        "event_type": "message:chunk",
        "data": {"content": "hello"},
        "timestamp": "2026-06-02T00:00:00Z",
        "id": "1-0",
    }

    line = _format_sse_event(event)

    assert line == (
        "event: message:chunk\n"
        'data: {"content": "hello", "_timestamp": "2026-06-02T00:00:00Z"}\n'
        "id: 1-0\n\n"
    )
    assert event["data"] == {"content": "hello"}


def test_format_sse_event_drops_oversized_payload() -> None:
    event = {
        "event_type": "message:chunk",
        "data": {"content": "x" * (CHAT_SSE_DATA_MAX_BYTES + 1)},
        "timestamp": "2026-06-02T00:00:00Z",
        "id": "1-0",
    }

    line = _format_sse_event(event)

    assert "event: error" in line
    assert "event_payload_too_large" in line
    assert len(line.encode("utf-8")) < 1024


@pytest.mark.asyncio
async def test_session_stream_offloads_sse_event_formatting(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    class _SessionManager:
        async def get_session(self, session_id):
            return type("Session", (), {"user_id": "user-1"})()

    class _DualWriter:
        async def read_from_redis(self, session_id, *, run_id):
            yield {
                "event_type": "message:chunk",
                "data": {"content": "hello"},
                "timestamp": "2026-06-02T00:00:00Z",
                "id": "1-0",
            }

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr("src.api.routes.chat.SessionManager", lambda: _SessionManager())
    monkeypatch.setattr("src.api.routes.chat.verify_session_ownership", lambda session, user: None)
    monkeypatch.setattr("src.api.routes.chat.run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _DualWriter(),
    )

    response = await session_stream(
        "session-1",
        run_id="run-1",
        user=type("User", (), {"sub": "user-1"})(),
    )
    body_iterator = response.body_iterator
    chunk = await body_iterator.__anext__()

    assert "event: message:chunk" in chunk
    assert calls == ["_format_sse_event"]


@pytest.mark.asyncio
async def test_execute_agent_stream_runs_agent_when_active_goal_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Presenter:
        run_id = "run-1"
        trace_id = "trace-1"

        def metadata(self):
            return {"event": "metadata", "data": {"run_id": self.run_id}}

    class _Agent:
        def __init__(self) -> None:
            self.stream_kwargs = None

        async def stream(self, *args, **kwargs):
            self.stream_kwargs = kwargs
            yield {"event": "message:chunk", "data": {"content": "ok"}}

    agent = _Agent()

    async def _get(_agent_id: str):
        return agent

    monkeypatch.setattr("src.api.routes.chat.AgentFactory.get", _get)

    events = [
        event
        async for event in _execute_agent_stream(
            session_id="session-1",
            agent_id="search",
            message="hi",
            user_id="user-1",
            presenter=_Presenter(),
            active_goal={"objective": "hi", "rubric": "- say hi"},
        )
    ]

    assert [event["event"] for event in events] == [
        "goal:start",
        "message:chunk",
        "goal:end",
    ]
    assert events[0]["data"]["goal"] == {"objective": "hi", "rubric": "- say hi"}
    assert events[0]["data"]["started_at"]
    assert events[2]["data"]["goal"] == {"objective": "hi", "rubric": "- say hi"}
    assert events[2]["data"]["ended_at"]
    assert agent.stream_kwargs["active_goal"] == {"objective": "hi", "rubric": "- say hi"}
