"""MCP 加载失败的可观测性辅助（issue #991）。

从 mcp_client.py 拆出以遵守后端单文件 1000 行上限（拆分先例见
mcp_schema_sanitizer）。包含：
- _format_load_error：递归展开 ExceptionGroup 的加载失败日志文本
- _persist_load_status / _schedule_status_write：加载失败及恢复的
  fire-and-forget 落库（面板徽标数据源）
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import urlsplit

from src.infra.logging import get_logger

logger = get_logger(__name__)

# 熔断状态回写的 fire-and-forget 任务引用（防 GC；完成即移除）
_status_write_tasks: set["asyncio.Task[None]"] = set()


def _safe_load_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else "[redacted URL]"
    except ValueError:
        return "[redacted URL]"


def _format_load_error(exc: BaseException, secrets: tuple[str, ...] = ()) -> str:
    """展开加载失败的异常链（含 ExceptionGroup 的全部子异常）。

    asyncio TaskGroup 把真实错误包进 ExceptionGroup，str() 只显示
    "N sub-exception(s)"，必须递归展开才能定位根因（issue #991）。
    """
    parts: list[str] = []

    def _walk(err: BaseException, depth: int) -> None:
        sub_exceptions = getattr(err, "exceptions", None)
        if isinstance(sub_exceptions, (list, tuple)) and sub_exceptions:
            parts.append("  " * depth + f"{type(err).__name__}: {err}")
            for sub in sub_exceptions:
                _walk(sub, depth + 1)
        else:
            parts.append("  " * depth + f"{type(err).__name__}: {err}")

    _walk(exc, 0)
    text = "\n".join(parts)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"https?://[^\s'\"<>]+", lambda m: _safe_load_url(m.group()), text)
    return text[:1000]


async def _persist_load_status(
    is_system: bool,
    server_name: str,
    user_id: Optional[str],
    ok: bool,
    error: Optional[str],
) -> None:
    """把熔断状态迁移落到 server 文档（issue #991 的面板可见性）。"""
    try:
        from src.infra.mcp.storage import MCPStorage

        storage = MCPStorage()
        if is_system:
            await storage.update_system_server_load_status(server_name, ok=ok, error=error)
        elif user_id:
            await storage.update_user_server_load_status(server_name, user_id, ok=ok, error=error)
    except Exception as e:
        logger.debug(f"[MCP] Load-status persistence skipped for '{server_name}': {e}")


def _schedule_status_write(
    is_system: bool,
    server_name: str,
    user_id: Optional[str],
    ok: bool,
    error: Optional[str],
) -> None:
    """Fire-and-forget 调度一次状态落库；失败静默（探测/加载结果优先可见）。"""
    try:
        task = asyncio.create_task(_persist_load_status(is_system, server_name, user_id, ok, error))
    except RuntimeError:  # 无事件循环（理论不可达，防御）
        return
    _status_write_tasks.add(task)
    task.add_done_callback(_status_write_tasks.discard)
