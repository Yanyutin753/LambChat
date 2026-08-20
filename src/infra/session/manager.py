"""
会话管理器
"""

import uuid
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, List, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import (
    ATTACHMENT_CLEAR_TERMINAL_STATUSES,
    get_trace_storage,
)
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
    ) -> tuple[Counter[str], list[str], list, list]:
        (
            counts,
            trace_ids,
            parent_ids,
            chunk_ids,
            _groups,
        ) = await self._collect_attachment_clear_groups(session_id, cutoff)
        return counts, trace_ids, parent_ids, chunk_ids

    @staticmethod
    def _count_attachment_events(events: list[dict]) -> Counter[str]:
        counts: Counter[str] = Counter()
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("event_type") != "user:message":
                continue
            data = event.get("data") or {}
            if not isinstance(data, dict):
                continue
            keys = {
                str(item.get("key")).strip()
                for item in data.get("attachments") or []
                if isinstance(item, dict) and item.get("key")
            }
            counts.update(key for key in keys if key)
        return counts

    async def _collect_attachment_clear_groups(
        self, session_id: str, cutoff: object
    ) -> tuple[Counter[str], list[str], list, list, dict[str, dict[str, Any]]]:
        snapshot = await self.trace_storage.snapshot_session_traces_for_cleanup(session_id, cutoff)
        raw_groups = snapshot.get("groups")
        if not isinstance(raw_groups, list):
            raise SessionError("attachment_clear_snapshot_invalid")
        counts: Counter[str] = Counter()
        groups: dict[str, dict[str, Any]] = {}
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                raise SessionError("attachment_clear_snapshot_invalid")
            group_id = raw_group.get("id")
            events = raw_group.get("events")
            if not isinstance(group_id, str) or not group_id or not isinstance(events, list):
                raise SessionError("attachment_clear_snapshot_invalid")
            if group_id in groups:
                raise SessionError("attachment_clear_snapshot_invalid")
            group_counts = self._count_attachment_events(events)
            counts.update(group_counts)
            groups[group_id] = {key: value for key, value in raw_group.items() if key != "events"}
            groups[group_id]["counts"] = dict(group_counts)
            groups[group_id]["status"] = "pending"
        return (
            counts,
            snapshot["trace_ids"],
            snapshot["parent_ids"],
            snapshot["chunk_ids"],
            groups,
        )

    @staticmethod
    def _parse_attachment_clear_operation(
        operation: object,
    ) -> tuple[str, str, dict[str, dict[str, Any]]]:
        if not isinstance(operation, dict):
            raise SessionError("attachment_clear_operation_invalid")
        operation_id = operation.get("id")
        raw_counts = operation.get("counts")
        raw_trace_ids = operation.get("trace_ids")
        raw_parent_ids = operation.get("parent_ids")
        raw_chunk_ids = operation.get("chunk_ids")
        raw_groups = operation.get("groups")
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
            or not isinstance(raw_parent_ids, list)
            or not isinstance(raw_chunk_ids, list)
            or not isinstance(raw_groups, dict)
        ):
            raise SessionError("attachment_clear_operation_invalid")
        counts: Counter[str] = Counter()
        for key, count in raw_counts.items():
            clean_key = str(key).strip() if key else ""
            if not clean_key or not isinstance(count, int) or count <= 0:
                raise SessionError("attachment_clear_operation_invalid")
            counts[clean_key] += count
        groups: dict[str, dict[str, Any]] = {}
        for group_id, raw_group in raw_groups.items():
            if (
                not isinstance(group_id, str)
                or not group_id
                or not isinstance(raw_group, dict)
                or raw_group.get("id") != group_id
                or raw_group.get("kind") not in {"parent", "chunk"}
                or raw_group.get("document_id") is None
                or raw_group.get("updated_at") is None
                or raw_group.get("status") not in {"pending", "deleted", "released", "survivor"}
                or not isinstance(raw_group.get("counts"), dict)
                or raw_group.get("release_operation_id") != f"{operation_id}:{group_id}"
            ):
                raise SessionError("attachment_clear_operation_invalid")
            if (
                raw_group["kind"] == "parent"
                and raw_group.get("terminal_status") not in ATTACHMENT_CLEAR_TERMINAL_STATUSES
            ):
                raise SessionError("attachment_clear_operation_invalid")
            parent_group_id = raw_group.get("parent_group_id")
            if parent_group_id is not None and not isinstance(parent_group_id, str):
                raise SessionError("attachment_clear_operation_invalid")
            group_counts: Counter[str] = Counter()
            for key, count in raw_group["counts"].items():
                clean_key = str(key).strip() if key else ""
                if not clean_key or not isinstance(count, int) or count <= 0:
                    raise SessionError("attachment_clear_operation_invalid")
                group_counts[clean_key] += count
            groups[group_id] = {**raw_group, "counts": group_counts}
        for group in groups.values():
            parent_group_id = group.get("parent_group_id")
            if parent_group_id is not None and parent_group_id not in groups:
                raise SessionError("attachment_clear_operation_invalid")
        grouped_counts: Counter[str] = Counter()
        for group in groups.values():
            grouped_counts.update(group["counts"])
        if grouped_counts != counts:
            raise SessionError("attachment_clear_operation_invalid")
        return operation_id, uploaded_by, groups

    async def _get_or_begin_attachment_clear_operation(
        self,
        session_id: str,
    ) -> tuple[str, str, dict[str, dict[str, Any]]]:
        operation = await self.storage.claim_attachment_clear_operation(session_id)
        if operation is None:
            raise SessionError("attachment_clear_operation_persist_failed")
        if "counts" not in operation:
            (
                counts,
                trace_ids,
                parent_ids,
                chunk_ids,
                groups,
            ) = await self._collect_attachment_clear_groups(session_id, operation["cutoff"])
            for group_id, group in groups.items():
                group["release_operation_id"] = f"{operation['id']}:{group_id}"
            operation = await self.storage.persist_attachment_clear_snapshot(
                session_id,
                operation["id"],
                dict(counts),
                trace_ids,
                parent_ids=parent_ids,
                chunk_ids=chunk_ids,
                groups=groups,
            )
            if operation is None:
                raise SessionError("attachment_clear_operation_persist_failed")
        return self._parse_attachment_clear_operation(operation)

    async def clear_session_messages(self, session_id: str) -> int:
        """Release attachment references and remove all traces for a session."""
        operation = await self._get_or_begin_attachment_clear_operation(session_id)
        operation_id, uploaded_by, groups = operation
        for group_id, group in groups.items():
            parent_group_id = group.get("parent_group_id")
            if parent_group_id and groups[parent_group_id]["status"] == "survivor":
                if not await self.storage.set_attachment_clear_group_status(
                    session_id,
                    operation_id,
                    group_id,
                    expected_status=group["status"],
                    status="survivor",
                ):
                    raise SessionError("attachment_clear_group_persist_failed")
                group["status"] = "survivor"
                continue
            if group["status"] == "pending":
                delete_status = await self.trace_storage.delete_attachment_clear_group(
                    session_id, group
                )
                if delete_status not in {"deleted", "survivor"}:
                    raise SessionError("attachment_clear_group_delete_invalid")
                if not await self.storage.set_attachment_clear_group_status(
                    session_id,
                    operation_id,
                    group_id,
                    expected_status="pending",
                    status=delete_status,
                ):
                    raise SessionError("attachment_clear_group_persist_failed")
                group["status"] = delete_status
            if group["status"] == "deleted":
                if group["counts"]:
                    await self._file_record_storage.release_reference_counts(
                        group["counts"],
                        operation_id=group["release_operation_id"],
                        uploaded_by=uploaded_by,
                    )
                if not await self.storage.set_attachment_clear_group_status(
                    session_id,
                    operation_id,
                    group_id,
                    expected_status="deleted",
                    status="released",
                ):
                    raise SessionError("attachment_clear_group_persist_failed")
                group["status"] = "released"
        if not await self.storage.complete_attachment_clear_operation(session_id, operation_id):
            raise SessionError("attachment_clear_operation_complete_failed")
        released_keys = {
            key
            for group in groups.values()
            if group["status"] == "released"
            for key in group["counts"]
        }
        return len(released_keys)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（同时删除关联的 traces）"""
        delete_operation = await self.storage.claim_attachment_delete_operation(session_id)
        if not isinstance(delete_operation, dict) or not isinstance(
            delete_operation.get("id"), str
        ):
            raise SessionError("session_delete_fence_unavailable")
        if delete_operation.get("acquired") is False:
            raise SessionError("session_delete_in_progress")
        delete_operation_id = delete_operation["id"]
        try:
            await self.trace_storage.expire_stale_running_traces(session_id)
            await self.clear_session_messages(session_id)
            if await self.trace_storage.has_session_trace_documents(session_id):
                raise SessionError("session_delete_has_trace_survivors")
        except BaseException:
            await self.storage.cancel_attachment_delete_operation(session_id, delete_operation_id)
            raise
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
        try:
            deleted = await self.storage.delete_claimed_session(
                session_id,
                delete_operation_id,
            )
        except BaseException:
            await self.storage.cancel_attachment_delete_operation(session_id, delete_operation_id)
            raise
        if not deleted:
            await self.storage.cancel_attachment_delete_operation(session_id, delete_operation_id)
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

    async def mark_read_for_user(self, session_id: str, user_id: str) -> bool:
        """仅在会话属于指定用户时标记已读。"""
        return await self.storage.mark_read_for_user(session_id, user_id)

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
        if not await self.storage.acquire_trace_write(target_session.id):
            raise SessionError("session_trace_write_fenced")
        try:
            return await self._clone_history_to_session_unfenced(
                source_session=source_session,
                target_session=target_session,
                target=target,
                user_id=user_id,
                collect_checkpoint_messages=collect_checkpoint_messages,
            )
        finally:
            await self.storage.release_trace_write(target_session.id)

    async def _clone_history_to_session_unfenced(
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
            clone_chunks = False
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
                    clone_chunks = True
            elif target.get("completed_run_ids") is not None:
                if run_id in target["completed_run_ids"]:
                    cloned_doc = await run_blocking_io(
                        self._build_cloned_trace_doc,
                        trace,
                        target_session.id,
                        user_id,
                    )
                    clone_chunks = True
            else:
                cloned_doc = await run_blocking_io(
                    self._build_cloned_trace_doc,
                    trace,
                    target_session.id,
                    user_id,
                )
                clone_chunks = True

            if cloned_doc is not None:
                result.copied_trace_count += 1
                # Chunked event storage: full clones keep the source's
                # event_count/chunk_count, so the chunk documents must be
                # copied under the cloned trace_id as well, otherwise the
                # clone has zero readable events.
                if clone_chunks:
                    await self._clone_trace_chunk_docs(trace, cloned_doc)
                if collect_checkpoint_messages:
                    docs_for_messages = [cloned_doc]
                    if clone_chunks and not cloned_doc.get("events"):
                        # Chunked storage: rebuild the in-memory legacy view
                        # from the source trace so message extraction works.
                        try:
                            source_events = await self.trace_storage.read_trace_events_compat(
                                str(trace.get("trace_id"))
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to read source events for checkpoint clone: %s", e
                            )
                            source_events = []
                        if source_events:
                            docs_for_messages = [{**cloned_doc, "events": source_events}]
                    checkpoint_messages = await run_blocking_io(
                        build_messages_from_trace_events,
                        docs_for_messages,
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
            },
        ).sort("started_at", 1)
        completed_run_count = 0

        async for trace in cursor:
            run_id = trace.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                continue
            turn_index = completed_run_count + 1

            # Chunked event storage keeps events out of the trace document;
            # use the compat reader so both storage modes are covered.
            trace_id = trace.get("trace_id")
            compat_reader = getattr(self.trace_storage, "read_trace_events_compat", None)
            # Chunked event storage keeps events out of the trace document;
            # the compat reader covers both storage modes, with the in-document
            # events as the legacy fallback.
            events: list[dict] = list(trace.get("events") or [])
            if callable(compat_reader) and trace_id:
                try:
                    events = await compat_reader(str(trace_id), event_types=["user:message"])
                except Exception as e:
                    logger.warning("Failed to read events for fork target %s: %s", trace_id, e)
                    events = []
            for event in events:
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
        # Never inherit an in-flight chunk write marker: it would fence every
        # later writer on the cloned trace with no owner to release it.
        cloned.pop("attachment_chunk_write_operation", None)
        return cloned

    async def _clone_trace_chunk_docs(self, source_trace: dict, cloned_trace: dict) -> None:
        """Copy chunked event documents of a trace to its cloned trace_id."""
        source_trace_id = source_trace.get("trace_id")
        cloned_trace_id = cloned_trace.get("trace_id")
        if not source_trace_id or not cloned_trace_id or source_trace_id == cloned_trace_id:
            return
        try:
            cursor = self.trace_storage.chunks_collection.find({"trace_id": source_trace_id})
            docs: list[dict] = []
            async for chunk_doc in cursor:
                cloned_chunk = deepcopy(chunk_doc)
                cloned_chunk.pop("_id", None)
                cloned_chunk["trace_id"] = cloned_trace_id
                cloned_chunk["session_id"] = cloned_trace.get("session_id", "")
                cloned_chunk.pop("attachment_chunk_staging", None)
                cloned_chunk.pop("replacement_target_trace_id", None)
                cloned_chunk.pop("replacement_operation_id", None)
                docs.append(cloned_chunk)
            if docs:
                await self.trace_storage.chunks_collection.insert_many(docs, ordered=False)
        except Exception as e:
            logger.error(
                "Failed to clone chunk docs from trace %s to %s: %s",
                source_trace_id,
                cloned_trace_id,
                e,
            )
            # A chunked clone advertising event_count > 0 with no chunk docs
            # has zero readable events — the exact symptom this clone path
            # exists to avoid — so reset the counters to keep it consistent.
            # Legacy docs keep their inline events and stay untouched.
            if not cloned_trace.get("events"):
                cloned_trace["event_count"] = 0
                cloned_trace.pop("chunk_count", None)

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
