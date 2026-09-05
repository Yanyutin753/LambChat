"""沙箱执行确认策略：needs_confirm 三档判定。

服务端统一确认门（本地沙箱 exec/文件写/上传，spec §3.5 服务端实现）按
``confirm_policy`` 判定操作是否需要用户确认：

- ``all``：一切操作都确认（默认，最保守）；
- ``commands``：仅 :data:`MUTATING_PATTERN` 命中的命令确认；
- ``none``：一律放行（无人值守）。

``commands`` 取保守误报取向——宁可多确认一次，不可漏掉一次 ``rm``：

- 变更类命令按**词**匹配（``\\b`` 边界），且必须位于命令首或 ``;``/``&``/``|``/
  空白之后（``echo hi; rm x``、``true && mv a b`` 都命中）；
- 输出重定向 ``>``/``>>`` 与管道 ``|`` 一律命中（静态无法判定管道右侧是否
  消费/改写状态，``cat a > b``、``echo hi | grep x`` 保守确认）；
- 代价是 ``git status`` 这类只读命令也会命中（git 整体在清单内），与 M2
  daemon 版语义一致。

正则与 client/lambchat_sandbox/confirm.py 逐字节互锁（该 client 副本随
daemon 侧门一并拆除），防两版漂移。
"""

from __future__ import annotations

import re

MUTATING_PATTERN = re.compile(
    r"(^|[;&|\s])(rm|mv|dd|chmod|chown|curl|wget|pip|npm|git|sudo|mkfs|shutdown|reboot)\b"
    r"|[>|]{1,2}\s*\S"
)

POLICIES = ("all", "commands", "none")


def needs_confirm(command: str, policy: str) -> bool:
    """按 policy 判定 command 是否需要用户确认；未知 policy 抛 ValueError。"""
    if policy == "all":
        return True
    if policy == "commands":
        return MUTATING_PATTERN.search(command) is not None
    if policy == "none":
        return False
    raise ValueError(f"未知确认策略: {policy!r}（可选: {'/'.join(POLICIES)}）")


def confirm_local_op(command: str, policy: str, *, description: str) -> bool:
    """统一确认门：needs_confirm 判定 + ask_human interrupt（服务端，spec §3.5）。

    必须在图任务内的工具调用栈中同步调用（与 AskHumanTool interrupt 模式同
    语义）：挂起时经 materialize_ask_human_approvals 物化审批卡，用户响应后
    图以 Command(resume) 重放本调用栈，interrupt() 返回
    ``{"approved": bool, "values": {...}}``。

    - policy=none 或 needs_confirm 未命中：直接放行，不触碰 interrupt；
    - 图不支持 interrupt（无 checkpointer）：fail-closed 拒绝；
    - 用户拒绝 / resume 值异常：False。

    ``command`` 是送 needs_confirm 判定的哨兵命令（exec 传原始命令，文件写
    传 ``rm {op} {path}`` 前缀哨兵）；``description`` 是审批卡展示文案。
    """
    if not needs_confirm(command, policy):
        return True

    from src.infra.logging import get_logger
    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    if not hitl_interrupt_supported.get():
        get_logger(__name__).warning(
            "[SandboxConfirm] interrupt 不可用，按拒绝收敛（fail-closed）: %s",
            description[:120],
        )
        return False

    from langgraph.types import interrupt

    resume_value = interrupt(
        {
            "kind": "ask_human",
            # 沙箱确认门标记：历史回放据此跳过 ask_human 工具卡合成——
            # 执行卡（等待确认→结果）+ 审批面板已完整表达，避免双卡
            "origin": "sandbox_confirm",
            "message": description,
            "fields": [],
        }
    )
    return bool(isinstance(resume_value, dict) and resume_value.get("approved"))
