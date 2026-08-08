from __future__ import annotations

import logging

import pytest


@pytest.mark.asyncio
async def test_initialize_settings_does_not_log_redis_url(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.settings.service import SettingsService
    from src.kernel.config import service as config_service

    secret_url = "redis://user:secret@redis.example.test:6379/0"

    class _FakeSettingsService:
        async def initialize(self) -> None:
            return None

        async def get_all(
            self,
            admin_mode: bool = True,
            mask_sensitive: bool = False,
        ) -> dict:
            return {}

    fake_service = _FakeSettingsService()
    monkeypatch.setattr(SettingsService, "get_instance", staticmethod(lambda: fake_service))
    monkeypatch.setattr(config_service, "_settings_service", None)
    monkeypatch.setattr(config_service.settings, "REDIS_URL", secret_url)
    monkeypatch.setattr(config_service.settings, "_vapid_keys_generated", False)

    with caplog.at_level(logging.INFO):
        await config_service.initialize_settings()

    assert secret_url not in caplog.text
