from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.infra.settings import pubsub as settings_pubsub


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["TEST_SETTING", None])
async def test_remote_setting_change_invalidates_snapshot_before_refresh(
    monkeypatch: pytest.MonkeyPatch,
    key: str | None,
) -> None:
    calls: list[str] = []

    class _Service:
        def invalidate_get_all_cache(self) -> None:
            calls.append("invalidate")

    async def _refresh(received_key):
        calls.append(f"refresh:{received_key}")

    listener = settings_pubsub.SettingsPubSub()
    monkeypatch.setattr(
        "src.infra.settings.service.get_settings_service",
        lambda: _Service(),
    )
    monkeypatch.setattr("src.kernel.config.refresh_settings", AsyncMock(side_effect=_refresh))

    await listener._handle_message(
        {
            "data": json.dumps(
                {
                    "key": key,
                    "instance_id": "another-instance",
                }
            )
        }
    )

    assert calls == ["invalidate", f"refresh:{key}"]
