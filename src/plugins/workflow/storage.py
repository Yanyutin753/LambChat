"""MongoDB storage for workflow definitions and versions."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from src.infra.async_utils import run_blocking_io
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.plugins.workflow.models import (
    WorkflowCredential,
    WorkflowDefinition,
    WorkflowListResult,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowVersion,
)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

WORKFLOW_LIST_LIMIT_MAX = 200
WORKFLOW_DEFINITION_STATUSES = {"draft", "published", "archived"}
WORKFLOW_RUN_FINISHABLE_STATUSES = ["queued", "running", "paused"]
WORKFLOW_RUN_TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"]
DEFAULT_MAX_EVENT_PAYLOAD_BYTES = 65536


def _bounded_limit(limit: int) -> int:
    return min(max(int(limit), 1), WORKFLOW_LIST_LIMIT_MAX)


def _workflow_list_query(
    *,
    owner_user_id: str,
    query: str | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    normalized_status = str(status_filter or "").strip().lower()
    mongo_query: dict[str, Any] = {"owner_user_id": owner_user_id}
    if normalized_status and normalized_status in WORKFLOW_DEFINITION_STATUSES:
        mongo_query["status"] = normalized_status
    else:
        mongo_query["status"] = {"$ne": "archived"}

    normalized_query = str(query or "").strip()
    if normalized_query:
        regex = {"$regex": re.escape(normalized_query), "$options": "i"}
        mongo_query["$or"] = [
            {"workflow_id": regex},
            {"name": regex},
            {"description": regex},
            {"latest_version_id": regex},
            {"published_version_id": regex},
        ]
    return mongo_query


def _bounded_event_payload_bytes(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_EVENT_PAYLOAD_BYTES
    return min(max(parsed, 1024), 1024 * 1024)


def _bounded_event_payload(payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8")
    if len(encoded) <= max_bytes:
        return payload
    return {
        "truncated": True,
        "reason": "workflow_event_payload_too_large",
        "original_bytes": len(encoded),
        "max_bytes": max_bytes,
        "keys": sorted(str(key) for key in payload.keys()),
    }


class WorkflowPluginStorage:
    """Storage adapter for workflow definitions and immutable versions."""

    def __init__(self, *, max_event_payload_bytes: int = DEFAULT_MAX_EVENT_PAYLOAD_BYTES) -> None:
        self._definitions: "AsyncIOMotorCollection[Any] | None" = None
        self._versions: "AsyncIOMotorCollection[Any] | None" = None
        self._runs: "AsyncIOMotorCollection[Any] | None" = None
        self._events: "AsyncIOMotorCollection[Any] | None" = None
        self._credentials: "AsyncIOMotorCollection[Any] | None" = None
        self.max_event_payload_bytes = _bounded_event_payload_bytes(max_event_payload_bytes)

    @property
    def definitions(self) -> "AsyncIOMotorCollection[Any]":
        if self._definitions is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._definitions = client[settings.MONGODB_DB]["workflow_definitions"]
        return self._definitions

    @property
    def versions(self) -> "AsyncIOMotorCollection[Any]":
        if self._versions is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._versions = client[settings.MONGODB_DB]["workflow_versions"]
        return self._versions

    @property
    def runs(self) -> "AsyncIOMotorCollection[Any]":
        if self._runs is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._runs = client[settings.MONGODB_DB]["workflow_runs"]
        return self._runs

    @property
    def events(self) -> "AsyncIOMotorCollection[Any]":
        if self._events is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._events = client[settings.MONGODB_DB]["workflow_run_events"]
        return self._events

    @property
    def credentials(self) -> "AsyncIOMotorCollection[Any]":
        if self._credentials is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._credentials = client[settings.MONGODB_DB]["workflow_credentials"]
        return self._credentials

    async def ensure_indexes(self) -> None:
        await self.definitions.create_index("workflow_id", unique=True)
        await self.definitions.create_index([("owner_user_id", 1), ("updated_at", -1)])
        await self.versions.create_index("version_id", unique=True)
        await self.versions.create_index([("workflow_id", 1), ("version_number", 1)])
        await self.runs.create_index("run_id", unique=True)
        await self.runs.create_index([("workflow_id", 1), ("started_at", -1)])
        await self.events.create_index([("run_id", 1), ("sequence", 1)])
        await self.credentials.create_index("credential_id", unique=True)
        await self.credentials.create_index(
            [("owner_user_id", 1), ("ref", 1)],
            unique=True,
        )
        await self.credentials.create_index([("owner_user_id", 1), ("updated_at", -1)])

    @staticmethod
    def _definition_from_doc(doc: dict[str, Any]) -> WorkflowDefinition:
        data = dict(doc)
        data.pop("_id", None)
        return WorkflowDefinition(**data)

    @staticmethod
    def _version_from_doc(doc: dict[str, Any]) -> WorkflowVersion:
        data = dict(doc)
        data.pop("_id", None)
        return WorkflowVersion(**data)

    @staticmethod
    def _run_from_doc(doc: dict[str, Any]) -> WorkflowRun:
        data = dict(doc)
        data.pop("_id", None)
        return WorkflowRun(**data)

    @staticmethod
    def _event_from_doc(doc: dict[str, Any]) -> WorkflowRunEvent:
        data = dict(doc)
        data.pop("_id", None)
        return WorkflowRunEvent(**data)

    @staticmethod
    def _credential_from_doc(doc: dict[str, Any]) -> WorkflowCredential:
        data = dict(doc)
        data.pop("_id", None)
        data.pop("secret_payload", None)
        data["has_secret"] = bool(doc.get("secret_payload"))
        return WorkflowCredential(**data)

    @staticmethod
    async def _encrypt_secret_payload(secret: str | None) -> dict[str, Any] | str:
        if not secret:
            return ""
        return await run_blocking_io(encrypt_value, {"value": secret})

    @staticmethod
    async def _decrypt_secret_payload(encrypted: Any) -> str:
        if not encrypted:
            return ""
        if isinstance(encrypted, str):
            return encrypted
        decrypted = await run_blocking_io(decrypt_value, encrypted)
        if isinstance(decrypted, dict):
            value = decrypted.get("value")
            return value if isinstance(value, str) else ""
        return ""

    async def list_workflows(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
        query: str | None = None,
        status_filter: str | None = None,
    ) -> WorkflowListResult:
        limit = _bounded_limit(limit)
        mongo_query = _workflow_list_query(
            owner_user_id=owner_user_id,
            query=query,
            status_filter=status_filter,
        )
        total = await self.definitions.count_documents(mongo_query)
        cursor = (
            self.definitions.find(mongo_query)
            .sort("updated_at", -1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        workflows = [self._definition_from_doc(doc) async for doc in cursor]
        return WorkflowListResult(workflows=workflows, total=total)

    async def list_credentials(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WorkflowCredential]:
        limit = _bounded_limit(limit)
        cursor = (
            self.credentials.find({"owner_user_id": owner_user_id})
            .sort("updated_at", -1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        return [self._credential_from_doc(doc) async for doc in cursor]

    async def list_credential_refs(self, *, owner_user_id: str) -> dict[str, WorkflowCredential]:
        cursor = self.credentials.find({"owner_user_id": owner_user_id})
        credentials = [self._credential_from_doc(doc) async for doc in cursor]
        return {credential.ref: credential for credential in credentials}

    async def upsert_credential(
        self,
        *,
        owner_user_id: str,
        ref: str,
        credential_type: str,
        label: str = "",
        description: str = "",
        secret: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowCredential:
        now = utc_now()
        existing = await self.credentials.find_one({"owner_user_id": owner_user_id, "ref": ref})
        update_fields: dict[str, Any] = {
            "ref": ref,
            "type": credential_type,
            "label": label,
            "description": description,
            "metadata": metadata or {},
            "updated_at": now,
        }
        if existing is None:
            update_fields.update(
                {
                    "credential_id": f"wfc_{uuid.uuid4().hex}",
                    "owner_user_id": owner_user_id,
                    "created_at": now,
                    "secret_payload": await self._encrypt_secret_payload(secret),
                }
            )
        elif secret is not None:
            update_fields["secret_payload"] = await self._encrypt_secret_payload(secret)

        await self.credentials.update_one(
            {"owner_user_id": owner_user_id, "ref": ref},
            {"$set": update_fields},
            upsert=True,
        )
        doc = await self.credentials.find_one({"owner_user_id": owner_user_id, "ref": ref})
        if doc is None:
            raise RuntimeError(f"workflow_credential_not_found_after_upsert:{ref}")
        return self._credential_from_doc(doc)

    async def delete_credential(self, *, owner_user_id: str, credential_id: str) -> bool:
        result = await self.credentials.delete_one(
            {"owner_user_id": owner_user_id, "credential_id": credential_id}
        )
        return bool(result.deleted_count)

    async def get_credential_secret_by_ref(self, *, owner_user_id: str, ref: str) -> str | None:
        doc = await self.credentials.find_one({"owner_user_id": owner_user_id, "ref": ref})
        if doc is None:
            return None
        return await self._decrypt_secret_payload(doc.get("secret_payload"))

    async def get_workflow(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
    ) -> WorkflowDefinition | None:
        doc = await self.definitions.find_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id}
        )
        return self._definition_from_doc(doc) if doc else None

    async def get_version(
        self,
        version_id: str,
        *,
        owner_user_id: str,
    ) -> WorkflowVersion | None:
        doc = await self.versions.find_one(
            {"version_id": version_id, "owner_user_id": owner_user_id}
        )
        return self._version_from_doc(doc) if doc else None

    async def get_latest_version(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
    ) -> WorkflowVersion | None:
        doc = await self.versions.find_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id},
            sort=[("version_number", -1)],
        )
        return self._version_from_doc(doc) if doc else None

    async def list_versions(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WorkflowVersion]:
        limit = _bounded_limit(limit)
        cursor = (
            self.versions.find({"workflow_id": workflow_id, "owner_user_id": owner_user_id})
            .sort("version_number", -1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        return [self._version_from_doc(doc) async for doc in cursor]

    async def create_imported_workflow(
        self,
        *,
        owner_user_id: str,
        created_by: str,
        name: str,
        source_format: Literal["json", "yaml"],
        source_payload: dict[str, Any],
        internal_model: dict[str, Any],
        compatibility_report: dict[str, Any],
    ) -> tuple[WorkflowDefinition, WorkflowVersion]:
        now = utc_now()
        workflow_id = f"wf_{uuid.uuid4().hex}"
        version_id = f"wfv_{uuid.uuid4().hex}"
        definition_doc: dict[str, Any] = {
            "workflow_id": workflow_id,
            "owner_user_id": owner_user_id,
            "name": name,
            "description": "",
            "status": "draft",
            "latest_version_id": version_id,
            "published_version_id": None,
            "version_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        version_doc: dict[str, Any] = {
            "version_id": version_id,
            "workflow_id": workflow_id,
            "owner_user_id": owner_user_id,
            "version_number": 1,
            "source": "workflow",
            "source_format": source_format,
            "source_payload": source_payload,
            "internal_model": internal_model,
            "compatibility_report": compatibility_report,
            "created_by": created_by,
            "created_at": now,
        }
        await self.definitions.insert_one(definition_doc)
        await self.versions.insert_one(version_doc)
        return self._definition_from_doc(definition_doc), self._version_from_doc(version_doc)

    async def create_workflow_version(
        self,
        *,
        workflow_id: str,
        owner_user_id: str,
        created_by: str,
        name: str | None,
        source_format: Literal["json", "yaml"],
        source_payload: dict[str, Any],
        internal_model: dict[str, Any],
        compatibility_report: dict[str, Any],
    ) -> tuple[WorkflowDefinition, WorkflowVersion]:
        definition = await self.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            raise LookupError("workflow_not_found")

        now = utc_now()
        latest = await self.get_latest_version(workflow_id, owner_user_id=owner_user_id)
        version_number = (latest.version_number if latest else definition.version_count) + 1
        version_id = f"wfv_{uuid.uuid4().hex}"
        version_doc: dict[str, Any] = {
            "version_id": version_id,
            "workflow_id": workflow_id,
            "owner_user_id": owner_user_id,
            "version_number": version_number,
            "source": "workflow",
            "source_format": source_format,
            "source_payload": source_payload,
            "internal_model": internal_model,
            "compatibility_report": compatibility_report,
            "created_by": created_by,
            "created_at": now,
        }
        update_fields: dict[str, Any] = {
            "latest_version_id": version_id,
            "version_count": version_number,
            "updated_at": now,
        }
        if name:
            update_fields["name"] = name

        await self.versions.insert_one(version_doc)
        await self.definitions.update_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id},
            {"$set": update_fields},
        )
        updated = await self.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if updated is None:
            raise RuntimeError(f"workflow_not_found_after_version_create:{workflow_id}")
        return updated, self._version_from_doc(version_doc)

    async def publish_workflow(
        self,
        *,
        workflow_id: str,
        owner_user_id: str,
        version_id: str,
    ) -> WorkflowDefinition:
        now = utc_now()
        await self.definitions.update_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id},
            {
                "$set": {
                    "status": "published",
                    "published_version_id": version_id,
                    "updated_at": now,
                }
            },
        )
        updated = await self.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if updated is None:
            raise LookupError("workflow_not_found")
        return updated

    async def unpublish_workflow(
        self,
        *,
        workflow_id: str,
        owner_user_id: str,
    ) -> WorkflowDefinition:
        now = utc_now()
        await self.definitions.update_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id},
            {"$set": {"status": "draft", "published_version_id": None, "updated_at": now}},
        )
        updated = await self.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if updated is None:
            raise LookupError("workflow_not_found")
        return updated

    async def archive_workflow(
        self,
        *,
        workflow_id: str,
        owner_user_id: str,
    ) -> WorkflowDefinition:
        now = utc_now()
        await self.definitions.update_one(
            {"workflow_id": workflow_id, "owner_user_id": owner_user_id},
            {
                "$set": {
                    "status": "archived",
                    "published_version_id": None,
                    "updated_at": now,
                }
            },
        )
        updated = await self.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if updated is None:
            raise LookupError("workflow_not_found")
        return updated

    async def create_run(
        self,
        *,
        workflow_id: str,
        version_id: str,
        owner_user_id: str,
        mode: Literal["sync", "async", "stream"],
        workflow_input: dict[str, Any],
    ) -> WorkflowRun:
        now = utc_now()
        run_doc: dict[str, Any] = {
            "run_id": f"wfr_{uuid.uuid4().hex}",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "owner_user_id": owner_user_id,
            "status": "running",
            "mode": mode,
            "input": workflow_input,
            "output": {},
            "error": None,
            "pause": {},
            "started_at": now,
            "finished_at": None,
        }
        await self.runs.insert_one(run_doc)
        return self._run_from_doc(run_doc)

    async def append_run_events(
        self,
        *,
        run: WorkflowRun,
        events: list[dict[str, Any]],
    ) -> list[WorkflowRunEvent]:
        if not events:
            return []
        now = utc_now()
        latest = await self.events.find_one(
            {"run_id": run.run_id, "owner_user_id": run.owner_user_id},
            sort=[("sequence", -1)],
        )
        next_sequence = int(latest.get("sequence") or 0) + 1 if latest else 1
        docs: list[dict[str, Any]] = []
        for index, event in enumerate(events, start=next_sequence):
            raw_payload = event.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            docs.append(
                {
                    "event_id": f"wfe_{uuid.uuid4().hex}",
                    "run_id": run.run_id,
                    "workflow_id": run.workflow_id,
                    "version_id": run.version_id,
                    "owner_user_id": run.owner_user_id,
                    "sequence": index,
                    "event_type": str(event.get("event_type") or "event"),
                    "node_id": event.get("node_id"),
                    "node_type": event.get("node_type"),
                    "payload": _bounded_event_payload(
                        payload, max_bytes=self.max_event_payload_bytes
                    ),
                    "created_at": now,
                }
            )
        await self.events.insert_many(docs)
        return [self._event_from_doc(doc) for doc in docs]

    async def finish_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
        status: Literal["succeeded", "failed", "cancelled"],
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> WorkflowRun:
        update = {
            "$set": {
                "status": status,
                "output": output or {},
                "error": error,
                "pause": {},
                "finished_at": utc_now(),
            }
        }
        await self.runs.update_one(
            {
                "run_id": run_id,
                "owner_user_id": owner_user_id,
                "status": {"$in": WORKFLOW_RUN_FINISHABLE_STATUSES},
            },
            update,
        )
        doc = await self.runs.find_one({"run_id": run_id, "owner_user_id": owner_user_id})
        if not doc:
            raise RuntimeError(f"workflow_run_not_found:{run_id}")
        return self._run_from_doc(doc)

    async def pause_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        pause: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        update = {
            "$set": {
                "status": "paused",
                "output": output or {},
                "error": error,
                "pause": pause or {},
                "finished_at": None,
            }
        }
        await self.runs.update_one(
            {
                "run_id": run_id,
                "owner_user_id": owner_user_id,
                "status": {"$in": WORKFLOW_RUN_FINISHABLE_STATUSES},
            },
            update,
        )
        doc = await self.runs.find_one({"run_id": run_id, "owner_user_id": owner_user_id})
        if not doc:
            raise RuntimeError(f"workflow_run_not_found:{run_id}")
        return self._run_from_doc(doc)

    async def cancel_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
        error: str = "workflow_run_cancelled_by_user",
    ) -> tuple[WorkflowRun, list[WorkflowRunEvent]]:
        run = await self.get_run(run_id, owner_user_id=owner_user_id)
        if run is None:
            raise RuntimeError(f"workflow_run_not_found:{run_id}")
        if run.status not in {"queued", "running", "paused"}:
            raise ValueError(f"workflow_run_not_cancellable:{run.status}")

        update_result = await self.runs.update_one(
            {
                "run_id": run_id,
                "owner_user_id": owner_user_id,
                "status": {"$in": WORKFLOW_RUN_FINISHABLE_STATUSES},
            },
            {
                "$set": {
                    "status": "cancelled",
                    "output": {},
                    "error": error,
                    "pause": {},
                    "finished_at": utc_now(),
                }
            },
        )
        if getattr(update_result, "matched_count", None) == 0:
            current = await self.get_run(run_id, owner_user_id=owner_user_id)
            if current is None:
                raise RuntimeError(f"workflow_run_not_found:{run_id}")
            raise ValueError(f"workflow_run_not_cancellable:{current.status}")

        cancelled = await self.get_run(run_id, owner_user_id=owner_user_id)
        if cancelled is None:
            raise RuntimeError(f"workflow_run_not_found:{run_id}")
        if cancelled.status != "cancelled":
            raise ValueError(f"workflow_run_not_cancellable:{cancelled.status}")

        events = await self.append_run_events(
            run=cancelled,
            events=[
                {
                    "event_type": "run_cancelled",
                    "payload": {"error": error, "cancelled_by": owner_user_id},
                }
            ],
        )
        return cancelled, events

    async def get_run(
        self,
        run_id: str,
        *,
        owner_user_id: str,
    ) -> WorkflowRun | None:
        doc = await self.runs.find_one({"run_id": run_id, "owner_user_id": owner_user_id})
        return self._run_from_doc(doc) if doc else None

    async def list_runs(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        limit = _bounded_limit(limit)
        cursor = (
            self.runs.find({"workflow_id": workflow_id, "owner_user_id": owner_user_id})
            .sort("started_at", -1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        return [self._run_from_doc(doc) async for doc in cursor]

    async def list_pending_approval_runs(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        limit = _bounded_limit(limit)
        cursor = (
            self.runs.find(
                {
                    "owner_user_id": owner_user_id,
                    "status": "paused",
                    "pause.kind": "human_approval",
                }
            )
            .sort("started_at", -1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        return [self._run_from_doc(doc) async for doc in cursor]

    async def fail_stale_running_runs(
        self,
        *,
        error: str = "workflow_run_interrupted_by_server_restart",
        limit: int = 200,
    ) -> int:
        limit = _bounded_limit(limit)
        cursor = (
            self.runs.find({"status": "running", "mode": {"$in": ["async", "stream"]}})
            .sort("started_at", 1)
            .limit(limit)
        )
        stale_runs = [self._run_from_doc(doc) async for doc in cursor]
        count = 0
        for run in stale_runs:
            await self.append_run_events(
                run=run,
                events=[
                    {
                        "event_type": "run_failed",
                        "payload": {"error": error, "recoverable": True},
                    }
                ],
            )
            await self.finish_run(
                run_id=run.run_id,
                owner_user_id=run.owner_user_id,
                status="failed",
                error=error,
            )
            count += 1
        return count

    async def delete_terminal_run_logs_before(self, cutoff: datetime) -> int:
        """Delete terminal workflow runs and trace events finished before cutoff."""
        query = {
            "status": {"$in": WORKFLOW_RUN_TERMINAL_STATUSES},
            "finished_at": {"$lt": cutoff},
        }
        cursor = self.runs.find(query)
        run_ids = [str(doc.get("run_id")) async for doc in cursor if doc.get("run_id")]
        if not run_ids:
            return 0
        await self.events.delete_many({"run_id": {"$in": run_ids}})
        result = await self.runs.delete_many(query)
        return int(getattr(result, "deleted_count", 0) or 0)

    async def list_run_events(
        self,
        run_id: str,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 200,
    ) -> list[WorkflowRunEvent]:
        limit = _bounded_limit(limit)
        cursor = (
            self.events.find({"run_id": run_id, "owner_user_id": owner_user_id})
            .sort("sequence", 1)
            .skip(max(skip, 0))
            .limit(limit)
        )
        return [self._event_from_doc(doc) async for doc in cursor]
