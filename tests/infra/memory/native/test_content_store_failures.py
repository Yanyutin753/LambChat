"""Unavailable content storage must never certify a saved or erased body."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.memory.client.native import content
from src.kernel.errors import AppError


@pytest.mark.parametrize("store", [None, object()])
async def test_long_body_write_refuses_missing_store_before_returning_a_pointer(monkeypatch, store):
    monkeypatch.setattr(content, "get_store", AsyncMock(return_value=store))
    with pytest.raises(AppError):
        await content.build_content_fields(SimpleNamespace(), "owner", "memory", "fact " * 500)


@pytest.mark.parametrize("store", [None, object()])
async def test_body_delete_refuses_missing_store_instead_of_certifying_erasure(monkeypatch, store):
    monkeypatch.setattr(content, "get_store", AsyncMock(return_value=store))
    with pytest.raises(AppError):
        await content.store_delete(SimpleNamespace(), ("memories", "owner", "content"), "key")
