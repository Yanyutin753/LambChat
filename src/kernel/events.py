"""
SSE 事件构建器

用于构建 Server-Sent Events (SSE) 格式的事件。
"""

import json
from typing import Any, Dict


class EventBuilder:
    """
    SSE 事件构建器

    构建标准化的 SSE 事件格式，用于流式输出。

    事件类型:
    - metadata: 会话元数据
    - message:chunk: 文本片段 (纯文本)
    - tool:start: 工具调用开始
    - tool:result: 工具调用结果
    - todo:created: TodoList创建
    - todo:updated: TodoList更新
    - skill:loaded: 技能加载
    - done: 流结束
    - error: 错误
    """

    @staticmethod
    def _build_event(event: str, data: Any) -> Dict[str, Any]:
        """构建事件字典"""
        return {
            "event": event,
            "data": (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)),
        }

    @classmethod
    def metadata(cls, session_id: str, agent_id: str) -> Dict[str, Any]:
        """
        构建元数据事件

        Args:
            session_id: 会话ID
            agent_id: Agent ID

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "metadata",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def message_chunk(cls, content: str) -> Dict[str, Any]:
        """
        构建消息片段事件

        Args:
            content: 文本内容

        Returns:
            SSE 事件字典
        """
        return cls._build_event("message:chunk", content)

    @classmethod
    def tool_start(cls, tool_name: str, tool_input: Any) -> Dict[str, Any]:
        """
        构建工具调用开始事件

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "tool:start",
            {
                "tool": tool_name,
                "input": tool_input,
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def tool_result(cls, tool_name: str, result: Any) -> Dict[str, Any]:
        """
        构建工具调用结果事件

        Args:
            tool_name: 工具名称
            result: 工具输出结果

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "tool:result",
            {
                "tool": tool_name,
                "result": str(result)[:1000],  # 限制结果长度
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def todo_created(cls, todos: list) -> Dict[str, Any]:
        """
        构建 TodoList 创建事件

        Args:
            todos: Todo 列表

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "todo:created",
            {"todos": todos, "timestamp": _get_timestamp()},
        )

    @classmethod
    def todo_updated(cls, todos: list[str], updated_index: int) -> Dict[str, Any]:
        """
        构建 TodoList 更新事件

        Args:
            todos: 更新后的 Todo 列表
            updated_index: 更新的索引

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "todo:updated",
            {
                "todos": todos,
                "updated_index": updated_index,
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def skill_loaded(cls, skill_name: str, description: str = "") -> Dict[str, Any]:
        """
        构建技能加载事件

        Args:
            skill_name: 技能名称
            description: 技能描述

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "skill:loaded",
            {
                "name": skill_name,
                "description": description,
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def done(cls) -> Dict[str, Any]:
        """
        构建流结束事件

        Returns:
            SSE 事件字典
        """
        return cls._build_event("done", {"status": "completed", "timestamp": _get_timestamp()})

    @classmethod
    def error(cls, message: str, error_type: str = "Error") -> Dict[str, Any]:
        """
        构建错误事件

        Args:
            message: 错误消息
            error_type: 错误类型

        Returns:
            SSE 事件字典
        """
        return cls._build_event(
            "error",
            {
                "error": message,
                "type": error_type,
                "timestamp": _get_timestamp(),
            },
        )

    @classmethod
    def thinking(cls, content: str) -> Dict[str, Any]:
        """
        构建思考过程事件

        Args:
            content: 思考内容

        Returns:
            SSE 事件字典
        """
        return cls._build_event("thinking", content)


def _get_timestamp() -> str:
    """获取当前时间戳"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
