"""Detached extraction must not inherit the foreground graph's usage callbacks."""

import asyncio

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables.config import ensure_config
from langgraph.graph import END, START, StateGraph

from src.infra.memory import extraction


async def test_delayed_extraction_has_no_foreground_graph_callbacks_or_runtime(monkeypatch):
    release = asyncio.Event()
    observed = {}
    foreground_model_starts = []

    class ForegroundUsage(AsyncCallbackHandler):
        async def on_chat_model_start(self, serialized, messages, **kwargs):
            foreground_model_starts.append(kwargs.get("metadata"))

    async def background_pass(user_id, *, backend=None):
        await release.wait()
        observed["user_id"] = user_id
        observed["config"] = ensure_config()
        observed["answer"] = await FakeListChatModel(responses=["background result"]).ainvoke(
            "Summarize an older session"
        )
        return {"claimed": 0}

    async def foreground(state):
        extraction.schedule_memory_extraction("owner-A")
        return state

    monkeypatch.setattr(extraction, "run_extraction_pass", background_pass)
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_ENABLED", True)
    before = set(extraction._extraction_tasks)
    builder = StateGraph(dict)
    builder.add_node("foreground", foreground)
    builder.add_edge(START, "foreground")
    builder.add_edge("foreground", END)
    try:
        await builder.compile().ainvoke(
            {},
            config={
                "callbacks": [ForegroundUsage()],
                "configurable": {"thread_id": "foreground-thread", "presenter": object()},
                "metadata": {"user_id": "owner-A", "session_id": "foreground-session"},
            },
        )
    finally:
        release.set()
        await asyncio.gather(*list(extraction._extraction_tasks - before))

    assert observed["user_id"] == "owner-A"
    assert observed["answer"].content == "background result"
    assert foreground_model_starts == []
    assert not observed["config"].get("callbacks")
    assert not observed["config"].get("configurable")
    assert not observed["config"].get("metadata")
