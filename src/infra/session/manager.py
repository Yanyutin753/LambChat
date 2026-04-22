"""
会话管理器
"""

from typing import List, Optional

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.s3 import get_storage_service
from src.infra.upload.file_record import FileRecordStorage
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate

logger = get_logger(__name__)


class SessionManager:
    """
    会话管理器

    提供会话的 CRUD 功能。
    """

    def __init__(self):
        self.storage = SessionStorage()
        self._trace_storage = None
        self._file_record_storage = FileRecordStorage()

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

    async def get_sessions(self, session_ids: list[str]) -> dict[str, Session]:
        """批量获取会话，返回 {session_id: Session} 映射"""
        return await self.storage.get_by_session_ids(session_ids)

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

    async def _collect_user_attachment_keys(self, session_id: str) -> list[str]:
        """Collect unique attachment keys from persisted user messages in a session."""
        events = await self.trace_storage.get_session_events(session_id)
        keys: set[str] = set()
        for event in events:
            if event.get("event_type") != "user:message":
                continue
            data = event.get("data", {})
            for attachment in data.get("attachments") or []:
                key = str(attachment.get("key", "")).strip()
                if key:
                    keys.add(key)
        return sorted(keys)

    async def _cleanup_unreferenced_files(self, keys: list[str]) -> int:
        """Delete backing files and records for keys whose references reached zero."""
        if not keys:
            return 0

        storage = get_storage_service()
        deleted = 0
        for key in keys:
            record = await self._file_record_storage.find_by_key(key)
            if record is None or record.get("reference_count", 0) > 0:
                continue

            await storage.delete_file(key)
            await self._file_record_storage.delete_by_key(key)
            deleted += 1

        return deleted

    async def clear_session_messages(self, session_id: str) -> int:
        """Release attachment references and remove all traces for a session."""
        attachment_keys = await self._collect_user_attachment_keys(session_id)
        await self._file_record_storage.release_references(attachment_keys)
        await self._cleanup_unreferenced_files(attachment_keys)
        await self.trace_storage.delete_session_traces(session_id)
        return len(attachment_keys)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（同时删除关联的 traces）"""
        await self.clear_session_messages(session_id)
        # Clean up revealed file index
        try:
            from src.infra.revealed_file.storage import get_revealed_file_storage

            revealed_storage = get_revealed_file_storage()
            deleted = await revealed_storage.delete_by_session(session_id)
            if deleted:
                logger.info(f"Deleted {deleted} revealed file records for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup revealed files for session {session_id}: {e}")
        # 再删除 session
        return await self.storage.delete(session_id)

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[Session], int]:
        """列出会话，返回 (sessions, total_count)"""
        return await self.storage.list_sessions(user_id, skip, limit, is_active, project_id, search)

    async def increment_unread_count(self, session_id: str) -> bool:
        """递增会话未读计数"""
        return await self.storage.increment_unread_count(session_id)

    async def mark_read(self, session_id: str) -> bool:
        """将会话标记为已读"""
        return await self.storage.mark_read(session_id)

    async def deactivate_session(self, session_id: str) -> Optional[Session]:
        """停用会话"""
        return await self.storage.update(
            session_id,
            SessionUpdate(metadata={"is_active": False}),
        )
