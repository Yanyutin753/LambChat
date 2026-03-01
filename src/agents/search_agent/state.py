"""
Search Agent 状态定义
"""

from typing import Any, Dict, List, Optional, TypedDict


class SearchAgentState(TypedDict):
    """
    Search Agent 状态

    Attributes:
        input: 用户输入
        session_id: 会话 ID
        messages: 消息历史
        output: 输出结果
        context: Agent 上下文（运行时注入）
        attachments: 用户上传的附件列表
    """

    input: str
    session_id: str
    messages: List[Any]
    output: str
    context: Optional[Dict[str, Any]]
    attachments: Optional[List[Dict[str, Any]]]
