from __future__ import annotations

import threading

"""进程级关闭标志：lifespan 关闭开始后，本实例不得再发起新的恢复/接管。

为什么需要：优雅关闭顺序里 trace/merger 等依赖先于周期调度器关闭，执行器会
先失败并被标记 recoverable；若此时孤儿扫描器仍在跑，垂死实例会把恢复任务
提交给自己即将关闭的 worker，随后被再次杀掉——多一次无效生成，还把恢复锁
占满整个 TTL。该标志只约束本进程（每个副本自治），跨副本协同仍靠 Redis。
"""

_shutting_down = threading.Event()


def mark_shutting_down() -> None:
    """lifespan 关闭入口调用；此后本进程所有扫描/恢复入口静默。"""
    _shutting_down.set()


def clear_shutting_down() -> None:
    """lifespan 启动入口调用，保证进程复用（如测试）间不串状态。"""
    _shutting_down.clear()


def is_shutting_down() -> bool:
    return _shutting_down.is_set()
