"""命令确认策略：needs_confirm 三策略 + terminal_confirm 终端 y/N 交互。

daemon 收到 ``op=exec`` 的 tool_call 后，先经 :func:`needs_confirm` 按
``confirm_policy`` 判定是否需要用户点头：

- ``all``：一切命令都确认（默认，最保守）；
- ``commands``：仅 :data:`MUTATING_PATTERN` 命中的命令确认；
- ``none``：一律放行（无人值守）。

``commands`` 取保守误报取向——宁可多确认一次，不可漏掉一次 ``rm``：

- 变更类命令按**词**匹配（``\\b`` 边界），且必须位于命令首或 ``;``/``&``/``|``/
  空白之后（``echo hi; rm x``、``true && mv a b`` 都命中）；
- 输出重定向 ``>``/``>>`` 与管道 ``|`` 一律命中（静态无法判定管道右侧是否
  消费/改写状态，``cat a > b``、``echo hi | grep x`` 保守确认）；
- 代价是 ``git status`` 这类只读命令也会命中（git 整体在清单内），M2 接受。

:func:`terminal_confirm` 是 M2 的终端交互确认（daemon 是前台 CLI）；
spec §3.5 的网页 HITL 确认属 M3。``input_fn`` 参数供测试注入。
"""

from __future__ import annotations

import re
from collections.abc import Callable

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


def terminal_confirm(command: str, *, input_fn: Callable[[str], str] = input) -> bool:
    """终端 y/N 确认：y/Y/yes（大小写/空白容错）放行，其余（含回车）拒绝。"""
    answer = input_fn(f"允许在本机执行 [{command}] ? (y/N): ").strip().lower()
    return answer in ("y", "yes")
