"""Workflow plugin API routes.

This first slice exposes guarded stubs so the plugin can be scanned, enabled,
disabled, and accounted for before the full workflow runtime lands.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import require_permissions
from src.api.routes.plugin_guard import plugin_route_guard
from src.infra.logging import get_logger
from src.kernel.schemas.user import TokenPayload
from src.plugins.workflow.compatibility import (
    compatibility_matrix_payload,
    node_types_for_catalog,
)
from src.plugins.workflow.contracts import (
    output_contract_status,
    workflow_callable_interface,
    workflow_next_action,
    workflow_result_interface,
)
from src.plugins.workflow.service import WorkflowPluginService, create_workflow_service

PLUGIN_ID: Literal["workflow"] = "workflow"
RUN_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
RUN_SSE_STOP_WAITING_STATUSES = {"paused"}
RUN_WAITING_STATUSES = {"queued", "running", "paused"}

logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(plugin_route_guard(PLUGIN_ID))])


class WorkflowSummary(BaseModel):
    workflow_id: str
    name: str
    status: Literal["draft", "published", "archived"] = "draft"
    latest_version_id: str | None = None
    published_version_id: str | None = None
    updated_at: datetime


class WorkflowVersionSummary(BaseModel):
    version_id: str
    workflow_id: str
    version_number: int
    source: Literal["workflow"] = "workflow"
    source_format: Literal["json", "yaml"] = "json"
    internal_model: dict[str, Any] = Field(default_factory=dict)
    compatibility_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowDetailResponse(WorkflowSummary):
    description: str = ""
    version_count: int = 0
    created_at: datetime
    latest_version: WorkflowVersionSummary | None = None


class WorkflowVersionListResponse(BaseModel):
    workflow_id: str
    versions: list[WorkflowVersionSummary]
    skip: int = 0
    limit: int = 50


class WorkflowInputSchemaResponse(BaseModel):
    plugin_id: Literal["workflow"] = PLUGIN_ID
    workflow_id: str
    version_id: str
    version_number: int
    input_schema: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published", "archived"] = "draft"
    schema_source: str = "inferred"
    inferred_fields: list[str] = Field(default_factory=list)
    interface: dict[str, Any] = Field(default_factory=dict)


class WorkflowIoContractResponse(BaseModel):
    plugin_id: Literal["workflow"] = PLUGIN_ID
    workflow_id: str
    version_id: str
    version_number: int
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published", "archived"] = "draft"
    input_schema_source: str = "inferred"
    output_schema_source: str = "inferred"
    inferred_input_fields: list[str] = Field(default_factory=list)
    inferred_output_fields: list[str] = Field(default_factory=list)
    interface: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunEventResponse(BaseModel):
    event_id: str
    run_id: str
    workflow_id: str
    version_id: str
    sequence: int
    event_type: str
    node_id: str | None = None
    node_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowRunEventsResponse(BaseModel):
    run: WorkflowRunResponse
    events: list[WorkflowRunEventResponse]
    skip: int = 0
    limit: int = 200


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowSummary]
    total: int
    skip: int = 0
    limit: int = 50
    plugin_id: str = PLUGIN_ID


class WorkflowImportRequest(BaseModel):
    name: str = Field(..., min_length=1)
    source_payload: dict[str, Any] | None = None
    source_content: str | None = None
    source_format: Literal["json", "yaml"] = "json"
    dry_run: bool = True


class WorkflowVersionCreateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    source_payload: dict[str, Any] | None = None
    source_content: str | None = None
    source_format: Literal["json", "yaml"] = "json"


class WorkflowPublishRequest(BaseModel):
    version_id: str | None = None


class WorkflowImportReport(BaseModel):
    source: Literal["workflow"] = "workflow"
    source_version: str = "unknown"
    workflow_id: str | None = None
    supported_nodes: list[str] = Field(default_factory=list)
    unsupported_nodes: list[dict[str, Any]] = Field(default_factory=list)
    credential_refs_required: list[str] = Field(default_factory=list)
    credential_refs_resolved: list[dict[str, Any]] = Field(default_factory=list)
    credential_refs_unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    lossless: bool = False


class WorkflowImportResponse(BaseModel):
    workflow_id: str | None = None
    version_id: str | None = None
    status: Literal["stub", "imported", "versioned"] = "stub"
    dry_run: bool
    compatibility_report: WorkflowImportReport
    io_contract: dict[str, Any] | None = None
    interface: dict[str, Any] | None = None


class WorkflowLifecycleResponse(BaseModel):
    workflow: WorkflowSummary


class WorkflowDeleteResponse(BaseModel):
    deleted: bool
    workflow_id: str
    workflow: WorkflowSummary


class WorkflowValidationResponse(BaseModel):
    workflow_id: str
    version_id: str
    version_number: int
    runnable: bool
    errors: list[str] = Field(default_factory=list)
    reachable_node_ids: list[str] = Field(default_factory=list)
    credential_refs_required: list[str] = Field(default_factory=list)
    credential_refs_resolved: list[dict[str, Any]] = Field(default_factory=list)
    credential_refs_unresolved: list[str] = Field(default_factory=list)


class WorkflowCredentialResponse(BaseModel):
    credential_id: str
    ref: str
    type: str = "credential_ref"
    label: str = ""
    description: str = ""
    has_secret: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WorkflowCredentialListResponse(BaseModel):
    credentials: list[WorkflowCredentialResponse]
    skip: int = 0
    limit: int = 50


class WorkflowCredentialUpsertRequest(BaseModel):
    ref: str = Field(..., min_length=1)
    type: str = Field(default="credential_ref", min_length=1)
    label: str = ""
    description: str = ""
    secret: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowCredentialDeleteResponse(BaseModel):
    deleted: bool
    credential_id: str


class WorkflowRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    version_id: str | None = None
    mode: Literal["sync", "async", "stream"] = "sync"


class WorkflowRunResumeRequest(BaseModel):
    approved: bool = True
    response: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None


class WorkflowRunResponse(BaseModel):
    run_id: str | None = None
    workflow_id: str
    version_id: str | None = None
    mode: Literal["sync", "async", "stream"] = "sync"
    status: Literal["stub", "queued", "running", "paused", "succeeded", "failed", "cancelled"] = (
        "stub"
    )
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    pause: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    events: list[WorkflowRunEventResponse] = Field(default_factory=list)
    io_contract: dict[str, Any] | None = None
    output_contract: dict[str, Any] | None = None
    interface: dict[str, Any] = Field(default_factory=dict)
    next_action: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunListResponse(BaseModel):
    workflow_id: str
    runs: list[WorkflowRunResponse]
    skip: int = 0
    limit: int = 50


class WorkflowPendingApprovalListResponse(BaseModel):
    plugin_id: Literal["workflow"] = PLUGIN_ID
    runs: list[WorkflowRunResponse]
    skip: int = 0
    limit: int = 50


def _workflow_run_response(
    run: Any,
    *,
    events: list[Any] | None = None,
    io_contract: dict[str, Any] | None = None,
) -> WorkflowRunResponse:
    output = run.output if isinstance(run.output, dict) else {}
    return WorkflowRunResponse(
        run_id=run.run_id,
        workflow_id=run.workflow_id,
        version_id=run.version_id,
        mode=getattr(run, "mode", "sync"),
        status=run.status,
        output=output,
        error=run.error,
        pause=getattr(run, "pause", {}) if isinstance(getattr(run, "pause", {}), dict) else {},
        started_at=run.started_at,
        finished_at=run.finished_at,
        events=[WorkflowRunEventResponse(**event.model_dump()) for event in events or []],
        io_contract=io_contract,
        output_contract=output_contract_status(output, io_contract) if io_contract else None,
        interface=workflow_result_interface(
            workflow_id=run.workflow_id,
            version_id=run.version_id,
            run_id=run.run_id,
        ),
        next_action=workflow_next_action(
            status=run.status,
            run_id=run.run_id,
            workflow_id=run.workflow_id,
            pause=getattr(run, "pause", {}) if isinstance(getattr(run, "pause", {}), dict) else {},
        ),
    )


def _workflow_version_io_contract(definition: Any, version: Any) -> dict[str, Any] | None:
    if definition is None or version is None:
        return None
    from src.plugins.workflow.tools import infer_workflow_io_contract_payload

    return infer_workflow_io_contract_payload(
        workflow_id=str(getattr(version, "workflow_id", getattr(definition, "workflow_id", ""))),
        status=str(getattr(definition, "status", "draft") or "draft"),
        version_id=str(getattr(version, "version_id", "")),
        version_number=int(getattr(version, "version_number", 0) or 0),
        internal_model=getattr(version, "internal_model", {}) or {},
    )


def _workflow_version_interface(definition: Any, version: Any) -> dict[str, Any] | None:
    if definition is None or version is None:
        return None
    return workflow_result_interface(
        workflow_id=getattr(version, "workflow_id", getattr(definition, "workflow_id", None)),
        version_id=getattr(version, "version_id", None),
        run_id=None,
    )


def _workflow_contract_payload_with_interface(
    payload: dict[str, Any], *, workflow_id: str, version_id: str | None
) -> dict[str, Any]:
    result = dict(payload)
    resolved_workflow_id = result.get("workflow_id") or workflow_id
    resolved_version_id = result.get("version_id") or version_id
    result["interface"] = workflow_callable_interface(
        workflow_id=resolved_workflow_id,
        version_id=resolved_version_id,
    )
    return result


async def _workflow_io_contract_for_run_response(
    service: WorkflowPluginService,
    run: Any,
    *,
    owner_user_id: str,
) -> dict[str, Any] | None:
    workflow_id = getattr(run, "workflow_id", None)
    if not workflow_id:
        return None
    try:
        contract = await service.get_workflow_io_contract(
            str(workflow_id),
            owner_user_id=owner_user_id,
            version_id=getattr(run, "version_id", None),
        )
    except Exception:  # noqa: BLE001 - contract metadata must not mask run payloads
        return None
    return contract if isinstance(contract, dict) else None


async def _workflow_run_response_with_contract(
    service: WorkflowPluginService,
    run: Any,
    *,
    owner_user_id: str,
    events: list[Any] | None = None,
) -> WorkflowRunResponse:
    io_contract = await _workflow_io_contract_for_run_response(
        service,
        run,
        owner_user_id=owner_user_id,
    )
    return _workflow_run_response(run, events=events, io_contract=io_contract)


def _workflow_run_error_snapshot(*, workflow_id: str, run_id: str, error: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "version_id": None,
        "mode": "stream",
        "status": "failed",
        "output": {},
        "error": error,
        "pause": {},
        "started_at": None,
        "finished_at": None,
        "events": [],
        "interface": workflow_result_interface(
            workflow_id=workflow_id,
            version_id=None,
            run_id=run_id,
        ),
        "next_action": workflow_next_action(status="failed", run_id=run_id),
    }


def _workflow_run_events_unavailable_error() -> str:
    return "workflow_run_events_unavailable"


def _workflow_run_event_stream_failed_error() -> str:
    return "workflow_run_event_stream_failed"


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _bounded_stream_poll_seconds(poll_ms: int) -> float:
    return min(max(poll_ms, 100), 5000) / 1000.0


def _bounded_stream_timeout_seconds(timeout_ms: int) -> float:
    return min(max(timeout_ms, 1000), 120000) / 1000.0


def _is_workflow_run_waiting(status_value: str) -> bool:
    return status_value in RUN_WAITING_STATUSES


def _workflow_lookup_error_detail(
    exc: LookupError,
    *,
    workflow_id: str,
    version_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {"error": str(exc), "workflow_id": workflow_id}
    if version_id:
        detail["version_id"] = version_id
    if run_id:
        detail["run_id"] = run_id
    return detail


async def get_workflow_service() -> WorkflowPluginService:
    try:
        return await create_workflow_service()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Workflow service is unavailable: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "workflow_service_unavailable", "plugin_id": PLUGIN_ID},
        ) from exc


@router.get("/credentials", response_model=WorkflowCredentialListResponse)
async def list_workflow_credentials(
    skip: int = 0,
    limit: int = 50,
    user: TokenPayload = Depends(require_permissions("workflow:credential:manage")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowCredentialListResponse:
    """Return credential aliases available to workflow imports and preflight."""
    credentials = await service.list_credentials(user=user, skip=skip, limit=limit)
    return WorkflowCredentialListResponse(
        credentials=[
            WorkflowCredentialResponse(**credential.model_dump()) for credential in credentials
        ],
        skip=skip,
        limit=limit,
    )


@router.put("/credentials", response_model=WorkflowCredentialResponse)
async def upsert_workflow_credential(
    request: WorkflowCredentialUpsertRequest,
    user: TokenPayload = Depends(require_permissions("workflow:credential:manage")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowCredentialResponse:
    """Create or update a workflow credential reference alias without returning secret material."""
    try:
        credential = await service.upsert_credential(
            user=user,
            ref=request.ref,
            credential_type=request.type,
            label=request.label,
            description=request.description,
            secret=request.secret,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc)},
        ) from exc
    return WorkflowCredentialResponse(**credential.model_dump())


@router.delete("/credentials/{credential_id}", response_model=WorkflowCredentialDeleteResponse)
async def delete_workflow_credential(
    credential_id: str,
    user: TokenPayload = Depends(require_permissions("workflow:credential:manage")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowCredentialDeleteResponse:
    """Delete a workflow credential alias owned by the current user."""
    deleted = await service.delete_credential(user=user, credential_id=credential_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "workflow_credential_not_found", "credential_id": credential_id},
        )
    return WorkflowCredentialDeleteResponse(deleted=True, credential_id=credential_id)


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    skip: int = 0,
    limit: int = 50,
    query: str | None = None,
    status_filter: Literal["draft", "published", "archived"] | None = Query(
        default=None, alias="status"
    ),
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowListResponse:
    """Return workflow summaries owned by this plugin."""
    result = await service.list_workflows(
        owner_user_id=user.sub,
        skip=skip,
        limit=limit,
        query=query,
        status_filter=status_filter,
    )
    return WorkflowListResponse(
        workflows=[WorkflowSummary(**workflow.model_dump()) for workflow in result.workflows],
        total=result.total,
        skip=skip,
        limit=limit,
    )


@router.post("/workflows/import", response_model=WorkflowImportResponse)
async def import_workflow(
    request: WorkflowImportRequest,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowImportResponse:
    """Import a Workflow DSL snapshot into LambChat workflow storage."""
    try:
        definition, version, report = await service.import_workflow(
            name=request.name,
            source_format=request.source_format,
            source_payload=request.source_payload,
            source_content=request.source_content,
            dry_run=request.dry_run,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc)},
        ) from exc
    return WorkflowImportResponse(
        workflow_id=definition.workflow_id if definition else None,
        version_id=version.version_id if version else None,
        status="stub" if request.dry_run else "imported",
        dry_run=request.dry_run,
        compatibility_report=WorkflowImportReport(**report),
        io_contract=_workflow_version_io_contract(definition, version),
        interface=_workflow_version_interface(definition, version),
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: str,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowDetailResponse:
    """Return one workflow definition with its latest version graph."""
    workflow, latest_version = await service.get_workflow_detail(
        workflow_id,
        owner_user_id=user.sub,
    )
    if workflow:
        version_payload = (
            WorkflowVersionSummary(**latest_version.model_dump()) if latest_version else None
        )
        return WorkflowDetailResponse(
            **workflow.model_dump(),
            latest_version=version_payload,
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "workflow_not_found", "workflow_id": workflow_id},
    )


@router.delete("/workflows/{workflow_id}", response_model=WorkflowDeleteResponse)
async def delete_workflow(
    workflow_id: str,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowDeleteResponse:
    """Archive a workflow so it is removed from default workflow lists."""
    try:
        workflow = await service.delete_workflow(workflow_id=workflow_id, user=user)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowDeleteResponse(
        deleted=True,
        workflow_id=workflow.workflow_id,
        workflow=WorkflowSummary(**workflow.model_dump()),
    )


@router.get("/workflows/{workflow_id}/versions", response_model=WorkflowVersionListResponse)
async def list_workflow_versions(
    workflow_id: str,
    skip: int = 0,
    limit: int = 50,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowVersionListResponse:
    """Return version snapshots for one workflow."""
    try:
        versions = await service.list_versions(
            workflow_id,
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowVersionListResponse(
        workflow_id=workflow_id,
        versions=[WorkflowVersionSummary(**version.model_dump()) for version in versions],
        skip=skip,
        limit=limit,
    )


@router.get("/workflows/{workflow_id}/input-schema", response_model=WorkflowInputSchemaResponse)
async def get_workflow_input_schema(
    workflow_id: str,
    version_id: str | None = None,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowInputSchemaResponse:
    """Return the persisted workflow input contract used by UI and tool callers."""
    try:
        payload = await service.get_workflow_input_schema(
            workflow_id,
            owner_user_id=user.sub,
            version_id=version_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_workflow_lookup_error_detail(
                exc,
                workflow_id=workflow_id,
                version_id=version_id,
            ),
        ) from exc
    return WorkflowInputSchemaResponse(
        **_workflow_contract_payload_with_interface(
            payload,
            workflow_id=workflow_id,
            version_id=version_id,
        )
    )


@router.get("/workflows/{workflow_id}/io-contract", response_model=WorkflowIoContractResponse)
async def get_workflow_io_contract(
    workflow_id: str,
    version_id: str | None = None,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowIoContractResponse:
    """Return the workflow input and output contract for callers and editors."""
    try:
        payload = await service.get_workflow_io_contract(
            workflow_id,
            owner_user_id=user.sub,
            version_id=version_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_workflow_lookup_error_detail(
                exc,
                workflow_id=workflow_id,
                version_id=version_id,
            ),
        ) from exc
    return WorkflowIoContractResponse(
        **_workflow_contract_payload_with_interface(
            payload,
            workflow_id=workflow_id,
            version_id=version_id,
        )
    )


@router.post("/workflows/{workflow_id}/versions", response_model=WorkflowImportResponse)
async def create_workflow_version(
    workflow_id: str,
    request: WorkflowVersionCreateRequest,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowImportResponse:
    """Save a new immutable version for an existing workflow."""
    try:
        _definition, version, report = await service.create_workflow_version(
            workflow_id=workflow_id,
            name=request.name,
            source_format=request.source_format,
            source_payload=request.source_payload,
            source_content=request.source_content,
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowImportResponse(
        workflow_id=workflow_id,
        version_id=version.version_id,
        status="versioned",
        dry_run=False,
        compatibility_report=WorkflowImportReport(**report),
        io_contract=_workflow_version_io_contract(_definition, version),
        interface=_workflow_version_interface(_definition, version),
    )


@router.post("/workflows/{workflow_id}/publish", response_model=WorkflowLifecycleResponse)
async def publish_workflow(
    workflow_id: str,
    request: WorkflowPublishRequest,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowLifecycleResponse:
    """Publish a runnable workflow version for chat, tasks, and tool calls."""
    try:
        workflow = await service.publish_workflow(
            workflow_id=workflow_id,
            version_id=request.version_id,
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_workflow_lookup_error_detail(
                exc,
                workflow_id=workflow_id,
                version_id=request.version_id,
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowLifecycleResponse(workflow=WorkflowSummary(**workflow.model_dump()))


@router.post("/workflows/{workflow_id}/validate", response_model=WorkflowValidationResponse)
async def validate_workflow_version(
    workflow_id: str,
    request: WorkflowPublishRequest,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowValidationResponse:
    """Validate a workflow version against publish-time runtime and policy checks."""
    try:
        payload = await service.validate_workflow_version(
            workflow_id=workflow_id,
            version_id=request.version_id,
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_workflow_lookup_error_detail(
                exc,
                workflow_id=workflow_id,
                version_id=request.version_id,
            ),
        ) from exc
    return WorkflowValidationResponse(**payload)


@router.post("/workflows/{workflow_id}/unpublish", response_model=WorkflowLifecycleResponse)
async def unpublish_workflow(
    workflow_id: str,
    user: TokenPayload = Depends(require_permissions("workflow:write")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowLifecycleResponse:
    """Return a workflow to draft state without deleting versions."""
    try:
        workflow = await service.unpublish_workflow(workflow_id=workflow_id, user=user)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowLifecycleResponse(workflow=WorkflowSummary(**workflow.model_dump()))


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: str,
    request: WorkflowRunRequest,
    user: TokenPayload = Depends(require_permissions("workflow:run")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowRunResponse:
    """Run a workflow through the first local sync executor."""
    try:
        run, events = await service.run_workflow(
            workflow_id=workflow_id,
            version_id=request.version_id,
            workflow_input=request.input,
            mode=request.mode,
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_workflow_lookup_error_detail(
                exc,
                workflow_id=workflow_id,
                version_id=request.version_id,
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return await _workflow_run_response_with_contract(
        service,
        run,
        owner_user_id=user.sub,
        events=events,
    )


@router.get("/workflows/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(
    workflow_id: str,
    skip: int = 0,
    limit: int = 50,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowRunListResponse:
    """Return recent persisted runs for a workflow."""
    try:
        runs = await service.list_runs(
            workflow_id,
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id},
        ) from exc
    return WorkflowRunListResponse(
        workflow_id=workflow_id,
        runs=[
            await _workflow_run_response_with_contract(
                service,
                run,
                owner_user_id=user.sub,
            )
            for run in runs
        ],
        skip=skip,
        limit=limit,
    )


@router.get("/approvals/pending", response_model=WorkflowPendingApprovalListResponse)
async def list_pending_workflow_approvals(
    skip: int = 0,
    limit: int = 50,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowPendingApprovalListResponse:
    """Return paused human approval runs across the user's workflows."""
    runs = await service.list_pending_approvals(
        owner_user_id=user.sub,
        skip=skip,
        limit=limit,
    )
    return WorkflowPendingApprovalListResponse(
        runs=[
            await _workflow_run_response_with_contract(
                service,
                run,
                owner_user_id=user.sub,
            )
            for run in runs
        ],
        skip=skip,
        limit=limit,
    )


@router.get(
    "/workflows/{workflow_id}/runs/{run_id}/events",
    response_model=WorkflowRunEventsResponse,
)
async def list_workflow_run_events(
    workflow_id: str,
    run_id: str,
    skip: int = 0,
    limit: int = 200,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowRunEventsResponse:
    """Return persisted debug events for a workflow run."""
    try:
        run, events = await service.list_run_events(
            workflow_id=workflow_id,
            run_id=run_id,
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    except Exception as exc:
        logger.warning(
            "Workflow run events are unavailable: workflow_id=%s, run_id=%s, error=%s",
            workflow_id,
            run_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": _workflow_run_events_unavailable_error(),
                "plugin_id": PLUGIN_ID,
                "workflow_id": workflow_id,
                "run_id": run_id,
            },
        ) from exc
    return WorkflowRunEventsResponse(
        run=await _workflow_run_response_with_contract(
            service,
            run,
            owner_user_id=user.sub,
        ),
        events=[WorkflowRunEventResponse(**event.model_dump()) for event in events],
        skip=skip,
        limit=limit,
    )


@router.get("/workflows/{workflow_id}/runs/{run_id}/events/stream")
async def stream_workflow_run_events(
    workflow_id: str,
    run_id: str,
    skip: int = 0,
    limit: int = 200,
    poll_ms: int = 500,
    timeout_ms: int = 30000,
    user: TokenPayload = Depends(require_permissions("workflow:read")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> StreamingResponse:
    """Stream persisted debug events until the run reaches a terminal state or times out."""
    try:
        run, events = await service.list_run_events(
            workflow_id=workflow_id,
            run_id=run_id,
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    except Exception as exc:
        logger.warning(
            "Workflow run event stream is unavailable: workflow_id=%s, run_id=%s, error=%s",
            workflow_id,
            run_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": _workflow_run_event_stream_failed_error(),
                "plugin_id": PLUGIN_ID,
                "workflow_id": workflow_id,
                "run_id": run_id,
            },
        ) from exc

    async def event_generator():
        current_run = run
        emitted_count = 0
        next_skip = max(skip, 0)
        deadline = monotonic() + _bounded_stream_timeout_seconds(timeout_ms)
        poll_seconds = _bounded_stream_poll_seconds(poll_ms)
        first_batch = True
        while True:
            current_events = events if first_batch else []
            if not first_batch:
                try:
                    current_run, current_events = await service.list_run_events(
                        workflow_id=workflow_id,
                        run_id=run_id,
                        owner_user_id=user.sub,
                        skip=next_skip,
                        limit=limit,
                    )
                except LookupError as exc:
                    error_payload = {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "error": str(exc),
                    }
                    yield _sse_event("workflow_run_error", error_payload)
                    yield _sse_event(
                        "workflow_run_snapshot",
                        {
                            "run": _workflow_run_error_snapshot(
                                workflow_id=workflow_id,
                                run_id=run_id,
                                error=str(exc),
                            ),
                            "skip": skip,
                            "limit": limit,
                            "event_count": emitted_count,
                            "terminal": True,
                            "waiting": False,
                            "error": str(exc),
                        },
                    )
                    return
                except Exception as exc:
                    logger.warning(
                        "Workflow run event stream poll failed: workflow_id=%s, run_id=%s, error=%s",
                        workflow_id,
                        run_id,
                        exc,
                        exc_info=True,
                    )
                    error = _workflow_run_event_stream_failed_error()
                    error_payload = {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "error": error,
                    }
                    yield _sse_event("workflow_run_error", error_payload)
                    yield _sse_event(
                        "workflow_run_snapshot",
                        {
                            "run": _workflow_run_error_snapshot(
                                workflow_id=workflow_id,
                                run_id=run_id,
                                error=error,
                            ),
                            "skip": skip,
                            "limit": limit,
                            "event_count": emitted_count,
                            "terminal": True,
                            "waiting": False,
                            "error": error,
                        },
                    )
                    return
            first_batch = False
            for event in current_events:
                yield _sse_event(
                    "workflow_run_event",
                    WorkflowRunEventResponse(**event.model_dump()).model_dump(mode="json"),
                )
            emitted_count += len(current_events)
            next_skip += len(current_events)
            if (
                current_run.status in RUN_TERMINAL_STATUSES
                or current_run.status in RUN_SSE_STOP_WAITING_STATUSES
                or monotonic() >= deadline
            ):
                break
            if not current_events:
                yield ": workflow_run_keepalive\n\n"
                await asyncio.sleep(poll_seconds)
            else:
                await asyncio.sleep(0)
        yield _sse_event(
            "workflow_run_snapshot",
            {
                "run": (
                    await _workflow_run_response_with_contract(
                        service,
                        current_run,
                        owner_user_id=user.sub,
                    )
                ).model_dump(mode="json"),
                "skip": skip,
                "limit": limit,
                "event_count": emitted_count,
                "terminal": current_run.status in RUN_TERMINAL_STATUSES,
                "waiting": _is_workflow_run_waiting(str(current_run.status)),
            },
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/workflows/{workflow_id}/runs/{run_id}/cancel",
    response_model=WorkflowRunResponse,
)
async def cancel_workflow_run(
    workflow_id: str,
    run_id: str,
    user: TokenPayload = Depends(require_permissions("workflow:run")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowRunResponse:
    """Cancel a queued or running workflow run."""
    try:
        run, events = await service.cancel_run(
            workflow_id=workflow_id,
            run_id=run_id,
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    return await _workflow_run_response_with_contract(
        service,
        run,
        owner_user_id=user.sub,
        events=events,
    )


@router.post(
    "/workflows/{workflow_id}/runs/{run_id}/resume",
    response_model=WorkflowRunResponse,
)
async def resume_workflow_run(
    workflow_id: str,
    run_id: str,
    request: WorkflowRunResumeRequest,
    user: TokenPayload = Depends(require_permissions("workflow:run")),
    service: WorkflowPluginService = Depends(get_workflow_service),
) -> WorkflowRunResponse:
    """Resume a paused workflow run after a human approval decision."""
    try:
        run, events = await service.resume_run(
            workflow_id=workflow_id,
            run_id=run_id,
            approval_response=request.model_dump(),
            user=user,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc), "workflow_id": workflow_id, "run_id": run_id},
        ) from exc
    return await _workflow_run_response_with_contract(
        service,
        run,
        owner_user_id=user.sub,
        events=events,
    )


@router.get("/node-types")
async def list_node_types(
    _: None = Depends(require_permissions("workflow:read")),
) -> dict[str, Any]:
    """Return the first planned node catalog for UI discovery."""
    return {
        "plugin_id": PLUGIN_ID,
        "node_types": node_types_for_catalog(),
        "compatibility": compatibility_matrix_payload(),
    }


__all__ = [
    "WorkflowImportRequest",
    "WorkflowCredentialDeleteResponse",
    "WorkflowCredentialListResponse",
    "WorkflowCredentialResponse",
    "WorkflowCredentialUpsertRequest",
    "WorkflowImportReport",
    "WorkflowImportResponse",
    "WorkflowInputSchemaResponse",
    "WorkflowIoContractResponse",
    "WorkflowListResponse",
    "WorkflowLifecycleResponse",
    "WorkflowPendingApprovalListResponse",
    "WorkflowPublishRequest",
    "WorkflowDetailResponse",
    "WorkflowRunEventResponse",
    "WorkflowRunEventsResponse",
    "WorkflowRunListResponse",
    "WorkflowRunRequest",
    "WorkflowRunResumeRequest",
    "WorkflowRunResponse",
    "WorkflowSummary",
    "WorkflowValidationResponse",
    "WorkflowVersionCreateRequest",
    "WorkflowVersionListResponse",
    "WorkflowVersionSummary",
    "cancel_workflow_run",
    "create_workflow_version",
    "delete_workflow_credential",
    "list_node_types",
    "list_pending_workflow_approvals",
    "list_workflow_credentials",
    "list_workflow_run_events",
    "list_workflow_runs",
    "list_workflow_versions",
    "list_workflows",
    "import_workflow",
    "get_workflow_input_schema",
    "get_workflow_io_contract",
    "get_workflow",
    "publish_workflow",
    "resume_workflow_run",
    "run_workflow",
    "router",
    "unpublish_workflow",
    "upsert_workflow_credential",
    "validate_workflow_version",
]
