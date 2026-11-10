from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import share


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference,by_id,by_value,expected",
    [
        (None, None, None, None),
        ("model-uuid", "展示名", None, "展示名"),
        ("provider/model", None, "旧模型展示名", "旧模型展示名"),
        ("deleted-uuid", None, None, None),
    ],
)
async def test_shared_model_name(monkeypatch, reference, by_id, by_value, expected):
    storage = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(label=by_id) if by_id else None),
        get_by_value=AsyncMock(return_value=SimpleNamespace(label=by_value) if by_value else None),
    )
    monkeypatch.setattr(share, "get_model_storage", lambda: storage)

    assert await share._shared_model_name(reference) == expected
    if not reference:
        storage.get.assert_not_awaited()
    if by_id:
        storage.get_by_value.assert_not_awaited()
