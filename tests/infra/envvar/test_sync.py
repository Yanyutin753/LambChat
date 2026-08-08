from __future__ import annotations

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
