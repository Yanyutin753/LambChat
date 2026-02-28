"""
SessionSandboxManager 单元测试

测试 Session-Sandbox 绑定管理器的核心逻辑。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.sandbox.session_manager import SessionSandboxManager


class TestSessionSandboxManager:
    """SessionSandboxManager 单元测试"""

    def test_init(self):
        """测试初始化"""
        manager = SessionSandboxManager()
        assert manager._session_manager is not None
        assert manager._daytona_client is None
        assert manager._cache == {}

    def test_get_daytona_client(self):
        """测试 Daytona 客户端创建"""
        with (
            patch("src.infra.sandbox.session_manager.DaytonaConfig") as mock_config,
            patch("src.infra.sandbox.session_manager.Daytona") as mock_daytona,
        ):
            manager = SessionSandboxManager()
            client = manager._get_daytona_client()

            assert client is not None
            mock_config.assert_called_once()
            mock_daytona.assert_called_once()

    def test_clear_cache(self):
        """测试清除缓存"""
        manager = SessionSandboxManager()
        manager._cache["test_session"] = ("sandbox_123", MagicMock())
        manager.clear_cache("test_session")
        assert "test_session" not in manager._cache

    @pytest.mark.asyncio
    async def test_get_sandbox_state_running(self):
        """测试获取沙箱状态 - running"""
        with patch("src.infra.sandbox.session_manager.Daytona") as mock_daytona:
            mock_client = MagicMock()
            mock_sandbox = MagicMock()
            mock_sandbox.state = "Running"
            mock_client.get.return_value = mock_sandbox
            mock_daytona.return_value = mock_client

            manager = SessionSandboxManager()
            state = await manager._get_sandbox_state("sandbox_123")

            assert state == "running"

    @pytest.mark.asyncio
    async def test_get_sandbox_state_not_found(self):
        """测试获取沙箱状态 - not found"""
        with patch("src.infra.sandbox.session_manager.Daytona") as mock_daytona:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Sandbox not found")
            mock_daytona.return_value = mock_client

            manager = SessionSandboxManager()
            state = await manager._get_sandbox_state("sandbox_123")

            assert state == "destroyed"

    @pytest.mark.asyncio
    async def test_stop_sandbox_success(self):
        """测试停止沙箱 - 成功"""
        with (
            patch("src.infra.sandbox.session_manager.Daytona") as mock_daytona,
            patch.object(
                SessionSandboxManager, "_update_session_metadata", new_callable=AsyncMock
            ) as mock_update,
        ):
            mock_client = MagicMock()
            mock_sandbox = MagicMock()
            mock_client.get.return_value = mock_sandbox
            mock_daytona.return_value = mock_client

            manager = SessionSandboxManager()
            manager._cache["test_session"] = ("sandbox_123", MagicMock())

            result = await manager.stop("test_session")

            assert result is True
            mock_sandbox.stop.assert_called_once_with(timeout=30)
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_sandbox_no_cache(self):
        """测试停止沙箱 - 无缓存"""
        with patch("src.infra.sandbox.session_manager.SessionManager") as mock_session_manager:
            mock_session = MagicMock()
            mock_session.metadata = None
            mock_session_manager.return_value.get_session = AsyncMock(return_value=mock_session)

            manager = SessionSandboxManager()
            result = await manager.stop("test_session")

            assert result is False
