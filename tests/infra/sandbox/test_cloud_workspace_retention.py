"""Cloud lifecycle operations must never erase or replace a previous workspace."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.infra.sandbox import session_manager as module
from src.infra.sandbox._adapters import CubeSandboxAdapter, E2BSandboxAdapter


@pytest.fixture(autouse=True)
def enabled_native_volumes(monkeypatch):
    monkeypatch.setattr(
        module.settings, "SANDBOX_PERSISTENT_VOLUME_PLATFORMS", "cubesandbox,daytona,e2b"
    )


@pytest.mark.parametrize("adapter_type", [E2BSandboxAdapter, CubeSandboxAdapter])
def test_failed_pause_never_kills_workspace(adapter_type):
    adapter = object.__new__(adapter_type)
    sandbox = SimpleNamespace(
        pause=Mock(side_effect=TimeoutError("provider unavailable")), kill=Mock()
    )
    with pytest.raises(TimeoutError):
        adapter.stop_sandbox(sandbox)
    sandbox.kill.assert_not_called()


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox", "daytona"])
@pytest.mark.parametrize("create", [True, False])
async def test_unavailable_bound_workspace_is_never_replaced(monkeypatch, platform, create):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    manager._get_binding = AsyncMock(return_value={"sandbox_id": "original"})
    manager._save_binding = AsyncMock()
    create_new = AsyncMock(return_value=(object(), "/empty"))
    manager._create_and_bind = create_new
    manager._create_and_bind_e2b = create_new
    manager._create_and_bind_cubesandbox = create_new
    manager._get_sandbox_state = AsyncMock(return_value="deleted")
    manager._find_existing_cubesandbox_for_user = AsyncMock(return_value=None)
    adapter = SimpleNamespace(get_sandbox=Mock(return_value=None))
    manager._e2b_adapter = adapter if platform == "e2b" else None
    manager._cube_adapter = adapter if platform == "cubesandbox" else None

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    with pytest.raises(module.SandboxPeekError, match="recycled"):
        await manager.get_or_create("session", "owner", create=create)
    create_new.assert_not_awaited()
    manager._save_binding.assert_not_awaited()
    manager._find_existing_cubesandbox_for_user.assert_not_awaited()


async def test_duplicate_cleanup_keeps_unverified_workspace(monkeypatch):
    manager = module.SessionSandboxManager()
    adapter = SimpleNamespace(
        list_user_sandboxes=Mock(return_value=[{"sandboxID": "previous"}]),
        get_sandbox=Mock(return_value=object()),
        kill_sandbox=Mock(),
    )
    manager._cube_adapter = adapter

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_blocking_io", run)
    monkeypatch.setattr(module, "run_long_blocking_io", run)
    await manager._cleanup_duplicate_cubesandboxes("owner", keep_sandbox_id="current")
    adapter.kill_sandbox.assert_not_called()
    adapter.get_sandbox.assert_not_called()


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox", "daytona"])
async def test_native_storage_is_saved_before_runtime_creation(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    collection = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    manager._collection = collection
    descriptor = {"volume_id": "durable-volume", "name": "stable-owner", "mount_path": "/workspace"}
    manager._collection.create_index = AsyncMock()
    provision = Mock(return_value=descriptor)
    monkeypatch.setattr(manager, "_provision_cloud_storage", provision, raising=False)

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    result = await manager._prepare_cloud_storage("owner")
    assert result == descriptor
    collection.create_index.assert_awaited_once_with(
        "user_id", unique=True, name="user_id_unique_idx", background=True
    )
    assert (
        collection.update_one.await_args.args[1]["$set"][f"cloud_storage.{platform}"] == descriptor
    )


async def test_existing_runtime_cannot_be_mounted_over_with_new_volume(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "e2b")
    manager = module.SessionSandboxManager()
    manager._collection = SimpleNamespace(find_one=AsyncMock(return_value={"sandbox_id": "legacy"}))
    with pytest.raises(RuntimeError, match="existing workspace"):
        await manager._prepare_cloud_storage("owner")


@pytest.mark.parametrize(
    "adapter_type, sdk", [(E2BSandboxAdapter, "e2b"), (CubeSandboxAdapter, "cubesandbox")]
)
def test_transient_reconnect_failure_is_not_reported_as_missing(monkeypatch, adapter_type, sdk):
    import importlib

    adapter = object.__new__(adapter_type)
    provider = SimpleNamespace(connect=Mock(side_effect=TimeoutError("temporary failure")))
    if sdk == "e2b":
        adapter._api_key = ""
        adapter._timeout = 60
        monkeypatch.setattr(adapter, "_get_e2b_class", lambda: provider)
        monkeypatch.setattr(adapter, "_get_e2b_opts", lambda: {})
    else:
        monkeypatch.setattr(adapter, "_sync_from_settings", lambda: None)
        monkeypatch.setattr(adapter, "_get_cube_class", lambda: provider)
        monkeypatch.setattr(adapter, "_get_config", lambda: None)
    assert importlib.import_module(sdk)
    with pytest.raises(TimeoutError):
        adapter.get_sandbox("original")


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox", "daytona"])
async def test_registered_volume_is_checked_never_recreated(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    descriptor = {"volume_id": "retained", "name": "owner", "mount_path": "/workspace"}
    manager._collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"cloud_storage": {platform: descriptor}}),
        update_one=AsyncMock(),
    )
    manager._collection.create_index = AsyncMock()
    provision = Mock(side_effect=RuntimeError("volume unavailable"))
    monkeypatch.setattr(manager, "_provision_cloud_storage", provision, raising=False)

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    with pytest.raises(RuntimeError, match="volume unavailable"):
        await manager._prepare_cloud_storage("owner")
    assert provision.call_args.args[1] == descriptor
    manager._collection.update_one.assert_not_awaited()


async def test_mount_verification_rejects_ephemeral_directory(monkeypatch):
    manager = module.SessionSandboxManager()
    backend = SimpleNamespace(
        default=SimpleNamespace(aexecute=AsyncMock(return_value=SimpleNamespace(exit_code=1)))
    )
    with pytest.raises(RuntimeError, match="mount"):
        await manager._verify_cloud_storage(backend, {"mount_path": "/workspace"})


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox"])
async def test_missing_runtime_recovers_only_registered_volume(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    storage = {"volume_id": "durable", "mount_path": "/workspace", "name": "owner"}
    manager._get_binding = AsyncMock(
        return_value={
            "sandbox_id": "previous",
            "sandbox_work_dir": "/workspace",
            "cloud_storage": {platform: storage},
        }
    )
    recreate = AsyncMock(return_value=(object(), "/workspace/sessions/session"))
    if platform == "e2b":
        manager._e2b_adapter = SimpleNamespace(get_sandbox=Mock(return_value=None))
        manager._create_and_bind_e2b = recreate
    else:
        manager._e2b_adapter = None
        manager._cube_adapter = SimpleNamespace(get_sandbox=Mock(return_value=None))
        manager._create_and_bind_cubesandbox = recreate

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    await manager.get_or_create("session", "owner")
    recreate.assert_awaited_once_with("session", "owner", previous_sandbox_id="previous")


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox"])
def test_provider_mounts_native_volume_on_new_runtime(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    adapter = manager._e2b_adapter if platform == "e2b" else manager._cube_adapter
    sandbox_class = SimpleNamespace(create=Mock(return_value=object()))
    monkeypatch.setattr(
        adapter, "_get_e2b_class" if platform == "e2b" else "_get_cube_class", lambda: sandbox_class
    )
    storage = {"volume_id": "vol-id", "name": "stable-name", "mount_path": "/workspace"}
    _, root = adapter.create_sandbox(user_id="owner", storage=storage)
    assert root == "/workspace"
    assert sandbox_class.create.call_args.kwargs["volume_mounts"] == {
        "/workspace": "stable-name" if platform == "e2b" else "vol-id"
    }


async def test_binding_update_retains_source_and_rejects_competing_runtime(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "e2b")
    manager = module.SessionSandboxManager()
    previous = {"user_id": "owner", "sandboxes": {"e2b": {"sandbox_id": "original"}}}
    manager._collection = SimpleNamespace(
        find_one=AsyncMock(return_value=previous),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1, upserted_id=None)),
    )
    with pytest.raises(RuntimeError, match="refusing"):
        await manager._save_binding("owner", "other", "running", is_new=True)
    manager._collection.update_one.assert_not_awaited()
    await manager._save_binding(
        "owner", "replacement", "running", is_new=True, previous_sandbox_id="original"
    )
    query, update = manager._collection.update_one.await_args.args
    assert query["sandboxes.e2b.sandbox_id"] == "original"
    assert update["$addToSet"]["sandboxes.e2b.previous_sandbox_ids"] == "original"


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox", "daytona"])
async def test_registered_workspace_mount_is_rechecked_when_reconnecting(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    storage = {"volume_id": "volume", "mount_path": "/workspace", "name": "owner"}
    manager._get_binding = AsyncMock(
        return_value={"sandbox_work_dir": "/workspace", "cloud_storage": {platform: storage}}
    )
    manager._verify_cloud_storage = AsyncMock(side_effect=RuntimeError("mount unavailable"))
    with pytest.raises(RuntimeError, match="mount unavailable"):
        await manager._cloud_work_dir("owner", "/home/user", object())


def test_volume_workspace_paths_do_not_alias_custom_session_ids():
    manager = module.SessionSandboxManager()
    assert manager._session_work_dir("/workspace", "a/b") != manager._session_work_dir(
        "/workspace", "a-b"
    )
    assert manager._session_work_dir("/workspace", "x" * 80 + "a") != manager._session_work_dir(
        "/workspace", "x" * 80 + "b"
    )
    assert manager._session_work_dir("/home/user", "a/b") == "/home/user/sessions/a-b"
    encoded = manager._session_work_dir("/workspace", "a/b").rsplit("/", 1)[-1]
    assert manager._session_work_dir("/workspace", encoded) != manager._session_work_dir(
        "/workspace", "a/b"
    )


async def test_storage_creation_race_uses_persisted_winner(monkeypatch):
    from pymongo.errors import DuplicateKeyError

    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "e2b")
    manager = module.SessionSandboxManager()
    winner = {"volume_id": "winner", "name": "stable-name", "mount_path": "/workspace"}
    loser = {**winner, "volume_id": "loser"}
    manager._collection = SimpleNamespace(
        find_one=AsyncMock(side_effect=[None, {"cloud_storage": {"e2b": winner}}]),
        update_one=AsyncMock(side_effect=DuplicateKeyError("concurrent creator")),
    )
    manager._collection.create_index = AsyncMock()
    provision = Mock(side_effect=[loser, winner])
    monkeypatch.setattr(manager, "_provision_cloud_storage", provision)

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    assert await manager._prepare_cloud_storage("owner") == winner
    assert provision.call_args.args == ("owner", winner)


async def test_unconfigured_native_storage_does_not_break_new_users(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PERSISTENT_VOLUME_PLATFORMS", "", raising=False)
    manager = module.SessionSandboxManager()
    manager._collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
    manager._provision_cloud_storage = Mock(side_effect=AssertionError("must not provision"))
    assert await manager._prepare_cloud_storage("owner") is None


def test_e2b_beta_volume_cannot_be_enabled_for_posix_workspace(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "e2b")
    manager = module.SessionSandboxManager()
    with pytest.raises(RuntimeError, match="locking"):
        manager._provision_cloud_storage("owner", None)


async def test_existing_daytona_backend_keeps_legacy_root(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "daytona")
    manager = module.SessionSandboxManager()
    sandbox = SimpleNamespace(id="existing", get_work_dir=lambda: "/home/daytona")
    monkeypatch.setattr(
        manager, "_get_daytona_client", lambda: SimpleNamespace(get=lambda _id: sandbox)
    )

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_blocking_io", run)
    backend = await manager._create_backend("existing", "owner")
    assert backend.default.id == "existing"


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox"])
async def test_failed_mount_recovery_does_not_update_prior_binding(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    sandbox = SimpleNamespace(sandbox_id="replacement")
    adapter = SimpleNamespace(
        create_sandbox=Mock(return_value=(sandbox, "/workspace")),
        get_sandbox_id=lambda _: "replacement",
        stop_sandbox=Mock(),
    )
    manager._e2b_adapter = adapter if platform == "e2b" else None
    manager._cube_adapter = adapter if platform == "cubesandbox" else None
    manager._get_user_env_vars = AsyncMock(return_value={})
    manager._prepare_cloud_storage = AsyncMock(
        return_value={"volume_id": "retained", "mount_path": "/workspace", "name": "owner"}
    )
    manager._verify_cloud_storage = AsyncMock(side_effect=RuntimeError("mount unavailable"))
    manager._save_binding = AsyncMock()

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    method = (
        manager._create_and_bind_e2b if platform == "e2b" else manager._create_and_bind_cubesandbox
    )
    with pytest.raises(RuntimeError, match="mount unavailable"):
        await method("session", "owner", previous_sandbox_id="original")
    manager._save_binding.assert_not_awaited()
    adapter.stop_sandbox.assert_called_once_with(sandbox)
    assert "owner" not in manager._cache


def test_cube_registered_volume_connects_by_id_without_create(monkeypatch):
    import cubesandbox

    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    manager = module.SessionSandboxManager()
    storage = {"volume_id": "retained", "name": "stable-name", "mount_path": "/workspace"}
    volume_class = SimpleNamespace(
        connect=Mock(return_value=SimpleNamespace(volume_id="retained", name="stable-name")),
        create=Mock(),
        list=Mock(),
    )
    monkeypatch.setattr(cubesandbox, "Volume", volume_class)
    monkeypatch.setattr(manager._cube_adapter, "_get_config", lambda: None)
    assert manager._provision_cloud_storage("owner", storage) == storage
    volume_class.connect.assert_called_once_with("retained", config=None)
    volume_class.create.assert_not_called()
    volume_class.list.assert_not_called()


def test_daytona_registered_volume_identity_cannot_change(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "daytona")
    manager = module.SessionSandboxManager()
    volumes = SimpleNamespace(get=Mock(return_value=SimpleNamespace(id="different")))
    monkeypatch.setattr(manager, "_get_daytona_client", lambda: SimpleNamespace(volume=volumes))
    with pytest.raises(RuntimeError, match="identity"):
        manager._provision_cloud_storage(
            "owner", {"volume_id": "original", "name": "name", "mount_path": "/workspace"}
        )
    volumes.get.assert_called_once_with("name", create=False)


@pytest.mark.parametrize(
    "message", ["API key not found", "template not found", "proxy host not found"]
)
async def test_daytona_non_lookup_failure_does_not_replace_running_workspace(monkeypatch, message):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "daytona")
    manager = module.SessionSandboxManager()
    manager._get_binding = AsyncMock(
        return_value={
            "sandbox_id": "existing",
            "sandbox_work_dir": "/workspace",
            "cloud_storage": {
                "daytona": {"volume_id": "durable", "name": "owner", "mount_path": "/workspace"}
            },
        }
    )
    manager._create_and_bind = AsyncMock(return_value=(object(), "/workspace"))
    monkeypatch.setattr(
        manager,
        "_get_daytona_client",
        lambda: SimpleNamespace(get=Mock(side_effect=RuntimeError(message))),
    )

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_blocking_io", run)
    with pytest.raises(RuntimeError, match=message):
        await manager.get_or_create("session", "owner")
    manager._create_and_bind.assert_not_awaited()


async def test_daytona_typed_missing_sandbox_is_destroyed(monkeypatch):
    from daytona import DaytonaNotFoundError

    manager = module.SessionSandboxManager()
    monkeypatch.setattr(
        manager,
        "_get_daytona_client",
        lambda: SimpleNamespace(get=Mock(side_effect=DaytonaNotFoundError("missing"))),
    )

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_blocking_io", run)
    assert await manager._get_sandbox_state("deleted") == "destroyed"


async def test_native_storage_requires_confirmed_unique_owner_index(monkeypatch):
    from pymongo.errors import OperationFailure

    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    manager = module.SessionSandboxManager()
    manager._collection = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        create_index=AsyncMock(side_effect=OperationFailure("duplicate owners")),
        update_one=AsyncMock(),
    )
    manager._provision_cloud_storage = Mock(
        return_value={"volume_id": "new", "name": "owner", "mount_path": "/workspace"}
    )

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    with pytest.raises(OperationFailure, match="duplicate owners"):
        await manager._prepare_cloud_storage("owner")
    manager._provision_cloud_storage.assert_not_called()
    manager._collection.update_one.assert_not_awaited()


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox"])
async def test_losing_runtime_claim_is_paused_and_never_exposed(monkeypatch, platform):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    sandbox = SimpleNamespace(sandbox_id="loser")
    adapter = SimpleNamespace(
        create_sandbox=Mock(return_value=(sandbox, "/workspace")),
        get_sandbox_id=lambda _: "loser",
        stop_sandbox=Mock(),
    )
    manager._e2b_adapter = adapter if platform == "e2b" else None
    manager._cube_adapter = adapter if platform == "cubesandbox" else None
    manager._get_user_env_vars = AsyncMock(return_value={})
    manager._prepare_cloud_storage = AsyncMock(
        return_value={"volume_id": "shared", "mount_path": "/workspace", "name": "owner"}
    )
    manager._verify_cloud_storage = AsyncMock()
    manager._ensure_work_dir = AsyncMock()
    manager._save_binding = AsyncMock(
        side_effect=RuntimeError("Workspace binding changed during recovery")
    )
    helper = "_e2b_helpers" if platform == "e2b" else "_cubesandbox_helpers"
    monkeypatch.setattr("src.infra.sandbox." + helper + ".sync_sandbox_env_vars", AsyncMock())

    async def run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(module, "run_long_blocking_io", run)
    create = (
        manager._create_and_bind_e2b if platform == "e2b" else manager._create_and_bind_cubesandbox
    )
    with pytest.raises(RuntimeError, match="binding changed"):
        await create("session", "owner")
    assert manager.get_cached_backend("owner") is None
    adapter.stop_sandbox.assert_called_once_with(sandbox)


async def test_binding_compare_and_swap_rejects_concurrent_owner_change(monkeypatch):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", "cubesandbox")
    manager = module.SessionSandboxManager()
    manager._collection = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "user_id": "owner",
                "sandboxes": {"cubesandbox": {"sandbox_id": "previous"}},
            }
        ),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0, upserted_id=None)),
    )
    with pytest.raises(RuntimeError, match="changed during recovery"):
        await manager._save_binding(
            "owner", "new", "running", is_new=True, previous_sandbox_id="previous"
        )
    query = manager._collection.update_one.await_args.args[0]
    assert query["sandboxes.cubesandbox.sandbox_id"] == "previous"
    assert manager._collection.update_one.await_args.kwargs["upsert"] is False
