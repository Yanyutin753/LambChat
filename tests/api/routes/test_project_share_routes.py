"""项目维度分享路由测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes import share as share_route
from src.kernel.schemas.share import (
    ProjectSnapshot,
    ShareCreate,
    SharedSession,
    ShareScope,
    ShareType,
    ShareUpdate,
    ShareVisibility,
)


def _user(sub: str = "user-1", permissions: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(sub=sub, permissions=permissions or ["session:share"])


class _FakeProjectStorage:
    def __init__(self, project: SimpleNamespace | None) -> None:
        self.project = project

    async def get_by_id(self, project_id: str, user_id: str):
        if self.project and self.project.id == project_id and self.project.user_id == user_id:
            return self.project
        return None


class _FakeSessionStorage:
    def __init__(self, project_session_ids: list[str]) -> None:
        self.project_session_ids = project_session_ids

    async def list_ids_by_project(self, project_id: str, user_id: str) -> list[str]:
        return list(self.project_session_ids)


class _FakeShareStorage:
    def __init__(self) -> None:
        self.created_with: dict[str, Any] = {}
        self.project_snapshot_received: Any = "UNSET"
        self.listed_project: tuple[str, str] | None = None

    async def create(self, share_data, owner_id, project_snapshot=None):
        self.created_with = {
            "share_scope": share_data.share_scope,
            "project_id": share_data.project_id,
            "session_ids": share_data.session_ids,
            "share_type": share_data.share_type,
            "visibility": share_data.visibility,
            "owner_id": owner_id,
        }
        self.project_snapshot_received = project_snapshot
        return SharedSession(
            id="db-1",
            share_id="sharetoken",
            session_id=share_data.session_id,
            owner_id=owner_id,
            share_scope=share_data.share_scope,
            share_type=share_data.share_type,
            run_ids=share_data.run_ids,
            session_ids=share_data.session_ids,
            project_id=share_data.project_id,
            project_snapshot=project_snapshot,
            visibility=share_data.visibility,
        )

    async def list_by_project(self, project_id: str, owner_id: str):
        self.listed_project = (project_id, owner_id)
        return []


# ---------------------------------------------------------------------------
# _validate_share_payload
# ---------------------------------------------------------------------------


def test_validate_payload_project_full_requires_project_id() -> None:
    data = ShareCreate(share_scope=ShareScope.PROJECT, share_type=ShareType.FULL)
    with pytest.raises(Exception):
        share_route._validate_share_payload(data)


def test_validate_payload_project_partial_requires_session_ids() -> None:
    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.PARTIAL,
    )
    with pytest.raises(Exception):
        share_route._validate_share_payload(data)


def test_validate_payload_project_partial_enforces_limit() -> None:
    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.PARTIAL,
        session_ids=[f"s{i}" for i in range(share_route.SHARE_PROJECT_SESSIONS_LIMIT + 1)],
    )
    with pytest.raises(Exception):
        share_route._validate_share_payload(data)


def test_validate_payload_project_full_ok() -> None:
    data = ShareCreate(share_scope=ShareScope.PROJECT, project_id="p1", share_type=ShareType.FULL)
    # should not raise
    share_route._validate_share_payload(data)


def test_validate_payload_session_still_requires_session_id() -> None:
    data = ShareCreate(share_scope=ShareScope.SESSION, share_type=ShareType.FULL)
    with pytest.raises(Exception):
        share_route._validate_share_payload(data)


# ---------------------------------------------------------------------------
# _validate_project_share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_project_share_rejects_non_member_session_ids(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="P", icon="💬")
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    monkeypatch.setattr(
        share_route,
        "SessionStorage",
        lambda: _FakeSessionStorage(project_session_ids=["s1", "s2"]),
    )

    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.PARTIAL,
        session_ids=["s1", "sX"],  # sX 不属于项目
    )
    with pytest.raises(Exception):
        await share_route._validate_project_share(data, _user())


@pytest.mark.asyncio
async def test_validate_project_share_returns_frozen_snapshot(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="我的项目", icon="⭐")
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    monkeypatch.setattr(
        share_route,
        "SessionStorage",
        lambda: _FakeSessionStorage(project_session_ids=["s1", "s2"]),
    )

    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.PARTIAL,
        session_ids=["s1"],
    )
    snapshot = await share_route._validate_project_share(data, _user())
    assert snapshot == ProjectSnapshot(id="p1", name="我的项目", icon="⭐")


@pytest.mark.asyncio
async def test_validate_project_share_rejects_other_users_project(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="P", icon="💬")
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))

    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.FULL,
    )
    with pytest.raises(Exception):
        await share_route._validate_project_share(data, _user(sub="user-2"))


# ---------------------------------------------------------------------------
# create_share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_project_full_passes_snapshot(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="项目A", icon="🚀")
    share_storage = _FakeShareStorage()
    monkeypatch.setattr(share_route, "ShareStorage", lambda: share_storage)
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    monkeypatch.setattr(
        share_route,
        "SessionStorage",
        lambda: _FakeSessionStorage(project_session_ids=[]),
    )

    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.FULL,
    )
    resp = await share_route.create_share(data, _user())

    assert resp.share_scope == ShareScope.PROJECT
    assert resp.project_id == "p1"
    assert resp.url == "/shared/sharetoken"
    assert share_storage.project_snapshot_received == ProjectSnapshot(
        id="p1", name="项目A", icon="🚀"
    )
    assert share_storage.created_with["share_type"] == ShareType.FULL


@pytest.mark.asyncio
async def test_create_share_project_partial_stores_session_ids(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="项目A", icon="🚀")
    share_storage = _FakeShareStorage()
    monkeypatch.setattr(share_route, "ShareStorage", lambda: share_storage)
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    monkeypatch.setattr(
        share_route,
        "SessionStorage",
        lambda: _FakeSessionStorage(project_session_ids=["s1", "s2", "s3"]),
    )

    data = ShareCreate(
        share_scope=ShareScope.PROJECT,
        project_id="p1",
        share_type=ShareType.PARTIAL,
        session_ids=["s2", "s3"],
    )
    resp = await share_route.create_share(data, _user())

    assert resp.share_scope == ShareScope.PROJECT
    assert sorted(resp.session_ids) == ["s2", "s3"]


@pytest.mark.asyncio
async def test_create_share_session_scope_backward_compatible(monkeypatch) -> None:
    """老的单会话分享路径仍正常工作。"""

    class _Manager:
        async def get_session(self, session_id):
            return SimpleNamespace(
                id=session_id,
                user_id="user-1",
                agent_id="fast",
                metadata={},
                created_at=None,
                updated_at=None,
                task_status=None,
                task_error=None,
                completed_at=None,
                name="hello",
            )

    share_storage = _FakeShareStorage()
    monkeypatch.setattr(share_route, "ShareStorage", lambda: share_storage)
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())

    data = ShareCreate(
        share_scope=ShareScope.SESSION,
        session_id="sess-1",
        share_type=ShareType.FULL,
    )
    resp = await share_route.create_share(data, _user())

    assert resp.share_scope == ShareScope.SESSION
    assert resp.session_id == "sess-1"
    assert share_storage.project_snapshot_received is None


@pytest.mark.asyncio
async def test_update_project_partial_visibility_keeps_stale_membership_snapshot(
    monkeypatch,
) -> None:
    """Changing visibility must not revalidate an unchanged membership snapshot."""
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["moved-session"])

    class _Storage:
        async def get_by_id(self, _share_id):
            return share

        async def update(
            self,
            _share_id,
            owner_id,
            share_type,
            run_ids,
            visibility,
            session_ids,
        ):
            return share.model_copy(
                update={
                    "owner_id": owner_id,
                    "share_type": share_type,
                    "run_ids": run_ids,
                    "visibility": visibility,
                    "session_ids": session_ids,
                }
            )

    class _ProjectStorage:
        async def get_by_id(self, _project_id, _owner_id):
            raise AssertionError("unchanged snapshots must not be revalidated")

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _ProjectStorage())

    response = await share_route.update_share(
        "db-1",
        ShareUpdate(visibility=ShareVisibility.AUTHENTICATED),
        _user(),
    )

    assert response.visibility == ShareVisibility.AUTHENTICATED
    assert response.session_ids == ["moved-session"]


# ---------------------------------------------------------------------------
# list_project_shares
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_project_shares_requires_project_owner(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="P", icon="💬")
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    with pytest.raises(Exception):
        await share_route.list_project_shares("p1", _user(sub="user-2"))


@pytest.mark.asyncio
async def test_list_project_shares_returns_shares(monkeypatch) -> None:
    project = SimpleNamespace(id="p1", user_id="user-1", name="项目A", icon="💬")
    share_storage = _FakeShareStorage()
    monkeypatch.setattr(share_route, "get_project_storage", lambda: _FakeProjectStorage(project))
    monkeypatch.setattr(share_route, "ShareStorage", lambda: share_storage)

    result = await share_route.list_project_shares("p1", _user())
    assert result == []
    assert share_storage.listed_project == ("p1", "user-1")


# ---------------------------------------------------------------------------
# get_shared_content dispatch (manifest vs session)
# ---------------------------------------------------------------------------


def _project_share(
    share_type: ShareType = ShareType.FULL,
    session_ids: list[str] | None = None,
    project_snapshot: ProjectSnapshot | None = None,
    visibility: ShareVisibility = ShareVisibility.PUBLIC,
) -> SharedSession:
    return SharedSession(
        id="db-1",
        share_id="sharetoken",
        session_id=None,
        owner_id="user-1",
        share_scope=ShareScope.PROJECT,
        share_type=share_type,
        session_ids=session_ids,
        project_id="p1",
        project_snapshot=project_snapshot or ProjectSnapshot(id="p1", name="项目A", icon="💬"),
        visibility=visibility,
    )


@pytest.mark.asyncio
async def test_get_shared_content_project_returns_manifest(monkeypatch) -> None:
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["s1", "s2"])

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    sessions = {
        "s1": SimpleNamespace(id="s1", name="会话1", agent_id="fast", metadata={}, updated_at=None),
        "s2": SimpleNamespace(id="s2", name="会话2", agent_id="fast", metadata={}, updated_at=None),
    }

    class _Manager:
        async def get_sessions(self, ids):
            return {sid: sessions[sid] for sid in ids if sid in sessions}

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    resp = await share_route.get_shared_content("sharetoken")

    assert resp.share_scope == ShareScope.PROJECT
    assert resp.project.name == "项目A"
    assert {s.id for s in resp.sessions} == {"s1", "s2"}
    assert resp.owner.username == "alice"


@pytest.mark.asyncio
async def test_get_shared_content_project_full_uses_live_members(monkeypatch) -> None:
    share = _project_share(share_type=ShareType.FULL)

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    class _SessionStorage:
        async def list_ids_by_project(self, _pid, _uid):
            return ["live-1", "live-2"]

    class _Manager:
        async def get_sessions(self, ids):
            return {
                sid: SimpleNamespace(
                    id=sid, name=sid, agent_id="fast", metadata={}, updated_at=None
                )
                for sid in ids
            }

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionStorage", lambda: _SessionStorage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    resp = await share_route.get_shared_content("sharetoken")
    assert resp.share_type == ShareType.FULL
    assert resp.sessions_total == 2


@pytest.mark.asyncio
async def test_get_shared_content_session_scope_still_returns_events(monkeypatch) -> None:
    """会话维度公开读未受重构影响。"""
    share = SharedSession(
        id="db-1",
        share_id="sharetoken",
        session_id="sess-1",
        owner_id="user-1",
        share_scope=ShareScope.SESSION,
        share_type=ShareType.FULL,
        visibility=ShareVisibility.PUBLIC,
    )

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    class _Manager:
        async def get_session(self, _sid):
            return SimpleNamespace(
                id="sess-1",
                name="hello",
                agent_id="fast",
                metadata={},
                created_at=None,
                updated_at=None,
                task_status=None,
                task_error=None,
                completed_at=None,
                user_id="user-1",
            )

    class _DualWriter:
        async def read_session_events(self, session_id, **_kwargs):
            return [{"event_type": "user:message", "data": {"content": "hi"}}]

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: _DualWriter())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    resp = await share_route.get_shared_content("sharetoken")
    assert resp.share_scope == ShareScope.SESSION
    assert resp.events[0]["event_type"] == "user:message"


# ---------------------------------------------------------------------------
# get_shared_session_in_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subsession_rejects_non_member(monkeypatch) -> None:
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["s1"])

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())

    with pytest.raises(Exception):
        await share_route.get_shared_session_in_project("sharetoken", "sX")


@pytest.mark.asyncio
async def test_subsession_rejects_session_scope_share(monkeypatch) -> None:
    share = SharedSession(
        id="db-1",
        share_id="sharetoken",
        session_id="sess-1",
        owner_id="user-1",
        share_scope=ShareScope.SESSION,
        share_type=ShareType.FULL,
        visibility=ShareVisibility.PUBLIC,
    )

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    with pytest.raises(Exception):
        await share_route.get_shared_session_in_project("sharetoken", "sess-1")


@pytest.mark.asyncio
async def test_subsession_returns_events_for_member(monkeypatch) -> None:
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["s1"])

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    class _Manager:
        async def get_session(self, _sid):
            return SimpleNamespace(
                id="s1",
                name="会话1",
                agent_id="fast",
                metadata={},
                created_at=None,
                updated_at=None,
                task_status=None,
                task_error=None,
                completed_at=None,
                user_id="user-1",
            )

    class _DualWriter:
        async def read_session_events(self, session_id, **_kwargs):
            return [{"event_type": "assistant:message", "data": {"content": "yo"}}]

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: _DualWriter())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    resp = await share_route.get_shared_session_in_project("sharetoken", "s1")
    assert resp.share_scope == ShareScope.SESSION
    assert resp.events[0]["event_type"] == "assistant:message"


@pytest.mark.asyncio
async def test_project_partial_subsession_does_not_apply_session_run_filter(monkeypatch) -> None:
    """Project partial freezes membership, not run IDs inside each session."""
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["s1"])
    share.run_ids = ["run-from-unrelated-session-share"]
    captured_kwargs: dict[str, Any] = {}

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    class _Manager:
        async def get_session(self, _sid):
            return SimpleNamespace(
                id="s1",
                name="会话1",
                agent_id="fast",
                metadata={},
                created_at=None,
                updated_at=None,
                task_status=None,
                task_error=None,
                completed_at=None,
                user_id="user-1",
            )

    class _DualWriter:
        async def read_session_events(self, session_id, **kwargs):
            captured_kwargs.update(kwargs)
            return []

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "get_dual_writer", lambda: _DualWriter())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    response = await share_route.get_shared_session_in_project("sharetoken", "s1")

    assert "run_ids" not in captured_kwargs
    assert response.run_ids is None


# ---------------------------------------------------------------------------
# project manifest pagination (has_more / session_skip / session_limit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shared_content_project_paginates(monkeypatch) -> None:
    """项目 manifest 支持分页：has_more 在未取完时为 True，取完为 False。"""
    share = _project_share(share_type=ShareType.PARTIAL, session_ids=["s1", "s2", "s3"])

    class _Storage:
        async def get_by_share_id(self, _sid):
            return share

    sessions = {
        sid: SimpleNamespace(id=sid, name=sid, agent_id="fast", metadata={}, updated_at=None)
        for sid in ["s1", "s2", "s3"]
    }

    class _Manager:
        async def get_sessions(self, ids):
            return {sid: sessions[sid] for sid in ids if sid in sessions}

    class _UserStorage:
        async def get_by_id(self, _uid):
            return SimpleNamespace(username="alice", avatar_url=None)

    monkeypatch.setattr(share_route, "ShareStorage", lambda: _Storage())
    monkeypatch.setattr(share_route, "SessionManager", lambda: _Manager())
    monkeypatch.setattr(share_route, "UserStorage", lambda: _UserStorage())

    page1 = await share_route.get_shared_content("sharetoken", session_limit=2, session_skip=0)
    assert page1.share_scope == ShareScope.PROJECT
    assert len(page1.sessions) == 2
    assert page1.sessions_total == 3
    assert page1.has_more is True

    page2 = await share_route.get_shared_content("sharetoken", session_limit=2, session_skip=2)
    assert len(page2.sessions) == 1
    assert page2.has_more is False
