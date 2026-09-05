"""沙箱统一确认门集成测试：真实 deepagents 图 + SandboxConfirmMiddleware。

用脚本化模型驱动并行工具调用，验证线上复盘发现的三类问题的修复：
1. 并行命令**整批一次 interrupt**（一张审批卡列全 N 项）；
2. 恢复后每个工具**恰好执行一次**、命令与执行一一对应（无 resume 值串用）；
3. 拒绝路径全批拒绝、跨批不共享批复、读类工具不参与确认。

链路与生产一致：interrupt() 真实挂起 → materialize_ask_human_approvals
真实物化 → 按 hitl.py 的映射 {interrupt_id: resume_value} 恢复。
"""

from types import SimpleNamespace
from typing import Any, List

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import src.infra.task.hitl as hitl_mod
from src.infra.agent.middleware.sandbox_confirm import SandboxConfirmMiddleware
from src.infra.task.hitl import materialize_ask_human_approvals
from src.infra.tool.human_tool.runtime import hitl_interrupt_supported
from src.kernel.config import settings

EXECUTED: List[str] = []


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


@tool
def execute(command: str) -> str:
    """执行命令。"""
    EXECUTED.append(command)
    return f"ran {command}"


@tool
def read_file(file_path: str) -> str:
    """读文件。"""
    EXECUTED.append(f"read {file_path}")
    return "content"


class ApprovalRecorder:
    def __init__(self) -> None:
        self.created: List[dict] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_create_approval(**kwargs):
            self.created.append(kwargs)
            return SimpleNamespace(
                id=f"approval-{len(self.created)}", message=kwargs.get("message", ""), type="form"
            )

        async def fake_send_sse(approval, fields, session_id, run_id, trace_id=None, origin=None):
            return None

        monkeypatch.setattr("src.api.routes.human.create_approval", fake_create_approval)
        monkeypatch.setattr(hitl_mod, "_send_approval_sse", fake_send_sse)
        monkeypatch.setattr(
            "src.infra.storage.mongodb.get_approval_storage",
            lambda: SimpleNamespace(list_pending=self._list_pending),
        )

    async def _list_pending(self, session_id=None, user_id=None, limit=100):
        return [
            SimpleNamespace(message=kw["message"], metadata=kw.get("metadata"))
            for kw in self.created
        ]


@pytest.fixture(autouse=True)
def policy_all(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.agent.middleware import sandbox_confirm as mw

    async def fake_lookup(user_id):
        return "all"

    monkeypatch.setattr(mw, "_lookup_confirm_policy", fake_lookup)


@pytest.fixture(autouse=True)
def interrupt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HITL_MODE", "interrupt", raising=False)


@pytest.fixture(autouse=True)
def clear_executed() -> None:
    EXECUTED.clear()


def _graph(model_messages: Any) -> Any:
    return create_deep_agent(
        model=ScriptedModel(messages=iter(model_messages)),
        tools=[execute, read_file],
        middleware=[SandboxConfirmMiddleware(user_id="user-1")],
        checkpointer=InMemorySaver(),
    )


async def _run(graph: Any, graph_input: Any, config: dict) -> None:
    async for _ in graph.astream(graph_input, config, stream_mode="values"):
        pass


def _interrupts(snapshot: Any) -> List[dict]:
    out: List[dict] = []
    tasks = snapshot.tasks
    iterable = tasks.values() if isinstance(tasks, dict) else tasks
    for t in iterable:
        for i in getattr(t, "interrupts", None) or ():
            out.append(dict(i.value, interrupt_id=str(i.id)))
    return out


async def test_parallel_batch_one_card_and_exactly_once_execution(
    recorder_install,
) -> None:
    """三条并行命令：各任务各中断（同消息）→ 物化一张卡 → 扩展恢复全批 →
    各执行恰好一次、命令一一对应（无串用）。"""
    rec = recorder_install
    model_messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "execute", "args": {"command": "df -h"}, "id": "c1", "type": "tool_call"},
                {"name": "execute", "args": {"command": "lsblk"}, "id": "c2", "type": "tool_call"},
                {"name": "execute", "args": {"command": "free -m"}, "id": "c3", "type": "tool_call"},
            ],
        ),
        AIMessage(content="done"),
    ]
    graph = _graph(model_messages)
    config = {"configurable": {"thread_id": "t-batch"}}

    token = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("查磁盘")]}, config)
        snapshot = await graph.aget_state(config)
        intrs = _interrupts(snapshot)
        assert len(intrs) == 3, "并行任务各持一个中断"
        assert len({i["message"] for i in intrs}) == 1, "同批消息完全一致"
        for cmd in ("df -h", "lsblk", "free -m"):
            assert cmd in intrs[0]["message"]
        assert EXECUTED == [], "挂起前零执行"

        # 真实物化：同源同消息去重为一张审批卡
        await materialize_ask_human_approvals(
            snapshot, session_id="s1", run_id="r1", user_id="user-1"
        )
        assert len(rec.created) == 1
        assert rec.created[0]["metadata"]["origin"] == "sandbox_confirm"
        await materialize_ask_human_approvals(
            await graph.aget_state(config), session_id="s1", run_id="r1", user_id="user-1"
        )
        assert len(rec.created) == 1, "重复物化不重复建卡"

        # 节点侧扩展恢复：同批全部中断共享批复值
        from src.infra.task.hitl import expand_sandbox_confirm_resume

        resume_map = await expand_sandbox_confirm_resume(
            graph,
            config,
            {"the-approval-interrupt": {"approved": True, "values": {}}},
            message=intrs[0]["message"],
        )
        assert len(resume_map) == 3
        await _run(graph, Command(resume=resume_map), config)
        snapshot = await graph.aget_state(config)
        assert not snapshot.next, "全批恢复后图应跑完"
        assert sorted(EXECUTED) == ["df -h", "free -m", "lsblk"]
    finally:
        hitl_interrupt_supported.reset(token)


async def test_decline_rejects_whole_batch(recorder_install) -> None:
    """拒绝：扩展映射后全批拒绝、零执行，图正常收尾。"""
    model_messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "execute", "args": {"command": "rm a"}, "id": "c1", "type": "tool_call"},
                {"name": "execute", "args": {"command": "rm b"}, "id": "c2", "type": "tool_call"},
            ],
        ),
        AIMessage(content="user declined"),
    ]
    graph = _graph(model_messages)
    config = {"configurable": {"thread_id": "t-decline"}}

    token = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("删文件")]}, config)
        intrs = _interrupts(await graph.aget_state(config))
        assert len(intrs) == 2 and len({i["message"] for i in intrs}) == 1

        from src.infra.task.hitl import expand_sandbox_confirm_resume

        resume_map = await expand_sandbox_confirm_resume(
            graph,
            config,
            {"x": {"approved": False, "values": {}}},
            message=intrs[0]["message"],
        )
        await _run(graph, Command(resume=resume_map), config)
        snapshot = await graph.aget_state(config)
        assert not snapshot.next
        assert EXECUTED == [], "拒绝后零执行"
        tool_msgs = [
            m for m in snapshot.values["messages"] if m.__class__.__name__ == "ToolMessage"
        ]
        declined = [m for m in tool_msgs if "declined_by_user" in str(m.content)]
        assert len(declined) == 2
    finally:
        hitl_interrupt_supported.reset(token)


async def test_read_tools_execute_without_confirmation(recorder_install) -> None:
    """读类不过门：中断消息只列 execute 项；read 不参与确认。"""
    model_messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "execute", "args": {"command": "du /var"}, "id": "c1", "type": "tool_call"},
                {"name": "read_file", "args": {"file_path": "a.txt"}, "id": "c2", "type": "tool_call"},
            ],
        ),
        AIMessage(content="done"),
    ]
    graph = _graph(model_messages)
    config = {"configurable": {"thread_id": "t-mixed"}}

    token = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("混合")]}, config)
        intrs = _interrupts(await graph.aget_state(config))
        assert all("du /var" in i["message"] for i in intrs)
        assert all("a.txt" not in i["message"] for i in intrs), "读类不进确认清单"

        from src.infra.task.hitl import expand_sandbox_confirm_resume

        resume_map = await expand_sandbox_confirm_resume(
            graph, config, {"x": {"approved": True, "values": {}}}, message=intrs[0]["message"]
        )
        await _run(graph, Command(resume=resume_map), config)
        assert "du /var" in EXECUTED
        assert "read a.txt" in EXECUTED
    finally:
        hitl_interrupt_supported.reset(token)


async def test_second_batch_confirms_again(recorder_install) -> None:
    """跨批隔离：新一批工具调用产生新消息中断 → 新审批卡，互不扩散。"""
    rec = recorder_install
    model_messages = [
        _tool_call("execute", {"command": "cmd-A"}, "c1"),
        AIMessage(content="", tool_calls=[
            {"name": "execute", "args": {"command": "cmd-B"}, "id": "c2", "type": "tool_call"},
        ]),
        AIMessage(content="done"),
    ]
    graph = _graph(model_messages)
    config = {"configurable": {"thread_id": "t-batches"}}

    token = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("第一批")]}, config)
        intrs = _interrupts(await graph.aget_state(config))
        assert len(intrs) == 1 and "cmd-A" in intrs[0]["message"]
        await materialize_ask_human_approvals(
            await graph.aget_state(config), session_id="s1", run_id="r1", user_id="user-1"
        )
        await _run(
            graph,
            Command(resume={intrs[0]["interrupt_id"]: {"approved": True, "values": {}}}),
            config,
        )
        intrs2 = _interrupts(await graph.aget_state(config))
        assert len(intrs2) == 1 and "cmd-B" in intrs2[0]["message"]
        await materialize_ask_human_approvals(
            await graph.aget_state(config), session_id="s1", run_id="r1", user_id="user-1"
        )
        assert len(rec.created) == 2
        await _run(
            graph,
            Command(resume={intrs2[0]["interrupt_id"]: {"approved": True, "values": {}}}),
            config,
        )
        assert sorted(EXECUTED) == ["cmd-A", "cmd-B"]
        assert not (await graph.aget_state(config)).next
    finally:
        hitl_interrupt_supported.reset(token)


async def test_write_tools_included_in_batch(recorder_install) -> None:
    """写类进确认清单：execute + write 并行 → 中断消息列两者 → 恢复全批执行。"""
    model_messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "execute", "args": {"command": "whoami"}, "id": "c1", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "x.txt", "content": "1"}, "id": "c2", "type": "tool_call"},
            ],
        ),
        AIMessage(content="done"),
    ]

    @tool
    def write_file(file_path: str, content: str) -> str:
        """写文件。"""
        EXECUTED.append(f"write {file_path}")
        return "ok"

    graph = create_deep_agent(
        model=ScriptedModel(messages=iter(model_messages)),
        tools=[execute, write_file],
        middleware=[SandboxConfirmMiddleware(user_id="user-1")],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-write"}}

    token = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("写")]}, config)
        intrs = _interrupts(await graph.aget_state(config))
        assert all("whoami" in i["message"] and "x.txt" in i["message"] for i in intrs)

        from src.infra.task.hitl import expand_sandbox_confirm_resume

        resume_map = await expand_sandbox_confirm_resume(
            graph, config, {"x": {"approved": True, "values": {}}}, message=intrs[0]["message"]
        )
        assert len(resume_map) == len(intrs)
        await _run(graph, Command(resume=resume_map), config)
        assert sorted(EXECUTED) == ["whoami", "write x.txt"]
    finally:
        hitl_interrupt_supported.reset(token)


@pytest.fixture
def recorder_install(monkeypatch: pytest.MonkeyPatch) -> ApprovalRecorder:
    rec = ApprovalRecorder()
    rec.install(monkeypatch)
    return rec
