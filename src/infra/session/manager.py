"""
会话管理器
"""

import uuid
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import List, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.checkpoint import (
    build_messages_from_trace_events,
    clone_checkpoints_for_fork,
    delete_checkpoints_for_thread,
    seed_checkpoint_from_messages,
)
from src.infra.upload.file_record import FileRecordStorage
from src.infra.utils.datetime import utc_now, utc_now_iso
from src.kernel.exceptions import NotFoundError, SessionError
from src.kernel.schemas.session import (
    Session,
    SessionCheckpoint,
    SessionCreate,
    SessionUpdate,
    clone_session_metadata,
)

logger = get_logger(__name__)

SESSION_FORK_TRACE_INSERT_BATCH_SIZE = 25


@dataclass
class SessionForkCloneResult:
    copied_trace_count: int = 0
    checkpoint_messages: list[object] = field(default_factory=list)
    _compat_docs: list[dict] = field(default_factory=list, repr=False)

    def __len__(self) -> int:
        return self.copied_trace_count

    def __iter__(self):
        return iter(self._compat_docs)


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
        del since_seq
        return await self.trace_storage.get_session_events(session_id, max_events=limit)

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

    async def update_session_metadata(self, session_id: str, metadata: dict) -> bool:
        """Update metadata fields without materializing the full session."""
        return await self.storage.update_metadata_only(session_id, metadata)

    async def _collect_user_attachment_reference_counts(self, session_id: str) -> Counter[str]:
        """Count attachment keys once per persisted user message in a session."""
        counts: Counter[str] = Counter()
        async for event in self.trace_storage.iter_session_events_for_cleanup(
            session_id,
            event_types=["user:message"],
        ):
            if event.get("event_type") != "user:message":
                continue
            data = event.get("data") or {}
            if not isinstance(data, dict):
                continue
            message_keys: set[str] = set()
            for attachment in data.get("attachments") or []:
                if not isinstance(attachment, dict):
                    continue
                raw_key = attachment.get("key")
                key = str(raw_key).strip() if raw_key else ""
                if key:
                    message_keys.add(key)
            counts.update(message_keys)
        return counts

    async def _collect_attachment_clear_snapshot(
        self, session_id: str, cutoff: object
    ) -> tuple[Counter[str], list[str]]:
        counts: Counter[str] = Counter()
        trace_ids: set[str] = set()
        async for event in self.trace_storage.iter_session_events_for_cleanup(
            session_id, event_types=["user:message"], cutoff=cutoff
        ):
            trace_id = event.get("trace_id")
            if trace_id:
                trace_ids.add(str(trace_id))
            if event.get("event_type") != "user:message":
                continue
            data = event.get("data") or {}
            if not isinstance(data, dict):
                continue
            message_keys = {
                str(attachment.get("key")).strip()
                for attachment in data.get("attachments") or []
                if isinstance(attachment, dict) and attachment.get("key")
            }
            counts.update(key for key in message_keys if key)
        return counts, sorted(trace_ids)

    @staticmethod
    def _parse_attachment_clear_operation(
        operation: object,
    ) -> tuple[str, Counter[str], list[str], object, str]:
        if not isinstance(operation, dict):
            raise SessionError("attachment_clear_operation_invalid")
        operation_id = operation.get("id")
        raw_counts = operation.get("counts")
        raw_trace_ids = operation.get("trace_ids")
        cutoff = operation.get("cutoff")
        uploaded_by = operation.get("uploaded_by")
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(raw_counts, dict)
            or not isinstance(raw_trace_ids, list)
            or cutoff is None
            or not isinstance(uploaded_by, str)
            or not uploaded_by
        ):
            raise SessionError("attachment_clear_operation_invalid")
        counts: Counter[str] = Counter()
        for key, count in raw_counts.items():
            clean_key = str(key).strip() if key else ""
            if not clean_key or not isinstance(count, int) or count <= 0:
                raise SessionError("attachment_clear_operation_invalid")
            counts[clean_key] += count
        return (
            operation_id,
            counts,
            [str(item) for item in raw_trace_ids if item],
            cutoff,
            uploaded_by,
        )

    async def _get_or_begin_attachment_clear_operation(
        self,
        session_id: str,
    ) -> tuple[str, Counter[str]] | None:
        operation = await self.storage.claim_attachment_clear_operation(session_id)
        if operation is None:
            raise SessionError("attachment_clear_operation_persist_failed")
        if "counts" not in operation:
            counts, trace_ids = await self._collect_attachment_clear_snapshot(
                session_id, operation["cutoff"]
            )
            operation = await self.storage.persist_attachment_clear_snapshot(
                session_id,
                operation["id"],
                dict(counts),
                trace_ids,
            )
            if operation is None:
                raise SessionError("attachment_clear_operation_persist_failed")
        return self._parse_attachment_clear_operation(operation)

    async def clear_session_messages(self, session_id: str) -> int:
        """Release attachment references and remove all traces for a session."""
        operation = await self._get_or_begin_attachment_clear_operation(session_id)
        operation_id, attachment_counts, trace_ids, cutoff, uploaded_by = operation
        await self._file_record_storage.release_reference_counts(
            attachment_counts,
            operation_id=operation_id,
            uploaded_by=uploaded_by,
        )
        await self.trace_storage.delete_session_traces_strict(
            session_id, trace_ids=trace_ids, cutoff=cutoff
        )
        if not await self.storage.complete_attachment_clear_operation(session_id, operation_id):
            raise SessionError("attachment_clear_operation_complete_failed")
        return len(attachment_counts)

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
        deleted = await self.storage.delete(session_id)
        if deleted:
            try:
                await delete_checkpoints_for_thread(session_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup checkpoints for session {session_id}: {e}")
        return deleted

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
        favorites_project_id: str | None = None,
    ) -> tuple[list[Session], int]:
        """列出会话，返回 (sessions, total_count)"""
        return await self.storage.list_sessions(
            user_id,
            skip,
            limit,
            is_active,
            project_id,
            search,
            favorites_only,
            favorites_project_id,
        )

    async def increment_unread_count(self, session_id: str) -> bool:
        """递增会话未读计数"""
        return await self.storage.increment_unread_count(session_id)

    async def mark_read(self, session_id: str) -> bool:
        """将会话标记为已读"""
        return await self.storage.mark_read(session_id)

    async def mark_all_read(
        self,
        user_id: str,
        project_id: str | None = None,
        scheduled_task_id: str | None = None,
    ) -> int:
        """批量将会话标记为已读，支持按项目或定时任务过滤。"""
        return await self.storage.mark_all_read(user_id, project_id, scheduled_task_id)

    async def deactivate_session(self, session_id: str) -> Optional[Session]:
        """停用会话"""
        return await self.storage.update(
            session_id,
            SessionUpdate(metadata={"is_active": False}),
        )

    async def create_message_checkpoint(
        self,
        session_id: str,
        message_id: str,
        *,
        user_id: str,
        name: str | None = None,
    ) -> dict:
        """Create a named checkpoint for a message within a session."""
        session = await self.get_session(session_id)
        if not session or session.user_id != user_id:
            raise NotFoundError("session_not_found")

        target = await self._resolve_fork_target(session_id, message_id)
        checkpoint = SessionCheckpoint(
            id=f"checkpoint_{uuid.uuid4().hex}",
            message_id=message_id,
            name=(name or "Checkpoint").strip() or "Checkpoint",
            source_run_id=target["run_id"],
            source_trace_id=target.get("trace_id"),
        )
        checkpoints = self._load_session_checkpoints(session)
        checkpoints.append(checkpoint)

        updated_session = await self.update_session(
            session_id,
            SessionUpdate(
                metadata={"checkpoints": [item.model_dump(mode="json") for item in checkpoints]}
            ),
        )
        return {
            "checkpoint": checkpoint.model_dump(mode="json"),
            "session": updated_session,
        }

    async def fork_session_from_checkpoint(
        self,
        session_id: str,
        checkpoint_id: str,
        *,
        user_id: str,
    ) -> dict:
        """Fork a new session from a stored checkpoint."""
        session = await self.get_session(session_id)
        if not session or session.user_id != user_id:
            raise NotFoundError("session_not_found")

        checkpoints = self._load_session_checkpoints(session)
        checkpoint = next((item for item in checkpoints if item.id == checkpoint_id), None)
        if checkpoint is None:
            raise NotFoundError("checkpoint_not_found")

        result = await self.fork_session_from_message(
            session_id,
            checkpoint.message_id,
            user_id,
            fork_metadata={
                "fork_type": "checkpoint",
                "checkpoint_id": checkpoint.id,
                "checkpoint_name": checkpoint.name,
            },
        )
        result["checkpoint_id"] = checkpoint.id
        return result

    async def fork_session_from_message(
        self,
        session_id: str,
        message_id: str,
        user_id: str,
        fork_metadata: dict | None = None,
    ) -> dict:
        """Fork a new session from a specific message anchor."""
        source_session = await self.get_session(session_id)
        if not source_session or source_session.user_id != user_id:
            raise NotFoundError("session_not_found")

        target = await self._resolve_fork_target(session_id, message_id)
        new_metadata = clone_session_metadata(source_session.metadata)
        new_metadata.update(
            {
                "forked_from_session_id": session_id,
                "forked_from_message_id": message_id,
                "forked_at": utc_now_iso(),
                **(fork_metadata or {}),
            }
        )
        if target.get("run_id"):
            new_metadata["current_run_id"] = target["run_id"]

        new_session = await self.create_session(
            SessionCreate(
                name=self._build_fork_session_name(source_session.name),
                metadata=new_metadata,
            ),
            user_id=user_id,
        )

        copied_checkpoint_count = 0
        checkpoint_clone_error: Exception | None = None
        try:
            copied_checkpoint_count = await clone_checkpoints_for_fork(
                source_session.id,
                new_session.id,
                turn_index=target["turn_index"],
                target_type=target["target_type"],
            )
        except Exception as exc:
            checkpoint_clone_error = exc
            logger.warning(
                "Failed to clone fork checkpoints: source_session=%s target_session=%s message=%s error=%s",
                source_session.id,
                new_session.id,
                message_id,
                exc,
            )

        try:
            needs_checkpoint_seed = (
                copied_checkpoint_count == 0 and checkpoint_clone_error is not None
            )
            clone_result = await self._clone_history_to_session(
                source_session=source_session,
                target_session=new_session,
                target=target,
                user_id=user_id,
                collect_checkpoint_messages=needs_checkpoint_seed,
            )
            if needs_checkpoint_seed:
                copied_checkpoint_count = await seed_checkpoint_from_messages(
                    new_session.id,
                    clone_result.checkpoint_messages,
                )
            await self.storage.rebuild_search_index(new_session.id)
            return {
                "session": new_session,
                "source_session_id": source_session.id,
                "source_message_id": message_id,
                "copied_trace_count": clone_result.copied_trace_count,
                "copied_checkpoint_count": copied_checkpoint_count,
            }
        except Exception as exc:
            await self.delete_session(new_session.id)
            raise SessionError(f"fork_checkpoint_copy_failed: {exc}") from exc

    async def _clone_history_to_session(
        self,
        *,
        source_session: Session,
        target_session: Session,
        target: dict,
        user_id: str,
        collect_checkpoint_messages: bool = False,
    ) -> SessionForkCloneResult:
        async def _flush_batch() -> None:
            if batch:
                await self.trace_storage.collection.insert_many(list(batch))
                batch.clear()

        cursor = self.trace_storage.collection.find(
            {"session_id": source_session.id},
            {"_id": 0},
        ).sort("started_at", 1)
        result = SessionForkCloneResult()
        batch: list[dict] = []
        async for trace in cursor:
            run_id = trace.get("run_id")
            if not run_id:
                continue
            cloned_doc = None
            if run_id == target["run_id"]:
                if target["target_type"] == "user":
                    cloned_doc = await run_blocking_io(
                        self._build_partial_user_trace_doc,
                        trace,
                        target["user_event"],
                        target_session.id,
                        user_id,
                    )
                elif target["target_type"] == "assistant":
                    cloned_doc = await run_blocking_io(
                        self._build_cloned_trace_doc,
                        trace,
                        target_session.id,
                        user_id,
                    )
            elif target.get("completed_run_ids") is not None:
                if run_id in target["completed_run_ids"]:
                    cloned_doc = await run_blocking_io(
                        self._build_cloned_trace_doc,
                        trace,
                        target_session.id,
                        user_id,
                    )
            else:
                cloned_doc = await run_blocking_io(
                    self._build_cloned_trace_doc,
                    trace,
                    target_session.id,
                    user_id,
                )

            if cloned_doc is not None:
                result.copied_trace_count += 1
                if collect_checkpoint_messages:
                    checkpoint_messages = await run_blocking_io(
                        build_messages_from_trace_events,
                        [cloned_doc],
                    )
                    result.checkpoint_messages.extend(checkpoint_messages)
                batch.append(cloned_doc)
                if len(batch) >= SESSION_FORK_TRACE_INSERT_BATCH_SIZE:
                    await _flush_batch()

            if run_id == target["run_id"] and target["target_type"] in {"user", "assistant"}:
                break

        await _flush_batch()
        return result

    async def _resolve_fork_target(self, session_id: str, message_id: str) -> dict:
        cursor = self.trace_storage.collection.find(
            {"session_id": session_id},
            {
                "_id": 0,
                "trace_id": 1,
                "run_id": 1,
                "events.event_type": 1,
                "events.data": 1,
            },
        ).sort("started_at", 1)
        completed_run_count = 0

        async for trace in cursor:
            run_id = trace.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                continue
            turn_index = completed_run_count + 1

            for event in trace.get("events", []):
                if event.get("event_type") != "user:message":
                    continue
                data = event.get("data") or {}
                current_message_id = self._resolve_user_message_id(run_id, data)
                if current_message_id == message_id:
                    return {
                        "target_type": "user",
                        "run_id": run_id,
                        "trace_id": trace.get("trace_id"),
                        "user_event": event,
                        "completed_run_count": completed_run_count,
                        "turn_index": turn_index,
                    }

            if run_id == message_id:
                return {
                    "target_type": "assistant",
                    "run_id": run_id,
                    "trace_id": trace.get("trace_id"),
                    "completed_run_count": completed_run_count + 1,
                    "turn_index": turn_index,
                }

            completed_run_count += 1

        raise NotFoundError("message_not_found")

    @staticmethod
    def _resolve_user_message_id(run_id: str, data: dict) -> str:
        message_id = str(data.get("message_id") or "").strip()
        if message_id:
            return message_id
        return f"{run_id}:user"

    @staticmethod
    def _build_cloned_trace_doc(trace: dict, session_id: str, user_id: str) -> dict:
        cloned = deepcopy(trace)
        cloned.pop("_id", None)
        cloned["trace_id"] = f"trace_{uuid.uuid4().hex}"
        cloned["session_id"] = session_id
        cloned["user_id"] = user_id
        return cloned

    def _build_partial_user_trace_doc(
        self,
        trace: dict,
        user_event: dict,
        session_id: str,
        user_id: str,
    ) -> dict:
        timestamp = user_event.get("timestamp") or utc_now()
        return {
            "trace_id": f"trace_{uuid.uuid4().hex}",
            "session_id": session_id,
            "run_id": trace.get("run_id"),
            "agent_id": trace.get("agent_id"),
            "user_id": user_id,
            "events": [deepcopy(user_event)],
            "event_count": 1,
            "started_at": timestamp,
            "updated_at": timestamp,
            "completed_at": timestamp,
            "status": "completed",
            "metadata": deepcopy(trace.get("metadata") or {}),
        }

    @staticmethod
    def _build_fork_session_name(name: str | None) -> str:
        base = (name or "New Chat").strip() or "New Chat"
        if base.endswith(" (Fork)"):
            return base
        return f"{base} (Fork)"

    @staticmethod
    def _load_session_checkpoints(session: Session) -> list[SessionCheckpoint]:
        raw_items = session.metadata.get("checkpoints") if session.metadata else []
        if not isinstance(raw_items, list):
            return []
        checkpoints: list[SessionCheckpoint] = []
        for item in raw_items:
            if isinstance(item, dict):
                checkpoints.append(SessionCheckpoint(**item))
        return checkpoints
