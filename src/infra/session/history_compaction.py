"""Lossless transport compaction for reconstructed chat history.

历史读取是无损传输压缩：只合并前端必然按序拼接的流式增量，
不改变任何折叠语义（前端 eventProcessor 对 thinking / tool:args:chunk /
message:chunk 都做「按块标识查找 + 追加」处理，见
frontend/src/hooks/useAgent/eventProcessor.ts）。

两类合并：

1. 相邻合并（message:chunk、无块标识的旧数据）
   仅当两个事件紧邻且身份一致时拼接，保持原有行为。
2. 分组归并（带 thinking_id 的 thinking、带 tool_call_id 的 tool:args:chunk）
   并行子代理/并行工具调用的增量在事件流里交错，相邻合并不生效，
   必须按块标识分组、在首现位置拼接全部内容——与前端「按 thinking_id /
   tool_call_id 反向查找 part 再追加」的实时折叠完全等价。

同一核心同时服务两条链路：

- 历史读取（``compact_history_events``，路由层传输压缩）
- 后台存量合并（``EventMerger`` 传 ``mark_merges=True``，把已完成 trace
  的交错增量归并落库，标记 merged/merged_count 便于观测与幂等）
"""

from __future__ import annotations

from typing import Any

# 写入端随流更新的易变字段（各条增量各不相同），不属于块身份；
# 参与身份比较会让相邻合并对所有真实数据空转。
_STREAM_VOLATILE_DATA_KEYS = frozenset(
    {"timestamp", "started_at", "ended_at", "merged", "merged_count"}
)

_MERGEABLE_EVENT_TYPES = frozenset({"message:chunk", "thinking", "tool:args:chunk"})


def _data_identity(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    return {
        key: value
        for key, value in data.items()
        if key != "content" and key not in _STREAM_VOLATILE_DATA_KEYS
    }


def _envelope_identity(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in {"data", "seq", "timestamp"}}


def _compatible_message_chunks(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("event_type") != "message:chunk" or right.get("event_type") != "message:chunk":
        return False

    left_data = left.get("data")
    right_data = right.get("data")
    if not isinstance(left_data, dict) or not isinstance(right_data, dict):
        return False
    if not isinstance(left_data.get("content"), str) or not isinstance(
        right_data.get("content"), str
    ):
        return False

    if _envelope_identity(left) != _envelope_identity(right):
        return False

    return _data_identity(left_data) == _data_identity(right_data)


def compact_consecutive_message_chunks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only adjacent semantically compatible assistant text chunks."""
    compacted: list[dict[str, Any]] = []
    for source_event in events:
        event = dict(source_event)
        event["data"] = dict(event.get("data") or {})
        if compacted and _compatible_message_chunks(compacted[-1], event):
            previous = compacted[-1]
            merged = event
            merged["data"]["content"] = previous["data"]["content"] + event["data"]["content"]
            compacted[-1] = merged
        else:
            compacted.append(event)
    return compacted


def _block_group_key(event: dict[str, Any]) -> tuple[Any, ...] | None:
    """带块标识的流式事件返回分组键；其余返回 None（走相邻合并）。

    分组键必须精确复刻前端的 part 路由语义（eventProcessor/messageParts），
    否则归并后的拼接顺序与逐条回放不一致：

    - tool:args:chunk：前端 findGeneratingToolIndex 只按 tool_call_id 在
      parts 树中全局查找（无视 agent/depth），因此键只用 (run_id,
      tool_call_id)——即使并行 worker 共用了同一 call id（生产实测发生过），
      归并内容仍等于逐条追加的结果。
    - thinking：depth 0 的前端按 thinking_id 在顶层 parts 反向查找（无视
      agent）；depth > 0 经 addPartToDepth 按 agent 路由进子代理块后再按
      thinking_id 块内合并，故嵌套时 agent 参与键。
    """
    event_type = event.get("event_type")
    data = event.get("data")
    if not isinstance(data, dict):
        return None

    if event_type == "thinking":
        block_id = data.get("thinking_id")
        if not (isinstance(block_id, str) and block_id.strip()):
            return None
        depth = data.get("depth") or 0
        return (
            event.get("run_id"),
            event_type,
            depth,
            data.get("agent_id") if depth else None,
            block_id,
        )

    if event_type == "tool:args:chunk":
        block_id = data.get("tool_call_id")
        if not (isinstance(block_id, str) and block_id.strip()):
            return None
        return (event.get("run_id"), event_type, block_id)

    return None


def _compatible_adjacent_stream_events(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """无块标识流式增量的相邻合并判定：身份一致且内容均为字符串。"""
    if left.get("event_type") not in _MERGEABLE_EVENT_TYPES or left.get("event_type") != right.get(
        "event_type"
    ):
        return False
    left_data = left.get("data")
    right_data = right.get("data")
    if not isinstance(left_data, dict) or not isinstance(right_data, dict):
        return False
    if not isinstance(left_data.get("content"), str) or not isinstance(
        right_data.get("content"), str
    ):
        return False
    if _envelope_identity(left) != _envelope_identity(right):
        return False
    return _data_identity(left_data) == _data_identity(right_data)


def _apply_merge_markers(target: dict[str, Any], delta_event: dict[str, Any]) -> None:
    """存量合并链路（mark_merges=True）的观测标记：合并次数与起止时间。

    多轮合并（已带 merged_count 的目标再并新增量）继续累加，
    started_at 保留最早一次的值。
    """
    data = target["data"]
    data["merged"] = True
    data["merged_count"] = int(data.get("merged_count") or 1) + 1
    if not data.get("started_at"):
        data["started_at"] = target.get("timestamp")
    data["ended_at"] = delta_event.get("timestamp")


def compact_history_events(
    events: list[dict[str, Any]], *, mark_merges: bool = False
) -> list[dict[str, Any]]:
    """无损压缩历史事件：thinking / tool:args:chunk 按块标识归并，
    message:chunk 保持相邻合并（易变流式元数据不参与身份判定）。

    归并事件保留首条增量的位置与信封（seq/timestamp）：前端按
    timestamp 排序后在各消息内按到达顺序创建 part，首现位置与实时
    折叠的 part 顺序一致。

    可合并类型的事件在入列时做浅拷贝（信封 + data 顶层）：后续归并只
    对拷贝做键赋值，输入列表与未参与合并的事件对象不被改动；后台
    合并链路一次要处理数万事件的 trace，避免整树深拷贝。

    mark_merges=True 时在归并目标上叠加 merged/merged_count/
    started_at/ended_at 标记（后台存量合并落库用）。
    """
    compacted: list[dict[str, Any]] = []
    group_target_index: dict[tuple[Any, ...], int] = {}

    for source_event in events:
        event_type = source_event.get("event_type")
        mergeable = event_type in _MERGEABLE_EVENT_TYPES
        # 可合并类型才需要可写的信封/数据拷贝；其余事件原样引用
        event: dict[str, Any] = (
            {**source_event, "data": dict(source_event.get("data") or {})}
            if mergeable
            else source_event
        )
        data = event.get("data")

        group_key = _block_group_key(event)
        if group_key is not None and group_key in group_target_index:
            target = compacted[group_target_index[group_key]]
            target_data = target.get("data")
            delta = data.get("content") if isinstance(data, dict) else None
            if (
                isinstance(target_data, dict)
                and isinstance(target_data.get("content"), str)
                and isinstance(delta, str)
            ):
                target_data["content"] = target_data["content"] + delta
                if mark_merges:
                    _apply_merge_markers(target, event)
                continue
            # 内容形态异常（非字符串）不做拼接，原样落为独立事件
            compacted.append(event)
            continue

        if group_key is not None:
            group_target_index[group_key] = len(compacted)
        elif mergeable and compacted and _compatible_adjacent_stream_events(compacted[-1], event):
            previous = compacted[-1]
            previous["data"]["content"] = previous["data"]["content"] + event["data"]["content"]
            if mark_merges:
                _apply_merge_markers(previous, event)
            continue

        compacted.append(event)

    return compacted
