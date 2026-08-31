"""Tests for session pin toggle API route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.deps import TokenPayload
from src.api.routes.session import router


def _make_user(user_id: str = "user_1") -> TokenPayload:
    return TokenPayload(sub=user_id, username="tester", exp=9999999999)


def _find_pin_route():
    """Locate the POST /pin route handler, if registered."""
    for route in router.routes:
        if (
            hasattr(route, "path")
            and route.path.endswith("/pin")
            and hasattr(route, "methods")
            and "POST" in route.methods
        ):
            return route.endpoint
    return None


@pytest.mark.asyncio
async def test_toggle_pin_success():
    """Pin toggle returns correct status and session."""
    session_id = "abc123"
    user = _make_user()

    mock_session = MagicMock()
    mock_session.user_id = "user_1"
    mock_session.metadata = {"is_pinned": True}

    mock_manager = AsyncMock()
    mock_manager.get_session = AsyncMock(return_value=mock_session)

    mock_storage = AsyncMock()
    mock_storage.toggle_pin = AsyncMock(return_value=mock_session)

    mock_normalized = MagicMock()
    mock_normalized.metadata = {"is_pinned": True}

    with (
        patch("src.api.routes.session.SessionManager", return_value=mock_manager),
        patch("src.api.routes.session.SessionStorage", return_value=mock_storage),
        patch("src.api.routes.session.verify_session_ownership"),
        patch(
            "src.api.routes.session._get_favorites_project_id",
            new=AsyncMock(return_value=None),
        ),
        patch("src.api.routes.session._normalize_session", return_value=mock_normalized),
    ):
        handler = _find_pin_route()
        if handler is None:
            pytest.fail("No /pin POST route found")
        response = await handler(session_id, user=user)
        assert response["status"] == "updated"
        assert response["is_pinned"] is True
        assert response["session"] is mock_normalized

        # The route looks up the session via the manager first, so sessions
        # with custom string session_id fields are found before toggle_pin.
        mock_manager.get_session.assert_awaited_once_with(session_id)
        mock_storage.toggle_pin.assert_awaited_once_with(session_id, "user_1")


@pytest.mark.asyncio
async def test_toggle_pin_session_not_found():
    """Route raises 404 when the session does not exist."""
    from src.kernel.errors import AppError

    user = _make_user()

    mock_manager = AsyncMock()
    mock_manager.get_session = AsyncMock(return_value=None)

    mock_storage = AsyncMock()

    with (
        patch("src.api.routes.session.SessionManager", return_value=mock_manager),
        patch("src.api.routes.session.SessionStorage", return_value=mock_storage),
    ):
        handler = _find_pin_route()
        if handler is None:
            pytest.fail("No /pin POST route found")
        with pytest.raises(AppError) as exc_info:
            await handler("missing", user=user)

    assert exc_info.value.error_code.code == "session_not_found"
    assert exc_info.value.http_status == 404
    mock_storage.toggle_pin.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_pin_storage_failure():
    """Route raises 500 when the storage toggle returns None."""
    from src.kernel.errors import AppError

    user = _make_user()

    mock_session = MagicMock()
    mock_session.user_id = "user_1"
    mock_session.metadata = {}

    mock_manager = AsyncMock()
    mock_manager.get_session = AsyncMock(return_value=mock_session)

    mock_storage = AsyncMock()
    mock_storage.toggle_pin = AsyncMock(return_value=None)

    with (
        patch("src.api.routes.session.SessionManager", return_value=mock_manager),
        patch("src.api.routes.session.SessionStorage", return_value=mock_storage),
        patch("src.api.routes.session.verify_session_ownership"),
        patch(
            "src.api.routes.session._get_favorites_project_id",
            new=AsyncMock(return_value=None),
        ),
    ):
        handler = _find_pin_route()
        if handler is None:
            pytest.fail("No /pin POST route found")
        with pytest.raises(AppError) as exc_info:
            await handler("abc123", user=user)

    assert exc_info.value.error_code.code == "pin_update_failed"
    assert exc_info.value.http_status == 500


@pytest.mark.asyncio
async def test_toggle_pin_unpinned_state():
    """Pin toggle reports is_pinned=False after unpinning."""
    user = _make_user()

    mock_session = MagicMock()
    mock_session.user_id = "user_1"
    mock_session.metadata = {"is_pinned": False}

    mock_manager = AsyncMock()
    mock_manager.get_session = AsyncMock(return_value=mock_session)

    mock_storage = AsyncMock()
    mock_storage.toggle_pin = AsyncMock(return_value=mock_session)

    mock_normalized = MagicMock()
    mock_normalized.metadata = {"is_pinned": False}

    with (
        patch("src.api.routes.session.SessionManager", return_value=mock_manager),
        patch("src.api.routes.session.SessionStorage", return_value=mock_storage),
        patch("src.api.routes.session.verify_session_ownership"),
        patch(
            "src.api.routes.session._get_favorites_project_id",
            new=AsyncMock(return_value=None),
        ),
        patch("src.api.routes.session._normalize_session", return_value=mock_normalized),
    ):
        handler = _find_pin_route()
        if handler is None:
            pytest.fail("No /pin POST route found")
        response = await handler("abc123", user=user)
        assert response["is_pinned"] is False
