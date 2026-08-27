import asyncio
import json
from contextlib import contextmanager
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


def test_native_memory_guide_does_not_advertise_consolidation_tool():
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    assert "memory_consolidate" not in NATIVE_MEMORY_GUIDE


def test_native_memory_guide_preserves_compact_behavior_contract() -> None:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    required = (
        "memory_retain",
        "memory_recall",
        "memory_delete",
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


@pytest.mark.asyncio
async def test_memory_recall_offloads_result_json(monkeypatch):
    from src.infra.memory import tools as memory_tools

    calls: list[object] = []

    class FakeBackend:
        async def recall(self, user_id: str, query: str, max_results: int, memory_types, context_filter=None):
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


@pytest.mark.asyncio
async def test_auto_memory_capture_forwards_current_source_refs(monkeypatch):
    from src.infra.memory import tools as memory_tools

    seen = {}

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id, user_input, source_refs=None):
            seen["call"] = (user_id, user_input, source_refs)
            return {"stored": 0}

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(_user_id, _instance_id):
        return "acquired"

    async def fake_release(_user_id, _instance_id):
        return None

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    refs = [{"session_id": "session-1", "run_id": "run-1"}]
    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )
    await memory_tools._auto_retain_user_memory("u1", "hello", source_refs=refs)

    assert seen["call"] == ("u1", "hello", refs)


@pytest.mark.asyncio
async def test_auto_memory_capture_serializes_per_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    state = {"active": 0, "max_active": 0, "calls": 0}
    release = asyncio.Event()

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            state["calls"] += 1
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            if state["calls"] == 1:
                await release.wait()
            state["active"] -= 1

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        return None

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )
    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )

    t1 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "first"))
    await asyncio.sleep(0)
    t2 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "second"))
    await asyncio.sleep(0.05)

    assert state["calls"] == 1
    assert state["max_active"] == 1

    release.set()
    await asyncio.gather(t1, t2)

    assert state["calls"] == 2
    assert state["max_active"] == 1


@pytest.mark.asyncio
async def test_auto_memory_capture_uses_distributed_lock(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )
    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_notifies_compaction_agent_after_store(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> dict[str, int]:
            events.append(("retain", user_id))
            return {"stored": 1}

    class FakeCompactionAgent:
        async def maybe_compact_after_write(self, backend, user_id: str):
            assert isinstance(backend, FakeBackend)
            events.append(("compact", user_id))
            return {"triggered": True}

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )
    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("compact", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_detaches_langsmith_parent(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, object]] = []

    @contextmanager
    def fake_tracing_context(**kwargs):
        events.append(("trace_kwargs", kwargs))
        yield

    async def fake_auto_retain(user_id: str, user_input: str) -> None:
        events.append(("retain", (user_id, user_input)))

    monkeypatch.setattr(memory_tools, "tracing_context", fake_tracing_context)
    monkeypatch.setattr(memory_tools, "_auto_retain_user_memory", fake_auto_retain)

    await memory_tools._auto_retain_user_memory_detached("u1", "hello")

    assert events == [
        ("trace_kwargs", {"parent": False}),
        ("retain", ("u1", "hello")),
    ]


@pytest.mark.asyncio
async def test_schedule_auto_memory_capture_dedupes_running_task_per_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    release = asyncio.Event()
    started = asyncio.Event()
    calls: list[tuple[str, str]] = []

    async def fake_detached(user_id: str, user_input: str) -> None:
        calls.append((user_id, user_input))
        started.set()
        await release.wait()

    monkeypatch.setattr(memory_tools, "_auto_retain_user_memory_detached", fake_detached)
    memory_tools._background_tasks.clear()
    memory_tools._auto_capture_tasks_by_user.clear()

    memory_tools.schedule_auto_memory_capture("u1", "first large input")
    await asyncio.wait_for(started.wait(), timeout=1)
    memory_tools.schedule_auto_memory_capture("u1", "second large input")

    assert len(memory_tools._background_tasks) == 1
    assert len(memory_tools._auto_capture_tasks_by_user) == 1
    assert calls == [("u1", "first large input")]

    release.set()
    await asyncio.gather(*list(memory_tools._background_tasks))
    assert memory_tools._auto_capture_tasks_by_user == {}


@pytest.mark.asyncio
async def test_schedule_auto_memory_capture_limits_global_background_tasks(monkeypatch):
    from src.infra.memory import tools as memory_tools

    release = asyncio.Event()
    started_users: list[str] = []

    async def fake_detached(user_id: str, user_input: str) -> None:
        started_users.append(user_id)
        await release.wait()

    monkeypatch.setattr(memory_tools, "_auto_retain_user_memory_detached", fake_detached)
    monkeypatch.setattr(memory_tools.settings, "NATIVE_MEMORY_AUTO_CAPTURE_MAX_TASKS", 2)
    memory_tools._background_tasks.clear()
    memory_tools._auto_capture_tasks_by_user.clear()

    memory_tools.schedule_auto_memory_capture("u1", "first")
    memory_tools.schedule_auto_memory_capture("u2", "second")
    memory_tools.schedule_auto_memory_capture("u3", "third")
    await asyncio.sleep(0)

    assert len(memory_tools._background_tasks) == 2
    assert set(memory_tools._auto_capture_tasks_by_user) == {"u1", "u2"}
    assert started_users == ["u1", "u2"]

    release.set()
    await asyncio.gather(*list(memory_tools._background_tasks))
    assert memory_tools._auto_capture_tasks_by_user == {}


@pytest.mark.asyncio
async def test_schedule_auto_memory_capture_truncates_large_inputs(monkeypatch):
    from src.infra.memory import tools as memory_tools

    calls: list[tuple[str, str]] = []

    async def fake_detached(user_id: str, user_input: str) -> None:
        calls.append((user_id, user_input))

    monkeypatch.setattr(memory_tools, "_auto_retain_user_memory_detached", fake_detached)
    monkeypatch.setattr(memory_tools.settings, "NATIVE_MEMORY_AUTO_CAPTURE_INPUT_MAX_CHARS", 12)
    memory_tools._background_tasks.clear()
    memory_tools._auto_capture_tasks_by_user.clear()

    memory_tools.schedule_auto_memory_capture("u1", "abcdefghijklmnopqrstuvwxyz")

    await asyncio.gather(*list(memory_tools._background_tasks))

    assert calls == [("u1", "abcdefghijkl\n\n[truncated from 26 chars for auto memory capture]")]


@pytest.mark.asyncio
async def test_auto_memory_capture_skips_compaction_when_nothing_stored(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> dict[str, int]:
            events.append(("retain", user_id))
            return {"stored": 0}

    class FakeCompactionAgent:
        async def maybe_compact_after_write(self, backend, user_id: str):
            events.append(("compact", user_id))
            return {"triggered": True}

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )
    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_skips_when_distributed_lock_not_acquired(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "not_acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    monkeypatch.setattr(
        memory_tools.settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 0
    )
    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1")]


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


@pytest.mark.asyncio
async def test_auto_retain_skipped_when_daily_limit_exceeded(monkeypatch):
    from src.infra.memory import distributed as distributed_module
    from src.infra.memory import tools as tools_module

    calls = []

    async def fake_exceeded(user_id):
        return "exceeded"

    monkeypatch.setattr(distributed_module, "check_auto_retain_daily_limit", fake_exceeded)
    monkeypatch.setattr(
        tools_module, "check_auto_retain_daily_limit", fake_exceeded, raising=False
    )

    class NoBackend:
        async def auto_retain_from_text(self, *args, **kwargs):
            calls.append(args)
            return {"success": True, "stored": 0, "candidates": 0}

    async def fake_get_backend():
        return NoBackend()

    async def fake_acquire(_uid, _iid):
        return "acquired"

    async def fake_release(_uid, _iid):
        return None

    monkeypatch.setattr(tools_module, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        tools_module, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await tools_module._auto_retain_user_memory("u1", "一条会被跳过的消息")

    assert calls == []  # 超限直接跳过评估


@pytest.mark.asyncio
async def test_auto_retain_proceeds_when_limit_unavailable(monkeypatch):
    from src.infra.memory import distributed as distributed_module
    from src.infra.memory import tools as tools_module

    calls = []

    async def fake_unavailable(user_id):
        return "unavailable"  # Redis 故障 → fail-open

    monkeypatch.setattr(distributed_module, "check_auto_retain_daily_limit", fake_unavailable)

    class NoBackend:
        async def auto_retain_from_text(self, *args, **kwargs):
            calls.append(args)
            return {"success": True, "stored": 0, "candidates": 0}

    async def fake_get_backend():
        return NoBackend()

    async def fake_acquire(_uid, _iid):
        return "acquired"

    async def fake_release(_uid, _iid):
        return None

    monkeypatch.setattr(tools_module, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        tools_module, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await tools_module._auto_retain_user_memory("u1", "Redis 挂了也要继续评估")

    assert len(calls) == 1


def test_native_memory_guide_vfs_preserves_compact_behavior_contract() -> None:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE_VFS

    required = (
        "memory_retain",
        "memory_recall",
        "memory_delete",
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
