"""Fallback protection for deepagents' auto-summarization model calls.

deepagents 的 SummarizationMiddleware 在自己的 ``awrap_model_call`` 里直接调用
主模型生成摘要（``_acreate_summary`` → ``model.with_retry().ainvoke``），这条
调用不经过 ``ModelRetryMiddleware`` / ``ModelFallbackMiddleware`` 链。主模型
挂死（首事件超时 / 429 / 5xx）时只有裸的 ``with_retry``（3 次同模型重试），
没有换模型的机会，最终把整个 agent 任务打挂。

本模块在 ``create_deep_agent`` 调用窗口内包装 deepagents 工厂产出的摘要
中间件：摘要失败且属于可重试错误或鉴权失败（401/403，同 key 重试无意义、
换模型才可能恢复）时，用兜底模型重建摘要一次。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from src.infra.agent.middleware.summary_stats import attach_summary_token_stats
from src.infra.llm.retry import is_auth_model_error, is_retryable_model_error

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage

logger = logging.getLogger(__name__)

_FALLBACK_MARKER = "_lambchat_summary_fallback"

# 图片的真实上下文成本估算（对齐 codex RESIZED_IMAGE_BYTES_ESTIMATE=7373 字节 ÷ 4
# 字节/token ≈ 1844）。langchain 默认按 85 token/张计，图片再多也推不动压缩触发器。
_IMAGE_TOKEN_ESTIMATE = 1844

# 从 lc SummarizationMiddleware 实例上拷贝到兜底 helper 的配置项，
# 保证兜底摘要使用与主摘要一致的提示词与裁剪预算。
_HELPER_SETTINGS = ("summary_prompt", "trim_tokens_to_summarize", "token_counter", "keep")


def _image_aware_counter_for(model: Any):
    """返回按真实成本计价的 token 计数器（保留 langchain 的模型调参与用量校准）。

    等价于 langchain 的 ``_get_approximate_token_counter``，但把每张图片按
    ``_IMAGE_TOKEN_ESTIMATE`` 计价，使带图会话能正确触发自动摘要压缩。
    """
    from functools import partial

    from langchain_core.messages.utils import count_tokens_approximately

    if str(getattr(model, "_llm_type", "")).startswith("anthropic-chat"):
        return partial(
            count_tokens_approximately,
            use_usage_metadata_scaling=True,
            chars_per_token=3.3,
            tokens_per_image=_IMAGE_TOKEN_ESTIMATE,
        )
    return partial(
        count_tokens_approximately,
        use_usage_metadata_scaling=True,
        tokens_per_image=_IMAGE_TOKEN_ESTIMATE,
    )


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
            # 鉴权失败（401/403）对同一把 key 永不瞬态，但换模型（不同 key）仍可能成功，
            # 与瞬态错误同样走兜底重做，避免裸 401 直接打挂整个 agent 任务
            if not (is_retryable_model_error(exc) or is_auth_model_error(exc)):
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
    """在窗口内增强 ``create_deep_agent`` 内部创建的所有摘要中间件。

    无论是否配置兜底模型，都注入图片感知 token 计数器（图片按真实成本计价，
    否则带图会话永远达不到压缩触发线）；配置了兜底模型时额外给摘要调用加
    "换模型重做"保护。

    ``create_deep_agent`` 是同步函数且在事件循环线程上执行，窗口内不存在
    await 点，因此临时替换模块属性不会与其他协程交错。
    """
    import deepagents.graph as deepagents_graph

    original = deepagents_graph.create_summarization_middleware

    def patched(model: Any, backend: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("token_counter", _image_aware_counter_for(model))
        middleware = original(model, backend, **kwargs)
        # 兜底保护先套、stats 包装在最外层：主模型或兜底模型任一路径成功，
        # stats 都能基于最终摘要文本计算；stats 包装同时透传兜底标记，
        # 保证 protect 的幂等检查与外层 introspection 不失效。
        if fallback_model:
            try:
                middleware = protect_summarization_middleware(
                    middleware, fallback_model=fallback_model, thinking=thinking
                )
            except Exception:
                logger.warning(
                    "[SummaryFallback] Could not wrap summarization middleware; "
                    "summaries stay on the primary model",
                    exc_info=True,
                )
        return attach_summary_token_stats(middleware, passthrough_markers=(_FALLBACK_MARKER,))

    deepagents_graph.create_summarization_middleware = patched
    try:
        yield
    finally:
        deepagents_graph.create_summarization_middleware = original
