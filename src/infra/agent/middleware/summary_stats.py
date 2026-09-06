"""自动摘要压缩的 token 释放统计。

deepagents 的 SummarizationMiddleware 触发压缩时，被摘要的历史消息会被
替换为一条摘要消息（``_build_new_messages``）。这里在 ``_acreate_summary``
成功返回后，用中间件自己的 token 计数器计算「压缩前 − 压缩后」的上下文
差值，经 presenter 推送一条 ``summary`` SSE 事件（content 为空、携带
``freed_tokens``），随 Redis 流实时下发并按 trace 持久化，前端总结 Item
据此展示本次压缩释放了多少 token。

统计属尽力而为：presenter 缺失、计数器异常等任何失败都只记日志，
绝不影响摘要主流程。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

_STATS_MARKER = "_lambchat_summary_stats"

# 与 langchain SummarizationMiddleware._build_new_messages 保持一致：
# 压缩后留在上下文里的摘要消息正文前缀。
_SUMMARY_MESSAGE_PREFIX = "Here is a summary of the conversation to date:\n\n"


def attach_summary_token_stats(
    middleware: Any,
    *,
    passthrough_markers: tuple[str, ...] = (),
) -> Any:
    """给摘要中间件的 ``_acreate_summary`` 挂上 token 释放统计。

    ``passthrough_markers`` 上的标记若存在于被包装函数，会复制到包装函数上
    （summary_fallback 用它保持兜底保护标记在最外层可见，幂等检查不失效）。
    结构不符合预期（deepagents 版本变化）时原样返回。
    """
    original = getattr(middleware, "_acreate_summary", None)
    token_counter = getattr(middleware, "token_counter", None)
    if not callable(original) or not callable(token_counter):
        return middleware
    if getattr(original, _STATS_MARKER, False):
        return middleware

    async def _acreate_summary_with_stats(messages_to_summarize: Sequence[Any]) -> str:
        summary = await original(messages_to_summarize)
        try:
            await _emit_freed_tokens(token_counter, messages_to_summarize, summary)
        except Exception:
            logger.debug("[SummaryStats] Failed to emit freed-token stats", exc_info=True)
        return summary

    setattr(_acreate_summary_with_stats, _STATS_MARKER, True)
    for marker in passthrough_markers:
        if getattr(original, marker, False):
            setattr(_acreate_summary_with_stats, marker, True)
    middleware._acreate_summary = _acreate_summary_with_stats
    return middleware


def _safe_count(token_counter: Any, messages: list[Any]) -> int | None:
    try:
        value = token_counter(messages)
    except Exception:
        logger.debug("[SummaryStats] Token counter failed", exc_info=True)
        return None
    return value if isinstance(value, int) and value >= 0 else None


async def _emit_freed_tokens(
    token_counter: Any,
    messages_to_summarize: Sequence[Any],
    summary: str,
) -> None:
    from langchain_core.messages import HumanMessage

    before = _safe_count(token_counter, list(messages_to_summarize))
    after = _safe_count(token_counter, [HumanMessage(content=_SUMMARY_MESSAGE_PREFIX + summary)])
    if before is None or after is None:
        return
    freed = before - after
    if freed <= 0:
        return

    presenter, depth = _resolve_presenter()
    if presenter is None:
        return
    await presenter.emit(
        presenter.present_summary("", summary_id=None, depth=depth, freed_tokens=freed)
    )


def _resolve_presenter() -> tuple[Any | None, int]:
    """从当前 LangGraph 运行上下文取 presenter 与事件深度。

    depth 推导对齐 ``AgentEventProcessor._get_agent_context``：
    checkpoint_ns 含「|」视为子代理（depth 1），否则主代理（depth 0）。
    """
    try:
        from langgraph.config import get_config

        config = get_config()
    except Exception:
        return None, 0
    configurable = (config or {}).get("configurable") or {}
    ns = configurable.get("checkpoint_ns") or ""
    depth = 1 if "|" in ns else 0
    return configurable.get("presenter"), depth


__all__ = ["attach_summary_token_stats"]
