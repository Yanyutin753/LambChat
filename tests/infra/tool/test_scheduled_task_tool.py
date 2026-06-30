"""Tests for scheduled_task_tool — LLM-callable scheduled task management tools."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from src.infra.scheduler.service import ScheduledTaskService as _RealService
from src.infra.tool import scheduled_task_tool
from src.kernel.extensions import (
    PluginRuntime,
    build_agent_team_plugin_manifest,
    build_workflow_plugin_manifest,
)
from src.kernel.schemas.scheduled_task import (
    ChannelDeliveryConfig,
    ScheduledTask,
    ScheduledTaskStatus,
    TriggerType,
)

# ── Helpers ─────────────────────────────────────────────────────


class _Runtime:
    """Fake ToolRuntime with user_id."""

    def __init__(self, user_id: str | None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}


async def _call_tool(tool: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a LangChain tool coroutine without depending on BaseTool's static type."""
    coroutine = getattr(tool, "coroutine")
    return await coroutine(*args, **kwargs)


def _tool_fields(tool: Any) -> dict[str, Any]:
    """Return pydantic arg-schema fields for a LangChain tool."""
    schema = getattr(tool, "args_schema")
    assert isinstance(schema, type)
    assert issubclass(schema, BaseModel)
    return dict(schema.model_fields)


def _task(
    task_id: str = "task-1",
    *,
    name: str = "Daily Report",
    owner_id: str = "user-1",
    agent_id: str = "fast",
    trigger_type: TriggerType = TriggerType.CRON,
    status: ScheduledTaskStatus = ScheduledTaskStatus.ACTIVE,
    enabled: bool = True,
    delivery: ChannelDeliveryConfig | None = None,
) -> ScheduledTask:
    return ScheduledTask.model_validate(
        {
            "_id": task_id,
            "name": name,
            "description": "Test task",
            "agent_id": agent_id,
            "trigger_type": trigger_type,
            "trigger_config": {"hour": "9", "minute": "0"},
            "input_payload": {"message": "Generate daily report"},
            "status": status,
            "enabled": enabled,
            "owner_id": owner_id,
            "delivery": delivery,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }
    )


def _fake_service_cls(**methods: AsyncMock):
    """Build a fake ScheduledTaskService class for monkeypatching.

    - ``ScheduledTaskService()`` returns a MagicMock with the given async methods
    - ``ScheduledTaskService.to_response(task)`` delegates to the real static method
    """

    instance = MagicMock()
    for name, mock in methods.items():
        setattr(instance, name, mock)

    class _Fake:
        to_response = _RealService.to_response  # preserve static method

        def __new__(cls):
            return instance

    return _Fake


def _auto_approve(monkeypatch: pytest.MonkeyPatch, approval_id: str = "approval-1") -> AsyncMock:
    approval_mock = AsyncMock(
        return_value={
            "approved": True,
            "status": "approved",
            "approval_id": approval_id,
        }
    )
    monkeypatch.setattr(
        scheduled_task_tool,
        "_confirm_scheduled_task_creation",
        approval_mock,
    )
    return approval_mock


@pytest.fixture(autouse=True)
def _allow_scheduled_task_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scheduled_task_tool,
        "_permission_error",
        AsyncMock(return_value=None),
    )


# ── Tool metadata tests ────────────────────────────────────────


def test_get_scheduled_task_tools_returns_compact_crud_tools() -> None:
    tools = scheduled_task_tool.get_scheduled_task_tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {
        "scheduled_task_create",
        "scheduled_task_list",
        "scheduled_task_update",
        "scheduled_task_delete",
    }


def test_create_tool_has_trigger_params() -> None:
    fields = _tool_fields(scheduled_task_tool.scheduled_task_create)
    # Structured trigger params should be present
    assert "trigger_type" in fields
    assert "delay_seconds" in fields
    assert "run_at_iso" in fields
    assert "interval_seconds" in fields
    assert "cron_hour" in fields
    assert "cron_minute" in fields
    assert "cron_day_of_week" in fields
    assert "cron_day" in fields
    assert "cron_month" in fields
    assert "persona_preset_id" in fields
    assert "team_id" in fields
    assert "plugin_options" in fields
    assert "role_query" in fields
    assert "team_query" in fields


def test_create_tool_timeout_prompt_prefers_3600s_default() -> None:
    fields = _tool_fields(scheduled_task_tool.scheduled_task_create)
    timeout_field = fields["timeout_seconds"]

    assert timeout_field.default == 3600
    assert timeout_field.description is not None
    assert "Default: 3600s" in timeout_field.description
    assert "Do not set this too short" in timeout_field.description


def test_list_tool_can_fetch_single_task_details() -> None:
    fields = _tool_fields(scheduled_task_tool.scheduled_task_list)
    assert "task_id" in fields


def test_update_tool_can_run_task_actions() -> None:
    fields = _tool_fields(scheduled_task_tool.scheduled_task_update)
    assert "action" in fields


# ── scheduled_task_create ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_interval_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(trigger_type=TriggerType.INTERVAL)
    create_mock = AsyncMock(return_value=task)
    approval_mock = _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Cache Cleanup",
            message="Clean up expired cache entries",
            trigger_type="interval",
            interval_seconds=300,
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "created"
    assert result["task"]["name"] == "Daily Report"
    assert result["approval_id"] == "approval-1"
    # The human-approval outcome must be propagated so channel handlers can
    # finalize the approval card to the correct terminal status.
    assert result["approved"] is True
    assert result["status"] == "approved"
    assert result["preview"]["schedule"] == "every 5 minute(s)"
    assert "Clean up expired cache entries" in result["preview"]["effect"]

    # Verify service was called with correct trigger config
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.trigger_type == TriggerType.INTERVAL
    assert request.trigger_config == {"seconds": 300}
    assert request.input_payload == {"message": "Clean up expired cache entries"}
    approval_mock.assert_awaited_once()
    assert approval_mock.call_args.kwargs["preview"]["trigger_config"] == {"seconds": 300}


@pytest.mark.asyncio
async def test_create_task_in_channel_session_attaches_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(
        delivery=ChannelDeliveryConfig(
            channel_type="feishu",
            chat_id="oc_target",
            channel_instance_id="bot_a",
        )
    )
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    class _FakeTraceContext:
        @staticmethod
        def get_request_context():
            return SimpleNamespace(session_id="feishu_oc_source", run_id="run-1")

    class _FakeSessionManager:
        async def get_session(self, session_id: str):
            assert session_id == "feishu_oc_source"
            return SimpleNamespace(
                metadata={
                    "agent_id": "fast",
                    "channel_delivery": {
                        "channel_type": "feishu",
                        "chat_id": "oc_target",
                        "channel_instance_id": "bot_a",
                    },
                }
            )

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )
    monkeypatch.setattr("src.infra.logging.context.TraceContext", _FakeTraceContext)
    monkeypatch.setattr("src.infra.session.manager.SessionManager", _FakeSessionManager)

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Channel Report",
            message="Generate channel report",
            trigger_type="interval",
            interval_seconds=300,
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.delivery == ChannelDeliveryConfig(
        channel_type="feishu",
        chat_id="oc_target",
        channel_instance_id="bot_a",
    )
    assert result["task"]["delivery"]["chat_id"] == "oc_target"


@pytest.mark.asyncio
async def test_create_date_task_with_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    task = _task(trigger_type=TriggerType.DATE)
    create_mock = AsyncMock(return_value=task)
    approval_mock = _auto_approve(monkeypatch)

    monkeypatch.setattr(scheduled_task_tool, "utc_now", lambda: now)
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="One-time Reminder",
            message="Send the AI news once",
            trigger_type="date",
            delay_seconds=300,
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["preview"]["trigger_type"] == "date"
    assert result["preview"]["schedule"] == "once at 2026-01-01T12:05:00+00:00 UTC"

    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.trigger_type == TriggerType.DATE
    assert request.trigger_config == {"run_date": "2026-01-01T12:05:00+00:00"}
    approval_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_cron_task_with_structured_params(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Weekly Digest",
            message="Send weekly summary",
            trigger_type="cron",
            cron_hour="9",
            cron_minute="30",
            cron_day_of_week="mon-fri",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert "minute=30" in result["preview"]["schedule"]
    assert "hour=9" in result["preview"]["schedule"]

    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.trigger_type == TriggerType.CRON
    assert request.trigger_config == {
        "hour": "9",
        "minute": "30",
        "day_of_week": "mon-fri",
    }


@pytest.mark.asyncio
async def test_create_cron_task_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Midnight Task",
            message="Run at midnight",
            trigger_type="cron",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True

    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    # Should default hour and minute to "0"
    assert request.trigger_config["hour"] == "0"
    assert request.trigger_config["minute"] == "0"


@pytest.mark.asyncio
async def test_create_task_inherits_source_session_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "_get_current_session_defaults",
        AsyncMock(return_value=("search", {}, "Asia/Shanghai", None, None, None)),
    )
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Morning Brief",
            message="Send a morning brief",
            trigger_type="cron",
            cron_hour="8",
            cron_minute="0",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.input_payload == {
        "message": "Send a morning brief",
        "user_timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_create_task_inherits_source_session_persona_or_team_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "_get_current_session_defaults",
        AsyncMock(return_value=("search", {}, None, None, "persona-1", "team-ignored")),
    )
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Inherited Persona Task",
            message="Write with inherited persona",
            trigger_type="cron",
            cron_hour="8",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "search"
    assert request.input_payload == {
        "message": "Write with inherited persona",
        "persona_preset_id": "persona-1",
    }

    create_mock.reset_mock()
    create_mock.return_value = task
    monkeypatch.setattr(
        scheduled_task_tool,
        "_get_current_session_defaults",
        AsyncMock(return_value=("team", {}, None, None, "persona-ignored", "team-1")),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Inherited Team Task",
            message="Write with inherited team",
            trigger_type="cron",
            cron_hour="8",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "team"
    assert request.input_payload == {
        "message": "Write with inherited team",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
    }


@pytest.mark.asyncio
async def test_create_non_team_task_stores_only_persona_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="fast")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Persona Brief",
            message="Write a brief",
            trigger_type="cron",
            cron_hour="9",
            agent_id="fast",
            persona_preset_id="persona-1",
            team_id="team-ignored",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "fast"
    assert request.input_payload == {
        "message": "Write a brief",
        "persona_preset_id": "persona-1",
    }


@pytest.mark.asyncio
async def test_create_team_task_stores_team_selection_under_plugin_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="team")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Team Launch Plan",
            message="Plan launch",
            trigger_type="cron",
            cron_hour="9",
            agent_id="team",
            persona_preset_id="persona-ignored",
            team_id="team-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "team"
    assert request.input_payload == {
        "message": "Plan launch",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
    }


@pytest.mark.asyncio
async def test_create_team_task_rejects_disabled_agent_team_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    scheduled_task_tool.set_plugin_runtime(runtime)
    create_mock = AsyncMock()
    approval_mock = _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    try:
        result = json.loads(
            await _call_tool(
                scheduled_task_tool.scheduled_task_create,
                name="Team Launch Plan",
                message="Plan launch",
                trigger_type="cron",
                cron_hour="9",
                agent_id="team",
                team_id="team-1",
                runtime=_Runtime("user-1"),
            )
        )
    finally:
        scheduled_task_tool.set_plugin_runtime(None)

    assert result == {
        "error": "Agent Team plugin is disabled; scheduled team tasks cannot be created.",
        "code": "plugin_unavailable",
        "plugin_id": "agent_team",
    }
    create_mock.assert_not_called()
    approval_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_task_accepts_generic_plugin_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="fast")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Workflow Task",
            message="Run workflow",
            trigger_type="cron",
            cron_hour="9",
            agent_id="fast",
            plugin_options={
                "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"},
                "bad": "ignored",
            },
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "fast"
    assert request.input_payload == {
        "message": "Run workflow",
        "plugin_options": {
            "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"},
        },
    }


@pytest.mark.asyncio
async def test_create_task_stores_workflow_plugin_options_for_pre_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="fast")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Workflow Task",
            message="Run nightly workflow",
            trigger_type="cron",
            cron_hour="2",
            agent_id="fast",
            plugin_options={
                "workflow": {
                    "SELECTED_WORKFLOW_ID": "wf-nightly",
                    "SELECTED_WORKFLOW_VERSION_ID": "wfv-nightly",
                },
                "bad": "ignored",
            },
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "fast"
    assert request.input_payload == {
        "message": "Run nightly workflow",
        "plugin_options": {
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-nightly",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-nightly",
            }
        },
    }


@pytest.mark.asyncio
async def test_create_workflow_task_rejects_disabled_workflow_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.disable_plugin("workflow")
    scheduled_task_tool.set_plugin_runtime(runtime)
    create_mock = AsyncMock()
    approval_mock = _auto_approve(monkeypatch)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    try:
        result = json.loads(
            await _call_tool(
                scheduled_task_tool.scheduled_task_create,
                name="Workflow Task",
                message="Run nightly workflow",
                trigger_type="cron",
                cron_hour="2",
                agent_id="fast",
                plugin_options={
                    "workflow": {
                        "SELECTED_WORKFLOW_ID": "wf-nightly",
                        "SELECTED_WORKFLOW_VERSION_ID": "wfv-nightly",
                    }
                },
                runtime=_Runtime("user-1"),
            )
        )
    finally:
        scheduled_task_tool.set_plugin_runtime(None)

    assert result == {
        "error": "Workflow plugin is disabled; scheduled workflow tasks cannot be created.",
        "code": "plugin_unavailable",
        "plugin_id": "workflow",
    }
    create_mock.assert_not_called()
    approval_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_task_searches_persona_by_role_query_and_uses_non_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="fast")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    class _FakePersonaManager:
        async def list_presets(self, **kwargs):
            assert kwargs["user_id"] == "user-1"
            assert kwargs["q"] == "写作"
            return [SimpleNamespace(id="persona-writer", name="写作助手")]

    monkeypatch.setattr(scheduled_task_tool, "_resolve_user", AsyncMock(return_value=None))
    monkeypatch.setattr(scheduled_task_tool, "PersonaPresetManager", lambda: _FakePersonaManager())
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Writer Brief",
            message="Write a brief",
            trigger_type="cron",
            cron_hour="9",
            agent_id="team",
            role_query="写作",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["preview"]["resolved_persona_preset"] == {
        "id": "persona-writer",
        "name": "写作助手",
        "query": "写作",
    }
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "fast"
    assert request.input_payload == {
        "message": "Write a brief",
        "persona_preset_id": "persona-writer",
    }


@pytest.mark.asyncio
async def test_create_task_searches_team_by_query_and_uses_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(agent_id="team")
    create_mock = AsyncMock(return_value=task)
    _auto_approve(monkeypatch)

    class _FakeTeamManager:
        async def list_teams(self, **kwargs):
            assert kwargs["owner_user_id"] == "user-1"
            assert kwargs["q"] == "研究团队"
            return SimpleNamespace(teams=[SimpleNamespace(id="team-research", name="研究团队")])

    monkeypatch.setattr(scheduled_task_tool, "_resolve_user", AsyncMock(return_value=None))
    monkeypatch.setattr(scheduled_task_tool, "TeamManager", lambda: _FakeTeamManager())
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Research Team Task",
            message="Research market",
            trigger_type="cron",
            cron_hour="9",
            agent_id="fast",
            team_query="研究团队",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["preview"]["resolved_team"] == {
        "id": "team-research",
        "name": "研究团队",
        "query": "研究团队",
    }
    request = create_mock.call_args.kwargs.get("request") or create_mock.call_args[0][0]
    assert request.agent_id == "team"
    assert request.input_payload == {
        "message": "Research market",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-research"}},
    }


@pytest.mark.asyncio
async def test_create_task_rejected_does_not_create(monkeypatch: pytest.MonkeyPatch) -> None:
    create_mock = AsyncMock()
    approval_mock = AsyncMock(
        return_value={
            "approved": False,
            "status": "rejected",
            "approval_id": "approval-2",
            "message": "User rejected scheduled task creation.",
        }
    )

    monkeypatch.setattr(
        scheduled_task_tool,
        "_confirm_scheduled_task_creation",
        approval_mock,
    )
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(create_task=create_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Daily Report",
            message="Generate daily report",
            trigger_type="cron",
            cron_hour="9",
            cron_minute="0",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is False
    assert result["action"] == "not_created"
    assert result["reason"] == "rejected"
    assert result["approval_id"] == "approval-2"
    # The human-approval outcome must be propagated so channel handlers can
    # finalize the approval card to the correct terminal status.
    assert result["approved"] is False
    assert result["status"] == "rejected"
    assert result["preview"]["name"] == "Daily Report"
    approval_mock.assert_awaited_once()
    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_confirmation_shows_preview_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.logging.context import TraceContext

    approval = SimpleNamespace(id="approval-3")
    response = SimpleNamespace(approved=True)
    create_approval = AsyncMock(return_value=approval)
    wait_for_response = AsyncMock(return_value=response)
    send_event = AsyncMock()

    monkeypatch.setattr(scheduled_task_tool, "create_approval", create_approval)
    monkeypatch.setattr(scheduled_task_tool, "wait_for_response", wait_for_response)
    monkeypatch.setattr(scheduled_task_tool, "_send_scheduled_task_approval_event", send_event)

    TraceContext.set_request_context(
        session_id="session-1",
        run_id="run-1",
        user_id="user-1",
    )
    try:
        preview = scheduled_task_tool._build_task_preview(
            name="Daily Report",
            message="Generate daily report",
            trigger_type=TriggerType.CRON,
            trigger_config={"hour": "9", "minute": "0"},
            agent_id="fast",
            description="Send a daily report",
            timeout_seconds=600,
            run_on_start=True,
        )

        result = await scheduled_task_tool._confirm_scheduled_task_creation(
            preview=preview,
            user_id="user-1",
            timeout=120,
        )
    finally:
        TraceContext.clear_request_context()

    assert result == {
        "approved": True,
        "status": "approved",
        "approval_id": "approval-3",
    }

    create_approval.assert_awaited_once()
    approval_kwargs = create_approval.call_args.kwargs
    assert approval_kwargs["approval_type"] == "confirm"
    assert approval_kwargs["fields"] == []
    assert approval_kwargs["session_id"] == "session-1"
    assert approval_kwargs["user_id"] == "user-1"
    assert approval_kwargs["metadata"]["approval_type"] == "scheduled_task_create"
    assert approval_kwargs["metadata"]["preview"]["name"] == "Daily Report"
    assert "No task has been created yet" in approval_kwargs["message"]
    assert "Generate daily report" in approval_kwargs["message"]
    assert "The task will also run immediately after creation" in approval_kwargs["message"]

    send_event.assert_awaited_once_with(
        approval_id="approval-3",
        message=approval_kwargs["message"],
        session_id="session-1",
        run_id="run-1",
        timeout=120,
    )
    wait_for_response.assert_awaited_once_with("approval-3", timeout=120)


@pytest.mark.asyncio
async def test_create_task_no_user() -> None:
    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Test",
            message="test",
            trigger_type="interval",
            interval_seconds=300,
            runtime=_Runtime(None),
        )
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_create_interval_task_missing_seconds() -> None:
    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Test",
            message="test",
            trigger_type="interval",
            runtime=_Runtime("user-1"),
        )
    )
    assert "error" in result
    assert "interval_seconds is required" in result["error"]


@pytest.mark.asyncio
async def test_create_interval_task_too_frequent() -> None:
    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Test",
            message="test",
            trigger_type="interval",
            interval_seconds=30,
            runtime=_Runtime("user-1"),
        )
    )
    assert "error" in result
    assert "at least 60" in result["error"]


@pytest.mark.asyncio
async def test_create_task_invalid_trigger_type() -> None:
    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_create,
            name="Test",
            message="test",
            trigger_type="invalid",
            runtime=_Runtime("user-1"),
        )
    )
    assert "error" in result
    assert "Invalid trigger_type" in result["error"]


# ── scheduled_task_list ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    tasks = [_task("t1"), _task("t2", name="Other")]
    list_mock = AsyncMock(return_value=tasks)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(list_tasks=list_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_list,
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["total"] == 2
    assert len(result["tasks"]) == 2

    list_mock.assert_called_once_with(owner_id="user-1", status=None)


@pytest.mark.asyncio
async def test_list_tasks_requires_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    list_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(
        scheduled_task_tool,
        "_permission_error",
        AsyncMock(
            return_value={
                "error": "Missing permission: scheduled_task:read",
                "code": "permission_denied",
            }
        ),
    )
    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(list_tasks=list_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_list,
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {
        "error": "Missing permission: scheduled_task:read",
        "code": "permission_denied",
    }
    list_mock.assert_not_called()


@pytest.mark.asyncio
async def test_list_tasks_with_status_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    list_mock = AsyncMock(return_value=[])

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(list_tasks=list_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_list,
            status="active",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    list_mock.assert_called_once_with(owner_id="user-1", status=ScheduledTaskStatus.ACTIVE)


# ── scheduled_task_get ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    get_mock = AsyncMock(return_value=task)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_get,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["task"]["id"] == "task-1"
    assert result["task"]["name"] == "Daily Report"


@pytest.mark.asyncio
async def test_get_task_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    get_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_get,
            task_id="nonexistent",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_get_task_wrong_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(owner_id="other-user")
    get_mock = AsyncMock(return_value=task)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_get,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result
    assert "not found" in result["error"]


# ── scheduled_task_update ───────────────────────────────────────


@pytest.mark.asyncio
async def test_update_task(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _task()
    updated = _task(name="Updated Name")
    get_mock = AsyncMock(side_effect=[original, updated])
    update_mock = AsyncMock(return_value=updated)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, update_task=update_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_update,
            task_id="task-1",
            name="Updated Name",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "updated"
    assert result["task"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_task_with_message(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _task()
    original.input_payload = {
        "message": "Old message content",
        "agent_options": {"model_id": "model-1", "model": "gpt-4.1"},
        "user_timezone": "Asia/Shanghai",
    }
    updated = _task()
    get_mock = AsyncMock(side_effect=[original, updated])
    update_mock = AsyncMock(return_value=updated)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, update_task=update_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_update,
            task_id="task-1",
            message="New message content",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    call_kwargs = update_mock.call_args
    update_obj = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs.get("request")
    assert update_obj is not None
    assert update_obj.input_payload == {
        "message": "New message content",
        "agent_options": {"model_id": "model-1", "model": "gpt-4.1"},
        "user_timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_update_task_no_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _task()
    get_mock = AsyncMock(return_value=original)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_update,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result
    assert "At least one field" in result["error"]


@pytest.mark.asyncio
async def test_update_task_wrong_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(owner_id="other-user")
    get_mock = AsyncMock(return_value=task)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_update,
            task_id="task-1",
            name="Hack",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result
    assert "not found" in result["error"]


# ── scheduled_task_pause ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pause_task(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _task()
    paused = _task(status=ScheduledTaskStatus.PAUSED, enabled=False)
    get_mock = AsyncMock(return_value=original)
    pause_mock = AsyncMock(return_value=paused)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, pause_task=pause_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_pause,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "paused"
    pause_mock.assert_called_once_with("task-1")


# ── scheduled_task_resume ───────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_task(monkeypatch: pytest.MonkeyPatch) -> None:
    paused_task = _task(status=ScheduledTaskStatus.PAUSED, enabled=False)
    resumed = _task()
    get_mock = AsyncMock(return_value=paused_task)
    resume_mock = AsyncMock(return_value=resumed)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, resume_task=resume_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_resume,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "resumed"
    resume_mock.assert_called_once_with("task-1")


# ── scheduled_task_delete ───────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    get_mock = AsyncMock(return_value=task)
    delete_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, delete_task=delete_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_delete,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "deleted"
    delete_mock.assert_called_once_with("task-1")


@pytest.mark.asyncio
async def test_delete_task_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    get_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_delete,
            task_id="nonexistent",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result


# ── scheduled_task_run ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    get_mock = AsyncMock(return_value=task)
    run_mock = AsyncMock(return_value={"run_id": "run-1", "status": "pending"})

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock, run_task_now=run_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_run,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["action"] == "triggered"
    assert result["result"]["run_id"] == "run-1"
    run_mock.assert_called_once_with("task-1")


# ── Cross-cutting concerns ──────────────────────────────────────


@pytest.mark.asyncio
async def test_pause_task_wrong_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(owner_id="other-user")
    get_mock = AsyncMock(return_value=task)

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(get_task=get_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_pause,
            task_id="task-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result


@pytest.mark.asyncio
async def test_service_error_handled_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    list_mock = AsyncMock(side_effect=Exception("DB connection lost"))

    monkeypatch.setattr(
        scheduled_task_tool,
        "ScheduledTaskService",
        _fake_service_cls(list_tasks=list_mock),
    )

    result = json.loads(
        await _call_tool(
            scheduled_task_tool.scheduled_task_list,
            runtime=_Runtime("user-1"),
        )
    )

    assert "error" in result
    assert "DB connection lost" in result["error"]
