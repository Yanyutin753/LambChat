"""
ask_human interrupt 模式运行时上下文（issue #218）

interrupt 模式下 ask_human 不再阻塞协程，而是通过 LangGraph interrupt()
挂起图执行，由 respond 路径以 Command(resume=...) 恢复。

对齐 deepagents 官方 HITL 语义：工具内部零副作用（只调用 interrupt()），
审批记录与 SSE 通知由编排层在图挂起后根据 interrupt payload 创建
（见 src/infra/task/hitl.py），因此节点重放不会产生重复副作用，
本模块只标记当前图执行是否支持 interrupt 模式。
"""

from __future__ import annotations

from contextvars import ContextVar

# 当前图执行是否支持 interrupt 模式（由 fast_agent_node 在持久
# checkpointer 可用时设置）
hitl_interrupt_supported: ContextVar[bool] = ContextVar("hitl_interrupt_supported", default=False)
