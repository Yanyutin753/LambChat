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
