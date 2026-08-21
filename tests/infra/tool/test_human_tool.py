from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.infra.tool.human_tool import tool as human_tool


@pytest.fixture(autouse=True)
def legacy_blocking_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep coverage for the retired blocking implementation in isolation."""
    monkeypatch.setattr(human_tool.settings, "HITL_MODE", "blocking", raising=False)


@pytest.mark.asyncio
async def test_ask_human_offloads_response_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def fake_create_approval(**kwargs):
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        assert approval_id == "approval-1"
        return SimpleNamespace(approved=True, response={"answer": "yes"})

    async def fake_send_approval_event(self, *args, **kwargs):
        return None

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)
    monkeypatch.setattr(human_tool, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await human_tool.AskHumanTool()._arun(
            message="Continue?",
            fields=[],
        )
    )

    assert result == {
        "status": "success",
        "message": "用户已响应",
        "values": {"answer": "yes"},
    }
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_ask_human_offloads_fields_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    captured_fields: list[dict] = []

    async def fake_create_approval(**kwargs):
        captured_fields.extend(kwargs["fields"])
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        assert approval_id == "approval-1"
        return SimpleNamespace(approved=True, response={"choice": "yes"})

    async def fake_send_approval_event(self, *args, **kwargs):
        return None

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)
    monkeypatch.setattr(human_tool, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await human_tool.AskHumanTool()._arun(
            message="Choose?",
            fields=json.dumps(
                [
                    {
                        "name": "choice",
                        "label": "Choice",
                        "type": "select",
                        "options": ["yes", "no"],
                    }
                ]
            ),
        )
    )

    assert result["values"] == {"choice": "yes"}
    assert captured_fields[0]["name"] == "choice"
    assert any(getattr(func, "__name__", "") == "_parse_fields" for func in calls)


@pytest.mark.asyncio
async def test_ask_human_expands_short_choice_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_fields: list[dict] = []

    async def fake_create_approval(**kwargs):
        captured_fields.extend(kwargs["fields"])
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        return SimpleNamespace(approved=True, response={"choice": "later"})

    async def fake_send_approval_event(self, *args, **kwargs):
        return None

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)

    await human_tool.AskHumanTool()._arun(
        message="When should I continue?",
        choices=["now", "later"],
    )

    assert captured_fields == [
        {
            "name": "choice",
            "label": "请选择",
            "type": "radio",
            "placeholder": None,
            "default": None,
            "required": True,
            "options": ["now", "later"],
            "multiple": False,
        }
    ]


@pytest.mark.asyncio
async def test_ask_human_expands_multiple_choice_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_fields: list[dict] = []

    async def fake_create_approval(**kwargs):
        captured_fields.extend(kwargs["fields"])
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        return SimpleNamespace(approved=True, response={"choice": ["a", "b"]})

    async def fake_send_approval_event(self, *args, **kwargs):
        return None

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)

    await human_tool.AskHumanTool()._arun(
        message="Pick blockers",
        choices=["a", "b", "c"],
        multiple=True,
    )

    assert captured_fields[0]["type"] == "multi_select"
    assert captured_fields[0]["multiple"] is True
    assert captured_fields[0]["options"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_ask_human_infers_field_type_from_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_fields: list[dict] = []

    async def fake_create_approval(**kwargs):
        captured_fields.extend(kwargs["fields"])
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        return SimpleNamespace(approved=True, response={"choice": "ship it"})

    async def fake_send_approval_event(self, *args, **kwargs):
        return None

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)

    await human_tool.AskHumanTool()._arun(
        message="Decision?",
        fields=[{"options": ["ship it", "hold"], "multiple": False}],
    )

    assert captured_fields[0]["name"] == "choice"
    assert captured_fields[0]["label"] == "请选择"
    assert captured_fields[0]["type"] == "radio"


@pytest.mark.asyncio
async def test_send_approval_event_passes_trace_id_to_dual_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approval_required 必须带 trace_id 双写，否则 Redis 流过期后历史缺失审批卡片。"""
    from src.infra.logging.context import TraceContext
    from src.infra.tool.human_tool.models import FormField

    write_calls: list[dict] = []

    async def fake_write_event(**kwargs):
        write_calls.append(kwargs)
        return True

    fake_dual_writer = SimpleNamespace(write_event=fake_write_event)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer
    )

    approval = SimpleNamespace(id="approval-1", message="需要确认", type="form")
    fields = [FormField(name="choice", label="请选择", type="radio", required=True)]

    await human_tool.AskHumanTool()._send_approval_event(
        approval, "session-1", "run-1", fields, trace_id="trace-1"
    )

    assert len(write_calls) == 1
    assert write_calls[0]["event_type"] == "approval_required"
    assert write_calls[0]["session_id"] == "session-1"
    assert write_calls[0]["run_id"] == "run-1"
    assert write_calls[0]["trace_id"] == "trace-1"
    assert TraceContext.get_request_context() is not None


@pytest.mark.asyncio
async def test_ask_human_forwards_request_trace_id_to_approval_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_arun 应把 TraceContext 的 trace_id 透传给审批事件发送。"""
    from src.infra.logging.context import TraceContext

    captured: list[dict] = []

    async def fake_create_approval(**kwargs):
        return SimpleNamespace(id="approval-1")

    async def fake_wait_for_response(approval_id: str, timeout: int = 300):
        return SimpleNamespace(approved=True, response={"choice": "yes"})

    async def fake_send_approval_event(self, approval, session_id, run_id, fields, trace_id=None):
        captured.append(
            {"session_id": session_id, "run_id": run_id, "trace_id": trace_id}
        )

    monkeypatch.setattr(human_tool, "create_approval", fake_create_approval)
    monkeypatch.setattr(human_tool, "wait_for_response", fake_wait_for_response)
    monkeypatch.setattr(human_tool.AskHumanTool, "_send_approval_event", fake_send_approval_event)

    TraceContext.set_request_context(
        session_id="session-ctx", run_id="run-ctx", trace_id="trace-ctx"
    )
    try:
        await human_tool.AskHumanTool()._arun(message="Continue?", fields=[])
    finally:
        TraceContext.clear_request_context()

    assert captured == [
        {"session_id": "session-ctx", "run_id": "run-ctx", "trace_id": "trace-ctx"}
    ]
