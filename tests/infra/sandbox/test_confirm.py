"""服务端确认策略：needs_confirm 三档判定 + 统一确认门 confirm_local_op。

needs_confirm 自 client/lambchat_sandbox/confirm.py 移植，语义互锁；
confirm_local_op 复用 ask_human interrupt 全链路（spec §3.5 服务端实现）。
"""

import pytest
from langgraph.errors import GraphBubbleUp, GraphInterrupt

from src.infra.sandbox.confirm import POLICIES, confirm_local_op, needs_confirm
from src.infra.tool.human_tool.runtime import hitl_interrupt_supported


@pytest.mark.parametrize("policy", ["all", "commands"])
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "echo hi; rm x",
        "true && mv a b",
        "cat a > b",
        "echo hi | grep x",
        "python3 -c 'pass' >> log",
    ],
)
def test_mutating_commands_confirm(policy, command):
    assert needs_confirm(command, policy) is True


def test_readonly_ls_passes_under_commands():
    assert needs_confirm("ls -la .", "commands") is False


def test_git_status_confirms_under_commands():
    # 保守误报取向：git 整体在清单内（M2 接受的取舍，移植保持一致）
    assert needs_confirm("git status", "commands") is True


def test_none_policy_passes_everything():
    assert needs_confirm("rm -rf /", "none") is False


def test_all_policy_confirms_everything():
    assert needs_confirm("ls", "all") is True


def test_unknown_policy_raises():
    with pytest.raises(ValueError, match="未知确认策略"):
        needs_confirm("ls", "yolo")


def test_policies_tuple():
    assert POLICIES == ("all", "commands", "none")


# ---- confirm_local_op：统一确认门 ----


@pytest.fixture
def interrupt_supported():
    token = hitl_interrupt_supported.set(True)
    yield
    hitl_interrupt_supported.reset(token)


def test_none_policy_passes_without_interrupt(interrupt_supported):
    # interrupt() 在无图上下文会抛 GraphInterrupt——policy=none 不应触碰它
    assert confirm_local_op("rm -rf /", "none", description="x") is True


def test_all_policy_raises_graph_interrupt_with_ask_human_payload(
    interrupt_supported, monkeypatch
):
    # 无图上下文时 langgraph interrupt() 抛 RuntimeError 而非挂起——
    # monkeypatch 模拟图任务内行为：raise GraphInterrupt(payload)
    import langgraph.types

    def fake_interrupt(payload):
        raise GraphInterrupt(payload)

    monkeypatch.setattr(langgraph.types, "interrupt", fake_interrupt)
    with pytest.raises(GraphBubbleUp) as exc_info:
        confirm_local_op("rm x", "all", description="确认在本机执行命令：\nrm x")
    assert isinstance(exc_info.value, GraphInterrupt)
    payload = exc_info.value.args[0] if exc_info.value.args else None
    assert payload is not None
    assert payload["kind"] == "ask_human"
    assert payload["fields"] == []
    assert "rm x" in payload["message"]


def test_resume_approved_returns_true(interrupt_supported, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(
        langgraph.types, "interrupt", lambda value: {"approved": True, "values": {}}
    )
    assert confirm_local_op("rm x", "all", description="d") is True


def test_resume_rejected_returns_false(interrupt_supported, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(
        langgraph.types, "interrupt", lambda value: {"approved": False, "values": {}}
    )
    assert confirm_local_op("rm x", "all", description="d") is False


def test_resume_non_dict_fails_closed(interrupt_supported, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(langgraph.types, "interrupt", lambda value: None)
    assert confirm_local_op("rm x", "all", description="d") is False


def test_interrupt_unsupported_fails_closed(monkeypatch):
    import langgraph.types

    def _boom(value):
        raise AssertionError("unsupported 时不得调用 interrupt")

    monkeypatch.setattr(langgraph.types, "interrupt", _boom)
    assert confirm_local_op("rm x", "all", description="d") is False
