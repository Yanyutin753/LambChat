from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

import pytest

from src.infra.client_sandbox.models import (
    ClientSandboxBindingCreate,
    ClientSandboxSessionBinding,
)
from src.infra.sandbox import session_manager as sandbox_module


class _FakeE2BAdapter:
    def __init__(self) -> None:
        self.method_calls: list[str] = []

    def sandbox_is_running(self, _provider_obj) -> bool:
        self.method_calls.append("sandbox_is_running")
        return True

    def extend_timeout(self, _provider_obj, _timeout: int) -> None:
        self.method_calls.append("extend_timeout")

    def get_work_dir(self, _provider_obj) -> str:
        self.method_calls.append("get_work_dir")
        return "/home/user"


class _FakeMongoClient:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def __getitem__(self, name: str):
        if name == sandbox_module.BINDING_COLLECTION:
            return self._collection
        return self


class _FakeClientSandboxStorage:
    def __init__(
        self,
        binding: ClientSandboxSessionBinding | None,
        devices: dict[str, str] | None = None,
        preference: Any | None = None,
    ) -> None:
        self.binding = binding
        self.devices = devices or {}
        self.preference = preference
        self.created_bindings: list[ClientSandboxBindingCreate] = []

    async def get_active_binding(
        self,
        user_id: str,
        session_id: str,
    ) -> ClientSandboxSessionBinding | None:
        assert user_id == "user-1"
        assert session_id == "session-1"
        return self.binding

    async def create_or_refresh_binding(
        self,
        user_id: str,
        binding: ClientSandboxBindingCreate,
    ) -> ClientSandboxSessionBinding:
        assert user_id == "user-1"
        self.created_bindings.append(binding)
        self.binding = ClientSandboxSessionBinding(
            user_id=user_id,
            session_id=binding.session_id,
            device_id=binding.device_id,
            workspace_root=binding.workspace_root,
        )
        return self.binding

    async def list_devices(self, user_id: str):
        assert user_id == "user-1"

        class _Device:
            def __init__(self, device_id: str, workspace_root: str) -> None:
                self.device_id = device_id
                self.workspace_root = workspace_root

        return [
            _Device(device_id, workspace_root) for device_id, workspace_root in self.devices.items()
        ]

    async def get_preference(self, user_id: str):
        assert user_id == "user-1"
        return self.preference


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

    async def fake_ensure_sandbox_mcp(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(sandbox_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(manager, "_save_binding", fake_save_binding)
    monkeypatch.setattr(sandbox_module, "ensure_sandbox_mcp", fake_ensure_sandbox_mcp)
    monkeypatch.setattr(sandbox_module.settings, "E2B_TIMEOUT", 123)

    _backend, work_dir = await manager._get_or_create_e2b("session-1", "user-1")

    assert work_dir == "/home/user"
    assert blocking_calls == ["sandbox_is_running", "extend_timeout", "get_work_dir"]
    assert adapter.method_calls == ["sandbox_is_running", "extend_timeout", "get_work_dir"]


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


@pytest.mark.asyncio
async def test_active_client_binding_takes_precedence_over_global_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = ClientSandboxSessionBinding(
        user_id="user-1",
        session_id="session-1",
        device_id="desktop-1",
        workspace_root="/tmp/lambchat",
    )
    storage = _FakeClientSandboxStorage(binding)

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "daytona")
    monkeypatch.setattr(
        "src.infra.client_sandbox.storage.ClientSandboxStorage",
        lambda: storage,
    )

    manager = sandbox_module.SessionSandboxManager()

    backend, work_dir = await manager.get_or_create("session-1", "user-1")

    assert work_dir == "/workspace"
    assert backend.default.id == "client:desktop-1"


@pytest.mark.asyncio
async def test_client_sandbox_auto_binds_single_connected_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeClientSandboxStorage(
        None,
        devices={"desktop-1": "/tmp/lambchat"},
    )

    class _Router:
        async def list_connected_device_ids(self, user_id: str) -> list[str]:
            assert user_id == "user-1"
            return ["desktop-1"]

    monkeypatch.setattr(
        "src.infra.client_sandbox.storage.ClientSandboxStorage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.client_sandbox.router.get_client_sandbox_router",
        lambda: _Router(),
    )

    manager = sandbox_module.SessionSandboxManager()

    backend, work_dir = await manager._get_or_create_client("session-1", "user-1")

    assert work_dir == "/workspace"
    assert backend.default.id == "client:desktop-1"
    assert storage.created_bindings[0].device_id == "desktop-1"


@pytest.mark.asyncio
async def test_connected_desktop_auto_binding_takes_precedence_for_any_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeClientSandboxStorage(
        None,
        devices={"desktop-1": "/tmp/lambchat"},
    )

    class _Router:
        async def list_connected_device_ids(self, user_id: str) -> list[str]:
            assert user_id == "user-1"
            return ["desktop-1"]

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "daytona")
    monkeypatch.setattr(
        "src.infra.client_sandbox.storage.ClientSandboxStorage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.client_sandbox.router.get_client_sandbox_router",
        lambda: _Router(),
    )

    manager = sandbox_module.SessionSandboxManager()

    backend, work_dir = await manager.get_or_create("session-1", "user-1")

    assert work_dir == "/workspace"
    assert backend.default.id == "client:desktop-1"
    assert storage.created_bindings[0].session_id == "session-1"


@pytest.mark.asyncio
async def test_enabled_client_sandbox_preference_blocks_e2b_fallback_when_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Preference:
        enabled = True
        device_id = "desktop-1"
        workspace_root = "/tmp/lambchat"

    storage = _FakeClientSandboxStorage(None, preference=_Preference())

    class _Router:
        async def list_connected_device_ids(self, user_id: str) -> list[str]:
            assert user_id == "user-1"
            return []

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    monkeypatch.setattr(
        "src.infra.client_sandbox.storage.ClientSandboxStorage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.client_sandbox.router.get_client_sandbox_router",
        lambda: _Router(),
    )

    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = _FakeE2BAdapter()

    with pytest.raises(RuntimeError, match="Local desktop sandbox is enabled"):
        await manager.get_or_create("session-1", "user-1")

    assert manager._e2b_adapter.method_calls == []


@pytest.mark.asyncio
async def test_enabled_client_sandbox_preference_uses_selected_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Preference:
        enabled = True
        device_id = "desktop-2"
        workspace_root = "/tmp/preferred"

    storage = _FakeClientSandboxStorage(
        None,
        devices={
            "desktop-1": "/tmp/other",
            "desktop-2": "/tmp/lambchat",
        },
        preference=_Preference(),
    )

    class _Router:
        async def list_connected_device_ids(self, user_id: str) -> list[str]:
            assert user_id == "user-1"
            return ["desktop-1", "desktop-2"]

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_PLATFORM", "e2b")
    monkeypatch.setattr(
        "src.infra.client_sandbox.storage.ClientSandboxStorage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.client_sandbox.router.get_client_sandbox_router",
        lambda: _Router(),
    )

    manager = sandbox_module.SessionSandboxManager()
    manager._e2b_adapter = _FakeE2BAdapter()

    backend, work_dir = await manager.get_or_create("session-1", "user-1")

    assert work_dir == "/workspace"
    assert backend.default.id == "client:desktop-2"
    assert manager._e2b_adapter.method_calls == []
