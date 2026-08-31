"""消息书签路由测试

toggle 路由挂在 session 路由上（与 fork/checkpoint 同级），
列表路由挂在独立 bookmark 路由上。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.deps import TokenPayload
from src.api.routes import bookmark as bookmark_routes
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.bookmark import Bookmark


def _make_user(user_id: str = "user-1") -> TokenPayload:
    return TokenPayload(sub=user_id, username="tester", exp=9999999999)


def _make_bookmark(**overrides) -> Bookmark:
    defaults = {
        "id": "bm-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "message_id": "message-1",
        "run_id": "run-1",
        "label": "大纲",
        "created_at": datetime(2026, 8, 1, 12, 0, 0),
    }
    defaults.update(overrides)
    return Bookmark(**defaults)


def _find_route(method: str, suffix: str):
    for route in bookmark_routes.router.routes:
        if (
            hasattr(route, "path")
            and route.path.endswith(suffix)
            and hasattr(route, "methods")
            and method in route.methods
        ):
            return route.endpoint
    return None


@pytest.mark.asyncio
async def test_toggle_message_bookmark_success():
    user = _make_user()
    session = MagicMock()
    session.user_id = "user-1"
    bookmark = _make_bookmark()
    toggle_result = (True, bookmark)

    with (
        patch(
            "src.api.routes.bookmark.SessionManager",
            return_value=MagicMock(get_session=AsyncMock(return_value=session)),
        ),
        patch("src.api.routes.bookmark.verify_session_ownership"),
        patch(
            "src.api.routes.bookmark.BookmarkStorage",
            return_value=MagicMock(toggle=AsyncMock(return_value=toggle_result)),
        ) as storage_cls,
    ):
        handler = _find_route("POST", "/bookmark")
        assert handler is not None, "消息书签 toggle 路由未注册"
        response = await handler("session-1", "message-1", user=user)

    assert response["status"] == "updated"
    assert response["bookmarked"] is True
    assert response["bookmark"].message_id == "message-1"
    storage_cls.return_value.toggle.assert_awaited_once_with(
        user_id="user-1",
        session_id="session-1",
        message_id="message-1",
        run_id=None,
        label=None,
    )


@pytest.mark.asyncio
async def test_toggle_message_bookmark_passes_body_fields():
    user = _make_user()
    session = MagicMock()
    session.user_id = "user-1"

    with (
        patch(
            "src.api.routes.bookmark.SessionManager",
            return_value=MagicMock(get_session=AsyncMock(return_value=session)),
        ),
        patch("src.api.routes.bookmark.verify_session_ownership"),
        patch(
            "src.api.routes.bookmark.BookmarkStorage",
            return_value=MagicMock(toggle=AsyncMock(return_value=(False, None))),
        ) as storage_cls,
    ):
        handler = _find_route("POST", "/bookmark")
        response = await handler(
            "session-1",
            "message-1",
            payload=MagicMock(run_id="run-9", label="周会纪要"),
            user=user,
        )

    assert response["bookmarked"] is False
    assert response["bookmark"] is None
    storage_cls.return_value.toggle.assert_awaited_once_with(
        user_id="user-1",
        session_id="session-1",
        message_id="message-1",
        run_id="run-9",
        label="周会纪要",
    )


@pytest.mark.asyncio
async def test_toggle_message_bookmark_session_not_found():
    user = _make_user()

    with patch(
        "src.api.routes.session.SessionManager",
        return_value=MagicMock(get_session=AsyncMock(return_value=None)),
    ):
        handler = _find_route("POST", "/bookmark")
        with pytest.raises(AppError) as exc_info:
            await handler("missing", "message-1", user=user)

    assert exc_info.value.error_code is ErrorCode.SESSION_NOT_FOUND


@pytest.mark.asyncio
async def test_toggle_message_bookmark_denies_other_users_session():
    user = _make_user()
    session = MagicMock()
    session.user_id = "user-2"

    with patch(
        "src.api.routes.bookmark.SessionManager",
        return_value=MagicMock(get_session=AsyncMock(return_value=session)),
    ):
        handler = _find_route("POST", "/bookmark")
        with pytest.raises(AppError) as exc_info:
            await handler("session-1", "message-1", user=user)

    assert exc_info.value.error_code is ErrorCode.SESSION_ACCESS_DENIED


@pytest.mark.asyncio
async def test_list_my_bookmarks_returns_items_for_current_user():
    user = _make_user()
    bookmark = _make_bookmark()

    with patch(
        "src.api.routes.bookmark.BookmarkStorage",
        return_value=MagicMock(
            list_for_user=AsyncMock(return_value=[bookmark]),
        ),
    ) as storage_cls:
        response = await bookmark_routes.list_my_bookmarks(user=user)

    assert response["total"] == 1
    assert response["items"] == [bookmark]
    storage_cls.return_value.list_for_user.assert_awaited_once_with("user-1")
