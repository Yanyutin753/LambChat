from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import share as share_route
from src.kernel.schemas.share import ShareCreate, ShareType, ShareUpdate, ShareVisibility
from src.kernel.types import Permission


class _FakeShareStorage:
    async def get_by_share_id(self, share_id: str):
        assert share_id == "share-1"
        return SimpleNamespace(
            share_id="share-1",
            session_id="session-1",
            owner_id="owner-1",
            share_type=ShareType.FULL,
            visibility=ShareVisibility.PUBLIC,
            run_ids=None,
        )


class _FakeLargePartialShareStorage:
    async def get_by_share_id(self, share_id: str):
        assert share_id == "share-large"
        return SimpleNamespace(
            share_id="share-large",
            session_id="session-1",
            owner_id="owner-1",
            share_type=ShareType.PARTIAL,
            visibility=ShareVisibility.PUBLIC,
            run_ids=[
                f"run-{index}" for index in range(share_route.SHARE_PARTIAL_RUN_IDS_LIMIT + 5)
            ],
        )


class _FakeSessionManager:
    async def get_session(self, session_id: str):
        assert session_id in {"session-1", "owned-session"}
        now = datetime(2026, 4, 25, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=session_id,
            user_id="owner-1",
            name="Shared Session",
            agent_id="agent-1",
            metadata={},
            created_at=now,
            updated_at=now,
            task_status=None,
            task_error=None,
            completed_at=None,
        )


class _FakeDualWriter:
    def __init__(self):
        self.calls = []

    async def read_session_events(self, session_id: str, **kwargs):
        self.calls.append({"session_id": session_id, **kwargs})
        return [
            {"event_type": "user:message", "data": {"content": "one"}},
            {"event_type": "message:chunk", "data": {"content": "two"}},
            {"event_type": "done", "data": {}},
        ]


class _FakeUserStorage:
    async def get_by_id(self, user_id: str):
        assert user_id == "owner-1"
        return SimpleNamespace(username="owner", avatar_url=None)


def _raise_unknown_agent(_agent_id: str):
    raise ValueError("unknown agent")


def test_get_shared_content_event_limit_has_no_upper_bound_in_route_validation() -> None:
    route = next(route for route in share_route.router.routes if route.path == "/public/{share_id}")
    limit_param = next(
        param for param in route.dependant.query_params if param.name == "event_limit"
    )
    constraints = {
        type(item).__name__: getattr(item, "ge", getattr(item, "le", None))
        for item in limit_param.field_info.metadata
    }

    assert constraints["Ge"] == 1
    assert "Le" not in constraints


class _CreateShouldNotBeCalledShareStorage:
    async def create(self, *_args, **_kwargs):
        raise AssertionError("oversized partial share should be rejected before storage")


class _FakeUpdateShareStorage:
    def __init__(self):
        self.updated = None

    async def get_by_id(self, share_id: str):
        assert share_id == "share-db-id"
        return SimpleNamespace(
            id="share-db-id",
            share_id="stable-share",
            session_id="owned-session",
            owner_id="owner-1",
            share_type=ShareType.FULL,
            visibility=ShareVisibility.PUBLIC,
            run_ids=None,
            created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        )

    async def update(self, share_id: str, **kwargs):
        self.updated = {"share_id": share_id, **kwargs}
        return SimpleNamespace(
            id="share-db-id",
            share_id="stable-share",
            session_id="owned-session",
            owner_id="owner-1",
            share_type=ShareType.PARTIAL,
            visibility=ShareVisibility.AUTHENTICATED,
            run_ids=["run-1"],
            created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_create_share_rejects_partial_share_with_too_many_run_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(share_route, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(share_route, "ShareStorage", _CreateShouldNotBeCalledShareStorage)

    user = SimpleNamespace(
        sub="owner-1",
        permissions=[Permission.SESSION_SHARE.value],
    )
    share_data = ShareCreate(
        session_id="owned-session",
        share_type=ShareType.PARTIAL,
        run_ids=[f"run-{index}" for index in range(share_route.SHARE_PARTIAL_RUN_IDS_LIMIT + 1)],
        visibility=ShareVisibility.PUBLIC,
    )

    with pytest.raises(HTTPException) as exc_info:
        await share_route.create_share(share_data, user=user)

    assert exc_info.value.status_code == 400
    assert "run_ids" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_share_edits_existing_share_without_changing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeUpdateShareStorage()
    monkeypatch.setattr(share_route, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(share_route, "ShareStorage", lambda: storage)

    user = SimpleNamespace(
        sub="owner-1",
        permissions=[Permission.SESSION_SHARE.value],
    )
    update_data = ShareUpdate(
        share_type=ShareType.PARTIAL,
        run_ids=["run-1"],
        visibility=ShareVisibility.AUTHENTICATED,
    )

    response = await share_route.update_share("share-db-id", update_data, user=user)

    assert response.share_id == "stable-share"
    assert response.url == "/shared/stable-share"
    assert response.share_type == ShareType.PARTIAL
    assert response.visibility == ShareVisibility.AUTHENTICATED
    assert response.run_ids == ["run-1"]
    assert storage.updated == {
        "share_id": "share-db-id",
        "owner_id": "owner-1",
        "share_type": ShareType.PARTIAL,
        "run_ids": ["run-1"],
        "visibility": ShareVisibility.AUTHENTICATED,
    }


@pytest.mark.asyncio
async def test_get_shared_content_returns_all_events_when_limit_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dual_writer = _FakeDualWriter()
    monkeypatch.setattr(share_route, "ShareStorage", _FakeShareStorage)
    monkeypatch.setattr(share_route, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: dual_writer)
    monkeypatch.setattr(share_route, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(share_route, "get_agent_class", _raise_unknown_agent)

    response = await share_route.get_shared_content("share-1", user=None)

    assert dual_writer.calls == [
        {
            "session_id": "session-1",
            "completed_only": True,
        }
    ]
    assert len(response.events) == 3
    assert response.events_limited is False
    assert response.events_limit is None


@pytest.mark.asyncio
async def test_get_shared_content_caps_legacy_partial_share_run_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dual_writer = _FakeDualWriter()
    monkeypatch.setattr(share_route, "ShareStorage", _FakeLargePartialShareStorage)
    monkeypatch.setattr(share_route, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: dual_writer)
    monkeypatch.setattr(share_route, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(share_route, "get_agent_class", _raise_unknown_agent)

    response = await share_route.get_shared_content(
        "share-large",
        event_limit=10,
        user=None,
    )

    capped_run_ids = [f"run-{index}" for index in range(share_route.SHARE_PARTIAL_RUN_IDS_LIMIT)]
    assert dual_writer.calls[0]["run_ids"] == capped_run_ids
    assert response.run_ids == capped_run_ids


@pytest.mark.asyncio
async def test_get_shared_content_caps_full_share_events_with_probe_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dual_writer = _FakeDualWriter()
    monkeypatch.setattr(share_route, "ShareStorage", _FakeShareStorage)
    monkeypatch.setattr(share_route, "SessionManager", _FakeSessionManager)
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: dual_writer)
    monkeypatch.setattr(share_route, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(share_route, "get_agent_class", _raise_unknown_agent)

    response = await share_route.get_shared_content(
        "share-1",
        event_limit=2,
        user=None,
    )

    assert dual_writer.calls == [
        {
            "session_id": "session-1",
            "completed_only": True,
            "max_events": 3,
        }
    ]
    assert len(response.events) == 2
    assert response.events_limited is True
    assert response.events_limit == 2
