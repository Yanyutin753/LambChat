import asyncio
import json
from types import SimpleNamespace

import pytest


class _Runtime:
    def __init__(self, user_id: str | None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}


def test_all_memory_tools_excludes_consolidation_tool():
    from src.infra.memory import tools as memory_tools

    tool_names = {tool.name for tool in memory_tools.get_all_memory_tools()}

    assert "memory_retain" in tool_names
    assert "memory_recall" in tool_names
    assert "memory_delete" in tool_names
    assert "memory_consolidate" not in tool_names


def test_memory_tool_exposure_split_keeps_delete_deferred():
    from src.infra.memory.tools import get_deferred_memory_tools, get_inline_memory_tools

    assert {tool.name for tool in get_inline_memory_tools()} == {"memory_retain", "memory_recall"}
    assert {tool.name for tool in get_deferred_memory_tools()} == {"memory_delete"}


@pytest.mark.asyncio
async def test_memory_shutdown_stops_extraction_tasks(monkeypatch):
    from src.infra.memory import extraction
    from src.infra.memory import tools as memory_tools

    events: list[str] = []

    async def stop_extraction():
        events.append("extraction")

    async def stop_compaction():
        events.append("compaction")

    monkeypatch.setattr(extraction, "stop_memory_extraction_tasks", stop_extraction)
    monkeypatch.setattr(memory_tools, "stop_memory_compaction_agent", stop_compaction)
    monkeypatch.setattr(memory_tools, "_backend", None)

    await memory_tools.shutdown()

    assert events == ["extraction", "compaction"]


def test_native_memory_guide_does_not_advertise_consolidation_tool():
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    assert "memory_consolidate" not in NATIVE_MEMORY_GUIDE


def test_native_memory_guide_preserves_compact_behavior_contract() -> None:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    required = (
        "memory_retain",
        "memory_recall",
        "memory_delete",
        "search_tools",
        "hint only",
        "user",
        "feedback",
        "project",
        "reference",
        "Remember",
        "Skip",
        "selective",
        "30 days",
        "stale",
        "/memories/",
    )

    assert all(marker.lower() in NATIVE_MEMORY_GUIDE.lower() for marker in required)
    assert len(NATIVE_MEMORY_GUIDE) <= 960


def test_memory_recall_description_embeds_source_lookup_sop() -> None:
    from src.infra.memory import tools as memory_tools

    description = memory_tools.memory_recall.description

    assert "source_refs" in description
    assert "get_conversation_detail" in description
    assert "session_id" in description
    assert "run_id" in description
    assert "complete `text`" in description
    assert "do not omit" in description.lower()
    assert "not injected into user messages" in description.lower()
    assert "call this tool" in description.lower()


@pytest.mark.asyncio
async def test_memory_recall_offloads_result_json(monkeypatch):
    from src.infra.memory import tools as memory_tools

    calls: list[object] = []

    class FakeBackend:
        async def recall(
            self, user_id: str, query: str, max_results: int, memory_types, context_filter=None
        ):
            assert user_id == "u1"
            assert query == "project"
            assert max_results == 5
            assert memory_types is None
            return {
                "success": True,
                "memories": [
                    {
                        "memory_id": f"m-{index}",
                        "content": "large memory text " * 100,
                    }
                    for index in range(5)
                ],
            }

    async def fake_get_backend():
        return FakeBackend()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(memory_tools, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await memory_tools.memory_recall.coroutine(
            "project",
            runtime=_Runtime("u1"),
        )
    )

    assert result["success"] is True
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_memory_retain_offloads_error_result_json(monkeypatch):
    from src.infra.memory import tools as memory_tools

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(memory_tools, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await memory_tools.memory_retain.coroutine(
            "remember this",
            runtime=_Runtime(None),
        )
    )

    assert result == {"success": False, "error": "User not authenticated"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_memory_retain_forwards_source_refs(monkeypatch):
    from src.infra.memory import tools as memory_tools

    seen = {}

    class FakeBackend:
        async def retain(self, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return {"success": True}

    async def fake_get_backend():
        return FakeBackend()

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)

    result = json.loads(
        await memory_tools.memory_retain.coroutine(
            "The user prefers raw SQL.",
            source_refs=[{"session_id": "session-1", "run_id": "run-1"}],
            runtime=_Runtime("u1"),
        )
    )

    assert result == {"success": True}
    assert seen["kwargs"]["source_refs"] == [{"session_id": "session-1", "run_id": "run-1"}]


def test_memory_recall_context_param_documents_family_prefix():
    from src.infra.memory.tools import memory_recall

    context_description = str(memory_recall.args["context"].get("description") or "")
    # context 参数必须说明家族前缀语义（'project' 覆盖 project_status 等）
    assert "family prefix" in context_description
    assert "project_status" in context_description


def test_start_memory_compaction_agent_registers_unified_scheduler_job(monkeypatch):
    from src.infra.memory import tools as memory_tools

    registered = []

    class FakeScheduler:
        def register_job(self, job):
            registered.append(job)

        def register_interval_job(self, job):
            registered.append(job)

    class FakeCompactionAgent:
        def is_periodic_enabled(self) -> bool:
            return True

        def get_periodic_interval_seconds(self) -> int:
            return 123

    monkeypatch.setattr(
        memory_tools,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=True),
    )
    monkeypatch.setattr(memory_tools, "get_runtime_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    memory_tools.start_memory_compaction_agent()

    assert len(registered) == 1
    job = registered[0]
    assert job.id == "memory.compaction"
    assert job.enabled() is True
    trigger = job.trigger()
    assert trigger.interval_length == 123
    assert job.run_on_start is False


@pytest.mark.asyncio
async def test_scheduled_memory_compaction_runs_periodic_once(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events = []

    class FakeBackend:
        pass

    class FakeCompactionAgent:
        async def run_periodic_once(self, backend):
            assert isinstance(backend, FakeBackend)
            events.append("run")
            return {"checked": 1, "triggered": 1}

    async def fake_get_backend():
        return FakeBackend()

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    result = await memory_tools.run_scheduled_memory_compaction()

    assert result == {"checked": 1, "triggered": 1}
    assert events == ["run"]


@pytest.mark.asyncio
async def test_schedule_backend_reset_deduplicates_inflight_reset_task(monkeypatch):
    from src.infra.memory import tools as memory_tools

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_close_and_reset_backend():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(
        memory_tools,
        "_close_and_reset_backend",
        fake_close_and_reset_backend,
    )
    memory_tools._background_tasks.clear()
    memory_tools._backend_reset_task = None

    memory_tools.schedule_backend_reset()
    await asyncio.wait_for(started.wait(), timeout=1)
    memory_tools.schedule_backend_reset()

    assert len(memory_tools._background_tasks) == 1
    assert calls == 1

    release.set()
    await asyncio.gather(*list(memory_tools._background_tasks))

    assert memory_tools._backend_reset_task is None


def test_native_memory_guide_vfs_preserves_compact_behavior_contract() -> None:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE_VFS

    required = (
        "memory_retain",
        "memory_recall",
        "memory_delete",
        "search_tools",
        "hint only",
        "user",
        "feedback",
        "project",
        "reference",
        "Remember",
        "Skip",
        "selective",
        "30 days",
        "stale",
        "/memories/",
    )

    assert all(marker.lower() in NATIVE_MEMORY_GUIDE_VFS.lower() for marker in required)
    assert "/memories/working/" in NATIVE_MEMORY_GUIDE_VFS
    assert len(NATIVE_MEMORY_GUIDE_VFS) <= 960


def test_get_memory_guide_selects_variant_by_vfs_setting(monkeypatch):
    from src.agents.core import subagent_prompts
    from src.infra.memory.client.types import (
        NATIVE_MEMORY_GUIDE,
        NATIVE_MEMORY_GUIDE_VFS,
    )
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_MEMORY_VFS", False)
    assert subagent_prompts.get_memory_guide() == NATIVE_MEMORY_GUIDE

    monkeypatch.setattr(settings, "ENABLE_MEMORY_VFS", True)
    assert subagent_prompts.get_memory_guide() == NATIVE_MEMORY_GUIDE_VFS


def test_get_memory_guide_keeps_delete_deferred_when_deferred_loading_enabled(monkeypatch):
    from src.agents.core import subagent_prompts
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_MEMORY_VFS", False)
    monkeypatch.setattr(settings, "ENABLE_DEFERRED_TOOL_LOADING", True)
    guide = subagent_prompts.get_memory_guide()
    assert "search_tools" in guide
    assert "(remove)" not in guide


def test_get_memory_guide_lists_delete_inline_when_deferred_loading_disabled(monkeypatch):
    """延迟加载关闭时 memory_delete 直挂，指南不得再指向不存在的 search_tools。"""
    from src.agents.core import subagent_prompts
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_MEMORY_VFS", False)
    monkeypatch.setattr(settings, "ENABLE_DEFERRED_TOOL_LOADING", False)
    guide = subagent_prompts.get_memory_guide()
    assert "search_tools" not in guide
    assert "`memory_delete` (remove)" in guide
