"""ask_human interrupt 模式测试（issue #218）。

对齐 deepagents 官方 HITL：工具内零副作用，只调用 interrupt()；
审批记录由编排层在挂起后创建（见 test_ask_human_graph_interrupt.py）。
"""

import json
from types import SimpleNamespace

import pytest

import src.infra.tool.human_tool.tool as tool_mod
from src.infra.tool.human_tool.runtime import hitl_interrupt_supported


class _FakeInterrupt(BaseException):
    """模拟 langgraph.types.interrupt 首次执行时抛出的 GraphInterrupt。"""

    def __init__(self, value):
        super().__init__("interrupt")
        self.value = value


def _setup_interrupt_mode(monkeypatch, *, resume_value=None):
    monkeypatch.setattr(tool_mod.settings, "HITL_MODE", "interrupt", raising=False)

    calls = SimpleNamespace(created=[], interrupts=[])

    async def fake_create_approval(**kwargs):
        calls.created.append(kwargs)
        raise AssertionError("interrupt 模式工具内不应创建审批（零副作用）")

    async def fake_wait(approval_id, timeout=300):
        raise AssertionError("interrupt 模式不应进入阻塞等待")

    monkeypatch.setattr(tool_mod, "create_approval", fake_create_approval)
    monkeypatch.setattr(tool_mod, "wait_for_response", fake_wait)

    def fake_interrupt(value):
        calls.interrupts.append(value)
        if resume_value is None:
            raise _FakeInterrupt(value)
        return resume_value

    import langgraph.types

    monkeypatch.setattr(langgraph.types, "interrupt", fake_interrupt)
    return calls


@pytest.mark.asyncio
async def test_first_execution_raises_without_side_effects(monkeypatch):
    calls = _setup_interrupt_mode(monkeypatch, resume_value=None)
    token = hitl_interrupt_supported.set(True)
    try:
        tool = tool_mod.AskHumanTool(session_id="s1")
        with pytest.raises(_FakeInterrupt):
            await tool._arun("需要确认", choices=["a", "b"])
    finally:
        hitl_interrupt_supported.reset(token)

    assert calls.created == []
    assert len(calls.interrupts) == 1
    payload = calls.interrupts[0]
    assert payload["kind"] == "ask_human"
    assert payload["message"] == "需要确认"
    # payload 随 checkpoint 持久化，字段必须是纯 JSON（枚举已转字符串）
    assert payload["fields"][0]["type"] == "radio"


@pytest.mark.asyncio
async def test_resume_value_maps_to_success(monkeypatch):
    _setup_interrupt_mode(
        monkeypatch,
        resume_value={"approved": True, "values": {"choice": "a"}},
    )
    token = hitl_interrupt_supported.set(True)
    try:
        tool = tool_mod.AskHumanTool(session_id="s1")
        result = json.loads(await tool._arun("需要确认", choices=["a", "b"]))
    finally:
        hitl_interrupt_supported.reset(token)
    assert result["status"] == "success"
    assert result["values"] == {"choice": "a"}


@pytest.mark.asyncio
async def test_resume_value_maps_to_rejected(monkeypatch):
    _setup_interrupt_mode(monkeypatch, resume_value={"approved": False, "values": {}})
    token = hitl_interrupt_supported.set(True)
    try:
        tool = tool_mod.AskHumanTool(session_id="s1")
        result = json.loads(await tool._arun("需要确认", choices=["a"]))
    finally:
        hitl_interrupt_supported.reset(token)
    assert result["status"] == "rejected"


@pytest.mark.asyncio
async def test_resume_value_defaults_when_missing(monkeypatch):
    _setup_interrupt_mode(monkeypatch, resume_value={"approved": True})
    token = hitl_interrupt_supported.set(True)
    try:
        tool = tool_mod.AskHumanTool(session_id="s1")
        result = json.loads(await tool._arun("需要确认", choices=["a"]))
    finally:
        hitl_interrupt_supported.reset(token)
    assert result["status"] == "success"
    assert result["values"]["choice"] is None  # 字段默认值


@pytest.mark.asyncio
async def test_interrupt_mode_rejects_graph_without_persistent_checkpoint(monkeypatch):
    """无 checkpointer 时必须明确失败，不能静默回退 blocking。"""
    _setup_interrupt_mode(monkeypatch, resume_value=None)
    created = []

    async def fake_create(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(id="approval-1", message=kwargs["message"], type="form")

    async def fake_send(self, approval, session_id, run_id, fields):
        pass

    async def fake_wait(approval_id, timeout=300):
        raise AssertionError("interrupt 模式不应进入阻塞等待")

    monkeypatch.setattr(tool_mod, "create_approval", fake_create)
    monkeypatch.setattr(tool_mod, "wait_for_response", fake_wait)
    monkeypatch.setattr(tool_mod.AskHumanTool, "_send_approval_event", fake_send)

    tool = tool_mod.AskHumanTool(session_id="s1")
    # 不设置 hitl_interrupt_supported（默认 False）
    with pytest.raises(RuntimeError, match="persistent checkpointer"):
        await tool._arun("需要确认", choices=["a", "b"])
    assert created == []
