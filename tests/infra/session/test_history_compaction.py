from __future__ import annotations

from copy import deepcopy

import pytest

from src.infra.session.history_compaction import (
    compact_consecutive_message_chunks,
    compact_history_events,
)

# 写入端随流更新的易变字段：不影响前端折叠语义，不应参与合并身份判定
STREAM_VOLATILE_DATA_KEYS = {"timestamp", "started_at", "ended_at", "merged", "merged_count"}


def _chunk(
    content: str,
    *,
    seq: int,
    trace_id: str = "trace-1",
    run_id: str = "run-1",
    agent_id: str = "main",
    depth: int = 0,
    **extra_data,
) -> dict:
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "event_type": "message:chunk",
        "data": {
            "content": content,
            "agent_id": agent_id,
            "depth": depth,
            **extra_data,
        },
        "seq": seq,
        "timestamp": f"2026-08-12T00:00:{seq:02d}Z",
    }


def _thinking(
    content: str,
    *,
    seq: int,
    thinking_id: str | None = "tid-1",
    trace_id: str = "trace-1",
    run_id: str = "run-1",
    agent_id: str = "main",
    depth: int | None = None,
    **extra_data,
) -> dict:
    data: dict = {
        "content": content,
        "agent_id": agent_id,
        "depth": depth,
    }
    if thinking_id is not None:
        data["thinking_id"] = thinking_id
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "event_type": "thinking",
        "data": {**data, **extra_data},
        "seq": seq,
        "timestamp": f"2026-08-12T00:00:{seq:02d}Z",
    }


def _tool_args(
    content: str,
    *,
    seq: int,
    tool: str = "read_file",
    tool_call_id: str | None = "call-1",
    trace_id: str = "trace-1",
    run_id: str = "run-1",
    agent_id: str = "main",
    depth: int | None = 0,
    **extra_data,
) -> dict:
    data: dict = {
        "content": content,
        "tool": tool,
        "agent_id": agent_id,
        "depth": depth,
    }
    if tool_call_id is not None:
        data["tool_call_id"] = tool_call_id
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "event_type": "tool:args:chunk",
        "data": {**data, **extra_data},
        "seq": seq,
        "timestamp": f"2026-08-12T00:00:{seq:02d}Z",
    }


def _tool_start(seq: int, tool: str = "read_file", tool_call_id: str = "call-1") -> dict:
    return {
        "trace_id": "trace-1",
        "run_id": "run-1",
        "event_type": "tool:start",
        "data": {"tool": tool, "tool_call_id": tool_call_id, "args": {}},
        "seq": seq,
        "timestamp": f"2026-08-12T00:00:{seq:02d}Z",
    }


# ---------------------------------------------------------------------------
# 旧入口（相邻 message:chunk 合并）行为保持
# ---------------------------------------------------------------------------


def test_compacts_only_consecutive_compatible_message_chunks() -> None:
    tool_event = {
        "trace_id": "trace-1",
        "run_id": "run-1",
        "event_type": "tool:start",
        "data": {"name": "search"},
        "seq": 3,
    }
    events = [
        _chunk("a", seq=1),
        _chunk("b", seq=2),
        tool_event,
        _chunk("c", seq=4),
    ]

    compacted = compact_consecutive_message_chunks(events)

    assert [event["event_type"] for event in compacted] == [
        "message:chunk",
        "tool:start",
        "message:chunk",
    ]
    assert [
        event["data"]["content"] for event in compacted if event["event_type"] == "message:chunk"
    ] == ["ab", "c"]
    assert compacted[0]["seq"] == 2
    assert compacted[0]["timestamp"] == "2026-08-12T00:00:02Z"


def test_does_not_merge_across_identity_or_data_boundaries() -> None:
    events = [
        _chunk("a", seq=1),
        _chunk("b", seq=2, trace_id="trace-2"),
        _chunk("c", seq=3, trace_id="trace-2", run_id="run-2"),
        _chunk("d", seq=4, trace_id="trace-2", run_id="run-2", depth=1),
        _chunk("e", seq=5, trace_id="trace-2", run_id="run-2", depth=1, agent_id="sub"),
        _chunk(
            "f",
            seq=6,
            trace_id="trace-2",
            run_id="run-2",
            depth=1,
            agent_id="sub",
            channel="analysis",
        ),
    ]

    compacted = compact_consecutive_message_chunks(events)

    assert [event["data"]["content"] for event in compacted] == ["a", "b", "c", "d", "e", "f"]


def test_compaction_does_not_mutate_inputs() -> None:
    events = [_chunk("a", seq=1), _chunk("b", seq=2)]
    original = deepcopy(events)

    compacted = compact_consecutive_message_chunks(events)

    assert events == original
    assert compacted is not events
    assert compacted[0] is not events[0]


# ---------------------------------------------------------------------------
# compact_history_events：thinking / tool:args:chunk 分组归并
# （并行子代理流交错，相邻合并不生效，必须按块标识分组）
# ---------------------------------------------------------------------------


def test_merges_interleaved_thinking_streams_by_thinking_id() -> None:
    """并行子代理的 thinking 增量交错落库：按 thinking_id 分组归并，
    保持首现位置与流内顺序（与前端按 thinking_id 反向扫描拼接等价）。"""
    events = [
        _thinking("A1", seq=1, thinking_id="tid-a"),
        _thinking("B1", seq=2, thinking_id="tid-b"),
        _tool_start(3),
        _thinking("A2", seq=4, thinking_id="tid-a"),
        _thinking("B2", seq=5, thinking_id="tid-b"),
        _thinking("A3", seq=6, thinking_id="tid-a"),
    ]

    compacted = compact_history_events(events)

    assert [event["event_type"] for event in compacted] == [
        "thinking",
        "thinking",
        "tool:start",
    ]
    assert compacted[0]["data"]["content"] == "A1A2A3"
    assert compacted[0]["data"]["thinking_id"] == "tid-a"
    assert compacted[1]["data"]["content"] == "B1B2"
    assert compacted[1]["data"]["thinking_id"] == "tid-b"
    # 归并事件保留首条增量的事件位置与信封（seq/timestamp）
    assert compacted[0]["seq"] == 1
    assert compacted[0]["timestamp"] == "2026-08-12T00:00:01Z"


def test_does_not_merge_thinking_across_identity_boundaries() -> None:
    events = [
        _thinking("a", seq=1, thinking_id="tid-1"),
        _thinking("b", seq=2, thinking_id="tid-2"),
        _thinking("c", seq=3, thinking_id="tid-1", run_id="run-2"),
        _thinking("d", seq=4, thinking_id="tid-1", depth=1),
        # 嵌套思考按 agent 路由进不同子代理块——agent 是边界
        _thinking("e", seq=5, thinking_id="tid-x", depth=1, agent_id="sub-a"),
        _thinking("f", seq=6, thinking_id="tid-x", depth=1, agent_id="sub-b"),
    ]

    compacted = compact_history_events(events)

    assert [event["data"]["content"] for event in compacted] == ["a", "b", "c", "d", "e", "f"]


def test_top_level_thinking_ignores_agent_id_in_grouping() -> None:
    """depth 0 的前端按 thinking_id 在顶层 parts 查找（无视 agent_id）：
    顶层思考流跨 agent 仍合并进同一块。"""
    events = [
        _thinking("a", seq=1, thinking_id="tid-1", agent_id="main"),
        _thinking("b", seq=2, thinking_id="tid-1", agent_id="other"),
    ]

    compacted = compact_history_events(events)

    assert [event["data"]["content"] for event in compacted] == ["ab"]


def test_thinking_without_thinking_id_merges_only_adjacent() -> None:
    """无 thinking_id 的旧数据无法安全跨事件归并，退化为相邻合并。"""
    events = [
        _thinking("a", seq=1, thinking_id=None),
        _thinking("b", seq=2, thinking_id=None),
        _tool_start(3),
        _thinking("c", seq=4, thinking_id=None),
    ]

    compacted = compact_history_events(events)

    assert [
        event["data"]["content"] for event in compacted if event["event_type"] == "thinking"
    ] == ["ab", "c"]


def test_merges_tool_args_chunks_by_tool_call_id_across_interleaving() -> None:
    """并行工具调用的参数增量交错：按 tool_call_id 分组归并。"""
    events = [
        _tool_args('{"a"', seq=1, tool_call_id="call-1"),
        _tool_args('{"b"', seq=2, tool_call_id="call-2", tool="grep"),
        _tool_args(": 1", seq=3, tool_call_id="call-1"),
        _tool_start(4),
        _tool_args(": 2}", seq=5, tool_call_id="call-2", tool="grep"),
        _tool_args("}", seq=6, tool_call_id="call-1"),
    ]

    compacted = compact_history_events(events)

    assert [event["event_type"] for event in compacted] == [
        "tool:args:chunk",
        "tool:args:chunk",
        "tool:start",
    ]
    assert compacted[0]["data"]["content"] == '{"a": 1}'
    assert compacted[0]["data"]["tool_call_id"] == "call-1"
    assert compacted[1]["data"]["content"] == '{"b": 2}'
    assert compacted[1]["data"]["tool_call_id"] == "call-2"
    assert compacted[0]["seq"] == 1


def test_parallel_same_tool_calls_merge_by_call_id_independently() -> None:
    """同名工具并行调用（如批量上传下载）各有独立 tool_call_id：
    按调用 id 分别归并，绝不能按工具名并组串参数。"""
    events = [
        _tool_args('{"u": 1', seq=1, tool_call_id="call-1"),
        _tool_args('{"u": 2', seq=2, tool_call_id="call-2"),
        _tool_args("}", seq=3, tool_call_id="call-1"),
        _tool_args("}", seq=4, tool_call_id="call-2"),
        _tool_args('{"u": 3}', seq=5, tool_call_id="call-3"),
    ]

    compacted = compact_history_events(events)

    assert [(event["data"]["tool_call_id"], event["data"]["content"]) for event in compacted] == [
        ("call-1", '{"u": 1}'),
        ("call-2", '{"u": 2}'),
        ("call-3", '{"u": 3}'),
    ]


def test_tool_args_without_call_id_merges_only_adjacent_same_tool() -> None:
    events = [
        _tool_args("a", seq=1, tool_call_id=None),
        _tool_args("b", seq=2, tool_call_id=None),
        _tool_args("c", seq=3, tool_call_id=None, tool="grep"),
        _tool_start(4),
        _tool_args("d", seq=5, tool_call_id=None),
    ]

    compacted = compact_history_events(events)

    assert [
        event["data"]["content"] for event in compacted if event["event_type"] == "tool:args:chunk"
    ] == ["ab", "c", "d"]


def test_message_chunk_merge_ignores_stream_volatile_fields() -> None:
    """生产数据里 message:chunk 携带逐条变化的 started_at/ended_at/merged 等
    流式元数据——它们不属于块身份，参与比较会让压缩空转。"""
    events = [
        _chunk("a", seq=1, started_at="T1", ended_at="T1", merged=False),
        _chunk("b", seq=2, started_at="T1", ended_at="T2", merged=True, merged_count=2),
    ]

    compacted = compact_history_events(events)

    assert [event["data"]["content"] for event in compacted] == ["ab"]


def test_message_chunk_merge_still_respects_text_identity() -> None:
    events = [
        _chunk("a", seq=1, text_id="t1"),
        _chunk("b", seq=2, text_id="t2"),
        _chunk("c", seq=3, text_id="t2", depth=1),
    ]

    compacted = compact_history_events(events)

    assert [event["data"]["content"] for event in compacted] == ["a", "b", "c"]


def test_thinking_merge_ignores_stream_volatile_fields() -> None:
    events = [
        _thinking("a", seq=1, thinking_id="tid-1", started_at="T1", merged=False),
        _thinking("b", seq=2, thinking_id="tid-1", ended_at="T9", merged=True, merged_count=7),
    ]

    compacted = compact_history_events(events)

    assert [event["data"]["content"] for event in compacted] == ["ab"]


def test_non_string_content_is_never_merged() -> None:
    weird = {
        "trace_id": "trace-1",
        "run_id": "run-1",
        "event_type": "thinking",
        "data": {"content": {"not": "a string"}, "thinking_id": "tid-1", "depth": None},
        "seq": 1,
        "timestamp": "2026-08-12T00:00:01Z",
    }
    events = [
        weird,
        _thinking("b", seq=2, thinking_id="tid-1"),
    ]

    compacted = compact_history_events(events)

    assert len(compacted) == 2
    assert compacted[0]["data"]["content"] == {"not": "a string"}
    assert compacted[1]["data"]["content"] == "b"


def test_history_compaction_does_not_mutate_inputs() -> None:
    events = [
        _thinking("a", seq=1, thinking_id="tid-1"),
        _thinking("b", seq=2, thinking_id="tid-1"),
        _chunk("c", seq=3),
        _chunk("d", seq=4),
    ]
    original = deepcopy(events)

    compacted = compact_history_events(events)

    assert events == original
    assert compacted is not events
    assert compacted[0] is not events[0]


def test_mixed_stream_compaction_end_to_end() -> None:
    """搜索代理典型交错流：thinking + 工具参数 + 正文混合，
    各自按块标识归并，互不干扰。"""
    events = [
        _thinking("t1.", seq=1, thinking_id="tid-1", agent_id="search"),
        _tool_args('{"q"', seq=2, tool_call_id="call-1", agent_id="search"),
        _thinking("t2.", seq=3, thinking_id="tid-2", agent_id="search"),
        _tool_args(": 1}", seq=4, tool_call_id="call-1", agent_id="search"),
        _thinking("t3.", seq=5, thinking_id="tid-1", agent_id="search"),
        _tool_start(6),
        _chunk("hello ", seq=7),
        _chunk("world", seq=8),
        _thinking("t4.", seq=9, thinking_id="tid-2", agent_id="search"),
    ]

    compacted = compact_history_events(events)

    assert [event["event_type"] for event in compacted] == [
        "thinking",
        "tool:args:chunk",
        "thinking",
        "tool:start",
        "message:chunk",
    ]
    assert compacted[0]["data"]["content"] == "t1.t3."
    assert compacted[1]["data"]["content"] == '{"q": 1}'
    assert compacted[2]["data"]["content"] == "t2.t4."
    assert compacted[4]["data"]["content"] == "hello world"


@pytest.mark.parametrize(
    "factory",
    [
        lambda seq: _chunk("a", seq=seq),
        lambda seq: _thinking("a", seq=seq),
        lambda seq: _tool_args("a", seq=seq),
    ],
)
def test_empty_and_single_events_pass_through(factory) -> None:
    assert compact_history_events([]) == []
    single = factory(1)
    assert compact_history_events([single]) == [single]
