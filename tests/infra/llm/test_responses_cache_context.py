"""responses prompt cache key 的跨 context 安全性回归。

生产事故（main-20260913-081350）：stall 看门狗把每个 __anext__ 包成独立
asyncio.Task（context 副本），36072e4a 的入口 set + finally reset 组合导致
「Token was created in a different Context」崩溃且后续事件丢失 key。
"""

import asyncio

from src.infra.llm.responses_cache import (
    current_responses_prompt_cache_key,
    reset_responses_prompt_cache_key,
    set_responses_prompt_cache_key,
)


async def test_reset_in_different_context_degrades_silently():
    """token 在别的 context 副本里 reset 不再抛 ValueError。"""
    import contextvars

    token_holder = {}
    ctx_a = contextvars.copy_context()
    ctx_a.run(lambda: token_holder.setdefault("token", set_responses_prompt_cache_key("session-a")))

    ctx_b = contextvars.copy_context()
    # 事故现场：token 属于 ctx_a，在 ctx_b 里 reset 此前抛 ValueError
    ctx_b.run(lambda: reset_responses_prompt_cache_key(token_holder["token"]))


async def test_rebind_per_event_survives_task_copies():
    """模拟看门狗迭代：每个 __anext__ 是独立 Task（context 副本）。"""

    async def agent_like_stream(session_id):
        for i in range(3):
            from src.infra.llm.responses_cache import set_responses_prompt_cache_key

            set_responses_prompt_cache_key(session_id)
            yield {"i": i, "key": current_responses_prompt_cache_key()}

    async def consume_like_watchdog():
        it = agent_like_stream("session-x")
        keys = []
        while True:
            task = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({task})
            if task.cancelled():
                break
            try:
                event = task.result()
            except StopAsyncIteration:
                break
            keys.append(event["key"])
        return keys

    keys = await consume_like_watchdog()
    assert keys == ["session-x", "session-x", "session-x"]
