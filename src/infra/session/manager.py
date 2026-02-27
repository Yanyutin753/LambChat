"""
会话管理器
"""

from typing import List, Optional

from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate


class SessionManager:
    """
    会话管理器

    提供会话的 CRUD 功能。
    """

    def __init__(self):
        self.storage = SessionStorage()
        self._trace_storage = None

    @property
    def trace_storage(self):
        """延迟加载 trace 存储"""
        if self._trace_storage is None:
            self._trace_storage = get_trace_storage()
        return self._trace_storage

    async def create_session(
        self,
        session_data: SessionCreate,
        user_id: Optional[str] = None,
    ) -> Session:
        """创建会话"""
        return await self.storage.create(session_data, user_id)

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话（优先使用自定义 session_id）"""
        # 优先使用自定义 session_id 查询
        session = await self.storage.get_by_session_id(session_id)
        if session:
            return session
        # 兼容旧的 ObjectId 查询
        return await self.storage.get_by_id(session_id)

    async def get_session_events(
        self,
        session_id: str,
        since_seq: Optional[int] = None,
        limit: int = 100,
    ) -> List[dict]:
        """获取会话事件（从 traces 聚合）"""
        return await self.trace_storage.get_session_events(session_id, since_seq, limit)

    async def get_session_traces(
        self,
        session_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> List[dict]:
        """获取会话的所有 traces"""
        return await self.trace_storage.list_traces(
            session_id=session_id,
            limit=limit,
            skip=skip,
        )

    async def update_session(
        self,
        session_id: str,
        session_data: SessionUpdate,
    ) -> Optional[Session]:
        """更新会话"""
        return await self.storage.update(session_id, session_data)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（同时删除关联的 traces）"""
        # 先删除关联的 traces
        await self.trace_storage.delete_session_traces(session_id)
        # 再删除 session
        return await self.storage.delete(session_id)

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[list[Session], int]:
        """列出会话，返回 (sessions, total_count)"""
        return await self.storage.list_sessions(user_id, skip, limit, is_active)

    async def deactivate_session(self, session_id: str) -> Optional[Session]:
        """停用会话"""
        return await self.storage.update(
            session_id,
            SessionUpdate(metadata={"is_active": False}),
        )
