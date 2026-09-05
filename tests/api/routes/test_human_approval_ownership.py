"""HITL 审批路由归属校验测试

respond/extend/get/delete 四个端点操作具体审批记录，必须校验记录归属：
非本人的审批一律按不存在处理（404 语义，避免存在性枚举）；
user_id 缺失的旧记录回退会话归属校验；两者皆缺则拒绝。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.deps import TokenPayload
from src.api.routes import human as human_routes
from src.infra.storage.mongodb import PendingApproval
from src.kernel.errors import AppError, ErrorCode


def _make_user(user_id: str = "user-1") -> TokenPayload:
    return TokenPayload(sub=user_id, username="tester", exp=9999999999)


def _make_approval(**overrides) -> PendingApproval:
    defaults = {
        "id": "approval-1",
        "message": "请确认",
        "type": "form",
        "fields": [],
        "status": "pending",
        "session_id": "session-1",
        "user_id": "user-1",
        "created_at": datetime(2026, 9, 1, 12, 0, 0),
        "metadata": None,
    }
    defaults.update(overrides)
    return PendingApproval(**defaults)


def _make_storage(approval: PendingApproval | None, **methods) -> MagicMock:
    storage = MagicMock()
    storage.get = AsyncMock(return_value=approval)
    for name, mock in methods.items():
        setattr(storage, name, mock)
    return storage


def _find_route(method: str, suffix: str):
    for route in human_routes.router.routes:
        if (
            hasattr(route, "path")
            and route.path.endswith(suffix)
            and hasattr(route, "methods")
            and method in route.methods
        ):
            return route.endpoint
    return None


# ---------------------------------------------------------------------------
# respond
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_rejects_other_users_approval():
    approval = _make_approval(user_id="user-2")
    storage = _make_storage(approval, respond_if_pending=AsyncMock())

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("POST", "/respond")
        assert handler is not None, "respond 路由未注册"
        with pytest.raises(AppError) as exc_info:
            await handler("approval-1", approved=True, response="{}", user=_make_user())

    assert exc_info.value.error_code is ErrorCode.APPROVAL_NOT_FOUND
    storage.respond_if_pending.assert_not_awaited()


@pytest.mark.asyncio
async def test_respond_allows_owner():
    approval = _make_approval()
    updated = _make_approval(status="approved")
    storage = _make_storage(
        approval,
        respond_if_pending=AsyncMock(return_value=updated),
        expire_after=AsyncMock(),
    )

    with (
        patch.object(human_routes, "_approval_storage", storage),
        patch.object(human_routes, "notify_approval_response", AsyncMock()),
    ):
        handler = _find_route("POST", "/respond")
        result = await handler("approval-1", approved=True, response="{}", user=_make_user())

    assert result["status"] == "success"
    assert result["approved"] is True
    storage.respond_if_pending.assert_awaited_once()


# ---------------------------------------------------------------------------
# extend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extend_rejects_other_users_approval():
    approval = _make_approval(user_id="user-2")
    storage = _make_storage(approval, extend_expires_at=AsyncMock())

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("POST", "/extend")
        with pytest.raises(AppError) as exc_info:
            await handler("approval-1", extra_seconds=60, user=_make_user())

    assert exc_info.value.error_code is ErrorCode.APPROVAL_NOT_FOUND
    storage.extend_expires_at.assert_not_awaited()


@pytest.mark.asyncio
async def test_extend_allows_owner():
    approval = _make_approval()
    new_expires = datetime(2026, 9, 1, 13, 0, 0, tzinfo=timezone.utc)
    storage = _make_storage(approval, extend_expires_at=AsyncMock(return_value=new_expires))

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("POST", "/extend")
        result = await handler("approval-1", extra_seconds=60, user=_make_user())

    assert result["status"] == "success"
    assert result["expires_at"] == new_expires.isoformat()


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_not_found_shape_for_other_users_approval():
    approval = _make_approval(user_id="user-2")
    storage = _make_storage(approval)

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("GET", "/{approval_id}")
        result = await handler("approval-1", user=_make_user())

    # 与"审批不存在"同形返回，避免存在性枚举
    assert result == {"id": "approval-1", "status": "not_found"}


@pytest.mark.asyncio
async def test_get_allows_owner():
    approval = _make_approval()
    storage = _make_storage(approval)

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("GET", "/{approval_id}")
        result = await handler("approval-1", user=_make_user())

    assert result["id"] == "approval-1"
    assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rejects_other_users_approval():
    approval = _make_approval(user_id="user-2")
    storage = _make_storage(approval, delete=AsyncMock())

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("DELETE", "/{approval_id}")
        with pytest.raises(AppError) as exc_info:
            await handler("approval-1", user=_make_user())

    assert exc_info.value.error_code is ErrorCode.APPROVAL_NOT_FOUND
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_allows_owner():
    approval = _make_approval()
    storage = _make_storage(approval, delete=AsyncMock())

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("DELETE", "/{approval_id}")
        result = await handler("approval-1", user=_make_user())

    assert result == {"status": "cancelled"}
    storage.delete.assert_awaited_once_with("approval-1")


# ---------------------------------------------------------------------------
# user_id 缺失时的会话归属回退
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_user_id_falls_back_to_session_ownership_allows_owner():
    approval = _make_approval(user_id=None, session_id="session-1")
    session = MagicMock()
    session.user_id = "user-1"
    storage = _make_storage(approval, delete=AsyncMock())

    with (
        patch.object(human_routes, "_approval_storage", storage),
        patch(
            "src.api.routes.human.SessionManager",
            return_value=MagicMock(get_session=AsyncMock(return_value=session)),
        ),
    ):
        handler = _find_route("DELETE", "/{approval_id}")
        result = await handler("approval-1", user=_make_user())

    assert result == {"status": "cancelled"}
    storage.delete.assert_awaited_once_with("approval-1")


@pytest.mark.asyncio
async def test_missing_user_id_falls_back_to_session_ownership_denies_stranger():
    approval = _make_approval(user_id=None, session_id="session-1")
    session = MagicMock()
    session.user_id = "user-2"
    storage = _make_storage(approval, delete=AsyncMock())

    with (
        patch.object(human_routes, "_approval_storage", storage),
        patch(
            "src.api.routes.human.SessionManager",
            return_value=MagicMock(get_session=AsyncMock(return_value=session)),
        ),
    ):
        handler = _find_route("DELETE", "/{approval_id}")
        with pytest.raises(AppError) as exc_info:
            await handler("approval-1", user=_make_user())

    assert exc_info.value.error_code is ErrorCode.APPROVAL_NOT_FOUND
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_without_owner_or_session_denied():
    approval = _make_approval(user_id=None, session_id=None)
    storage = _make_storage(approval, delete=AsyncMock())

    with patch.object(human_routes, "_approval_storage", storage):
        handler = _find_route("DELETE", "/{approval_id}")
        with pytest.raises(AppError) as exc_info:
            await handler("approval-1", user=_make_user())

    assert exc_info.value.error_code is ErrorCode.APPROVAL_NOT_FOUND
    storage.delete.assert_not_awaited()
