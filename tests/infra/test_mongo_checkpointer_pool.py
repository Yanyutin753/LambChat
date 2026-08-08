"""Tests for the MongoDB checkpointer's independent connection pool.

Seam under test: ``get_mongo_checkpointer`` / ``close_mongo_checkpointer``
module-level functions. We inject a fake ``pymongo.MongoClient`` and a fake
``MongoDBSaver`` to assert observable behavior (construction kwargs, singleton,
close debounce) without exercising pymongo internals. Pattern follows the
existing PG checkpointer concurrent-init test.
"""

from __future__ import annotations

from datetime import timezone

import pytest

import src.infra.storage.checkpoint as checkpoint_mod
from src.infra.storage import mongodb as mongodb_mod


@pytest.fixture(autouse=True)
def _reset_mongo_checkpointer_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset singleton state and isolate tests from local Mongo credentials."""
    checkpoint_mod._mongo_checkpointer = None
    checkpoint_mod._mongo_checkpoint_client = None
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_USERNAME", "")
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_PASSWORD", "")
    yield
    checkpoint_mod._mongo_checkpointer = None
    checkpoint_mod._mongo_checkpoint_client = None


def _install_fake_mongo(monkeypatch: pytest.MonkeyPatch, capture: dict) -> None:
    """Replace only pymongo.MongoClient so the rest of pymongo stays real.

    ``langgraph.checkpoint.mongodb`` imports other names from pymongo (e.g.
    ``ASCENDING``) at import time, so we must not swap the whole module out —
    only the constructor the factory actually calls.
    """

    class _FakeMongoClient:
        def __init__(self, connection_string: str, **kwargs: object) -> None:
            self._kwargs = {"connection_string": connection_string, **kwargs}
            capture.setdefault("clients", []).append(self)

        def close(self) -> None:
            capture.setdefault("close_count", 0)
            capture["close_count"] += 1

    monkeypatch.setattr("pymongo.MongoClient", _FakeMongoClient)


def _install_fake_saver(monkeypatch: pytest.MonkeyPatch, capture: dict) -> None:
    """Install a fake MongoDBSaver that records the client it received."""

    class _FakeSaver:
        def __init__(self, client, *, db_name, checkpoint_collection_name) -> None:
            capture.setdefault("saver_clients", []).append(client)

    monkeypatch.setattr(
        "langgraph.checkpoint.mongodb.MongoDBSaver",
        _FakeSaver,
    )


def test_mongo_checkpointer_creates_independent_client_with_pool_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)
    _install_fake_saver(monkeypatch, capture)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setattr(mongodb_mod.settings, "CHECKPOINT_MONGO_POOL_MIN_SIZE", 3)
    monkeypatch.setattr(mongodb_mod.settings, "CHECKPOINT_MONGO_POOL_MAX_SIZE", 12)

    cp = checkpoint_mod.get_mongo_checkpointer()

    assert cp is not None
    assert len(capture["clients"]) == 1
    client_kwargs = capture["clients"][0]._kwargs
    assert client_kwargs["connection_string"] == "mongodb://localhost:27017"
    assert client_kwargs["maxPoolSize"] == 12
    assert client_kwargs["minPoolSize"] == 3
    assert client_kwargs["tz_aware"] is True
    assert client_kwargs["tzinfo"] is timezone.utc
    # The saver must be built on the independent client, not a motor delegate.
    assert capture["saver_clients"][0] is capture["clients"][0]


def test_mongo_checkpointer_is_process_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)
    _install_fake_saver(monkeypatch, capture)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")

    first = checkpoint_mod.get_mongo_checkpointer()
    second = checkpoint_mod.get_mongo_checkpointer()

    assert first is second
    assert len(capture["clients"]) == 1


def test_close_mongo_checkpointer_closes_client_and_clears_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)
    _install_fake_saver(monkeypatch, capture)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")

    checkpoint_mod.get_mongo_checkpointer()
    assert checkpoint_mod._mongo_checkpoint_client is not None

    checkpoint_mod.close_mongo_checkpointer()

    assert capture["close_count"] == 1
    assert checkpoint_mod._mongo_checkpointer is None
    assert checkpoint_mod._mongo_checkpoint_client is None


def test_close_mongo_checkpointer_debounces_when_never_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)

    # Never created: close must be a no-op and must not create a client.
    checkpoint_mod.close_mongo_checkpointer()

    assert capture.get("close_count", 0) == 0
    assert capture.get("clients", []) == []


def test_mongo_checkpointer_closes_independent_client_when_saver_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")

    class _FailingSaver:
        def __init__(self, client, *, db_name, checkpoint_collection_name) -> None:
            raise RuntimeError("index setup failed")

    monkeypatch.setattr("langgraph.checkpoint.mongodb.MongoDBSaver", _FailingSaver)

    assert checkpoint_mod.get_mongo_checkpointer() is None
    assert capture["close_count"] == 1
    assert checkpoint_mod._mongo_checkpoint_client is None


def test_mongo_checkpointer_diagnostics_reports_independent_client_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict = {}
    _install_fake_mongo(monkeypatch, capture)
    _install_fake_saver(monkeypatch, capture)
    monkeypatch.setattr(mongodb_mod.settings, "MONGODB_URL", "mongodb://localhost:27017")

    assert checkpoint_mod.get_checkpointer_diagnostics()["mongo_checkpoint_client_active"] is False

    checkpoint_mod.get_mongo_checkpointer()

    assert checkpoint_mod.get_checkpointer_diagnostics()["mongo_checkpoint_client_active"] is True
