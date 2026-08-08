from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

import pytest

from src.infra.backend.lazy_sandbox import LazySandboxBackend
from src.infra.sandbox import session_manager as sandbox_module


class _FakeE2BAdapter:
    def __init__(self) -> None:
        self.method_calls: list[str] = []
        self.connected: list[str] = []
        self.created = type("FakeE2BSandbox", (), {"sandbox_id": "created-e2b-sandbox"})()

    def sandbox_is_running(self, _provider_obj) -> bool:
        self.method_calls.append("sandbox_is_running")
        return True

    def extend_timeout(self, _provider_obj, _timeout: int) -> None:
        self.method_calls.append("extend_timeout")

    def get_work_dir(self, _provider_obj) -> str:
        self.method_calls.append("get_work_dir")
        return "/home/user"

    def get_sandbox_info(self, _provider_obj) -> dict:
        self.method_calls.append("get_sandbox_info")
        return {"sandbox_id": "sandbox-1", "state": "running"}

    def get_sandbox(self, sandbox_id: str):
        self.method_calls.append("get_sandbox")
        self.connected.append(sandbox_id)
        return object()

    def get_sandbox_id(self, _sandbox) -> str:
        return "created-e2b-sandbox"

    def create_sandbox(self, user_id=None, envs=None):
        self.method_calls.append("create_sandbox")
        return self.created, "/home/user"


class _FakeCubeAdapter(_FakeE2BAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.connected: list[str] = []
        self.killed: list[str] = []
        self.created = type("FakeCubeSandbox", (), {"sandbox_id": "created-sandbox"})()

    def get_sandbox(self, sandbox_id: str):
        self.method_calls.append("get_sandbox")
        self.connected.append(sandbox_id)
        return object()

    def get_sandbox_id(self, _sandbox) -> str:
        return "created-sandbox"

    def create_sandbox(self, user_id=None, envs=None):
        self.method_calls.append("create_sandbox")
        return self.created, "/home/user"

    def list_user_sandboxes(self, user_id: str) -> list[dict]:
        self.method_calls.append("list_user_sandboxes")
        return []

    def kill_sandbox(self, sandbox) -> None:
        self.method_calls.append("kill_sandbox")
        self.killed.append(sandbox)


class _FakeMongoClient:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def __getitem__(self, name: str):
        if name == sandbox_module.BINDING_COLLECTION:
            return self._collection
        return self


class _MemoryBindingCollection:
    def __init__(self) -> None:
        self.doc: dict[str, Any] | None = None

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        if self.doc is None or self.doc.get("user_id") != query.get("user_id"):
            return None
        return dict(self.doc)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        if self.doc is None:
            if not upsert:
                return None
            self.doc = {"user_id": query["user_id"]}
        for key, value in update.get("$setOnInsert", {}).items():
            self.doc.setdefault(key, value)
        for key, value in update.get("$set", {}).items():
            target = self.doc
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return None


class _RecordingPresenter:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    async def emit_sandbox_starting(self) -> None:
        self.attempts.append("starting")

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> None:
        del sandbox_id, work_dir
        self.attempts.append("ready")

    async def emit_sandbox_error(self, error: str) -> None:
        del error
        self.attempts.append("error")


async def _cancel_lazy_creation_and_finish_manager(
    manager: sandbox_module.SessionSandboxManager,
    *,
    create_entered: asyncio.Event,
    release_create: asyncio.Event,
) -> _RecordingPresenter:
    presenter = _RecordingPresenter()
    backend = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=presenter,
        manager_factory=lambda: manager,
    )
    operation = asyncio.create_task(backend.aresolve_path("report.txt"))
    await create_entered.wait()

    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    release_create.set()

    initialization_task = backend._initialization_task  # noqa: SLF001
    assert initialization_task is not None
    await initialization_task
    with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
        await backend.aresolve_path("later.txt")
    return presenter


@pytest.mark.asyncio
async def test_cancelled_lazy_e2b_waiter_allows_manager_to_bind_and_cache_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_entered = asyncio.Event()
    release_create = asyncio.Event()
    collection = _MemoryBindingCollection()
    adapter = _FakeE2BAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = adapter
    manager._cube_adapter = None
    manager._collection = collection

    async def gated_run_blocking_io(func, *args, **kwargs):
        del kwargs
        if func.__name__ == "_sync_create":
            create_entered.set()
            await release_create.wait()
        return func(*args)

    async def no_user_env_vars(_user_id: str) -> dict[str, str]:
        return {}

    async def no_async_side_effect(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    monkeypatch.setattr(sandbox_module, "run_blocking_io", gated_run_blocking_io)
    monkeypatch.setattr(manager, "_get_user_env_vars", no_user_env_vars)
    monkeypatch.setattr(manager, "_ensure_work_dir", no_async_side_effect)
    monkeypatch.setattr(
        "src.infra.sandbox._e2b_helpers.sync_sandbox_env_vars",
        no_async_side_effect,
    )

    presenter = await _cancel_lazy_creation_and_finish_manager(
        manager,
        create_entered=create_entered,
        release_create=release_create,
    )

    assert manager._cache["user-1"][0] == "created-e2b-sandbox"
    assert collection.doc is not None
    assert collection.doc["sandboxes"]["e2b"]["sandbox_id"] == "created-e2b-sandbox"
    assert presenter.attempts == ["starting"]


@pytest.mark.asyncio
async def test_cancelled_lazy_cubesandbox_waiter_allows_manager_to_bind_and_cache_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_entered = asyncio.Event()
    release_create = asyncio.Event()
    collection = _MemoryBindingCollection()
    adapter = _FakeCubeAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = None
    manager._cube_adapter = adapter
    manager._collection = collection

    async def gated_run_blocking_io(func, *args, **kwargs):
        del kwargs
        if func.__name__ == "_sync_create":
            create_entered.set()
            await release_create.wait()
        return func(*args)

    async def no_user_env_vars(_user_id: str) -> dict[str, str]:
        return {}

    async def no_async_side_effect(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    monkeypatch.setattr(sandbox_module, "run_blocking_io", gated_run_blocking_io)
    monkeypatch.setattr(manager, "_get_user_env_vars", no_user_env_vars)
    monkeypatch.setattr(manager, "_ensure_work_dir", no_async_side_effect)
    monkeypatch.setattr(
        "src.infra.sandbox._cubesandbox_helpers.sync_sandbox_env_vars",
        no_async_side_effect,
    )

    presenter = await _cancel_lazy_creation_and_finish_manager(
        manager,
        create_entered=create_entered,
        release_create=release_create,
    )

    assert manager._cache["user-1"][0] == "created-sandbox"
    assert collection.doc is not None
    assert collection.doc["sandboxes"]["cubesandbox"]["sandbox_id"] == "created-sandbox"
    assert presenter.attempts == ["starting"]


@pytest.mark.asyncio
async def test_cancelled_lazy_daytona_waiter_allows_manager_to_bind_and_cache_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DaytonaSandbox:
        id = "created-daytona-sandbox"

        def get_work_dir(self) -> str:
            return "/home/daytona"

    class _DaytonaClient:
        def create(self, _params) -> _DaytonaSandbox:
            return _DaytonaSandbox()

    create_entered = asyncio.Event()
    release_create = asyncio.Event()
    collection = _MemoryBindingCollection()
    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = None
    manager._cube_adapter = None
    manager._daytona_client = _DaytonaClient()
    manager._collection = collection

    async def gated_run_blocking_io(func, *args, **kwargs):
        del kwargs
        if func.__name__ == "_sync_create":
            create_entered.set()
            await release_create.wait()
        return func(*args)

    async def no_user_env_vars(_user_id: str) -> dict[str, str]:
        return {}

    async def no_async_side_effect(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "daytona")
    monkeypatch.setattr(sandbox_module, "run_blocking_io", gated_run_blocking_io)
    monkeypatch.setattr(manager, "_get_user_env_vars", no_user_env_vars)
    monkeypatch.setattr(manager, "_ensure_work_dir", no_async_side_effect)
    monkeypatch.setattr(
        "src.infra.sandbox._daytona_helpers.sync_sandbox_env_vars",
        no_async_side_effect,
    )

    presenter = await _cancel_lazy_creation_and_finish_manager(
        manager,
        create_entered=create_entered,
        release_create=release_create,
    )

    assert manager._cache["user-1"][0] == "created-daytona-sandbox"
    assert collection.doc is not None
    assert collection.doc["sandboxes"]["daytona"]["sandbox_id"] == "created-daytona-sandbox"
    assert presenter.attempts == ["starting"]


@pytest.mark.asyncio
async def test_binding_is_scoped_by_sandbox_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _MemoryBindingCollection()
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(collection),
    )

    manager = sandbox_module.SessionSandboxManager()
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    await manager._save_binding("user-1", "e2b-sandbox", "running", is_new=True)

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    await manager._save_binding("user-1", "cube-sandbox", "running", is_new=True)

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    e2b_binding = await manager._get_binding("user-1")
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    cube_binding = await manager._get_binding("user-1")

    assert e2b_binding["sandbox_id"] == "e2b-sandbox"
    assert cube_binding["sandbox_id"] == "cube-sandbox"


@pytest.mark.asyncio
async def test_legacy_e2b_binding_is_reused_without_platform_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _MemoryBindingCollection()
    collection.doc = {
        "user_id": "user-1",
        "sandbox_id": "legacy-e2b-sandbox",
        "sandbox_state": "running",
    }
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(collection),
    )
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")

    manager = sandbox_module.SessionSandboxManager()

    binding = await manager._get_binding("user-1")

    assert binding["sandbox_id"] == "legacy-e2b-sandbox"


@pytest.mark.asyncio
async def test_e2b_reconnects_legacy_binding_without_creating_new_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _MemoryBindingCollection()
    collection.doc = {
        "user_id": "user-1",
        "sandbox_id": "legacy-e2b-sandbox",
        "sandbox_state": "running",
    }
    adapter = _FakeE2BAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = adapter
    manager._cube_adapter = None

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        return func(*args)

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(collection),
    )
    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    monkeypatch.setattr(sandbox_module.settings, "E2B_TIMEOUT", 123)

    _backend, work_dir = await manager._get_or_create_e2b("session-1", "user-1")

    assert work_dir == "/home/user/sessions/session-1"
    assert adapter.connected == ["legacy-e2b-sandbox"]
    assert "create_sandbox" not in adapter.method_calls
    assert collection.doc["sandboxes"]["e2b"]["sandbox_id"] == "legacy-e2b-sandbox"


@pytest.mark.asyncio
async def test_e2b_cache_hit_runs_sync_sdk_calls_in_blocking_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeE2BAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = adapter
    manager._cache = OrderedDict({"user-1": ("sandbox-1", object(), object())})

    blocking_calls: list[str] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        blocking_calls.append(func.__name__)
        return func(*args)

    async def fake_save_binding(*_args, **_kwargs) -> None:
        return None

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(sandbox_module.settings, "E2B_TIMEOUT", 123)

    _backend, work_dir = await manager._get_or_create_e2b("session-1", "user-1")

    assert work_dir == "/home/user/sessions/session-1"
    assert blocking_calls == ["sandbox_is_running", "extend_timeout", "get_work_dir"]
    assert adapter.method_calls == ["sandbox_is_running", "extend_timeout", "get_work_dir"]


@pytest.mark.asyncio
async def test_cubesandbox_cache_hit_uses_cube_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeCubeAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._cube_adapter = adapter
    manager._e2b_adapter = None
    manager._cache = OrderedDict({"user-1": ("sandbox-1", object(), object())})

    blocking_calls: list[str] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        blocking_calls.append(func.__name__)
        return func(*args)

    async def fake_save_binding(*_args, **_kwargs) -> None:
        return None

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(sandbox_module.settings, "CUBE_TIMEOUT", 456, raising=False)

    _backend, work_dir = await manager._get_or_create_cubesandbox("session-1", "user-1")
    await asyncio.sleep(0)

    assert work_dir == "/home/user/sessions/session-1"
    assert blocking_calls == [
        "sandbox_is_running",
        "extend_timeout",
        "get_work_dir",
        "list_user_sandboxes",
    ]
    assert adapter.method_calls == [
        "sandbox_is_running",
        "extend_timeout",
        "get_work_dir",
        "list_user_sandboxes",
    ]


@pytest.mark.asyncio
async def test_cubesandbox_reuses_running_sandbox_found_by_user_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeCubeAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._cube_adapter = adapter
    manager._e2b_adapter = None

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        return func(*args)

    async def fake_get_binding(_user_id: str):
        return {"sandbox_id": "missing-binding-sandbox"}

    async def fake_save_binding(*_args, **_kwargs) -> None:
        return None

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_get_binding", fake_get_binding)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(
        adapter,
        "get_sandbox",
        lambda sandbox_id: object() if sandbox_id == "usable-existing-sandbox" else None,
    )
    monkeypatch.setattr(
        adapter,
        "list_user_sandboxes",
        lambda user_id: [
            {"sandboxID": "usable-existing-sandbox", "state": "running"},
        ],
    )

    backend, work_dir = await manager._get_or_create_cubesandbox("session-1", "user-1")

    assert work_dir == "/home/user/sessions/session-1"
    assert "user-1" in manager._cache
    assert manager._cache["user-1"][0] == "usable-existing-sandbox"
    assert getattr(backend.default, "work_dir", None) == "/home/user/sessions/session-1"
    assert "create_sandbox" not in adapter.method_calls


@pytest.mark.asyncio
async def test_cubesandbox_create_cleans_other_user_sandboxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeCubeAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._cube_adapter = adapter
    manager._e2b_adapter = None

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        return func(*args)

    async def fake_save_binding(*_args, **_kwargs) -> None:
        return None

    async def fake_get_user_env_vars(_user_id: str) -> dict[str, str]:
        return {}

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(manager, "_get_user_env_vars", fake_get_user_env_vars)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(
        adapter,
        "list_user_sandboxes",
        lambda user_id: [
            {"sandboxID": "old-1", "state": "running"},
            {"sandboxID": "created-sandbox", "state": "running"},
        ],
    )
    monkeypatch.setattr(
        adapter,
        "get_sandbox",
        lambda sandbox_id: sandbox_id,
    )

    await manager._create_and_bind_cubesandbox("session-1", "user-1")

    assert adapter.killed == ["old-1"]


@pytest.mark.asyncio
async def test_cubesandbox_reconnect_cleans_other_user_sandboxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeCubeAdapter()
    manager = sandbox_module.SessionSandboxManager()
    manager._cube_adapter = adapter
    manager._e2b_adapter = None

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        return func(*args)

    async def fake_get_binding(_user_id: str):
        return {"sandbox_id": "bound-sandbox"}

    async def fake_save_binding(*_args, **_kwargs) -> None:
        return None

    async def fake_ensure_work_dir(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_get_binding", fake_get_binding)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(manager, "_ensure_work_dir", fake_ensure_work_dir)
    monkeypatch.setattr(
        adapter,
        "get_sandbox",
        lambda sandbox_id: sandbox_id,
    )
    monkeypatch.setattr(
        adapter,
        "list_user_sandboxes",
        lambda user_id: [
            {"sandboxID": "old-1", "state": "running"},
            {"sandboxID": "bound-sandbox", "state": "running"},
        ],
    )

    await manager._get_or_create_cubesandbox("session-1", "user-1")
    await asyncio.sleep(0)

    assert adapter.killed == ["old-1"]


@pytest.mark.asyncio
async def test_ensure_work_dir_skips_already_ready_directory() -> None:
    manager = sandbox_module.SessionSandboxManager()
    calls = 0

    class _Backend:
        id = "sandbox-1"

        async def aexecute(self, command: str):
            nonlocal calls
            calls += 1
            return type("Result", (), {"exit_code": 0, "output": command})()

    backend = type("Composite", (), {"default": _Backend()})()

    await manager._ensure_work_dir(backend, "/home/user/sessions/session-1")
    await manager._ensure_work_dir(backend, "/home/user/sessions/session-1")

    assert calls == 1


def test_session_work_dir_uses_safe_session_specific_subdirectory() -> None:
    manager = sandbox_module.SessionSandboxManager()

    work_dir = manager._session_work_dir("/home/user", "../session with spaces/中文")

    assert work_dir == "/home/user/sessions/session-with-spaces"


@pytest.mark.asyncio
async def test_close_session_sandbox_manager_does_not_create_unused_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_module._session_sandbox_manager = None

    def _raise_if_created() -> None:
        raise AssertionError("unused sandbox manager should not be created during close")

    monkeypatch.setattr(sandbox_module, "SessionSandboxManager", _raise_if_created)

    await sandbox_module.close_session_sandbox_manager()

    assert sandbox_module._session_sandbox_manager is None


@pytest.mark.asyncio
async def test_close_session_sandbox_manager_closes_existing_singleton() -> None:
    class _Manager:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close_all(self) -> None:
            self.close_calls += 1

    manager = _Manager()
    sandbox_module._session_sandbox_manager = manager

    await sandbox_module.close_session_sandbox_manager()

    assert manager.close_calls == 1
    assert sandbox_module._session_sandbox_manager is None


@pytest.mark.asyncio
async def test_close_all_clears_collection_reference() -> None:
    manager = sandbox_module.SessionSandboxManager()
    manager._collection = object()

    await manager.close_all()

    assert manager._collection is None


@pytest.mark.asyncio
async def test_bindings_reuses_inflight_index_task_across_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowIndexCollection:
        def __init__(self) -> None:
            self.create_index_calls = 0

        async def create_index(self, *_args, **_kwargs) -> None:
            self.create_index_calls += 1
            started.set()
            await release.wait()

    collection = _SlowIndexCollection()
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(collection),
    )
    monkeypatch.setattr(sandbox_module.SessionSandboxManager, "_index_task", None, raising=False)
    monkeypatch.setattr(
        sandbox_module.SessionSandboxManager,
        "_index_ensured",
        False,
        raising=False,
    )

    first = sandbox_module.SessionSandboxManager()
    second = sandbox_module.SessionSandboxManager()

    first._bindings
    await asyncio.wait_for(started.wait(), timeout=1)
    second._bindings
    await asyncio.sleep(0)

    release.set()
    task = sandbox_module.SessionSandboxManager._index_task
    if task is not None:
        await task

    assert collection.create_index_calls == 1
