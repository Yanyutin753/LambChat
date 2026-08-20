from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.infra.tool.human_tool import tool as human_tool


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
