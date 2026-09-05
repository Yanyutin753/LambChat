"""工具事件稳定 id：interrupt/resume 重放前后同逻辑调用同 id（修复恢复后重复执行卡）。

langgraph 的 on_tool_start/end 每次执行尝试都换 run_id——确认门（ask_human/
沙箱确认）挂起后图以同任务重放，run_id 变化导致前端/历史把同一执行渲染成
两张卡。稳定键 = checkpoint_ns（任务级，重放不变）+ 工具名 + 参数摘要；
并行同任务多工具靠后两段区分。
"""

from src.infra.agent.events.tool_events import ToolEventMixin


def _event(run_id: str, ns: str | None, name: str = "execute", args: dict | None = None):
    ev = {
        "event": "on_tool_start",
        "name": name,
        "run_id": run_id,
        "data": {"input": args or {"command": "df -h"}},
    }
    if ns is not None:
        ev["metadata"] = {"langgraph_checkpoint_ns": ns}
    return ev


def _id(ev) -> str:
    return ToolEventMixin()._get_tool_call_id(ev)


def test_same_task_same_args_same_id_across_attempts():
    a = _id(_event("run-uuid-1", "tools:338ecfeb"))
    b = _id(_event("run-uuid-2", "tools:338ecfeb"))
    assert a == b
    assert a.startswith("tools:338ecfeb|")


def test_different_args_same_task_get_distinct_ids():
    a = _id(_event("r1", "tools:t1", args={"command": "df -h"}))
    b = _id(_event("r2", "tools:t1", args={"command": "ls"}))
    assert a != b


def test_tool_end_shaped_event_matches_start_id():
    start = _event("r1", "tools:t1", args={"command": "df -h"})
    end = {
        "event": "on_tool_end",
        "name": "execute",
        "run_id": "run-uuid-2",
        "data": {"input": {"command": "df -h"}, "output": "ok"},
        "metadata": {"langgraph_checkpoint_ns": "tools:t1"},
    }
    assert _id(start) == _id(end)


def test_missing_checkpoint_ns_falls_back_to_run_id():
    assert _id(_event("run-uuid-1", None)) == "run-uuid-1"


def test_missing_both_generates_tool_prefix():
    value = _id(_event("", None))
    assert value.startswith("tool_")


def test_distinct_names_same_task_distinct_ids():
    a = _id(_event("r1", "tools:t1", name="execute", args={"command": "x"}))
    b = _id(_event("r2", "tools:t1", name="read", args={"command": "x"}))
    assert a != b
