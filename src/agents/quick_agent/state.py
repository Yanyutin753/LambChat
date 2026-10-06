"""
Quick Agent 状态定义

messages channel 继承 deepagents 的 DeepAgentState（DeltaChannel）：
fast/search/team 的内层图同款格式，跨 agent 切换会话时历史双向互通
（BinaryOperatorAggregate 形状的 messages 读不了 DeltaChannel 的
增量 checkpoint，这是必须同款的原因）。
"""

from typing import Annotated, Any, Dict, List, NotRequired, Optional

from deepagents import DeepAgentState
from langgraph.channels import EphemeralValue


class QuickAgentState(DeepAgentState):
    """
    Quick Agent 状态

    Attributes:
        input: 用户输入
        session_id: 会话 ID
        messages: 消息历史（DeltaChannel + checkpointer，与 deepagents 内层图同款）
        output: 输出结果
        attachments: 用户上传的附件列表（可选）
        context: EphemeralValue 通道——BaseGraphAgent._stream 会把含 Presenter
            等不可序列化对象的 kwargs 以 "context" 键传入初始状态；外层图带
            checkpointer 时未知键会被序列化落库直接报错，声明为临时通道既
            接住该键又不会被持久化。
    """

    input: str
    session_id: str
    output: str
    attachments: Optional[List[Dict[str, Any]]]
    context: NotRequired[Annotated[Any, EphemeralValue]]
