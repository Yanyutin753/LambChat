"""
OpenViking 客户端管理

单例管理 AsyncHTTPClient 生命周期，在 FastAPI app startup/shutdown 中注册。
封装常用 API，提供类型安全的调用接口。

支持多租户：每个用户使用自己的 API key 访问自己的数据。
"""

import logging
from typing import Any, Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# Root client（用于管理操作）
_root_client: Optional[Any] = None

# 用户客户端缓存（user_id -> client）
_user_clients: dict[str, Any] = {}

# 用户 API key 缓存（user_id -> api_key）
_user_api_keys: dict[str, str] = {}


class OpenVikingClient:
    """OpenViking 客户端封装，提供类型安全的 API。"""

    def __init__(self, inner_client: Any):
        self._client = inner_client

    def __getattr__(self, name: str) -> Any:
        """将未定义的方法代理到底层 client。"""
        return getattr(self._client, name)

    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        target_uri: Optional[str] = None,
        limit: int = 10,
    ) -> Any:
        """
        智能检索：带意图分析 + session context。

        Args:
            query: 搜索查询
            session_id: OpenViking session ID（用于上下文感知）
            target_uri: 搜索范围限制
            limit: 返回结果数量

        Returns:
            FindResult 对象，包含 memories, resources, skills
        """
        kwargs: dict = {"query": query, "limit": limit}
        if session_id:
            kwargs["session_id"] = session_id
        if target_uri:
            kwargs["target_uri"] = target_uri

        return await self._client.search(**kwargs)

    async def find(
        self,
        query: str,
        target_uri: Optional[str] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> Any:
        """
        简单检索：无 session context。

        Args:
            query: 搜索查询
            target_uri: 搜索范围限制
            limit: 返回结果数量
            score_threshold: 相关度阈值（0-1），过滤低于此分数的结果

        Returns:
            FindResult 对象
        """
        kwargs: dict = {"query": query, "limit": limit}
        if target_uri:
            kwargs["target_uri"] = target_uri
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold

        return await self._client.find(**kwargs)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        parts: Optional[list] = None,
    ) -> None:
        """添加消息到 session。"""
        await self._client.add_message(session_id, role, content=content, parts=parts)

    async def create_session(self) -> dict:
        """创建新 session。"""
        return await self._client.create_session()

    async def commit_session(self, session_id: str) -> dict:
        """提交 session，触发记忆提取。"""
        return await self._client.commit_session(session_id)

    async def close(self) -> None:
        """关闭客户端连接。"""
        await self._client.close()

    # ==================== File System API ====================

    async def ls(
        self,
        uri: str,
        simple: bool = False,
        recursive: bool = False,
        **kwargs,
    ) -> list:
        """
        列出目录内容。

        Args:
            uri: Viking URI
            simple: 返回简化的路径列表
            recursive: 递归列出子目录
            **kwargs: 其他参数 (output, abs_limit, show_all_hidden, node_limit)

        Returns:
            目录项列表
        """
        return await self._client.ls(uri, simple=simple, recursive=recursive, **kwargs)

    async def read(self, uri: str, offset: int = 0, limit: int = -1) -> str:
        """
        读取资源内容。

        Args:
            uri: Viking URI
            offset: 起始偏移量
            limit: 读取行数（-1 表示全部）

        Returns:
            资源内容
        """
        return await self._client.read(uri, offset=offset, limit=limit)

    async def rm(self, uri: str, recursive: bool = False) -> None:
        """
        删除资源。

        Args:
            uri: Viking URI
            recursive: 递归删除目录
        """
        await self._client.rm(uri, recursive=recursive)

    async def stat(self, uri: str) -> dict:
        """
        获取资源状态。

        Args:
            uri: Viking URI

        Returns:
            资源状态信息
        """
        return await self._client.stat(uri)

    async def glob(self, pattern: str, uri: str = "viking://") -> dict:
        """
        模式匹配搜索。

        Args:
            pattern: glob 模式
            uri: 搜索起始 URI

        Returns:
            匹配结果
        """
        return await self._client.glob(pattern, uri=uri)

    async def mkdir(self, uri: str) -> None:
        """
        创建目录。

        Args:
            uri: Viking URI
        """
        await self._client.mkdir(uri)

    async def mv(self, from_uri: str, to_uri: str) -> None:
        """
        移动资源。

        Args:
            from_uri: 源 URI
            to_uri: 目标 URI
        """
        await self._client.mv(from_uri, to_uri)

    async def tree(self, uri: str, **kwargs) -> dict:
        """
        获取目录树结构。

        Args:
            uri: Viking URI
            **kwargs: 其他参数 (output, abs_limit, show_all_hidden, node_limit)

        Returns:
            目录树结构
        """
        return await self._client.tree(uri, **kwargs)

    async def abstract(self, uri: str) -> str:
        """
        获取资源的 L0 摘要。

        Args:
            uri: Viking URI

        Returns:
            L0 摘要内容
        """
        return await self._client.abstract(uri)

    async def overview(self, uri: str) -> str:
        """
        获取资源的 L1 概览。

        Args:
            uri: Viking URI

        Returns:
            L1 概览内容
        """
        return await self._client.overview(uri)

    async def add_resource(
        self,
        path: str,
        to: Optional[str] = None,
        parent: Optional[str] = None,
        reason: str = "",
        instruction: str = "",
        wait: bool = False,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> dict:
        """
        添加资源到 OpenViking。

        Args:
            path: 本地文件路径或 URL
            to: 目标 URI（必须不存在）
            parent: 父目录 URI（必须存在）
            reason: 添加原因
            instruction: 处理指令
            wait: 是否等待处理完成
            timeout: 等待超时时间

        Returns:
            添加结果
        """
        return await self._client.add_resource(
            path=path,
            to=to,
            parent=parent,
            reason=reason,
            instruction=instruction,
            wait=wait,
            timeout=timeout,
            **kwargs,
        )

    async def wait_processed(self, timeout: Optional[float] = None) -> dict:
        """
        等待所有处理任务完成。

        Args:
            timeout: 超时时间

        Returns:
            处理状态
        """
        return await self._client.wait_processed(timeout=timeout)

    # ==================== Admin API (多租户) ====================

    async def admin_create_account(self, account_id: str, admin_user_id: str) -> dict:
        """
        创建新账户及其管理员用户。

        Args:
            account_id: 账户 ID
            admin_user_id: 管理员用户 ID

        Returns:
            创建结果，包含 api_key
        """
        return await self._client.admin_create_account(account_id, admin_user_id)

    async def admin_register_user(self, account_id: str, user_id: str, role: str = "user") -> dict:
        """
        在账户中注册新用户。

        Args:
            account_id: 账户 ID
            user_id: 用户 ID
            role: 角色 (admin/user)

        Returns:
            注册结果
        """
        return await self._client.admin_register_user(account_id, user_id, role)

    async def admin_list_accounts(self) -> list:
        """列出所有账户。"""
        return await self._client.admin_list_accounts()

    async def admin_list_users(self, account_id: str) -> list:
        """列出账户中的所有用户。"""
        return await self._client.admin_list_users(account_id)

    async def admin_regenerate_key(self, account_id: str, user_id: str) -> dict:
        """
        重新生成用户的 API Key。

        Args:
            account_id: 账户 ID
            user_id: 用户 ID

        Returns:
            包含新 api_key 的结果
        """
        return await self._client.admin_regenerate_key(account_id, user_id)


async def get_openviking_client() -> Optional[OpenVikingClient]:
    """
    获取 OpenViking Root 客户端单例。

    用于管理操作（创建账户等）。普通数据访问应使用 get_user_client()。
    """
    global _root_client

    if _root_client is not None:
        return _root_client

    if not settings.ENABLE_OPENVIKING:
        return None

    try:
        from openviking import AsyncHTTPClient

        inner_client = AsyncHTTPClient(
            url=settings.OPENVIKING_URL,
            api_key=settings.OPENVIKING_API_KEY or None,
            agent_id=settings.OPENVIKING_AGENT_ID or None,
        )
        await inner_client.initialize()
        _root_client = OpenVikingClient(inner_client)
        logger.info("[OpenViking] Root client initialized, url=%s", settings.OPENVIKING_URL)
        return _root_client
    except ImportError:
        logger.error("[OpenViking] openviking package not installed. Run: pip install openviking")
        return None
    except Exception as e:
        logger.error("[OpenViking] Failed to initialize root client: %s", e)
        _root_client = None
        return None


async def get_user_client(user_id: str, api_key: str) -> Optional[OpenVikingClient]:
    """
    获取用户的 OpenViking 客户端。

    每个用户使用自己的 API key，只能访问自己的数据。

    Args:
        user_id: 用户 ID（用于缓存）
        api_key: 用户的 OpenViking API key

    Returns:
        OpenVikingClient 实例
    """
    if not settings.ENABLE_OPENVIKING:
        return None

    # 检查缓存
    if user_id in _user_clients:
        return _user_clients[user_id]

    try:
        from openviking import AsyncHTTPClient

        inner_client = AsyncHTTPClient(
            url=settings.OPENVIKING_URL,
            api_key=api_key,
            agent_id=settings.OPENVIKING_AGENT_ID or None,
        )
        await inner_client.initialize()
        client = OpenVikingClient(inner_client)
        _user_clients[user_id] = client
        logger.debug("[OpenViking] User client initialized for: %s", user_id)
        return client
    except Exception as e:
        logger.error("[OpenViking] Failed to initialize user client for %s: %s", user_id, e)
        return None


async def close_openviking_client() -> None:
    """关闭所有 OpenViking 客户端连接。"""
    global _root_client, _user_clients

    def _is_expected_shutdown_error(e: Exception) -> bool:
        """检查是否为预期的关闭时错误（可安全忽略）。"""
        msg = str(e).lower()
        return "event loop is closed" in msg or "event loop stopped" in msg

    # 关闭 root client
    if _root_client is not None:
        try:
            await _root_client.close()
            logger.info("[OpenViking] Root client closed")
        except Exception as e:
            if _is_expected_shutdown_error(e):
                logger.debug("[OpenViking] Root client cleanup skipped (event loop closed)")
            else:
                logger.warning("[OpenViking] Error closing root client: %s", e)
        finally:
            _root_client = None

    # 关闭所有 user clients
    for user_id, client in list(_user_clients.items()):
        try:
            await client.close()
        except Exception as e:
            if _is_expected_shutdown_error(e):
                pass  # 预期的关闭时错误，静默忽略
            else:
                logger.debug("[OpenViking] Error closing user client %s: %s", user_id, e)
    _user_clients.clear()


async def _invalidate_user_client(user_id: str) -> None:
    """
    清除用户的客户端缓存。

    当用户 API key 失效时调用。

    Args:
        user_id: 用户 ID
    """
    global _user_clients

    if user_id in _user_clients:
        try:
            await _user_clients[user_id].close()
        except Exception as e:
            logger.debug("[OpenViking] Error closing user client %s: %s", user_id, e)
        finally:
            del _user_clients[user_id]
            logger.debug("[OpenViking] User client invalidated: %s", user_id)
