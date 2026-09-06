"""SandboxConfirmMiddleware：本地沙箱确认门的整批单次中断。

背景（2026-09-06 线上复盘）：per-tool 后端门在并行工具场景下，每个工具各自
interrupt，恢复值按中断序号匹配会**串用**（实验复现：给 A 的批准可能被 B
消费、A 不执行），且 N 条并行命令要经历 N 轮挂起-恢复+重复弹卡。本中间件把
门上移到 ToolNode 包裹层：同批 tool_calls **一次 interrupt 覆盖全部**，恢复
后 memo 直通，杜绝串用与逐条恢复。

测试策略：monkeypatch _lookup_confirm_policy 与 langgraph.types.interrupt，
fake request.state 携带 AIMessage（整批 tool_calls），fake handler 记录调用。
"""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.infra.agent import middleware as mw_pkg
from src.infra.agent.middleware.sandbox_confirm import SandboxConfirmMiddleware


def _request(name: str, args: dict, calls: list[dict] | None = None):
    """构造 ToolCallRequest 形状的最小替身（state 携带整批 tool_calls）。"""
    all_calls = calls if calls is not None else [{"name": name, "args": args, "id": "c0"}]
    state = {"messages": [AIMessage(content="", tool_calls=all_calls)]}
    return type("R", (), {"tool_call": {"name": name, "args": args, "id": "c0"}, "state": state})()


class _Recorder:
    def __init__(self):
        self.handled: list[str] = []

    async def handler(self, request):
        self.handled.append(request.tool_call["name"])
        return ToolMessage(
            content="ok", tool_call_id=request.tool_call["id"], name=request.tool_call["name"]
        )


@pytest.fixture
def policy(monkeypatch):
    holder = {"value": "all"}

    async def fake_lookup(user_id, machine_id=None):
        return holder["value"]

    monkeypatch.setattr(mw_pkg.sandbox_confirm, "_lookup_confirm_policy", fake_lookup)
    return holder


@pytest.fixture
def interrupt(monkeypatch):
    import langgraph.types
    from langgraph.errors import GraphInterrupt

    holder = {"resume": None, "payloads": [], "raise": True}

    def fake_interrupt(payload):
        holder["payloads"].append(payload)
        if holder["raise"]:
            raise GraphInterrupt(payload)
        return holder["resume"]

    monkeypatch.setattr(langgraph.types, "interrupt", fake_interrupt)
    return holder


@pytest.fixture
def supported(monkeypatch):
    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    token = hitl_interrupt_supported.set(True)
    yield
    hitl_interrupt_supported.reset(token)


async def test_single_execute_interrupts_once_and_passes_on_approve(policy, interrupt, supported):
    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    result = await mw.awrap_tool_call(_request("execute", {"command": "df -h"}), rec.handler)
    assert rec.handled == ["execute"]
    assert result.content == "ok"
    assert len(interrupt["payloads"]) == 1
    p = interrupt["payloads"][0]
    assert p["kind"] == "ask_human"
    assert p["origin"] == "sandbox_confirm"
    assert "df -h" in p["message"]


async def test_declined_returns_error_tool_message_without_executing(policy, interrupt, supported):
    interrupt["raise"] = False
    interrupt["resume"] = {"approved": False, "values": {}}
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    result = await mw.awrap_tool_call(_request("execute", {"command": "rm x"}), rec.handler)
    assert rec.handled == []
    assert "declined_by_user" in result.content
    assert result.status == "error"


async def test_parallel_batch_each_call_interrupts_with_identical_payload(
    policy, interrupt, supported
):
    """并行整批：每个需确认调用各自 interrupt（任务隔离语义），但携带
    同一份确定性批清单——物化层按 origin+message 去重为一张审批卡。"""
    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}
    batch = [
        {"name": "execute", "args": {"command": "du /home"}, "id": "c1"},
        {"name": "execute", "args": {"command": "du /var"}, "id": "c2"},
        {"name": "execute", "args": {"command": "snap list"}, "id": "c3"},
    ]
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()

    for item in batch:
        await mw.awrap_tool_call(_request("execute", item["args"], batch), rec.handler)

    assert rec.handled == ["execute", "execute", "execute"]
    assert len(interrupt["payloads"]) == 3  # 每任务各一次
    messages = {p["message"] for p in interrupt["payloads"]}
    assert len(messages) == 1  # 消息完全一致（同批同卡）
    msg = interrupt["payloads"][0]["message"]
    assert "du /home" in msg and "du /var" in msg and "snap list" in msg


async def test_replay_each_task_interrupt_returns_batch_decision(policy, interrupt, supported):
    """恢复重放：各任务 interrupt() 返回（扩展映射后的）批复值，各自执行。"""
    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}
    batch = [
        {"name": "execute", "args": {"command": "ls"}, "id": "c1"},
        {"name": "write_file", "args": {"file_path": "a.txt", "content": "x"}, "id": "c2"},
    ]
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    await mw.awrap_tool_call(_request("execute", batch[0]["args"], batch), rec.handler)
    await mw.awrap_tool_call(_request("write_file", batch[1]["args"], batch), rec.handler)
    assert rec.handled == ["execute", "write_file"]
    assert len({p["message"] for p in interrupt["payloads"]}) == 1
    msg = interrupt["payloads"][0]["message"]
    assert "a.txt" in msg


async def test_policy_none_passes_without_interrupt(policy, interrupt, supported):
    policy["value"] = "none"
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    await mw.awrap_tool_call(_request("execute", {"command": "rm -rf /"}), rec.handler)
    assert rec.handled == ["execute"]
    assert interrupt["payloads"] == []


async def test_policy_commands_readonly_command_skips(policy, interrupt, supported):
    policy["value"] = "commands"
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    await mw.awrap_tool_call(_request("execute", {"command": "ls"}), rec.handler)
    assert rec.handled == ["execute"]
    assert interrupt["payloads"] == []


async def test_non_confirmable_tool_passthrough(policy, interrupt, supported):
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    await mw.awrap_tool_call(_request("read_file", {"file_path": "a"}), rec.handler)
    assert rec.handled == ["read_file"]
    assert interrupt["payloads"] == []


async def test_unsupported_hitl_fails_closed(policy, interrupt, supported, monkeypatch):
    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    token = hitl_interrupt_supported.set(False)
    try:
        mw = SandboxConfirmMiddleware(user_id="u1")
        rec = _Recorder()
        result = await mw.awrap_tool_call(_request("execute", {"command": "df -h"}), rec.handler)
        assert rec.handled == []
        assert "declined_by_user" in result.content
    finally:
        hitl_interrupt_supported.reset(token)


async def test_memo_scoped_per_middleware_batch_not_global(policy, interrupt, supported):
    """不同批（新 AIMessage）不共享批复：第二批重新走门。"""
    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}
    mw = SandboxConfirmMiddleware(user_id="u1")
    rec = _Recorder()
    b1 = [{"name": "execute", "args": {"command": "a1"}, "id": "c1"}]
    b2 = [{"name": "execute", "args": {"command": "a2"}, "id": "c2"}]
    await mw.awrap_tool_call(_request("execute", {"command": "a1"}, b1), rec.handler)
    await mw.awrap_tool_call(_request("execute", {"command": "a2"}, b2), rec.handler)
    assert len(interrupt["payloads"]) == 2


async def test_cloud_policy_resolver_all_gates(supported):
    """云端策略源（部署配置）：all 过门；none 直通。"""
    mw_all = SandboxConfirmMiddleware(user_id="u1", policy_resolver=_const_policy("all"))
    mw_none = SandboxConfirmMiddleware(user_id="u1", policy_resolver=_const_policy("none"))
    rec = _Recorder()

    # none 直通不过门
    await mw_none.awrap_tool_call(_request("execute", {"command": "rm -rf /"}), rec.handler)
    assert rec.handled == ["execute"]

    # all 过门（interrupt 打桩在 fixture 外，这里手工验证走中断分支）
    import langgraph.types
    from langgraph.errors import GraphInterrupt

    class _Raise:
        def __bool__(self):
            return True

    called = []
    orig = langgraph.types.interrupt

    def fake(payload):
        called.append(payload)
        raise GraphInterrupt(payload)

    langgraph.types.interrupt = fake
    try:
        await mw_all.awrap_tool_call(_request("execute", {"command": "rm -rf /"}), rec.handler)
    except GraphInterrupt:
        pass
    finally:
        langgraph.types.interrupt = orig
    assert len(called) == 1


def _const_policy(value: str):
    async def resolver():
        return value

    return resolver


# ---------- AppError 护盾：单命令失败不再击穿整个 run ----------


async def test_app_error_from_handler_becomes_error_tool_message(policy, interrupt, supported):
    """后端派发失败（超时/离线/exec_failed）转错误 ToolMessage，模型可继续。"""
    from src.kernel.errors import AppError, ErrorCode

    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}

    async def failing_handler(request):
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": 30})

    mw = SandboxConfirmMiddleware(user_id="u1")
    result = await mw.awrap_tool_call(_request("execute", {"command": "du /"}), failing_handler)
    assert result.status == "error"
    assert "timed out after 30s" in result.content
    assert "{{" not in result.content


async def test_read_tool_app_error_also_shielded(policy, interrupt, supported):
    """非确认类工具（读）同样受护盾——读失败也不该打死对话。"""
    from src.kernel.errors import AppError, ErrorCode

    async def failing_handler(request):
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    mw = SandboxConfirmMiddleware(user_id="u1")
    result = await mw.awrap_tool_call(_request("read_file", {"file_path": "x"}), failing_handler)
    assert result.status == "error"
    assert "offline" in result.content.lower()


async def test_programming_error_still_propagates(policy, interrupt, supported):
    """非业务异常（编程错误）照旧上抛——护盾不掩盖 bug。"""
    import pytest as _pytest

    interrupt["raise"] = False
    interrupt["resume"] = {"approved": True, "values": {}}

    async def buggy_handler(request):
        raise TypeError("bug")

    mw = SandboxConfirmMiddleware(user_id="u1")
    with _pytest.raises(TypeError):
        await mw.awrap_tool_call(_request("execute", {"command": "ls"}), buggy_handler)


# ---------------------------------------------------------------------------
# 多机：确认门策略按目标机解析
# ---------------------------------------------------------------------------


async def test_registry_policy_resolver_passes_machine_id(monkeypatch):
    from src.infra.agent.middleware import sandbox_confirm

    calls: list[tuple[str, str | None]] = []

    class _FakeRegistry:
        async def get_confirm_policy(self, user_id, machine_id=None):
            calls.append((user_id, machine_id))
            return "none"

    monkeypatch.setattr(sandbox_confirm, "SandboxClientRegistry", _FakeRegistry)
    resolver = sandbox_confirm._RegistryPolicyResolver("u1", machine_id="mac1")
    assert await resolver() == "none"
    assert calls == [("u1", "mac1")]
