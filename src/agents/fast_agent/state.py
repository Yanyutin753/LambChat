"""
Fast Agent 状态定义 - 极简状态
"""

from typing import Any, Dict, List, Optional, TypedDict


class FastAgentState(TypedDict):
    """
    Fast Agent 状态 - 最小化字段

    Attributes:
        input: 用户输入
        session_id: 会话 ID
        messages: 消息历史
        output: 输出结果
        attachments: 用户上传的附件列表（可选）
    """

    input: str
    session_id: str
    messages: List[Any]
    output: str
    attachments: Optional[List[Dict[str, Any]]]
