from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.envvar.sync import sync_envvar_change


@pytest.mark.asyncio
async def test_sync_envvar_change_invalidates_prompt_cache_and_broadcasts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    async def _publish(cache: str, user_id: str | None = None) -> None:
        calls.append((cache, user_id or ""))

    monkeypatch.setattr(
        "src.infra.envvar.sync.publish_tool_cache_invalidation",
        _publish,
    )

    await sync_envvar_change("user-1")

    assert calls == [("env_var_prompt", "user-1")]


@pytest.mark.asyncio
async def test_sync_sandbox_env_vars_refreshes_backend_from_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.envvar import sync

    class _Storage:
        async def get_decrypted_vars(self, user_id: str) -> dict[str, str]:
            assert user_id == "user-1"
            return {"NEW_KEY": "new-value"}

    backend = SimpleNamespace(default=SimpleNamespace(env_vars={"OLD_KEY": "old-value"}))
    monkeypatch.setattr(sync, "EnvVarStorage", _Storage, raising=False)

    await sync.sync_sandbox_env_vars(backend, "user-1")

    assert backend.default.env_vars == {"NEW_KEY": "new-value"}


@pytest.mark.asyncio
async def test_sync_envvar_change_refreshes_cached_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.envvar import sync

    class _Storage:
        async def get_decrypted_vars(self, user_id: str) -> dict[str, str]:
            assert user_id == "user-1"
            return {"LIVE_KEY": "live-value"}

    backend = SimpleNamespace(default=SimpleNamespace(env_vars={}))
    manager = SimpleNamespace(get_cached_backend=lambda user_id: backend)

    async def _publish(_cache: str, user_id: str | None = None) -> None:
        assert user_id == "user-1"

    monkeypatch.setattr(sync, "EnvVarStorage", _Storage, raising=False)
    monkeypatch.setattr(sync, "get_session_sandbox_manager", lambda: manager, raising=False)
    monkeypatch.setattr(sync, "publish_tool_cache_invalidation", _publish)

    await sync.sync_envvar_change("user-1")

    assert backend.default.env_vars == {"LIVE_KEY": "live-value"}
