"""Fallback protection for deepagents' auto-summarization model calls.

deepagents 的 SummarizationMiddleware 在自己的 ``awrap_model_call`` 里直接调用
主模型生成摘要（``_acreate_summary`` → ``model.with_retry().ainvoke``），这条
调用不经过 ``ModelRetryMiddleware`` / ``ModelFallbackMiddleware`` 链。主模型
挂死（首事件超时 / 429 / 5xx）时只有裸的 ``with_retry``（3 次同模型重试），
没有换模型的机会，最终把整个 agent 任务打挂。

本模块在 ``create_deep_agent`` 调用窗口内包装 deepagents 工厂产出的摘要
中间件：摘要失败且属于可重试错误时，用兜底模型重建摘要一次。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from src.infra.llm.retry import is_retryable_model_error

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage

logger = logging.getLogger(__name__)

_FALLBACK_MARKER = "_lambchat_summary_fallback"

# 从 lc SummarizationMiddleware 实例上拷贝到兜底 helper 的配置项，
# 保证兜底摘要使用与主摘要一致的提示词与裁剪预算。
_HELPER_SETTINGS = ("summary_prompt", "trim_tokens_to_summarize", "token_counter", "keep")


async def _summarize_with_fallback(
    helper_settings: dict[str, Any],
    messages_to_summarize: Sequence[AnyMessage],
    *,
    fallback_model: str,
    thinking: dict | None,
) -> str:
    from langchain.agents.middleware import SummarizationMiddleware as LCSummarizationMiddleware

    from src.infra.llm.client import LLMClient

    fallback_llm = await LLMClient.get_model(model=fallback_model, thinking=thinking)
    helper = LCSummarizationMiddleware(model=fallback_llm, **helper_settings)
    return await helper._acreate_summary(list(messages_to_summarize))


def protect_summarization_middleware(
    middleware: Any,
    *,
    fallback_model: str | None,
    thinking: dict | None = None,
) -> Any:
    """给摘要中间件实例的 ``_acreate_summary`` 加"换模型重做"保护。

    无兜底模型、或中间件结构不符合预期（deepagents 版本变化）时原样返回。
    """
    original: Awaitable | None = getattr(middleware, "_acreate_summary", None)
    if not fallback_model or not callable(original):
        return middleware
    if getattr(original, _FALLBACK_MARKER, False):
        return middleware

    lc_helper = getattr(middleware, "_lc_helper", None)
    helper_settings = {
        name: getattr(lc_helper, name)
        for name in _HELPER_SETTINGS
        if lc_helper is not None and getattr(lc_helper, name, None) is not None
    }

    async def _acreate_summary(messages_to_summarize: Sequence[AnyMessage]) -> str:
        try:
            return await original(messages_to_summarize)
        except Exception as exc:
            if not is_retryable_model_error(exc):
                raise
            logger.warning(
                "[SummaryFallback] Summary model failed: %s — retrying summary with %s",
                exc,
                fallback_model,
            )
            try:
                return await _summarize_with_fallback(
                    helper_settings,
                    messages_to_summarize,
                    fallback_model=fallback_model,
                    thinking=thinking,
                )
            except Exception:
                logger.error(
                    "[SummaryFallback] Fallback summary with %s also failed",
                    fallback_model,
                )
                raise

    setattr(_acreate_summary, _FALLBACK_MARKER, True)
    middleware._acreate_summary = _acreate_summary
    return middleware


@contextmanager
def summarization_fallback_patch(
    fallback_model: str | None,
    thinking: dict | None = None,
) -> Iterator[None]:
    """在窗口内让 ``create_deep_agent`` 内部创建的所有摘要中间件带兜底保护。

    ``create_deep_agent`` 是同步函数且在事件循环线程上执行，窗口内不存在
    await 点，因此临时替换模块属性不会与其他协程交错。未配置兜底模型时
    直接透传。
    """
    if not fallback_model:
        yield
        return

    import deepagents.graph as deepagents_graph

    original = deepagents_graph.create_summarization_middleware

    def patched(model: Any, backend: Any, **kwargs: Any) -> Any:
        middleware = original(model, backend, **kwargs)
        try:
            return protect_summarization_middleware(
                middleware, fallback_model=fallback_model, thinking=thinking
            )
        except Exception:
            logger.warning(
                "[SummaryFallback] Could not wrap summarization middleware; "
                "summaries stay on the primary model",
                exc_info=True,
            )
            return middleware

    deepagents_graph.create_summarization_middleware = patched
    try:
        yield
    finally:
        deepagents_graph.create_summarization_middleware = original
