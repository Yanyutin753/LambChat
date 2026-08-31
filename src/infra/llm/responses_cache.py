"""Codex 同款 /v1/responses KV 缓存路由上下文。

openai/codex（codex-rs `core/src/client.rs`）对 Responses API 的缓存策略是
`prompt_cache_key = session_id`：同一会话的所有请求（含子 agent，经父线程
共享）携带同一个路由提示，让前缀相同的请求持续落在同一台缓存机器上。

LambChat 的模型实例按 (模型, 参数) 全局 LRU 缓存、跨会话共享，无法在构造
时固定会话级 key，因此用 ContextVar 在请求执行期传递：

- `BaseGraphAgent` 在 graph 执行任务内 `set_responses_prompt_cache_key()`
  （嵌套子图/子 agent 任务继承上下文，天然共享父会话 key，对齐 codex-rs
  的 `{source}:{parent_thread_id}` 语义）；
- `LambChatOpenAIChatModel._get_request_payload` 在 responses 线格式下把
  当前 key 注入 payload。

仅 async 执行路径生效（同步 `_generate`/`_stream` 在线程池中运行，上下文
不跟随线程），LambChat 全部走 async 路径。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

# OpenAI API 对 prompt_cache_key 的长度上限（同 user/safety_identifier 字段）
_PROMPT_CACHE_KEY_MAX_LENGTH = 64

_responses_prompt_cache_key: ContextVar[Optional[str]] = ContextVar(
    "lambchat_responses_prompt_cache_key", default=None
)


def _sanitize_prompt_cache_key(session_id: object) -> Optional[str]:
    """非字符串/空白/超长的 session_id 一律视为无 key（跳过注入）。"""
    if not isinstance(session_id, str):
        return None
    key = session_id.strip()
    if not key:
        return None
    return key[:_PROMPT_CACHE_KEY_MAX_LENGTH]


def set_responses_prompt_cache_key(session_id: object) -> Token[Optional[str]]:
    """绑定会话级 prompt_cache_key，返回用于 `reset` 的 token。"""
    return _responses_prompt_cache_key.set(_sanitize_prompt_cache_key(session_id))


def reset_responses_prompt_cache_key(token: Token[Optional[str]]) -> None:
    """恢复 set 之前的上下文值（token 为 None 时无操作）。"""
    if token is not None:
        _responses_prompt_cache_key.reset(token)


def current_responses_prompt_cache_key() -> Optional[str]:
    """当前执行上下文的会话级 prompt_cache_key（未设置时为 None）。"""
    return _responses_prompt_cache_key.get()


@contextmanager
def session_prompt_cache_key(session_id: object) -> Iterator[None]:
    """作用域内绑定会话级 key，退出（含异常）后恢复原值。"""
    token = set_responses_prompt_cache_key(session_id)
    try:
        yield
    finally:
        reset_responses_prompt_cache_key(token)
