"""Tests for get_mongo_client reading pool sizes from settings (P0-3).

Seam under test: the ``get_mongo_client`` lru_cache singleton in
``src.infra.storage.mongodb``. We inject a fake ``AsyncIOMotorClient`` to assert
the pool-size kwargs come from settings, without exercising motor internals.
Pattern follows the checkpointer pool test (test_mongo_checkpointer_pool.py).
"""

from __future__ import annotations

import pytest

from src.infra.storage import mongodb as mongodb_mod


@pytest.fixture(autouse=True)
def _reset_mongo_client_cache() -> None:
    """Ensure each test starts with a fresh lru_cache (no leaked singleton)."""
    mongodb_mod.get_mongo_client.cache_clear()
    yield
    mongodb_mod.get_mongo_client.cache_clear()


def _install_fake_motor(monkeypatch: pytest.MonkeyPatch, capture: dict) -> None:
    """Replace motor's AsyncIOMotorClient constructor with a recording fake."""

    class _FakeMotorClient:
        def __init__(self, connection_string: str, **kwargs: object) -> None:
            self._kwargs = {"connection_string": connection_string, **kwargs}
            capture.setdefault("clients", []).append(self)

        def close(self) -> None:
            capture["close_count"] = capture.get("close_count", 0) + 1

    monkeypatch.setattr("motor.motor_asyncio.AsyncIOMotorClient", _FakeMotorClient)


def _plain_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep build_mongo_connection_string on a credential-free URL."""
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_USERNAME", "")
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_PASSWORD", "")


def test_get_mongo_client_reads_pool_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    capture: dict = {}
    _install_fake_motor(monkeypatch, capture)
    _plain_connection(monkeypatch)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_POOL_MAX_SIZE", 15)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_POOL_MIN_SIZE", 5)

    client = mongodb_mod.get_mongo_client()

    assert client is capture["clients"][0]
    kwargs = capture["clients"][0]._kwargs
    assert kwargs["maxPoolSize"] == 15
    assert kwargs["minPoolSize"] == 5


def test_get_mongo_client_defaults_when_settings_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default settings (20/2) must reproduce the prior hardcoded behavior exactly."""
    capture: dict = {}
    _install_fake_motor(monkeypatch, capture)
    _plain_connection(monkeypatch)

    mongodb_mod.get_mongo_client()

    kwargs = capture["clients"][0]._kwargs
    assert kwargs["maxPoolSize"] == 20
    assert kwargs["minPoolSize"] == 2
