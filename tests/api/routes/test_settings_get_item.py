"""GET /settings/{key} must go through the service layer (cache-backed).

The route used to call service._storage.get directly, bypassing the
service-layer get_all cache — every single-key lookup hit MongoDB. The
service now exposes get_item() which serves masked SettingItem responses
from the shared cache.
"""

from pathlib import Path

import pytest

from src.api.routes import settings as settings_routes
from src.infra.settings.service import SettingsService
from src.kernel.errors import AppError
from src.kernel.schemas.setting import SettingCategory, SettingItem, SettingType

ROUTE_SOURCE = Path(settings_routes.__file__).read_text(encoding="utf-8")


def test_route_no_longer_bypasses_service_layer() -> None:
    assert "service._storage" not in ROUTE_SOURCE
    assert "await service.get_item(key)" in ROUTE_SOURCE


@pytest.mark.asyncio
async def test_route_returns_item_via_service_get_item() -> None:
    item = SettingItem(
        key="DEFAULT_AGENT",
        value="fast-agent",
        type=SettingType.STRING,
        category=SettingCategory.FRONTEND,
        description="",
        default_value="",
    )

    class _Service:
        async def get_item(self, key: str):
            assert key == "DEFAULT_AGENT"
            return item

    response = await settings_routes.get_setting(
        key="DEFAULT_AGENT",
        service=_Service(),  # type: ignore[arg-type]
    )
    assert response.value == "fast-agent"


@pytest.mark.asyncio
async def test_route_raises_not_found_when_item_missing() -> None:
    class _Service:
        async def get_item(self, key: str):
            return None

    with pytest.raises(AppError):
        await settings_routes.get_setting(
            key="NOPE",
            service=_Service(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_service_get_item_serves_from_get_all_cache() -> None:
    service = SettingsService()
    loaded: list[tuple[bool, bool]] = []

    class _Storage:
        async def get_all(self, *, admin_mode=False, mask_sensitive=True):
            loaded.append((admin_mode, mask_sensitive))
            inner = SettingItem(
                key="DEFAULT_AGENT",
                value="fast-agent",
                type=SettingType.STRING,
                category=SettingCategory.FRONTEND,
                description="",
                default_value="",
            )
            return {"general": [inner]}

    service._storage = _Storage()  # type: ignore[assignment]

    first = await service.get_item("DEFAULT_AGENT")
    second = await service.get_item("DEFAULT_AGENT")

    assert first is not None and first.value == "fast-agent"
    assert second is not None and second.value == "fast-agent"
    # Second lookup hits the in-memory cache — storage only queried once.
    assert loaded == [(True, True)]


@pytest.mark.asyncio
async def test_service_get_item_unknown_key_returns_none() -> None:
    service = SettingsService()
    assert await service.get_item("NOT_A_DEFINED_SETTING") is None
