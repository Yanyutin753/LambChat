"""Minimal local executor for LambChat workflow models."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from time import perf_counter
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from src.plugins.workflow.policy import HttpRequestPolicy

RUNTIME_SUPPORTED_NODE_TYPES = {
    "start",
    "variable_assign",
    "template_transform",
    "parameter_extractor",
    "question_classifier",
    "variable_aggregator",
    "list_operator",
    "iteration",
    "document_extractor",
    "knowledge_retrieval",
    "sub_workflow",
    "human_approval",
    "condition",
    "llm",
    "tool_call",
    "http_request",
    "answer",
    "end",
}
RUNTIME_BLOCKED_NODE_TYPES = {"unsupported"}
BLOCKED_POLICY_SOURCE_TYPES = {"code": "workflow_code_node_blocked_by_policy"}
BLOCKED_POLICY_SOURCE_TYPE_ERRORS = {
    "sub-workflow": "workflow_sub_workflow_node_blocked_by_policy",
    "sub_workflow": "workflow_sub_workflow_node_blocked_by_policy",
    "human-approval": "workflow_human_approval_node_blocked_by_policy",
    "human_approval": "workflow_human_approval_node_blocked_by_policy",
}
TERMINAL_NODE_TYPES = {"end"}
BRANCHING_NODE_TYPES = {"condition", "question_classifier"}
_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_REDACTED = "[redacted]"
_SENSITIVE_KEY_NAMES = {
    "authorization",
    "proxyauthorization",
    "proxy-authorization",
    "cookie",
    "setcookie",
    "set-cookie",
    "apikey",
    "api-key",
    "api_key",
    "xapikey",
    "x-api-key",
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "id_token",
    "idtoken",
    "token",
    "secret",
    "password",
    "credential",
    "credentials",
}
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(bearer\s+)[^\s,;]+|((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)=)[^\s,;&]+"
)
_LIST_OPERATOR_FILTER_OPERATIONS = {"filter", "where", "select", "keep", "match", "matches"}
_LIST_OPERATOR_FIND_OPERATIONS = {
    "find",
    "find_first",
    "first_match",
    "first-match",
    "first_where",
    "first-where",
}
_LIST_OPERATOR_ANY_OPERATIONS = {
    "any",
    "some",
    "has_match",
    "has-match",
    "exists_match",
    "exists-match",
}
_LIST_OPERATOR_ALL_OPERATIONS = {"all", "every"}
_LIST_OPERATOR_NONE_OPERATIONS = {"none", "not_any", "not-any", "no_match", "no-match"}
_LIST_OPERATOR_COUNT_MATCHING_OPERATIONS = {
    "count_matching",
    "count-matching",
    "count_matches",
    "count-matches",
    "count_where",
    "count-where",
}
_LIST_OPERATOR_CONDITION_OPERATIONS = (
    _LIST_OPERATOR_FILTER_OPERATIONS
    | _LIST_OPERATOR_FIND_OPERATIONS
    | _LIST_OPERATOR_ANY_OPERATIONS
    | _LIST_OPERATOR_ALL_OPERATIONS
    | _LIST_OPERATOR_NONE_OPERATIONS
    | _LIST_OPERATOR_COUNT_MATCHING_OPERATIONS
)
_LIST_OPERATOR_VALUE_KEY_OPERATIONS = {
    "pluck",
    "values",
    "extract",
    "field_values",
    "field-values",
    "field values",
}
_LIST_OPERATOR_SUPPORTED_OPERATIONS = (
    {
        "first",
        "head",
        "last",
        "tail",
        "count",
        "length",
        "len",
        "size",
        "join",
        "slice",
        "item_at",
        "item at",
        "at",
        "get",
        "index",
        "nth",
        "reverse",
        "reversed",
        "unique",
        "dedupe",
        "deduplicate",
        "distinct",
        "sort",
        "sorted",
        "order",
        "order_by",
        "order-by",
        "orderby",
        "sum",
        "total",
        "average",
        "avg",
        "mean",
        "min",
        "minimum",
        "max",
        "maximum",
    }
    | _LIST_OPERATOR_VALUE_KEY_OPERATIONS
    | _LIST_OPERATOR_CONDITION_OPERATIONS
)
DEFAULT_NODE_TIMEOUT_SECONDS = 120.0
CANCEL_CHECK_INTERVAL_SECONDS = 0.05
ToolInvoker = Callable[[str, dict[str, Any]], Awaitable[Any]]
HttpInvoker = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
CredentialSecretResolver = Callable[[str], Awaitable[str | None]]
LlmInvoker = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
KnowledgeRetriever = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
SubWorkflowInvoker = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
CancelChecker = Callable[[], Awaitable[bool]]


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow graph cannot be executed by this runtime slice."""

    def __init__(self, message: str, *, events: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.events = events or []


class WorkflowExecutionPaused(RuntimeError):  # noqa: N818
    """Raised when execution reaches a node that needs external resume input."""

    def __init__(
        self,
        message: str,
        *,
        events: list[dict[str, Any]] | None = None,
        output: dict[str, Any] | None = None,
        pause_state: dict[str, Any] | None = None,
        pending_approval: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.events = events or []
        self.output = output or {}
        self.pause_state = pause_state or {}
        self.pending_approval = pending_approval or {}


@dataclass
class WorkflowExecutionResult:
    output: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowStaticValidationResult:
    errors: list[str] = field(default_factory=list)
    reachable_node_ids: set[str] = field(default_factory=set)

    @property
    def runnable(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise WorkflowExecutionError(
                "workflow_static_validation_failed:" + ";".join(self.errors)
            )


class MinimalWorkflowExecutor:
    def __init__(
        self, *, default_node_timeout_seconds: float | None = DEFAULT_NODE_TIMEOUT_SECONDS
    ) -> None:
        self.default_node_timeout_seconds = _normalize_timeout_seconds(
            default_node_timeout_seconds,
            default=DEFAULT_NODE_TIMEOUT_SECONDS,
        )

    def execute(
        self,
        internal_model: dict[str, Any],
        *,
        workflow_input: dict[str, Any],
    ) -> WorkflowExecutionResult:
        return self._execute_sync(internal_model, workflow_input=workflow_input)

    async def execute_async(
        self,
        internal_model: dict[str, Any],
        *,
        workflow_input: dict[str, Any],
        tool_invoker: ToolInvoker | None = None,
        http_policy: HttpRequestPolicy | None = None,
        http_invoker: HttpInvoker | None = None,
        credential_secret_resolver: CredentialSecretResolver | None = None,
        llm_invoker: LlmInvoker | None = None,
        knowledge_retriever: KnowledgeRetriever | None = None,
        sub_workflow_invoker: SubWorkflowInvoker | None = None,
        available_sub_workflow_refs: set[str] | None = None,
        cancel_checker: CancelChecker | None = None,
        default_node_timeout_seconds: float | None = None,
    ) -> WorkflowExecutionResult:
        return await self._execute_async(
            internal_model,
            workflow_input=workflow_input,
            tool_invoker=tool_invoker,
            http_policy=http_policy,
            http_invoker=http_invoker,
            credential_secret_resolver=credential_secret_resolver,
            llm_invoker=llm_invoker,
            knowledge_retriever=knowledge_retriever,
            sub_workflow_invoker=sub_workflow_invoker,
            available_sub_workflow_refs=available_sub_workflow_refs,
            cancel_checker=cancel_checker,
            default_node_timeout_seconds=(
                self.default_node_timeout_seconds
                if default_node_timeout_seconds is None
                else _normalize_timeout_seconds(
                    default_node_timeout_seconds,
                    default=self.default_node_timeout_seconds,
                )
            ),
        )

    async def resume_async(
        self,
        internal_model: dict[str, Any],
        *,
        resume_state: dict[str, Any],
        approval_response: dict[str, Any],
        tool_invoker: ToolInvoker | None = None,
        http_policy: HttpRequestPolicy | None = None,
        http_invoker: HttpInvoker | None = None,
        credential_secret_resolver: CredentialSecretResolver | None = None,
        llm_invoker: LlmInvoker | None = None,
        knowledge_retriever: KnowledgeRetriever | None = None,
        sub_workflow_invoker: SubWorkflowInvoker | None = None,
        available_sub_workflow_refs: set[str] | None = None,
        cancel_checker: CancelChecker | None = None,
        default_node_timeout_seconds: float | None = None,
    ) -> WorkflowExecutionResult:
        return await self._execute_async(
            internal_model,
            workflow_input={},
            tool_invoker=tool_invoker,
            http_policy=http_policy,
            http_invoker=http_invoker,
            credential_secret_resolver=credential_secret_resolver,
            llm_invoker=llm_invoker,
            knowledge_retriever=knowledge_retriever,
            sub_workflow_invoker=sub_workflow_invoker,
            available_sub_workflow_refs=available_sub_workflow_refs,
            cancel_checker=cancel_checker,
            default_node_timeout_seconds=(
                self.default_node_timeout_seconds
                if default_node_timeout_seconds is None
                else _normalize_timeout_seconds(
                    default_node_timeout_seconds,
                    default=self.default_node_timeout_seconds,
                )
            ),
            resume_state=resume_state,
            approval_response=approval_response,
        )

    def validate_static(
        self,
        internal_model: dict[str, Any],
        *,
        available_tool_names: set[str] | None = None,
        http_policy: HttpRequestPolicy | None = None,
        llm_available: bool = False,
        knowledge_available: bool = False,
        available_sub_workflow_refs: set[str] | None = None,
    ) -> WorkflowStaticValidationResult:
        return validate_workflow_static(
            internal_model,
            available_tool_names=available_tool_names,
            http_policy=http_policy,
            llm_available=llm_available,
            knowledge_available=knowledge_available,
            available_sub_workflow_refs=available_sub_workflow_refs,
        )

    def _execute_sync(
        self,
        internal_model: dict[str, Any],
        *,
        workflow_input: dict[str, Any],
    ) -> WorkflowExecutionResult:
        graph = _as_dict(internal_model.get("graph"))
        nodes = [_as_dict(node) for node in _as_list(graph.get("nodes"))]
        edges = [_as_dict(edge) for edge in _as_list(graph.get("edges")) if edge.get("valid", True)]
        node_by_id = {str(node.get("id") or ""): node for node in nodes if node.get("id")}
        if not node_by_id:
            raise WorkflowExecutionError("workflow_has_no_nodes")

        unsupported = [
            node
            for node in nodes
            if str(node.get("type") or "") in RUNTIME_BLOCKED_NODE_TYPES
            or not bool(node.get("supported", True))
        ]
        if unsupported:
            raise WorkflowExecutionError(_runtime_blocked_nodes_error(unsupported))

        start_node = _select_start_node(nodes)
        outgoing = _outgoing_edges(edges)
        unreachable_errors = _unreachable_node_errors(
            nodes,
            reachable=_reachable_node_ids_from_start(
                node_by_id,
                outgoing,
                start_id=str(start_node.get("id") or ""),
            ),
        )
        if unreachable_errors:
            raise WorkflowExecutionError(
                "workflow_static_validation_failed:" + ";".join(unreachable_errors)
            )
        variables: dict[str, Any] = _initial_workflow_variables(
            workflow_input,
            start_node=start_node,
        )
        visited: set[str] = set()
        events: list[dict[str, Any]] = []
        current: dict[str, Any] | None = start_node
        output: dict[str, Any] = {}

        while current is not None:
            node_id = str(current.get("id") or "")
            node_type = str(current.get("type") or "")
            if node_id in visited:
                raise WorkflowExecutionError(f"workflow_cycle_detected:{node_id}")
            visited.add(node_id)
            if node_type not in RUNTIME_SUPPORTED_NODE_TYPES:
                raise WorkflowExecutionError(
                    f"workflow_node_type_not_executable:{node_id}:{node_type}"
                )
            if node_type == "tool_call":
                raise WorkflowExecutionError(
                    f"workflow_tool_call_requires_async_executor:{node_id}"
                )
            if node_type == "http_request":
                raise WorkflowExecutionError(
                    f"workflow_http_request_requires_async_executor:{node_id}"
                )
            if node_type == "llm":
                raise WorkflowExecutionError(f"workflow_llm_requires_async_executor:{node_id}")
            if node_type == "parameter_extractor":
                raise WorkflowExecutionError(
                    f"workflow_parameter_extractor_requires_async_executor:{node_id}"
                )
            if node_type == "question_classifier":
                raise WorkflowExecutionError(
                    f"workflow_question_classifier_requires_async_executor:{node_id}"
                )

            node_started_at = perf_counter()
            events.append(
                _node_event("node_started", current, payload={"title": current.get("title")})
            )
            try:
                if node_type == "start":
                    _validate_start_required_inputs(current, variables)
                    _validate_start_input_contract(current, variables)
                node_output = _execute_node(current, variables)
                if node_output:
                    variables.update(node_output)
                if node_type == "answer":
                    output = {"answer": str(node_output.get("answer", ""))}
                elif node_type == "end":
                    output = node_output or output or dict(variables)

                events.append(
                    _node_event(
                        "node_finished",
                        current,
                        payload={"output": node_output},
                        duration_ms=_elapsed_ms(node_started_at),
                    )
                )

                next_edges = _select_next_edges(
                    current,
                    outgoing.get(node_id, []),
                    node_output=node_output,
                )
                if not next_edges or node_type == "end":
                    current = None
                    continue
                if len(next_edges) > 1:
                    raise WorkflowExecutionError(f"workflow_branching_not_supported:{node_id}")
                target_id = str(next_edges[0].get("target") or "")
                current = node_by_id.get(target_id)
                if current is None:
                    raise WorkflowExecutionError(
                        f"workflow_edge_target_missing:{node_id}->{target_id}"
                    )
            except WorkflowExecutionError as exc:
                raise _with_events(
                    exc,
                    _events_with_node_failed(
                        events,
                        current,
                        error=str(exc),
                        duration_ms=_elapsed_ms(node_started_at),
                    ),
                ) from exc

        return WorkflowExecutionResult(output=output or dict(variables), events=events)

    async def _execute_async(
        self,
        internal_model: dict[str, Any],
        *,
        workflow_input: dict[str, Any],
        tool_invoker: ToolInvoker | None,
        http_policy: HttpRequestPolicy | None,
        http_invoker: HttpInvoker | None,
        credential_secret_resolver: CredentialSecretResolver | None,
        llm_invoker: LlmInvoker | None,
        knowledge_retriever: KnowledgeRetriever | None,
        sub_workflow_invoker: SubWorkflowInvoker | None,
        available_sub_workflow_refs: set[str] | None,
        cancel_checker: CancelChecker | None,
        default_node_timeout_seconds: float | None,
        resume_state: dict[str, Any] | None = None,
        approval_response: dict[str, Any] | None = None,
    ) -> WorkflowExecutionResult:
        graph = _as_dict(internal_model.get("graph"))
        nodes = [_as_dict(node) for node in _as_list(graph.get("nodes"))]
        edges = [_as_dict(edge) for edge in _as_list(graph.get("edges")) if edge.get("valid", True)]
        node_by_id = {str(node.get("id") or ""): node for node in nodes if node.get("id")}
        if not node_by_id:
            raise WorkflowExecutionError("workflow_has_no_nodes")

        unsupported = [
            node
            for node in nodes
            if str(node.get("type") or "") in RUNTIME_BLOCKED_NODE_TYPES
            or not bool(node.get("supported", True))
        ]
        if unsupported:
            raise WorkflowExecutionError(_runtime_blocked_nodes_error(unsupported))

        outgoing = _outgoing_edges(edges)
        start_node = _select_start_node(nodes)
        unreachable_errors = _unreachable_node_errors(
            nodes,
            reachable=_reachable_node_ids_from_start(
                node_by_id,
                outgoing,
                start_id=str(start_node.get("id") or ""),
            ),
        )
        if unreachable_errors:
            raise WorkflowExecutionError(
                "workflow_static_validation_failed:" + ";".join(unreachable_errors)
            )
        if resume_state:
            variables: dict[str, Any] = dict(_as_dict(resume_state.get("variables")))
            visited: set[str] = {
                str(item) for item in _as_list(resume_state.get("visited_node_ids"))
            }
            events: list[dict[str, Any]] = []
            output: dict[str, Any] = dict(_as_dict(resume_state.get("output")))
            current = _resume_after_human_approval(
                resume_state,
                approval_response or {},
                node_by_id=node_by_id,
                outgoing=outgoing,
                variables=variables,
                output=output,
                events=events,
            )
        else:
            variables = _initial_workflow_variables(
                workflow_input,
                start_node=start_node,
            )
            visited = set()
            events = []
            current = start_node
            output = {}

        while current is not None:
            if await _is_cancelled(cancel_checker):
                return WorkflowExecutionResult(output=output or dict(variables), events=events)

            node_id = str(current.get("id") or "")
            node_type = str(current.get("type") or "")
            if node_id in visited:
                raise WorkflowExecutionError(f"workflow_cycle_detected:{node_id}")
            visited.add(node_id)
            if node_type not in RUNTIME_SUPPORTED_NODE_TYPES:
                raise WorkflowExecutionError(
                    f"workflow_node_type_not_executable:{node_id}:{node_type}"
                )

            node_started_at = perf_counter()
            events.append(
                _node_event("node_started", current, payload={"title": current.get("title")})
            )
            try:
                if node_type == "start":
                    _validate_start_required_inputs(current, variables)
                    _validate_start_input_contract(current, variables)
                if node_type == "human_approval":
                    raise _human_approval_pause(
                        current,
                        variables=variables,
                        visited_node_ids=visited,
                        output=output,
                        events=events,
                    )
                node_output = await _execute_node_async(
                    current,
                    variables,
                    tool_invoker=tool_invoker,
                    http_policy=http_policy,
                    http_invoker=http_invoker,
                    credential_secret_resolver=credential_secret_resolver,
                    llm_invoker=llm_invoker,
                    knowledge_retriever=knowledge_retriever,
                    sub_workflow_invoker=sub_workflow_invoker,
                    cancel_checker=cancel_checker,
                    default_node_timeout_seconds=default_node_timeout_seconds,
                )
                if node_output:
                    variables.update(node_output)
                if node_type == "answer":
                    output = {"answer": str(node_output.get("answer", ""))}
                elif node_type == "end":
                    output = node_output or output or dict(variables)

                events.append(
                    _node_event(
                        "node_finished",
                        current,
                        payload={"output": node_output},
                        duration_ms=_elapsed_ms(node_started_at),
                    )
                )

                if await _is_cancelled(cancel_checker):
                    return WorkflowExecutionResult(output=output or dict(variables), events=events)

                next_edges = _select_next_edges(
                    current,
                    outgoing.get(node_id, []),
                    node_output=node_output,
                )
                if not next_edges or node_type == "end":
                    current = None
                    continue
                if len(next_edges) > 1:
                    raise WorkflowExecutionError(f"workflow_branching_not_supported:{node_id}")
                target_id = str(next_edges[0].get("target") or "")
                current = node_by_id.get(target_id)
                if current is None:
                    raise WorkflowExecutionError(
                        f"workflow_edge_target_missing:{node_id}->{target_id}"
                    )
            except WorkflowExecutionPaused:
                raise
            except WorkflowExecutionError as exc:
                raise _with_events(
                    exc,
                    _events_with_node_failed(
                        events,
                        current,
                        error=str(exc),
                        duration_ms=_elapsed_ms(node_started_at),
                    ),
                ) from exc

        return WorkflowExecutionResult(output=output or dict(variables), events=events)


async def _is_cancelled(cancel_checker: CancelChecker | None) -> bool:
    if cancel_checker is None:
        return False
    return bool(await cancel_checker())


async def _await_with_runtime_guard(
    awaitable: Awaitable[Any],
    *,
    node_id: str,
    node_type: str,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> Any:
    task = asyncio.ensure_future(awaitable)
    started_at = perf_counter()
    try:
        await asyncio.sleep(0)
        while not task.done():
            if await _is_cancelled(cancel_checker):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise WorkflowExecutionError(f"workflow_node_cancelled:{node_id}:{node_type}")
            if timeout_seconds is not None and perf_counter() - started_at >= timeout_seconds:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise WorkflowExecutionError(f"workflow_node_timeout:{node_id}:{node_type}")
            remaining = (
                None
                if timeout_seconds is None
                else max(timeout_seconds - (perf_counter() - started_at), 0.0)
            )
            wait_for = (
                CANCEL_CHECK_INTERVAL_SECONDS
                if remaining is None
                else min(CANCEL_CHECK_INTERVAL_SECONDS, remaining)
            )
            done, _ = await asyncio.wait({task}, timeout=wait_for)
            if done:
                break
        return await task
    except asyncio.CancelledError:
        task.cancel()
        raise


def _select_start_node(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    start_nodes = [node for node in nodes if node.get("type") == "start"]
    if not start_nodes:
        raise WorkflowExecutionError("workflow_missing_start_node")
    if len(start_nodes) > 1:
        raise WorkflowExecutionError("workflow_has_multiple_start_nodes")
    return start_nodes[0]


def _events_with_node_failed(
    events: list[dict[str, Any]],
    node: dict[str, Any] | None,
    *,
    error: str,
    duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    failed_node = node or {"id": "unknown", "type": "unknown", "title": "Unknown node"}
    return [
        *events,
        _node_event(
            "node_failed",
            failed_node,
            payload={"title": failed_node.get("title"), "error": error},
            duration_ms=duration_ms,
        ),
    ]


def _with_events(
    exc: WorkflowExecutionError,
    events: list[dict[str, Any]],
) -> WorkflowExecutionError:
    return WorkflowExecutionError(str(exc), events=events)


def _node_event(
    event_type: str,
    node: dict[str, Any],
    *,
    payload: dict[str, Any],
    duration_ms: int | None = None,
) -> dict[str, Any]:
    sanitized_payload = _sanitize_event_payload(payload)
    if duration_ms is not None:
        sanitized_payload["duration_ms"] = duration_ms
    return {
        "event_type": event_type,
        "node_id": str(node.get("id") or ""),
        "node_type": str(node.get("type") or ""),
        "payload": sanitized_payload,
    }


def _elapsed_ms(started_at: float) -> int:
    return max(int((perf_counter() - started_at) * 1000), 0)


def _sanitize_event_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _REDACTED if _is_sensitive_key(str(key)) else _sanitize_event_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_event_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_event_payload(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_TEXT_PATTERN.sub(_redact_sensitive_text_match, value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("_", "").replace("-", "")
    return normalized in _SENSITIVE_KEY_NAMES


def _redact_sensitive_text_match(match: re.Match[str]) -> str:
    prefix = match.group(1) or match.group(2) or ""
    return f"{prefix}{_REDACTED}"


def validate_workflow_static(
    internal_model: dict[str, Any],
    *,
    available_tool_names: set[str] | None = None,
    http_policy: HttpRequestPolicy | None = None,
    llm_available: bool = False,
    knowledge_available: bool = False,
    available_sub_workflow_refs: set[str] | None = None,
) -> WorkflowStaticValidationResult:
    graph = _as_dict(internal_model.get("graph"))
    nodes = [_as_dict(node) for node in _as_list(graph.get("nodes"))]
    all_edges = [_as_dict(edge) for edge in _as_list(graph.get("edges"))]
    edges = [edge for edge in all_edges if edge.get("valid", True)]
    node_by_id = {str(node.get("id") or ""): node for node in nodes if node.get("id")}
    errors: list[str] = []
    if not node_by_id:
        return WorkflowStaticValidationResult(
            errors=["workflow_has_no_nodes"], reachable_node_ids=set()
        )

    start_nodes = [node for node in nodes if node.get("type") == "start"]
    if not start_nodes:
        return WorkflowStaticValidationResult(
            errors=["workflow_missing_start_node"], reachable_node_ids=set()
        )
    if len(start_nodes) > 1:
        errors.append("workflow_has_multiple_start_nodes")
    start_node = start_nodes[0]
    start_id = str(start_node.get("id") or "")
    errors.extend(_workflow_boundary_edge_errors(all_edges, node_by_id=node_by_id))
    outgoing = _outgoing_edges(edges)

    reachable: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            errors.append(f"workflow_cycle_detected:{node_id}")
            return
        node = node_by_id.get(node_id)
        if node is None:
            errors.append(f"workflow_node_missing:{node_id}")
            return
        if node_id in reachable:
            return

        visiting.add(node_id)
        reachable.add(node_id)
        node_type = str(node.get("type") or "")
        if node_type in RUNTIME_BLOCKED_NODE_TYPES or not bool(node.get("supported", True)):
            errors.append(_runtime_blocked_node_error(node))
        elif node_type not in RUNTIME_SUPPORTED_NODE_TYPES:
            errors.append(f"workflow_node_type_not_executable:{node_id}:{node_type}")

        if node_type == "tool_call":
            tool_name = _tool_name_from_data(_as_dict(node.get("data")))
            if not tool_name:
                errors.append(f"workflow_tool_name_missing:{node_id}")
            elif available_tool_names is not None and tool_name not in available_tool_names:
                errors.append(f"workflow_tool_not_available:{tool_name}")

        if node_type in {"llm", "parameter_extractor", "question_classifier"}:
            try:
                _validate_llm_backed_node_static(
                    _as_dict(node.get("data")),
                    node_type=node_type,
                    llm_available=llm_available,
                )
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_{node_type}_node_not_allowed:{node_id}:{exc}")

        if node_type == "knowledge_retrieval":
            try:
                _validate_knowledge_retrieval_static(
                    _as_dict(node.get("data")),
                    knowledge_available=knowledge_available,
                )
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_knowledge_retrieval_node_not_allowed:{node_id}:{exc}")

        if node_type == "sub_workflow":
            try:
                _validate_sub_workflow_static(
                    _as_dict(node.get("data")),
                    available_sub_workflow_refs=available_sub_workflow_refs,
                )
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_sub_workflow_node_not_allowed:{node_id}:{exc}")

        if node_type == "template_transform":
            data = _as_dict(node.get("data"))
            if not _template_transform_template_from_data(data):
                errors.append(f"workflow_template_transform_template_missing:{node_id}")

        if node_type == "variable_aggregator" and not _aggregator_selectors_from_data(
            _as_dict(node.get("data"))
        ):
            errors.append(f"workflow_variable_aggregator_selectors_missing:{node_id}")

        if node_type == "list_operator":
            try:
                _validate_list_operator_static(_as_dict(node.get("data")))
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_list_operator_node_not_allowed:{node_id}:{exc}")

        if node_type == "iteration":
            try:
                _validate_iteration_static(_as_dict(node.get("data")))
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_iteration_node_not_allowed:{node_id}:{exc}")

        if node_type == "document_extractor":
            try:
                _validate_document_extractor_static(_as_dict(node.get("data")))
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_document_extractor_node_not_allowed:{node_id}:{exc}")

        if node_type == "http_request":
            try:
                _validate_http_node_static(_as_dict(node.get("data")), http_policy=http_policy)
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_http_node_not_allowed:{node_id}:{exc}")

        next_edges = outgoing.get(node_id, [])
        if node_type in TERMINAL_NODE_TYPES:
            visiting.remove(node_id)
            return
        if node_type not in BRANCHING_NODE_TYPES and len(next_edges) > 1:
            errors.append(f"workflow_branching_not_supported:{node_id}")
        if node_type == "condition" and len(next_edges) > 1:
            handles = {str(edge.get("source_handle") or "").lower() for edge in next_edges}
            if not handles.intersection({"false", "else", "default", "fallback"}):
                errors.append(f"workflow_condition_default_branch_missing:{node_id}")
        if node_type == "question_classifier":
            try:
                classes = _question_classifier_classes_from_data(_as_dict(node.get("data")))
            except WorkflowExecutionError as exc:
                errors.append(f"workflow_question_classifier_node_not_allowed:{node_id}:{exc}")
                classes = []
            if len(next_edges) > 1:
                handles = {str(edge.get("source_handle") or "").lower() for edge in next_edges}
                class_handles = {_normalize_classifier_label(option["id"]) for option in classes}
                class_handles.update(
                    _normalize_classifier_label(option["name"]) for option in classes
                )
                if not handles.intersection(class_handles):
                    errors.append(f"workflow_question_classifier_branch_missing:{node_id}")
                if not handles.intersection({"default", "fallback", "else"}):
                    errors.append(f"workflow_question_classifier_default_branch_missing:{node_id}")

        for edge in next_edges:
            target_id = str(edge.get("target") or "")
            if not target_id or target_id not in node_by_id:
                errors.append(f"workflow_edge_target_missing:{node_id}->{target_id}")
                continue
            visit(target_id)
        visiting.remove(node_id)

    visit(start_id)
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id and node_id not in reachable:
            errors.append(f"workflow_unreachable_node:{node_id}")
    return WorkflowStaticValidationResult(
        errors=_dedupe_preserve_order(errors),
        reachable_node_ids=reachable,
    )


def _reachable_node_ids_from_start(
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    *,
    start_id: str,
) -> set[str]:
    reachable: set[str] = set()
    stack = [start_id] if start_id else []
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        node = node_by_id.get(node_id)
        if node is None:
            continue
        reachable.add(node_id)
        if str(node.get("type") or "") in TERMINAL_NODE_TYPES:
            continue
        for edge in outgoing.get(node_id, []):
            target_id = str(edge.get("target") or "")
            if target_id and target_id not in reachable:
                stack.append(target_id)
    return reachable


def _unreachable_node_errors(nodes: list[dict[str, Any]], *, reachable: set[str]) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id and node_id not in reachable:
            errors.append(f"workflow_unreachable_node:{node_id}")
    return errors


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _workflow_boundary_edge_errors(
    edges: list[dict[str, Any]],
    *,
    node_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for index, edge in enumerate(edges):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        source_node = node_by_id.get(source)
        target_node = node_by_id.get(target)
        if source_node is None or target_node is None:
            continue
        edge_id = str(edge.get("id") or f"edge_{index + 1}")
        if str(target_node.get("type") or "") == "start":
            errors.append(f"workflow_boundary_edge_targets_entry:{edge_id}:{source}->{target}")
            continue
        source_type = str(source_node.get("type") or "")
        target_type = str(target_node.get("type") or "")
        if source_type == "end" or (source_type == "answer" and target_type != "end"):
            errors.append(f"workflow_boundary_edge_starts_from_exit:{edge_id}:{source}->{target}")
    return errors


def _runtime_blocked_nodes_error(nodes: list[dict[str, Any]]) -> str:
    return "workflow_contains_runtime_blocked_nodes:" + ";".join(
        _runtime_blocked_node_error(node) for node in nodes
    )


def _runtime_blocked_node_error(node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    source_type = str(node.get("source_type") or "").strip().lower()
    if source_type in BLOCKED_POLICY_SOURCE_TYPES:
        return f"{BLOCKED_POLICY_SOURCE_TYPES[source_type]}:{node_id}"
    if source_type in BLOCKED_POLICY_SOURCE_TYPE_ERRORS:
        return f"{BLOCKED_POLICY_SOURCE_TYPE_ERRORS[source_type]}:{node_id}"
    node_type = str(node.get("type") or "")
    reason = _as_dict(node.get("metadata")).get("unsupported_reason") or "unsupported"
    return f"workflow_contains_runtime_unsupported_node:{node_id}:{node_type}:{reason}"


def _outgoing_edges(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        source = str(edge.get("source") or "")
        if source:
            outgoing.setdefault(source, []).append(edge)
    return outgoing


def _select_next_edges(
    node: dict[str, Any],
    edges: list[dict[str, Any]],
    *,
    node_output: dict[str, Any],
) -> list[dict[str, Any]]:
    if node.get("type") not in BRANCHING_NODE_TYPES or len(edges) <= 1:
        return edges
    branch = str(node_output.get("branch") or "").lower()
    normalized_branch = _normalize_classifier_label(branch)
    fallback: dict[str, Any] | None = None
    for edge in edges:
        handle = str(edge.get("source_handle") or "").lower()
        normalized_handle = _normalize_classifier_label(handle)
        if handle == branch or normalized_handle == normalized_branch:
            return [edge]
        if handle in {"false", "else", "default", "fallback"}:
            fallback = edge
    if fallback is not None:
        return [fallback]
    node_type = str(node.get("type") or "condition")
    raise WorkflowExecutionError(f"workflow_{node_type}_branch_missing:{node.get('id')}:{branch}")


def _execute_node(node: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    node_type = str(node.get("type") or "")
    data = _as_dict(node.get("data"))
    if node_type == "start":
        return {}
    if node_type == "variable_assign":
        return _execute_variable_assign(data, variables)
    if node_type == "template_transform":
        return _execute_template_transform(data, variables)
    if node_type == "variable_aggregator":
        return _execute_variable_aggregator(data, variables)
    if node_type == "list_operator":
        return _execute_list_operator(data, variables)
    if node_type == "iteration":
        return _execute_iteration(data, variables)
    if node_type == "document_extractor":
        return _execute_document_extractor(data, variables)
    if node_type == "knowledge_retrieval":
        raise WorkflowExecutionError(
            f"workflow_knowledge_retrieval_requires_async_executor:{node.get('id')}"
        )
    if node_type == "sub_workflow":
        raise WorkflowExecutionError(
            f"workflow_sub_workflow_requires_async_executor:{node.get('id')}"
        )
    if node_type == "human_approval":
        raise WorkflowExecutionError(
            f"workflow_human_approval_requires_async_executor:{node.get('id')}"
        )
    if node_type == "condition":
        return _execute_condition(data, variables)
    if node_type == "tool_call":
        raise WorkflowExecutionError(f"workflow_tool_call_requires_async_executor:{node.get('id')}")
    if node_type == "parameter_extractor":
        raise WorkflowExecutionError(
            f"workflow_parameter_extractor_requires_async_executor:{node.get('id')}"
        )
    if node_type == "question_classifier":
        raise WorkflowExecutionError(
            f"workflow_question_classifier_requires_async_executor:{node.get('id')}"
        )
    if node_type == "answer":
        template = _answer_template_from_data(data)
        return {"answer": _render_template(template, variables)}
    if node_type == "end":
        return _execute_end(data, variables)
    raise WorkflowExecutionError(f"workflow_node_type_not_executable:{node.get('id')}:{node_type}")


def _answer_template_from_data(data: dict[str, Any]) -> str:
    for key in ("answer", "text", "content", "template", "message", "value"):
        template = _text_template_to_string(data.get(key))
        if template:
            return template
    return ""


async def _execute_node_async(
    node: dict[str, Any],
    variables: dict[str, Any],
    *,
    tool_invoker: ToolInvoker | None,
    http_policy: HttpRequestPolicy | None,
    http_invoker: HttpInvoker | None,
    credential_secret_resolver: CredentialSecretResolver | None,
    llm_invoker: LlmInvoker | None,
    knowledge_retriever: KnowledgeRetriever | None,
    sub_workflow_invoker: SubWorkflowInvoker | None,
    cancel_checker: CancelChecker | None,
    default_node_timeout_seconds: float | None,
) -> dict[str, Any]:
    node_type = str(node.get("type") or "")
    data = _as_dict(node.get("data"))
    node_id = str(node.get("id") or node_type or "node")
    timeout_seconds = _node_timeout_seconds(
        data,
        None if node_type == "http_request" else default_node_timeout_seconds,
    )
    if node_type == "llm":
        return await _execute_llm(
            data,
            variables,
            node_id=node_id,
            llm_invoker=llm_invoker,
            credential_secret_resolver=credential_secret_resolver,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "parameter_extractor":
        return await _execute_parameter_extractor(
            data,
            variables,
            node_id=node_id,
            llm_invoker=llm_invoker,
            credential_secret_resolver=credential_secret_resolver,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "question_classifier":
        return await _execute_question_classifier(
            data,
            variables,
            node_id=node_id,
            llm_invoker=llm_invoker,
            credential_secret_resolver=credential_secret_resolver,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "tool_call":
        return await _execute_tool_call(
            data,
            variables,
            tool_invoker,
            node_id=node_id,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "knowledge_retrieval":
        return await _execute_knowledge_retrieval(
            data,
            variables,
            node_id=node_id,
            knowledge_retriever=knowledge_retriever,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "sub_workflow":
        return await _execute_sub_workflow(
            data,
            variables,
            node_id=node_id,
            sub_workflow_invoker=sub_workflow_invoker,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    if node_type == "http_request":
        return await _execute_http_request(
            data,
            variables,
            node_id=node_id,
            http_policy=http_policy,
            http_invoker=http_invoker,
            credential_secret_resolver=credential_secret_resolver,
            timeout_seconds=timeout_seconds,
            cancel_checker=cancel_checker,
        )
    return _execute_node(node, variables)


def _human_approval_pause(
    node: dict[str, Any],
    *,
    variables: dict[str, Any],
    visited_node_ids: set[str],
    output: dict[str, Any],
    events: list[dict[str, Any]],
) -> WorkflowExecutionPaused:
    data = _as_dict(node.get("data"))
    pending = _human_approval_pending_payload(node, data, variables)
    pause_state = {
        "kind": "human_approval",
        "node_id": str(node.get("id") or ""),
        "variables": dict(variables),
        "visited_node_ids": sorted(visited_node_ids),
        "output": dict(output),
    }
    pause_events = [
        *events,
        _node_event("human_approval_required", node, payload=pending),
    ]
    return WorkflowExecutionPaused(
        f"workflow_human_approval_paused:{node.get('id')}",
        events=pause_events,
        output=output or dict(variables),
        pause_state=pause_state,
        pending_approval=pending,
    )


def _resume_after_human_approval(
    resume_state: dict[str, Any],
    approval_response: dict[str, Any],
    *,
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    variables: dict[str, Any],
    output: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if str(resume_state.get("kind") or "") != "human_approval":
        raise WorkflowExecutionError("workflow_resume_state_not_supported")
    node_id = str(resume_state.get("node_id") or "")
    node = node_by_id.get(node_id)
    if node is None or node.get("type") != "human_approval":
        raise WorkflowExecutionError(f"workflow_resume_node_missing:{node_id}")
    node_started_at = perf_counter()
    node_output = _human_approval_output(_as_dict(node.get("data")), approval_response)
    events.append(_node_event("human_approval_resumed", node, payload=node_output))
    if not bool(node_output.get("approved")):
        error = f"workflow_human_approval_rejected:{node_id}"
        raise WorkflowExecutionError(
            error,
            events=_events_with_node_failed(
                events,
                node,
                error=error,
                duration_ms=_elapsed_ms(node_started_at),
            ),
        )
    variables.update(node_output)
    events.append(
        _node_event(
            "node_finished",
            node,
            payload={"output": node_output},
            duration_ms=_elapsed_ms(node_started_at),
        )
    )
    next_edges = _select_next_edges(node, outgoing.get(node_id, []), node_output=node_output)
    if not next_edges:
        return None
    if len(next_edges) > 1:
        raise WorkflowExecutionError(f"workflow_branching_not_supported:{node_id}")
    target_id = str(next_edges[0].get("target") or "")
    current = node_by_id.get(target_id)
    if current is None:
        raise WorkflowExecutionError(f"workflow_edge_target_missing:{node_id}->{target_id}")
    return current


def _human_approval_pending_payload(
    node: dict[str, Any],
    data: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    instructions = _first_string(
        data,
        "instructions",
        "instruction",
        "prompt",
        "description",
        "message",
    )
    assignee = _first_string(data, "assignee", "assignee_id", "assigneeId", "role", "owner")
    return {
        "node_id": str(node.get("id") or ""),
        "title": str(node.get("title") or data.get("title") or node.get("id") or "Approval"),
        "instructions": _render_template(instructions, variables) if instructions else "",
        "assignee": assignee,
        "output_key": _human_approval_output_key(data),
    }


def _human_approval_output(
    data: dict[str, Any], approval_response: dict[str, Any]
) -> dict[str, Any]:
    approved = bool(approval_response.get("approved", True))
    response_payload = approval_response.get("response")
    if not isinstance(response_payload, dict):
        response_payload = {}
    values = approval_response.get("values")
    if isinstance(values, dict):
        response_payload = {**response_payload, **values}
    comment = approval_response.get("comment")
    approval = {
        "approved": approved,
        "response": response_payload,
        "comment": "" if comment is None else str(comment),
    }
    return {_human_approval_output_key(data): approval, "approved": approved}


def _human_approval_output_key(data: dict[str, Any]) -> str:
    return _first_string(data, "output_key", "outputKey", "variable", "name") or "approval"


def _execute_variable_assign(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    for item_data in _assignment_items_from_data(data):
        name = _assignment_target_name(item_data)
        if not name:
            continue
        assignments[name] = _resolve_assignment_value(item_data, variables)
    direct = _as_dict(data.get("assignments"))
    for name, value in direct.items():
        assignments[str(name)] = _resolve_assignment_direct_value(value, variables)
    return assignments


def _assignment_items_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in (
        "variables",
        "items",
        "assignments",
        "variable_assignments",
        "variableAssignments",
        "assignment_items",
        "assignmentItems",
    ):
        value = data.get(key)
        if key == "assignments" and isinstance(value, dict):
            continue
        items.extend(_assignment_items(value))
    return items


def _assignment_target_name(item_data: dict[str, Any]) -> str:
    for key in (
        "variable",
        "name",
        "key",
        "output_key",
        "outputKey",
        "target_variable",
        "targetVariable",
        "assigned_variable",
        "assignedVariable",
        "assigned_variable_selector",
        "assignedVariableSelector",
        "variable_selector",
        "variableSelector",
        "target",
        "selector",
    ):
        value = item_data.get(key)
        if value in (None, "", [], {}):
            continue
        return _selector_to_key(value) if isinstance(value, list) else str(value)
    return ""


def _assignment_items(raw_items: Any) -> list[dict[str, Any]]:
    if isinstance(raw_items, list):
        return [_as_dict(item) for item in raw_items if isinstance(item, dict)]
    if isinstance(raw_items, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_items.items():
            if isinstance(raw_item, dict):
                item = dict(raw_item)
            else:
                item = {"value": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _resolve_assignment_value(item_data: dict[str, Any], variables: dict[str, Any]) -> Any:
    if "value" in item_data:
        return _resolve_value(item_data.get("value"), variables)
    selector = (
        item_data.get("value_selector")
        or item_data.get("valueSelector")
        or item_data.get("source_selector")
        or item_data.get("sourceSelector")
        or item_data.get("input_selector")
        or item_data.get("inputSelector")
    )
    if selector is not None:
        return _resolve_path(variables, _selector_to_key(selector))
    return None


def _resolve_assignment_direct_value(value: Any, variables: dict[str, Any]) -> Any:
    value_data = _as_dict(value)
    if value_data:
        selector = (
            value_data.get("value_selector")
            or value_data.get("valueSelector")
            or value_data.get("source_selector")
            or value_data.get("sourceSelector")
            or value_data.get("input_selector")
            or value_data.get("inputSelector")
        )
        if selector is not None and "value" not in value_data:
            return _resolve_path(variables, _selector_to_key(selector))
    return _resolve_value(value, variables)


def _execute_template_transform(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    template = _template_transform_template_from_data(data)
    if not template:
        raise WorkflowExecutionError("workflow_template_transform_template_missing")
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or "result"
    )
    return {output_key: _render_template(template, variables)}


def _template_transform_template_from_data(data: dict[str, Any]) -> str:
    for key in (
        "template",
        "template_string",
        "templateString",
        "prompt_template",
        "promptTemplate",
        "text",
        "content",
        "value",
    ):
        template = _text_template_to_string(data.get(key))
        if template:
            return template
    return ""


def _text_template_to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text_template_part_to_string(item) for item in value)
    if isinstance(value, dict):
        return _text_template_part_to_string(value)
    return ""


def _text_template_part_to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    part_type = str(value.get("type") or value.get("kind") or "").strip().lower()
    if part_type and part_type not in {"text", "input_text", "paragraph", "markdown", "template"}:
        return ""
    for key in ("text", "content", "template", "prompt", "message", "value"):
        if key in value:
            return _text_template_to_string(value.get(key))
    if part_type in {"text", "input_text", "paragraph", "markdown", "template"} and isinstance(
        value.get("data"), str
    ):
        return str(value.get("data"))
    return ""


def _execute_variable_aggregator(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    selectors = _aggregator_selectors_from_data(data)
    if not selectors:
        raise WorkflowExecutionError("workflow_variable_aggregator_selectors_missing")
    mode = (
        str(
            data.get("mode")
            or data.get("strategy")
            or data.get("output_type")
            or data.get("outputType")
            or data.get("type")
            or "first_non_empty"
        )
        .strip()
        .lower()
    )
    values = [_resolve_path(variables, selector) for selector in selectors]
    if mode in {"array", "list", "all"}:
        aggregated: Any = [value for value in values if value is not None]
    else:
        aggregated = None
        for value in values:
            if value not in (None, "", [], {}):
                aggregated = value
                break
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or "result"
    )
    return {output_key: aggregated}


def _aggregator_selectors_from_data(data: dict[str, Any]) -> list[str]:
    selectors: list[str] = []
    for key in (
        "variables",
        "items",
        "selectors",
        "input_variables",
        "inputVariables",
        "variable_groups",
        "variableGroups",
        "groups",
    ):
        selectors.extend(_aggregator_selectors_from_value(data.get(key)))
    return _dedupe_preserve_order([selector for selector in selectors if selector])


def _aggregator_selectors_from_value(value: Any, *, list_as_selector: bool = False) -> list[str]:
    if isinstance(value, list):
        if list_as_selector:
            selector = _selector_to_key(value)
            return [selector] if selector else []
        selectors: list[str] = []
        for item in value:
            selectors.extend(_aggregator_selectors_from_value(item))
        return selectors
    if isinstance(value, dict):
        descriptor_selector = (
            value.get("variable_selector")
            or value.get("variableSelector")
            or value.get("value_selector")
            or value.get("valueSelector")
            or value.get("input_selector")
            or value.get("inputSelector")
            or value.get("source_selector")
            or value.get("sourceSelector")
            or value.get("selector")
            or value.get("variable")
            or value.get("name")
        )
        if descriptor_selector is not None:
            return [_selector_to_key(descriptor_selector)]
        for wrapper_key in (
            "value",
            "values",
            "variables",
            "selectors",
            "items",
            "children",
            "group",
        ):
            if wrapper_key in value:
                return _aggregator_selectors_from_value(value.get(wrapper_key))
        nested_selectors: list[str] = []
        for raw_selector in value.values():
            nested_selectors.extend(
                _aggregator_selectors_from_value(raw_selector, list_as_selector=True)
            )
        return nested_selectors
    selector = _selector_to_key(value)
    return [selector] if selector else []


def _execute_list_operator(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    selector = _list_operator_selector_from_data(data)
    if not selector:
        raise WorkflowExecutionError("workflow_list_operator_selector_missing")
    value = _resolve_path(variables, selector)
    if value is None:
        items: list[Any] = []
    elif isinstance(value, list):
        items = value
    else:
        raise WorkflowExecutionError("workflow_list_operator_input_not_list")

    operation = (
        str(data.get("operation") or data.get("op") or data.get("operator") or "first")
        .strip()
        .lower()
    )
    if operation in {"first", "head"}:
        result: Any = items[0] if items else None
    elif operation in {"last", "tail"}:
        result = items[-1] if items else None
    elif operation in {"count", "length", "len", "size"}:
        result = len(items)
    elif operation == "join":
        separator = str(data.get("separator") or data.get("delimiter") or ",")
        result = separator.join(str(item) for item in items)
    elif operation == "slice":
        start = _list_operator_int_param(data, variables, "start", "offset", default=0)
        if start is None:
            start = 0
        end = _list_operator_int_param(data, variables, "end", "limit", default=None)
        if _list_operator_param_present(data, "limit") and not _list_operator_param_present(
            data, "end"
        ):
            limit = _list_operator_int_param(data, variables, "limit", default=None)
            end = None if limit is None else start + limit
        result = items[start:end]
    elif operation in {"item_at", "item at", "at", "get", "index", "nth"}:
        index = _list_operator_int_param(
            data, variables, "index", "item_index", "itemIndex", default=0
        )
        result = items[index] if index is not None and -len(items) <= index < len(items) else None
    elif operation in {"reverse", "reversed"}:
        result = list(reversed(items))
    elif operation in {"unique", "dedupe", "deduplicate", "distinct"}:
        result = _dedupe_list_items(items)
    elif operation in _LIST_OPERATOR_VALUE_KEY_OPERATIONS:
        result = _pluck_list_items(items, data, variables)
    elif operation in _LIST_OPERATOR_CONDITION_OPERATIONS:
        matched_items = _filter_list_items(items, data, variables)
        if operation in _LIST_OPERATOR_FILTER_OPERATIONS:
            result = matched_items
        elif operation in _LIST_OPERATOR_FIND_OPERATIONS:
            result = matched_items[0] if matched_items else None
        elif operation in _LIST_OPERATOR_ANY_OPERATIONS:
            result = bool(matched_items)
        elif operation in _LIST_OPERATOR_ALL_OPERATIONS:
            result = bool(items) and len(matched_items) == len(items)
        elif operation in _LIST_OPERATOR_NONE_OPERATIONS:
            result = not matched_items
        else:
            result = len(matched_items)
    elif operation in {"sort", "sorted", "order", "order_by", "order-by", "orderby"}:
        result = _sort_list_items(items, data, variables)
    elif operation in {"sum", "total"}:
        result = sum(_list_operator_numeric_values(items, data, variables))
    elif operation in {"average", "avg", "mean"}:
        numeric_values = _list_operator_numeric_values(items, data, variables)
        result = None if not numeric_values else sum(numeric_values) / len(numeric_values)
    elif operation in {"min", "minimum"}:
        numeric_values = _list_operator_numeric_values(items, data, variables)
        result = None if not numeric_values else min(numeric_values)
    elif operation in {"max", "maximum"}:
        numeric_values = _list_operator_numeric_values(items, data, variables)
        result = None if not numeric_values else max(numeric_values)
    else:
        raise WorkflowExecutionError(f"workflow_list_operator_operation_not_supported:{operation}")

    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or "result"
    )
    return {output_key: result}


def _validate_list_operator_static(data: dict[str, Any]) -> None:
    if not _list_operator_selector_from_data(data):
        raise WorkflowExecutionError("workflow_list_operator_selector_missing")
    operation = (
        str(data.get("operation") or data.get("op") or data.get("operator") or "first")
        .strip()
        .lower()
    )
    if operation not in _LIST_OPERATOR_SUPPORTED_OPERATIONS:
        raise WorkflowExecutionError(f"workflow_list_operator_operation_not_supported:{operation}")
    if operation in _LIST_OPERATOR_VALUE_KEY_OPERATIONS:
        _list_operator_require_value_key(data)
    if operation in _LIST_OPERATOR_CONDITION_OPERATIONS:
        if not _list_operator_filter_conditions_from_data(data):
            raise WorkflowExecutionError("workflow_list_operator_filter_conditions_missing")


def _dedupe_list_items(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        identity = _list_item_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def _list_item_identity(item: Any) -> str:
    try:
        return json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(item)


def _pluck_list_items(
    items: list[Any], data: dict[str, Any], variables: dict[str, Any]
) -> list[Any]:
    value_key = _list_operator_sort_key_from_data(data, variables)
    if not value_key:
        raise WorkflowExecutionError("workflow_list_operator_value_key_missing")
    return [_resolve_item_sort_value(item, value_key) for item in items]


def _filter_list_items(
    items: list[Any], data: dict[str, Any], variables: dict[str, Any]
) -> list[Any]:
    conditions = _list_operator_filter_conditions_from_data(data)
    if not conditions:
        raise WorkflowExecutionError("workflow_list_operator_filter_conditions_missing")
    logical_operator = str(
        data.get("logical_operator")
        or data.get("logicalOperator")
        or data.get("condition_operator")
        or data.get("conditionOperator")
        or data.get("combinator")
        or data.get("join")
        or data.get("mode")
        or "and"
    )
    result: list[Any] = []
    for index, item in enumerate(items):
        item_variables = _list_operator_item_condition_variables(variables, item, index)
        if _evaluate_conditions(conditions, logical_operator, item_variables):
            result.append(item)
    return result


def _list_operator_filter_conditions_from_data(data: dict[str, Any]) -> list[Any]:
    for key in (
        "conditions",
        "rules",
        "filters",
        "filter_conditions",
        "filterConditions",
        "where",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return value
    condition = data.get("condition") or data.get("filter") or data.get("predicate")
    if isinstance(condition, dict):
        return [condition]
    return []


def _list_operator_item_condition_variables(
    variables: dict[str, Any],
    item: Any,
    index: int,
) -> dict[str, Any]:
    item_variables = dict(variables)
    item_variables.update(
        {
            "item": item,
            "list_item": item,
            "iteration_item": item,
            "index": index,
            "list_index": index,
            "iteration_index": index,
        }
    )
    if isinstance(item, dict):
        for key, value in item.items():
            item_variables.setdefault(str(key), value)
    return item_variables


def _list_operator_require_value_key(data: dict[str, Any]) -> None:
    if _list_operator_sort_key_from_data(data, {}):
        return
    raise WorkflowExecutionError("workflow_list_operator_value_key_missing")


def _sort_list_items(
    items: list[Any], data: dict[str, Any], variables: dict[str, Any]
) -> list[Any]:
    sort_key = _list_operator_sort_key_from_data(data, variables)
    descending = _list_operator_descending_from_data(data, variables)
    indexed_items = list(enumerate(items))

    def item_key(indexed_item: tuple[int, Any]) -> tuple[int, int, Any, int]:
        index, item = indexed_item
        value = _resolve_item_sort_value(item, sort_key)
        category, comparable = _list_sort_comparable(value)
        missing_rank = 1 if value is None else 0
        return (missing_rank, category, comparable, index)

    def present_key(indexed_item: tuple[int, Any]) -> tuple[int, Any]:
        _, category, comparable, _ = item_key(indexed_item)
        return (category, comparable)

    if not descending:
        sorted_items = sorted(indexed_items, key=item_key)
        return [item for _, item in sorted_items]

    sorted_items = sorted(indexed_items, key=item_key)
    if descending:
        present = [item for item in sorted_items if item_key(item)[0] == 0]
        missing = [item for item in sorted_items if item_key(item)[0] != 0]
        present = sorted(present, key=present_key, reverse=True)
        sorted_items = present + missing
    return [item for _, item in sorted_items]


def _list_operator_sort_key_from_data(data: dict[str, Any], variables: dict[str, Any]) -> str:
    selector = (
        data.get("sort_key")
        or data.get("sortKey")
        or data.get("sort_by")
        or data.get("sortBy")
        or data.get("order_by")
        or data.get("orderBy")
        or data.get("key")
        or data.get("by")
        or data.get("field")
        or data.get("field_name")
        or data.get("fieldName")
        or data.get("property")
        or data.get("path")
        or data.get("value_key")
        or data.get("valueKey")
        or data.get("number_key")
        or data.get("numberKey")
        or data.get("item_key")
        or data.get("itemKey")
    )
    if selector is None:
        selector = _first_present_param_selector(data, "sort_key")
    if selector is None:
        return ""
    resolved = _resolve_value(selector, variables)
    return _selector_to_key(resolved)


def _list_operator_descending_from_data(data: dict[str, Any], variables: dict[str, Any]) -> bool:
    for key in ("descending", "desc", "reverse"):
        if key in data:
            return _coerce_bool(_resolve_value(data.get(key), variables))
        selector = _first_present_param_selector(data, key)
        if selector is not None:
            return _coerce_bool(_resolve_path(variables, _selector_to_key(selector)))
    order = (
        str(
            _resolve_value(
                data.get("order")
                or data.get("direction")
                or data.get("sort_order")
                or data.get("sortOrder")
                or "",
                variables,
            )
        )
        .strip()
        .lower()
    )
    return order in {"desc", "descending", "reverse", "reversed", "-1"}


def _resolve_item_sort_value(item: Any, sort_key: str) -> Any:
    if not sort_key:
        return item
    if not isinstance(item, dict):
        return None
    return _resolve_path(item, sort_key)


def _list_sort_comparable(value: Any) -> tuple[int, Any]:
    if value is None:
        return (5, "")
    if isinstance(value, bool):
        return (0, int(value))
    number = _optional_number(value)
    if number is not None:
        return (1, float(number))
    if isinstance(value, str):
        return (2, value.casefold())
    if isinstance(value, (dict, list)):
        return (3, _list_item_identity(value))
    return (4, str(value))


def _list_operator_numeric_values(
    items: list[Any], data: dict[str, Any], variables: dict[str, Any]
) -> list[int | float]:
    value_key = _list_operator_sort_key_from_data(data, variables)
    numeric_values: list[int | float] = []
    for item in items:
        value = _resolve_item_sort_value(item, value_key)
        numeric_value = _optional_number(value)
        if numeric_value is not None:
            numeric_values.append(numeric_value)
    return numeric_values


def _coerce_bool(value: Any) -> bool:
    parsed = _as_bool(value)
    if parsed is not None:
        return parsed
    if isinstance(value, str):
        return value.strip().lower() in {"desc", "descending", "reverse", "reversed"}
    return bool(value)


def _list_operator_int_param(
    data: dict[str, Any],
    variables: dict[str, Any],
    *names: str,
    default: int | None = None,
) -> int | None:
    for name in names:
        if name in data:
            return _optional_int(_resolve_value(data.get(name), variables), default=default)
        selector = _first_present_param_selector(data, name)
        if selector is not None:
            return _optional_int(
                _resolve_path(variables, _selector_to_key(selector)), default=default
            )
    return default


def _first_present_param_selector(data: dict[str, Any], name: str) -> Any:
    snake_name = _camel_to_snake(name)
    camel_name = _snake_to_camel(name)
    for key in (
        f"{name}_selector",
        f"{name}Selector",
        f"{snake_name}_selector",
        f"{camel_name}Selector",
    ):
        if key in data:
            return data.get(key)
    return None


def _list_operator_param_present(data: dict[str, Any], name: str) -> bool:
    return name in data or _first_present_param_selector(data, name) is not None


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _list_operator_selector_from_data(data: dict[str, Any]) -> str:
    selector = (
        data.get("variable_selector")
        or data.get("variableSelector")
        or data.get("selector")
        or data.get("input_selector")
        or data.get("inputSelector")
        or data.get("input_variable")
        or data.get("inputVariable")
        or data.get("variable")
        or data.get("input")
    )
    return _selector_to_key(selector)


def _execute_iteration(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    selector = _iteration_selector_from_data(data)
    if not selector:
        raise WorkflowExecutionError("workflow_iteration_selector_missing")
    value = _resolve_path(variables, selector)
    if value is None:
        items: list[Any] = []
    elif isinstance(value, list):
        items = value
    else:
        raise WorkflowExecutionError("workflow_iteration_input_not_list")

    max_items = _iteration_max_items_from_data(data, variables, default=100)
    if max_items is not None and len(items) > max_items:
        raise WorkflowExecutionError(
            f"workflow_iteration_item_limit_exceeded:{len(items)}>{max_items}"
        )

    item_template = _iteration_item_template_from_data(data)
    if item_template:
        results: list[Any] = []
        for index, item in enumerate(items):
            scoped_variables = {
                **variables,
                "item": item,
                "iteration_item": item,
                "index": index,
                "iteration_index": index,
            }
            results.append(_render_template(item_template, scoped_variables))
    else:
        results = list(items)

    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or "iteration_result"
    )
    return {
        output_key: results,
        f"{output_key}_count": len(items),
        "iteration_count": len(items),
    }


def _validate_iteration_static(data: dict[str, Any]) -> None:
    if not _iteration_selector_from_data(data):
        raise WorkflowExecutionError("workflow_iteration_selector_missing")
    max_items = _iteration_max_items_from_data(data, {}, default=100)
    if max_items is not None and max_items < 0:
        raise WorkflowExecutionError("workflow_iteration_max_items_invalid")


def _iteration_item_template_from_data(data: dict[str, Any]) -> str:
    for key in (
        "item_template",
        "itemTemplate",
        "template",
        "template_string",
        "templateString",
        "content",
        "value",
    ):
        template = _text_template_to_string(data.get(key))
        if template:
            return template
    return ""


def _iteration_max_items_from_data(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    default: int | None = None,
) -> int | None:
    return _list_operator_int_param(
        data, variables, "max_items", "maxItems", "limit", default=default
    )


def _iteration_selector_from_data(data: dict[str, Any]) -> str:
    selector = (
        data.get("iterator_selector")
        or data.get("iteratorSelector")
        or data.get("variable_selector")
        or data.get("variableSelector")
        or data.get("selector")
        or data.get("input_selector")
        or data.get("inputSelector")
        or data.get("input_variable")
        or data.get("inputVariable")
        or data.get("variable")
        or data.get("input")
    )
    return _selector_to_key(selector)


def _execute_document_extractor(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    selector = _document_extractor_selector_from_data(data)
    if not selector:
        raise WorkflowExecutionError("workflow_document_extractor_selector_missing")
    raw_value = _resolve_path(variables, selector)
    documents = _document_items_from_value(raw_value)
    text_parts = [_extract_document_text(item) for item in documents]
    text_parts = [text for text in text_parts if text]
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or "document_text"
    )
    joined_text = "\n".join(text_parts)
    return {
        output_key: joined_text,
        f"{output_key}_documents": documents,
        f"{output_key}_count": len(documents),
        "document_text": joined_text,
        "document_count": len(documents),
    }


def _validate_document_extractor_static(data: dict[str, Any]) -> None:
    if not _document_extractor_selector_from_data(data):
        raise WorkflowExecutionError("workflow_document_extractor_selector_missing")


def _document_extractor_selector_from_data(data: dict[str, Any]) -> str:
    selector = (
        data.get("variable_selector")
        or data.get("variableSelector")
        or data.get("input_selector")
        or data.get("inputSelector")
        or data.get("file_selector")
        or data.get("fileSelector")
        or data.get("document_selector")
        or data.get("documentSelector")
        or data.get("selector")
        or data.get("input_variable")
        or data.get("inputVariable")
        or data.get("variable")
        or data.get("input")
    )
    return _selector_to_key(selector)


def _document_items_from_value(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    documents: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if isinstance(raw_item, dict):
            document = dict(raw_item)
        else:
            document = {"text": str(raw_item)}
        document.setdefault("index", index)
        documents.append(document)
    return documents


def _extract_document_text(document: dict[str, Any]) -> str:
    for key in (
        "text",
        "content",
        "markdown",
        "body",
        "data",
        "transcript",
        "extracted_text",
        "extractedText",
        "extracted_content",
        "extractedContent",
        "plain_text",
        "plainText",
        "page_content",
        "pageContent",
    ):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in (
        "document",
        "file",
        "upload_file",
        "uploadFile",
        "metadata",
        "meta",
        "parsed",
        "result",
    ):
        value = document.get(key)
        nested_text = _document_text_from_nested_value(value)
        if nested_text:
            return nested_text
    for key in ("pages", "chunks", "segments", "documents", "items"):
        nested_text = _document_text_from_nested_value(document.get(key))
        if nested_text:
            return nested_text
    return ""


def _document_text_from_nested_value(value: Any) -> str:
    if isinstance(value, str):
        return value if value.strip() else ""
    if isinstance(value, dict):
        return _extract_document_text(value)
    if isinstance(value, list):
        parts = [_document_text_from_nested_value(item) for item in value]
        return "\n".join(part for part in parts if part)
    return ""


def _optional_int(value: Any, *, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _execute_condition(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    cases = _as_list(data.get("cases")) or _as_list(data.get("branches"))
    for index, raw_case in enumerate(cases):
        case = _as_dict(raw_case)
        case_id = str(
            case.get("id") or case.get("case_id") or case.get("handle") or f"case_{index + 1}"
        )
        conditions = _as_list(case.get("conditions"))
        logical_operator = str(case.get("logical_operator") or case.get("logicalOperator") or "and")
        if _evaluate_conditions(conditions, logical_operator, variables):
            return {"branch": case_id, "matched": True}

    conditions = _as_list(data.get("conditions"))
    if conditions:
        logical_operator = str(data.get("logical_operator") or data.get("logicalOperator") or "and")
        matched = _evaluate_conditions(conditions, logical_operator, variables)
        return {"branch": "true" if matched else "false", "matched": matched}

    expression = data.get("expression")
    if isinstance(expression, str) and expression.strip():
        matched = bool(_render_template(expression, variables).strip())
        return {"branch": "true" if matched else "false", "matched": matched}

    return {"branch": "false", "matched": False}


async def _execute_tool_call(
    data: dict[str, Any],
    variables: dict[str, Any],
    tool_invoker: ToolInvoker | None,
    *,
    node_id: str,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if tool_invoker is None:
        raise WorkflowExecutionError("workflow_tool_invoker_unavailable")
    tool_name = _tool_name_from_data(data)
    if not tool_name:
        raise WorkflowExecutionError("workflow_tool_name_missing")
    arguments = _tool_arguments_from_data(data, variables)
    result = await _await_with_runtime_guard(
        tool_invoker(tool_name, arguments),
        node_id=node_id,
        node_type="tool_call",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    output_key = str(data.get("output_key") or data.get("outputKey") or "tool_result")
    return {output_key: result, "tool_name": tool_name}


async def _execute_knowledge_retrieval(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    knowledge_retriever: KnowledgeRetriever | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if knowledge_retriever is None:
        raise WorkflowExecutionError("workflow_knowledge_retriever_unavailable")
    request = _knowledge_retrieval_request_from_data(data, variables)
    result = await _await_with_runtime_guard(
        knowledge_retriever(request),
        node_id=node_id,
        node_type="knowledge_retrieval",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    normalized = _normalize_knowledge_result(result)
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or node_id
        or "knowledge"
    )
    output = {output_key: normalized}
    if output_key != "knowledge_result":
        output["knowledge_result"] = normalized
    return output


async def _execute_sub_workflow(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    sub_workflow_invoker: SubWorkflowInvoker | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if sub_workflow_invoker is None:
        raise WorkflowExecutionError("workflow_sub_workflow_invoker_unavailable")
    workflow_id = _sub_workflow_id_from_data(data)
    if not workflow_id:
        raise WorkflowExecutionError("workflow_sub_workflow_id_missing")
    request = _sub_workflow_request_from_data(data, variables)
    result = await _await_with_runtime_guard(
        sub_workflow_invoker(request),
        node_id=node_id,
        node_type="sub_workflow",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    normalized = _normalize_sub_workflow_result(result)
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or node_id
        or "sub_workflow"
    )
    output = {output_key: normalized.get("output", normalized)}
    if output_key != "sub_workflow_result":
        output["sub_workflow_result"] = normalized
    return output


async def _execute_llm(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    llm_invoker: LlmInvoker | None,
    credential_secret_resolver: CredentialSecretResolver | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if llm_invoker is None:
        raise WorkflowExecutionError("workflow_llm_invoker_unavailable")
    request = _llm_request_from_data(data, variables)
    await _inject_llm_credential_secret(
        request,
        data,
        node_id=node_id,
        credential_secret_resolver=credential_secret_resolver,
    )
    if not request.get("prompt") and not request.get("messages"):
        raise WorkflowExecutionError("workflow_llm_prompt_missing")
    result = await _await_with_runtime_guard(
        llm_invoker(request),
        node_id=node_id,
        node_type="llm",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    normalized = _normalize_llm_result(
        result, model=str(request.get("model") or request.get("model_id") or "")
    )
    output_key = str(data.get("output_key") or data.get("outputKey") or node_id or "llm_result")
    output = {output_key: normalized}
    if output_key != "llm_result":
        output["llm_result"] = normalized
    if output_key != "llm_text":
        output["llm_text"] = normalized["text"]
    return output


async def _execute_parameter_extractor(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    llm_invoker: LlmInvoker | None,
    credential_secret_resolver: CredentialSecretResolver | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if llm_invoker is None:
        raise WorkflowExecutionError("workflow_llm_invoker_unavailable")
    request = _parameter_extractor_request_from_data(data, variables)
    await _inject_llm_credential_secret(
        request,
        data,
        node_id=node_id,
        credential_secret_resolver=credential_secret_resolver,
    )
    result = await _await_with_runtime_guard(
        llm_invoker(request),
        node_id=node_id,
        node_type="parameter_extractor",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    text = _stringify_llm_content(
        result.get("text", result.get("content", result.get("output", "")))
    )
    parsed = _parse_extractor_json(text)
    output_key = str(
        data.get("output_key")
        or data.get("outputKey")
        or data.get("variable")
        or data.get("name")
        or node_id
        or "parameters"
    )
    output: dict[str, Any] = {
        output_key: parsed,
        "parameters": parsed,
        "parameter_extractor_text": text,
    }
    return output


async def _execute_question_classifier(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    llm_invoker: LlmInvoker | None,
    credential_secret_resolver: CredentialSecretResolver | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if llm_invoker is None:
        raise WorkflowExecutionError("workflow_llm_invoker_unavailable")
    classes = _question_classifier_classes_from_data(data)
    request = _question_classifier_request_from_data(data, variables, classes)
    await _inject_llm_credential_secret(
        request,
        data,
        node_id=node_id,
        credential_secret_resolver=credential_secret_resolver,
    )
    result = await _await_with_runtime_guard(
        llm_invoker(request),
        node_id=node_id,
        node_type="question_classifier",
        timeout_seconds=timeout_seconds,
        cancel_checker=cancel_checker,
    )
    text = _stringify_llm_content(
        result.get("text", result.get("content", result.get("output", "")))
    )
    matched = _match_question_class(text, classes)
    if matched is None:
        branch = str(data.get("default_class") or data.get("defaultClass") or "default")
        output: dict[str, Any] = {
            "branch": branch,
            "matched": False,
            "question_class": None,
            "question_classifier_text": text,
        }
    else:
        output = {
            "branch": matched["id"],
            "matched": True,
            "question_class": matched["id"],
            "question_class_name": matched["name"],
            "question_classifier_text": text,
        }
    output_key = str(data.get("output_key") or data.get("outputKey") or node_id or "question_class")
    if output_key not in output:
        output[output_key] = output["question_class"] or output["branch"]
    return output


def _validate_llm_backed_node_static(
    data: dict[str, Any],
    *,
    node_type: str,
    llm_available: bool,
) -> None:
    if not llm_available:
        raise WorkflowExecutionError("workflow_llm_invoker_unavailable")
    if node_type == "parameter_extractor":
        request = _parameter_extractor_request_from_data(data, {})
    elif node_type == "question_classifier":
        classes = _question_classifier_classes_from_data(data)
        request = _question_classifier_request_from_data(data, {}, classes)
    else:
        request = _llm_request_from_data(data, {})
    if not request.get("prompt") and not request.get("messages"):
        raise WorkflowExecutionError(
            "workflow_parameter_extractor_prompt_missing"
            if node_type == "parameter_extractor"
            else "workflow_question_classifier_prompt_missing"
            if node_type == "question_classifier"
            else "workflow_llm_prompt_missing"
        )


def _validate_knowledge_retrieval_static(
    data: dict[str, Any],
    *,
    knowledge_available: bool,
) -> None:
    if not knowledge_available:
        raise WorkflowExecutionError("workflow_knowledge_retriever_unavailable")


def _validate_sub_workflow_static(
    data: dict[str, Any],
    *,
    available_sub_workflow_refs: set[str] | None,
) -> None:
    workflow_id = _sub_workflow_id_from_data(data)
    if not workflow_id:
        raise WorkflowExecutionError("workflow_sub_workflow_id_missing")
    if available_sub_workflow_refs is None:
        raise WorkflowExecutionError("workflow_sub_workflow_refs_unavailable")
    if (
        _sub_workflow_ref_key(workflow_id, _sub_workflow_version_id_from_data(data))
        not in available_sub_workflow_refs
    ):
        raise WorkflowExecutionError(f"workflow_sub_workflow_not_available:{workflow_id}")


def _sub_workflow_request_from_data(
    data: dict[str, Any], variables: dict[str, Any]
) -> dict[str, Any]:
    return {
        "workflow_id": _sub_workflow_id_from_data(data),
        "version_id": _sub_workflow_version_id_from_data(data),
        "input": _sub_workflow_input_from_data(data, variables),
    }


def _sub_workflow_id_from_data(data: dict[str, Any]) -> str:
    value = (
        data.get("workflow_id")
        or data.get("workflowId")
        or data.get("target_workflow_id")
        or data.get("targetWorkflowId")
        or data.get("app_id")
        or data.get("appId")
    )
    return str(value or "").strip()


def _sub_workflow_version_id_from_data(data: dict[str, Any]) -> str | None:
    value = (
        data.get("version_id")
        or data.get("versionId")
        or data.get("workflow_version_id")
        or data.get("workflowVersionId")
    )
    text = str(value or "").strip()
    return text or None


def _sub_workflow_input_from_data(
    data: dict[str, Any], variables: dict[str, Any]
) -> dict[str, Any]:
    raw_input = None
    for key in (
        "input",
        "inputs",
        "arguments",
        "args",
        "parameters",
        "workflow_inputs",
        "workflowInputs",
    ):
        if key in data and data.get(key) not in (None, "", [], {}):
            raw_input = data.get(key)
            break
    if raw_input is None:
        selector = (
            data.get("input_selector")
            or data.get("inputSelector")
            or data.get("variable_selector")
            or data.get("variableSelector")
        )
        if selector is not None:
            resolved = _resolve_path(variables, _selector_to_key(selector))
            return dict(resolved) if isinstance(resolved, dict) else {"input": resolved}
        return dict(variables)
    if isinstance(raw_input, list):
        raw_input = _descriptor_list_to_dict(raw_input)
    resolved = _resolve_structured_value(raw_input, variables)
    return dict(resolved) if isinstance(resolved, dict) else {"input": resolved}


def _normalize_sub_workflow_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        output = result.get("output") if isinstance(result.get("output"), dict) else None
        normalized = dict(result)
        normalized["output"] = (
            output
            if output is not None
            else {
                key: value
                for key, value in result.items()
                if key not in {"events", "run", "run_id", "workflow_id", "version_id", "status"}
            }
        )
        return normalized
    return {"output": {"value": result}}


def _sub_workflow_ref_key(workflow_id: str, version_id: str | None = None) -> str:
    return f"{workflow_id}@{version_id or 'published'}"


def _knowledge_retrieval_request_from_data(
    data: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    query = _first_string(
        data,
        "query",
        "retrieval_query",
        "retrievalQuery",
        "text",
        "content",
    )
    if query:
        query = _render_template(query, variables)
    else:
        selector = (
            data.get("query_variable_selector")
            or data.get("queryVariableSelector")
            or data.get("variable_selector")
            or data.get("variableSelector")
            or data.get("selector")
        )
        if selector is not None:
            value = _resolve_path(variables, _selector_to_key(selector))
            query = "" if value is None else str(value)
    if not query:
        query = _implicit_knowledge_query(variables)
    dataset_ids = [
        str(item) for item in _as_list(data.get("dataset_ids") or data.get("datasetIds"))
    ]
    dataset_filters = _knowledge_dataset_filters_from_data(data)
    return {
        "query": query,
        "dataset_ids": dataset_ids,
        "dataset_filters": dataset_filters,
        "top_k": _knowledge_numeric_param(data, variables, "top_k", "topK", "limit", default=5)
        or 5,
        "score_threshold": _knowledge_numeric_param(
            data, variables, "score_threshold", "scoreThreshold"
        ),
    }


def _knowledge_numeric_param(
    data: dict[str, Any],
    variables: dict[str, Any],
    *names: str,
    default: int | float | None = None,
) -> int | float | None:
    for name in names:
        if name in data:
            return _optional_number(_resolve_value(data.get(name), variables), default=default)
        selector = _first_present_param_selector(data, name)
        if selector is not None:
            return _optional_number(
                _resolve_path(variables, _selector_to_key(selector)), default=default
            )
    return default


def _optional_number(value: Any, *, default: int | float | None = None) -> int | float | None:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number.is_integer():
        return int(number)
    return number


def _knowledge_dataset_filters_from_data(data: dict[str, Any]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    dataset_filter = _as_dict(data.get("dataset_filter") or data.get("datasetFilter"))
    if dataset_filter:
        filters.update(dataset_filter)
    metadata_filter = _as_dict(data.get("metadata_filter") or data.get("metadataFilter"))
    if metadata_filter:
        filters["metadata"] = metadata_filter
    return filters


def _implicit_knowledge_query(variables: dict[str, Any]) -> str:
    for key in ("sys.query", "query", "message", "input"):
        value = _resolve_path(variables, key)
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _normalize_knowledge_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"success": True, "items": [], "text": str(result)}
    items = (
        result.get("items")
        or result.get("memories")
        or result.get("documents")
        or result.get("results")
        or []
    )
    if not isinstance(items, list):
        items = [items]
    text_parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            content = item.get("content") or item.get("text") or item.get("summary")
            if content not in (None, ""):
                text_parts.append(str(content))
        elif item not in (None, ""):
            text_parts.append(str(item))
    return {
        "success": bool(result.get("success", True)),
        "items": items,
        "text": "\n".join(text_parts),
        "raw": result,
        "dataset_ids": [str(item) for item in _as_list(result.get("dataset_ids"))],
        "resolved_dataset_ids": [
            str(item) for item in _as_list(result.get("resolved_dataset_ids"))
        ],
        "unresolved_dataset_ids": [
            str(item) for item in _as_list(result.get("unresolved_dataset_ids"))
        ],
    }


def _llm_request_from_data(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    model_id, model = _llm_model_from_data(data)
    request: dict[str, Any] = {
        "prompt": _llm_prompt_from_data(data, variables),
        "messages": _llm_messages_from_data(data, variables),
        "model_id": model_id,
        "model": model,
    }
    request.update(_llm_generation_params_from_data(data, variables))
    system_prompt = _first_string(data, "system_prompt", "systemPrompt", "system")
    if system_prompt:
        request["system_prompt"] = _render_template(system_prompt, variables)
    return request


async def _inject_llm_credential_secret(
    request: dict[str, Any],
    data: dict[str, Any],
    *,
    node_id: str,
    credential_secret_resolver: CredentialSecretResolver | None,
) -> None:
    if credential_secret_resolver is None or request.get("api_key"):
        return
    for ref in _llm_credential_refs_from_data(data, node_id=node_id):
        secret = await credential_secret_resolver(ref)
        if secret:
            payload = _credential_secret_payload(secret)
            api_key = _credential_secret_value(
                payload, "api_key", "apiKey", "token", "secret", "value"
            )
            if api_key:
                request["api_key"] = api_key
            api_base = _credential_secret_value(
                payload, "api_base", "apiBase", "base_url", "baseUrl", "endpoint"
            )
            if api_base:
                request["api_base"] = api_base
            return


def _llm_credential_refs_from_data(data: dict[str, Any], *, node_id: str) -> list[str]:
    refs: list[str] = []
    model_data = _as_dict(data.get("model"))
    for source in (data, model_data):
        for key in (
            "credential_ref",
            "credentialRef",
            "credential_id",
            "credentialId",
            "provider_credential_id",
            "providerCredentialId",
        ):
            value = source.get(key)
            if value not in (None, ""):
                refs.append(str(value).strip())
    provider_credential_id = model_data.get("provider_credential_id") or data.get(
        "provider_credential_id"
    )
    if provider_credential_id not in (None, ""):
        refs.append(f"{node_id}:provider_credential_id:{provider_credential_id}")
    provider = model_data.get("provider") or data.get("provider")
    if provider not in (None, ""):
        refs.append(f"{node_id}:llm_provider:{provider}")
    return _dedupe_non_empty(refs)


def _llm_generation_params_from_data(
    data: dict[str, Any], variables: dict[str, Any]
) -> dict[str, Any]:
    nested_params = _llm_nested_params_from_data(data)
    params: dict[str, Any] = {}
    for output_key, aliases in {
        "temperature": ("temperature",),
        "max_tokens": (
            "max_tokens",
            "maxTokens",
            "max_token",
            "maxToken",
            "max_new_tokens",
            "maxNewTokens",
        ),
        "top_p": ("top_p", "topP"),
        "presence_penalty": ("presence_penalty", "presencePenalty"),
        "frequency_penalty": ("frequency_penalty", "frequencyPenalty"),
        "stop": ("stop", "stop_sequences", "stopSequences"),
    }.items():
        value = _first_llm_param_value(data, nested_params, *aliases)
        if value is not None:
            params[output_key] = _resolve_structured_value(value, variables)
    return params


def _llm_nested_params_from_data(data: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    model_data = _as_dict(data.get("model"))
    for key in (
        "temperature",
        "max_tokens",
        "maxTokens",
        "max_token",
        "maxToken",
        "max_new_tokens",
        "maxNewTokens",
        "top_p",
        "topP",
        "presence_penalty",
        "presencePenalty",
        "frequency_penalty",
        "frequencyPenalty",
        "stop",
        "stop_sequences",
        "stopSequences",
    ):
        if key in model_data:
            merged[key] = model_data.get(key)
    for key in (
        "model_parameters",
        "modelParameters",
        "completion_params",
        "completionParams",
        "generation_params",
        "generationParams",
        "parameters",
    ):
        merged.update(_as_dict(model_data.get(key)))
    for key in (
        "model_parameters",
        "modelParameters",
        "completion_params",
        "completionParams",
        "generation_params",
        "generationParams",
        "parameters",
    ):
        merged.update(_as_dict(data.get(key)))
    return merged


def _first_llm_param_value(
    data: dict[str, Any], nested_params: dict[str, Any], *aliases: str
) -> Any:
    for alias in aliases:
        if alias in data:
            return data.get(alias)
    for alias in aliases:
        if alias in nested_params:
            return nested_params.get(alias)
    return None


def _parameter_extractor_request_from_data(
    data: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    request = _llm_request_from_data(data, variables)
    explicit_prompt = bool(
        _first_string(data, "prompt_template", "promptTemplate", "prompt")
        or _as_list(data.get("messages"))
        or _as_list(data.get("prompt_template"))
    )
    instruction = _first_string(
        data,
        "instruction",
        "instructions",
        "extract_instruction",
        "extractInstruction",
    )
    query = _parameter_extractor_query_from_data(data, variables)
    schema = (
        data.get("schema") or data.get("parameters") or data.get("fields") or data.get("outputs")
    )
    if not explicit_prompt:
        prompt_parts = [
            instruction or "Extract parameters from the input and return only a JSON object.",
        ]
        if schema:
            prompt_parts.append("Schema:")
            prompt_parts.append(
                json.dumps(_resolve_structured_value(schema, variables), ensure_ascii=False)
            )
        if query:
            prompt_parts.append("Input:")
            prompt_parts.append(query)
        request["prompt"] = "\n".join(prompt_parts)
    return request


def _parameter_extractor_query_from_data(data: dict[str, Any], variables: dict[str, Any]) -> str:
    query = _first_string(data, "query", "input", "text", "content")
    if query:
        return _render_template(query, variables)
    selector = (
        data.get("query_variable_selector")
        or data.get("queryVariableSelector")
        or data.get("variable_selector")
        or data.get("variableSelector")
        or data.get("input_selector")
        or data.get("inputSelector")
        or data.get("selector")
    )
    if selector is not None:
        resolved = _resolve_path(variables, _selector_to_key(selector))
        return "" if resolved is None else str(resolved)
    return ""


def _question_classifier_request_from_data(
    data: dict[str, Any],
    variables: dict[str, Any],
    classes: list[dict[str, str]],
) -> dict[str, Any]:
    request = _llm_request_from_data(data, variables)
    explicit_prompt = bool(
        _first_string(data, "prompt_template", "promptTemplate", "prompt")
        or _as_list(data.get("messages"))
        or _as_list(data.get("prompt_template"))
    )
    if explicit_prompt:
        return request

    instruction = _first_string(data, "instruction", "instructions")
    query = _classifier_query_from_data(data, variables)
    class_lines = [f"- {item['id']}: {item['name']}" for item in classes]
    prompt_parts = [
        instruction
        or 'Classify the input into exactly one class. Return only JSON like {"class": "class_id"}.',
        "Classes:",
        *class_lines,
    ]
    if query:
        prompt_parts.extend(["Input:", query])
    request["prompt"] = "\n".join(prompt_parts)
    return request


def _question_classifier_classes_from_data(data: dict[str, Any]) -> list[dict[str, str]]:
    raw_classes = (
        _as_list(data.get("classes"))
        or _as_list(data.get("topics"))
        or _as_list(data.get("categories"))
        or _as_list(data.get("options"))
    )
    classes: list[dict[str, str]] = []
    for index, raw_item in enumerate(raw_classes):
        if isinstance(raw_item, str):
            class_id = raw_item
            name = raw_item
        else:
            item = _as_dict(raw_item)
            class_id = str(
                item.get("id")
                or item.get("class_id")
                or item.get("classId")
                or item.get("value")
                or item.get("handle")
                or item.get("name")
                or item.get("label")
                or f"class_{index + 1}"
            )
            name = str(item.get("name") or item.get("label") or item.get("title") or class_id)
        class_id = class_id.strip()
        name = name.strip()
        if class_id:
            classes.append({"id": class_id, "name": name or class_id})
    if not classes:
        raise WorkflowExecutionError("workflow_question_classifier_classes_missing")
    return classes


def _classifier_query_from_data(data: dict[str, Any], variables: dict[str, Any]) -> str:
    query = _first_string(data, "query", "input", "text", "content")
    if query:
        return _render_template(query, variables)
    selector = (
        data.get("query_variable_selector")
        or data.get("queryVariableSelector")
        or data.get("variable_selector")
        or data.get("variableSelector")
        or data.get("input_selector")
        or data.get("inputSelector")
        or data.get("selector")
    )
    if selector is not None:
        resolved = _resolve_path(variables, _selector_to_key(selector))
        return "" if resolved is None else str(resolved)
    return ""


def _match_question_class(text: str, classes: list[dict[str, str]]) -> dict[str, str] | None:
    candidates = _classifier_response_candidates(text)
    class_lookup: dict[str, dict[str, str]] = {}
    for item in classes:
        class_lookup[_normalize_classifier_label(item["id"])] = item
        class_lookup[_normalize_classifier_label(item["name"])] = item
    for candidate in candidates:
        normalized = _normalize_classifier_label(candidate)
        if normalized in class_lookup:
            return class_lookup[normalized]
    return None


def _classifier_response_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    if not stripped:
        return candidates
    json_candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        json_candidates.insert(0, fenced.group(1).strip())
    object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if object_match:
        json_candidates.append(object_match.group(0))
    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            for key in ("class", "class_id", "classId", "category", "topic", "label", "value"):
                value = parsed.get(key)
                if value not in (None, ""):
                    candidates.append(str(value))
        elif parsed not in (None, ""):
            candidates.append(str(parsed))
    candidates.append(stripped.strip("\"'"))
    return _dedupe_preserve_order(candidates)


def _normalize_classifier_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _parse_extractor_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if object_match:
        candidates.append(object_match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"raw_text": text, "parse_error": "parameter_extractor_json_parse_failed"}


def _llm_model_from_data(data: dict[str, Any]) -> tuple[str | None, str | None]:
    model_id = data.get("model_id") or data.get("modelId")
    model_data = _as_dict(data.get("model"))
    model_name = (
        model_data.get("name")
        or model_data.get("model")
        or data.get("model_name")
        or data.get("modelName")
        or data.get("model")
    )
    provider = model_data.get("provider") or data.get("provider")
    model = str(model_name or "").strip()
    if provider and model and "/" not in model:
        model = f"{provider}/{model}"
    return (str(model_id).strip() if model_id else None, model or None)


def _llm_prompt_from_data(data: dict[str, Any], variables: dict[str, Any]) -> str:
    for key in ("prompt_template", "promptTemplate", "prompt", "query", "text", "instruction"):
        value = data.get(key)
        if isinstance(value, str):
            return _render_template(value, variables)
    return ""


def _llm_messages_from_data(
    data: dict[str, Any], variables: dict[str, Any]
) -> list[dict[str, str]]:
    raw_messages = _as_list(data.get("messages")) or _as_list(data.get("prompt_template"))
    messages: list[dict[str, str]] = []
    for index, item in enumerate(raw_messages):
        item_data = _as_dict(item)
        text = _llm_message_text_from_data(item_data)
        if not text:
            continue
        role = _llm_message_role_from_data(item_data, index=index)
        messages.append({"role": role, "content": _render_template(text, variables)})
    return messages


def _llm_message_text_from_data(data: dict[str, Any]) -> str:
    for key in (
        "text",
        "content",
        "message",
        "prompt",
        "template",
        "prompt_template",
        "promptTemplate",
        "value",
    ):
        text = _llm_message_content_to_text(data.get(key))
        if text:
            return text
    return ""


def _llm_message_content_to_text(value: Any) -> str:
    return _text_template_to_string(value)


def _llm_message_part_to_text(value: Any) -> str:
    return _text_template_part_to_string(value)


def _llm_message_role_from_data(data: dict[str, Any], *, index: int) -> str:
    role = (
        str(
            data.get("role")
            or data.get("name")
            or data.get("type")
            or ("user" if index else "system")
        )
        .strip()
        .lower()
    )
    role_aliases = {
        "ai": "assistant",
        "bot": "assistant",
        "model": "assistant",
        "human": "user",
    }
    role = role_aliases.get(role, role)
    if role not in {"system", "user", "assistant"}:
        role = "user"
    return role


def _normalize_llm_result(result: dict[str, Any], *, model: str) -> dict[str, Any]:
    content = result.get(
        "text", result.get("content", result.get("answer", result.get("output", "")))
    )
    return {
        "text": _stringify_llm_content(content),
        "model": str(result.get("model") or model),
        "usage": _as_dict(result.get("usage")),
    }


def _stringify_llm_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)
    return "" if content is None else str(content)


async def _execute_http_request(
    data: dict[str, Any],
    variables: dict[str, Any],
    *,
    node_id: str,
    http_policy: HttpRequestPolicy | None,
    http_invoker: HttpInvoker | None,
    credential_secret_resolver: CredentialSecretResolver | None,
    timeout_seconds: float | None,
    cancel_checker: CancelChecker | None,
) -> dict[str, Any]:
    if http_policy is None:
        raise WorkflowExecutionError("workflow_http_policy_disabled")
    method = _http_method_from_data(data)
    raw_url = _first_string(data, "url", "endpoint", "uri")
    rendered_url = _render_template(raw_url, variables)
    try:
        method = http_policy.validate_method(method)
        url = http_policy.validate_url(rendered_url)
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc

    headers = _http_headers_from_data(data, variables)
    await _inject_http_credential_secret(
        headers,
        data,
        node_id=node_id,
        credential_secret_resolver=credential_secret_resolver,
    )
    request = {
        "method": method,
        "url": url,
        "headers": headers,
        "params": _http_params_from_data(data, variables),
        "body": _http_body_from_data(data, variables),
        "timeout_seconds": timeout_seconds or http_policy.timeout_seconds,
        "max_response_bytes": http_policy.max_response_bytes,
    }
    invoker = http_invoker or _default_http_invoker
    result = await _await_with_runtime_guard(
        invoker(request),
        node_id=node_id,
        node_type="http_request",
        timeout_seconds=timeout_seconds or http_policy.timeout_seconds,
        cancel_checker=cancel_checker,
    )
    normalized = _normalize_http_result(result, max_response_bytes=http_policy.max_response_bytes)
    output_key = str(data.get("output_key") or data.get("outputKey") or node_id or "http_result")
    output = {output_key: normalized}
    if output_key != "http_result":
        output["http_result"] = normalized
    return output


def _validate_http_node_static(
    data: dict[str, Any],
    *,
    http_policy: HttpRequestPolicy | None,
) -> None:
    if http_policy is None:
        raise WorkflowExecutionError("workflow_http_policy_disabled")
    try:
        http_policy.validate_method(_http_method_from_data(data))
        http_policy.validate_url(_first_string(data, "url", "endpoint", "uri"))
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc


def _http_method_from_data(data: dict[str, Any]) -> str:
    return str(
        data.get("method") or data.get("request_method") or data.get("requestMethod") or "GET"
    )


def _http_headers_from_data(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, str]:
    headers = _http_mapping_from_data(
        data,
        variables,
        "headers",
        "header_parameters",
        "headerParameters",
        "request_headers",
        "requestHeaders",
    )
    return {str(key): str(value) for key, value in headers.items() if key and value is not None}


async def _inject_http_credential_secret(
    headers: dict[str, str],
    data: dict[str, Any],
    *,
    node_id: str,
    credential_secret_resolver: CredentialSecretResolver | None,
) -> None:
    if credential_secret_resolver is None:
        return
    for ref in _http_credential_refs_from_data(data, node_id=node_id):
        secret = await credential_secret_resolver(ref)
        if not secret:
            continue
        _apply_http_credential_secret(headers, data, payload=_credential_secret_payload(secret))
        return


def _http_credential_refs_from_data(data: dict[str, Any], *, node_id: str) -> list[str]:
    refs: list[str] = []
    for key in (
        "credential_ref",
        "credentialRef",
        "credential_id",
        "credentialId",
        "provider_credential_id",
    ):
        value = data.get(key)
        if value not in (None, ""):
            refs.append(str(value).strip())
    for auth_key in ("authorization", "auth"):
        auth = _as_dict(data.get(auth_key))
        for key in (
            "credential_ref",
            "credentialRef",
            "credential_id",
            "credentialId",
            "provider_credential_id",
        ):
            value = auth.get(key)
            if value not in (None, ""):
                refs.append(str(value).strip())
    refs.append(f"{node_id}:http_auth")
    return _dedupe_non_empty(refs)


def _apply_http_credential_secret(
    headers: dict[str, str], data: dict[str, Any], *, payload: dict[str, Any]
) -> None:
    for key, value in _credential_secret_headers(payload).items():
        if not _header_exists(headers, key):
            headers[key] = value

    secret = _credential_secret_value(payload, "token", "api_key", "apiKey", "secret", "value")
    if not secret:
        return
    auth = _as_dict(data.get("authorization")) or _as_dict(data.get("auth"))
    header_name = (
        str(
            auth.get("header")
            or auth.get("header_name")
            or auth.get("headerName")
            or payload.get("header")
            or payload.get("header_name")
            or payload.get("headerName")
            or auth.get("name")
            or "Authorization"
        ).strip()
        or "Authorization"
    )
    if _header_exists(headers, header_name):
        return

    prefix = _http_auth_prefix(auth, payload=payload)
    headers[header_name] = f"{prefix}{secret}" if prefix else secret


def _http_auth_prefix(auth: dict[str, Any], *, payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    for key in ("prefix", "value_prefix", "valuePrefix"):
        if auth.get(key) not in (None, ""):
            return str(auth.get(key))
        if payload.get(key) not in (None, ""):
            return str(payload.get(key))
    scheme = str(
        auth.get("scheme")
        or payload.get("scheme")
        or auth.get("type")
        or payload.get("type")
        or auth.get("auth_type")
        or auth.get("authType")
        or payload.get("auth_type")
        or payload.get("authType")
        or "bearer"
    )
    if scheme.strip().lower() in {"", "none", "raw", "custom", "api_key", "apikey", "key"}:
        return ""
    if scheme.strip().lower() == "bearer":
        return "Bearer "
    return f"{scheme.strip()} "


def _header_exists(headers: dict[str, str], header_name: str) -> bool:
    normalized = header_name.strip().lower()
    return any(str(existing).strip().lower() == normalized for existing in headers)


def _credential_secret_payload(secret: str) -> dict[str, Any]:
    text = str(secret or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"value": text}
    if isinstance(parsed, dict):
        return parsed
    return {"value": text}


def _credential_secret_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return ""


def _credential_secret_headers(payload: dict[str, Any]) -> dict[str, str]:
    raw_headers = (
        payload.get("headers") or payload.get("request_headers") or payload.get("requestHeaders")
    )
    headers = raw_headers if isinstance(raw_headers, dict) else {}
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).strip() and value not in (None, "")
    }


def _dedupe_non_empty(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _http_params_from_data(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    return _http_mapping_from_data(
        data,
        variables,
        "params",
        "query",
        "query_parameters",
        "queryParameters",
        "request_params",
        "requestParams",
    )


def _http_mapping_from_data(
    data: dict[str, Any], variables: dict[str, Any], *keys: str
) -> dict[str, Any]:
    for key in keys:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            value = _descriptor_list_to_dict(value)
        else:
            value = _as_dict(value)
        return {
            str(item_key): _resolve_structured_value(item_value, variables)
            for item_key, item_value in value.items()
        }
    return {}


def _http_body_from_data(data: dict[str, Any], variables: dict[str, Any]) -> Any:
    for key in (
        "body",
        "request_body",
        "requestBody",
        "json",
        "payload",
        "data",
    ):
        if key in data:
            return _resolve_structured_value(data.get(key), variables)
    return None


async def _default_http_invoker(request: dict[str, Any]) -> dict[str, Any]:
    import httpx

    method = str(request.get("method") or "GET")
    body = request.get("body")
    kwargs: dict[str, Any] = {
        "headers": _as_dict(request.get("headers")),
        "params": _as_dict(request.get("params")),
    }
    if body not in (None, "") and method not in {"GET", "HEAD"}:
        if isinstance(body, dict | list):
            kwargs["json"] = body
        else:
            kwargs["content"] = str(body)
    async with httpx.AsyncClient(timeout=float(request.get("timeout_seconds") or 10.0)) as client:
        response = await client.request(method, str(request.get("url") or ""), **kwargs)
    max_response_bytes = _optional_int(request.get("max_response_bytes")) or 65536
    content = response.content[:max_response_bytes]
    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": content.decode(response.encoding or "utf-8", errors="replace"),
    }


def _normalize_http_result(result: dict[str, Any], *, max_response_bytes: int) -> dict[str, Any]:
    status_code = result.get("status_code", result.get("status"))
    try:
        normalized_status = int(status_code) if status_code is not None else 0
    except (TypeError, ValueError):
        normalized_status = 0
    headers = _as_dict(result.get("headers"))
    body = result.get("body", "")
    if isinstance(body, bytes):
        body_text = body[:max_response_bytes].decode("utf-8", errors="replace")
    else:
        body_text = str(body)[:max_response_bytes]
    return {
        "status_code": normalized_status,
        "headers": {str(key): str(value) for key, value in headers.items()},
        "body": body_text,
    }


def _node_timeout_seconds(
    data: dict[str, Any], default_timeout_seconds: float | None
) -> float | None:
    timeout = (
        data.get("timeout_seconds")
        or data.get("timeoutSeconds")
        or data.get("timeout")
        or data.get("request_timeout_seconds")
        or data.get("requestTimeoutSeconds")
    )
    return _normalize_timeout_seconds(timeout, default=default_timeout_seconds)


def _normalize_timeout_seconds(value: Any, *, default: float | None) -> float | None:
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return None
    return min(parsed, 3600.0)


def _tool_name_from_data(data: dict[str, Any]) -> str:
    value = (
        data.get("tool_name")
        or data.get("toolName")
        or data.get("name")
        or data.get("tool")
        or _as_dict(data.get("provider")).get("tool_name")
        or _as_dict(data.get("provider")).get("name")
    )
    return str(value or "").strip()


def _tool_arguments_from_data(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    raw_arguments = _first_tool_arguments_value(data)
    if isinstance(raw_arguments, list):
        raw_arguments = _descriptor_list_to_dict(raw_arguments)
    else:
        raw_arguments = _as_dict(raw_arguments)
    return {
        str(key): _resolve_structured_value(value, variables)
        for key, value in raw_arguments.items()
    }


def _first_tool_arguments_value(data: dict[str, Any]) -> Any:
    for key in (
        "arguments",
        "args",
        "inputs",
        "tool_parameters",
        "toolParameters",
        "tool_configurations",
        "toolConfigurations",
        "parameters",
    ):
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return {}


def _descriptor_list_to_dict(items: list[Any]) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    for index, raw_item in enumerate(items):
        item = _as_dict(raw_item)
        if not item:
            continue
        name = str(
            item.get("name")
            or item.get("variable")
            or item.get("key")
            or item.get("parameter")
            or item.get("field")
            or f"arg_{index + 1}"
        ).strip()
        if not name:
            continue
        arguments[name] = _descriptor_item_value(item)
    return arguments


def _descriptor_item_value(item: dict[str, Any]) -> Any:
    for key in (
        "value",
        "default",
        "input",
        "text",
        "content",
        "value_selector",
        "valueSelector",
        "variable_selector",
        "variableSelector",
        "input_selector",
        "inputSelector",
        "source_selector",
        "sourceSelector",
        "selector",
    ):
        if key in item:
            if key.endswith("selector") or key.endswith("Selector") or key == "selector":
                return {key: item.get(key)}
            return item.get(key)
    return {
        key: value
        for key, value in item.items()
        if key not in {"name", "variable", "key", "parameter", "field"}
    }


def _resolve_structured_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_template(value, variables)
    if isinstance(value, list):
        return [_resolve_structured_value(item, variables) for item in value]
    if isinstance(value, dict):
        selector = _structured_value_selector(value)
        if selector is not None:
            return _resolve_path(variables, _selector_to_key(selector))
        if "value" in value and _is_structured_value_descriptor(value):
            return _resolve_structured_value(value.get("value"), variables)
        return {str(key): _resolve_structured_value(item, variables) for key, item in value.items()}
    return value


def _structured_value_selector(value: dict[str, Any]) -> Any:
    selector = (
        value.get("value_selector")
        or value.get("valueSelector")
        or value.get("variable_selector")
        or value.get("variableSelector")
        or value.get("source_selector")
        or value.get("sourceSelector")
        or value.get("input_selector")
        or value.get("inputSelector")
    )
    if selector is not None and _is_structured_value_descriptor(value):
        return selector
    if set(value) == {"selector"}:
        return value.get("selector")
    return None


def _is_structured_value_descriptor(value: dict[str, Any]) -> bool:
    descriptor_keys = {
        "value",
        "value_selector",
        "valueSelector",
        "variable_selector",
        "variableSelector",
        "source_selector",
        "sourceSelector",
        "input_selector",
        "inputSelector",
        "selector",
        "type",
        "label",
        "name",
    }
    return bool(set(value) & descriptor_keys) and set(value).issubset(descriptor_keys)


def _evaluate_conditions(
    conditions: list[Any],
    logical_operator: str,
    variables: dict[str, Any],
) -> bool:
    if not conditions:
        return False
    results = [
        _evaluate_condition_entry(_as_dict(condition), variables) for condition in conditions
    ]
    normalized_operator = _normalize_condition_logical_operator(logical_operator)
    if normalized_operator == "or":
        return any(results)
    if normalized_operator == "not":
        return not all(results)
    return all(results)


def _evaluate_condition_entry(condition: dict[str, Any], variables: dict[str, Any]) -> bool:
    nested_conditions = _condition_group_items(condition)
    if nested_conditions is not None:
        logical_operator = _condition_group_operator(condition)
        matched = _evaluate_conditions(nested_conditions, logical_operator, variables)
        if _condition_group_negated(condition):
            return not matched
        return matched
    return _evaluate_condition(condition, variables)


def _condition_group_items(condition: dict[str, Any]) -> list[Any] | None:
    for key in ("conditions", "rules", "children", "items"):
        value = condition.get(key)
        if isinstance(value, list):
            return value
    return None


def _condition_group_operator(condition: dict[str, Any]) -> str:
    return str(
        condition.get("logical_operator")
        or condition.get("logicalOperator")
        or condition.get("condition_operator")
        or condition.get("conditionOperator")
        or condition.get("combinator")
        or condition.get("join")
        or condition.get("mode")
        or "and"
    )


def _normalize_condition_logical_operator(logical_operator: str) -> str:
    normalized = logical_operator.strip().lower().replace("_", "-")
    if normalized in {"or", "any", "some", "union", "||"}:
        return "or"
    if normalized in {"not", "none", "nor"}:
        return "not"
    return "and"


def _condition_group_negated(condition: dict[str, Any]) -> bool:
    negated = condition.get("not") or condition.get("negate") or condition.get("negated")
    return _as_bool(negated) is True


def _evaluate_condition(condition: dict[str, Any], variables: dict[str, Any]) -> bool:
    left = _resolve_condition_left(condition, variables)
    right = _resolve_condition_right(condition, variables)
    operator = (
        str(
            condition.get("comparison_operator")
            or condition.get("operator")
            or condition.get("op")
            or "equals"
        )
        .strip()
        .lower()
    )
    if operator in {"equals", "=", "==", "is"}:
        return left == right
    if operator in {"not equals", "not_equal", "!=", "is not"}:
        return left != right
    if operator in {"contains", "include", "includes"}:
        return str(right) in str(left)
    if operator in {
        "not contains",
        "not_contains",
        "not contain",
        "not_include",
        "not include",
        "not includes",
    }:
        return str(right) not in str(left)
    if operator in {"matches", "regex", "regexp", "matches regex", "match_regex"}:
        return _condition_regex_match(left, right)
    if operator in {"not matches", "not_matches", "not regex", "not_regex", "does not match"}:
        return not _condition_regex_match(left, right)
    if operator in {"in", "is in", "one_of", "one of", "belongs_to", "belongs to"}:
        return _condition_membership(left, right)
    if operator in {
        "not in",
        "not_in",
        "not one of",
        "not_one_of",
        "not belongs to",
        "not_belongs_to",
    }:
        return not _condition_membership(left, right)
    if operator in {"starts with", "start with", "start_with", "starts_with", "startswith"}:
        return str(left).startswith(str(right))
    if operator in {
        "not starts with",
        "not start with",
        "not_start_with",
        "not_starts_with",
        "not startswith",
    }:
        return not str(left).startswith(str(right))
    if operator in {"ends with", "end with", "end_with", "ends_with", "endswith"}:
        return str(left).endswith(str(right))
    if operator in {
        "not ends with",
        "not end with",
        "not_end_with",
        "not_ends_with",
        "not endswith",
    }:
        return not str(left).endswith(str(right))
    if operator in {"empty", "is empty"}:
        return left in (None, "", [], {})
    if operator in {"not empty", "not_empty", "is not empty"}:
        return left not in (None, "", [], {})
    if operator in {"exists", "exist", "present", "is present"}:
        return left is not None
    if operator in {"not exists", "not_exist", "not exist", "missing", "is missing"}:
        return left is None
    if operator in {"null", "is null", "none", "is none"}:
        return left is None
    if operator in {"not null", "not_null", "is not null", "not none", "is not none"}:
        return left is not None
    if operator in {"true", "is true", "boolean true"}:
        return _as_bool(left) is True
    if operator in {"false", "is false", "boolean false"}:
        return _as_bool(left) is False
    if operator in {"after", "date_after", "time_after", "later than"}:
        return _compare_condition_values(left, right) > 0
    if operator in {"on or after", "date_on_or_after", "time_on_or_after"}:
        return _compare_condition_values(left, right) >= 0
    if operator in {"before", "date_before", "time_before", "earlier than"}:
        return _compare_condition_values(left, right) < 0
    if operator in {"on or before", "date_on_or_before", "time_on_or_before"}:
        return _compare_condition_values(left, right) <= 0
    if operator in {">", "greater than", "gt"}:
        return _compare_condition_values(left, right) > 0
    if operator in {">=", "greater than or equal", "ge"}:
        return _compare_condition_values(left, right) >= 0
    if operator in {"<", "less than", "lt"}:
        return _compare_condition_values(left, right) < 0
    if operator in {"<=", "less than or equal", "le"}:
        return _compare_condition_values(left, right) <= 0
    raise WorkflowExecutionError(f"workflow_condition_operator_not_supported:{operator}")


def _condition_regex_match(left: Any, right: Any) -> bool:
    try:
        return re.search(str(right), str(left)) is not None
    except re.error as exc:
        raise WorkflowExecutionError("workflow_condition_regex_invalid") from exc


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "no", "n", "0", "off"}:
            return False
    return None


def _compare_condition_values(left: Any, right: Any) -> int:
    left_temporal = _as_temporal(left)
    right_temporal = _as_temporal(right)
    if left_temporal is not None and right_temporal is not None:
        return (left_temporal > right_temporal) - (left_temporal < right_temporal)

    left_number = _as_number(left)
    right_number = _as_number(right)
    return (left_number > right_number) - (left_number < right_number)


def _condition_membership(left: Any, right: Any) -> bool:
    if isinstance(right, (list, tuple, set)):
        return any(left == candidate for candidate in right)
    if isinstance(left, (list, tuple, set)):
        return any(item == right for item in left)
    if isinstance(right, str):
        return str(left) in right
    return left == right


def _resolve_condition_left(condition: dict[str, Any], variables: dict[str, Any]) -> Any:
    selector = condition.get("variable_selector") or condition.get("selector")
    if isinstance(selector, list):
        return _resolve_path(variables, _selector_to_key(selector))
    if isinstance(selector, str):
        return _resolve_path(variables, selector)
    variable = condition.get("variable") or condition.get("left") or condition.get("key")
    if isinstance(variable, str):
        return _resolve_path(variables, variable)
    return condition.get("actual")


def _resolve_condition_right(condition: dict[str, Any], variables: dict[str, Any]) -> Any:
    if "value" in condition:
        return _resolve_value(condition.get("value"), variables)
    selector = (
        condition.get("value_selector")
        or condition.get("valueSelector")
        or condition.get("right_selector")
        or condition.get("rightSelector")
        or condition.get("target_selector")
        or condition.get("targetSelector")
    )
    if selector is not None:
        return _resolve_path(variables, _selector_to_key(selector))
    if "right" in condition:
        return _resolve_value(condition.get("right"), variables)
    if "expected" in condition:
        return _resolve_value(condition.get("expected"), variables)
    return None


def _selector_to_key(selector: Any) -> str:
    if isinstance(selector, list):
        return ".".join(str(part) for part in selector if part not in (None, ""))
    if isinstance(selector, str):
        return selector
    return ""


def _initial_workflow_variables(
    workflow_input: dict[str, Any],
    *,
    start_node: dict[str, Any],
) -> dict[str, Any]:
    defaults = _start_input_defaults(start_node)
    if not defaults:
        return _normalize_workflow_input(workflow_input)
    return _normalize_workflow_input({**defaults, **workflow_input})


def _start_input_defaults(start_node: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(start_node.get("data"))
    defaults: dict[str, Any] = {}
    for raw_variables in (data.get("variables"), data.get("inputs")):
        defaults.update(_defaults_from_start_variables(raw_variables))
    for raw_schema in (
        data.get("input_schema"),
        data.get("inputSchema"),
        data.get("schema"),
        data.get("parameters"),
    ):
        defaults.update(_defaults_from_json_schema(raw_schema))
    return defaults


def _validate_start_required_inputs(start_node: dict[str, Any], variables: dict[str, Any]) -> None:
    for input_field in _start_required_input_fields(start_node):
        if _resolve_path(variables, input_field) in (None, "", [], {}):
            raise WorkflowExecutionError(f"workflow_start_required_input_missing:{input_field}")


def _validate_start_input_contract(start_node: dict[str, Any], variables: dict[str, Any]) -> None:
    for input_field, rule in _start_input_rules(start_node).items():
        value = _resolve_path(variables, input_field)
        if value in (None, "", [], {}):
            continue
        expected_types = rule.get("types") or []
        if expected_types and not _matches_start_input_type(value, expected_types):
            raise WorkflowExecutionError(
                f"workflow_start_input_type_mismatch:{input_field}:{'|'.join(expected_types)}"
            )
        enum_values = rule.get("enum") or []
        if enum_values and not any(value == candidate for candidate in enum_values):
            raise WorkflowExecutionError(f"workflow_start_input_enum_mismatch:{input_field}")
        _validate_start_input_constraints(input_field, value, _as_dict(rule.get("constraints")))


def _start_required_input_fields(start_node: dict[str, Any]) -> list[str]:
    data = _as_dict(start_node.get("data"))
    required: list[str] = []
    for raw_variables in (data.get("variables"), data.get("inputs")):
        for item in _start_variable_items(raw_variables):
            name = _start_variable_name(item)
            if name and bool(item.get("required")):
                required.append(name)
    for raw_schema in (
        data.get("input_schema"),
        data.get("inputSchema"),
        data.get("schema"),
        data.get("parameters"),
    ):
        schema = _as_dict(raw_schema)
        required.extend(
            str(item).strip() for item in _as_list(schema.get("required")) if str(item).strip()
        )
    return sorted(set(required))


def _start_input_rules(start_node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = _as_dict(start_node.get("data"))
    rules: dict[str, dict[str, Any]] = {}
    for raw_variables in (data.get("variables"), data.get("inputs")):
        for item in _start_variable_items(raw_variables):
            name = _start_variable_name(item)
            if not name:
                continue
            raw_type = (
                item.get("type")
                or item.get("input_type")
                or item.get("inputType")
                or item.get("field_type")
                or item.get("fieldType")
                or item.get("data_type")
                or item.get("dataType")
                or item.get("variable_type")
                or item.get("variableType")
            )
            _merge_start_input_rule(
                rules,
                name,
                types=_normalize_start_input_types(raw_type),
                enum_values=_start_enum_values(item),
                constraints=_start_input_constraints(item, raw_type=raw_type),
            )
    for raw_schema in (
        data.get("input_schema"),
        data.get("inputSchema"),
        data.get("schema"),
        data.get("parameters"),
    ):
        schema = _as_dict(raw_schema)
        for key, raw_property in _as_dict(schema.get("properties")).items():
            property_schema = _as_dict(raw_property)
            _merge_start_input_rule(
                rules,
                str(key),
                types=_normalize_start_input_types(property_schema.get("type")),
                enum_values=_start_enum_values(property_schema),
                constraints=_start_input_constraints(property_schema),
            )
    return rules


def _start_variable_name(item: dict[str, Any]) -> str:
    return str(
        item.get("variable")
        or item.get("name")
        or item.get("key")
        or item.get("field")
        or item.get("field_name")
        or item.get("fieldName")
        or item.get("parameter")
        or item.get("parameter_name")
        or item.get("parameterName")
        or item.get("id")
        or item.get("label")
        or ""
    ).strip()


def _start_variable_items(raw_variables: Any) -> list[dict[str, Any]]:
    if isinstance(raw_variables, list):
        return [_as_dict(item) for item in raw_variables if isinstance(item, dict)]
    if isinstance(raw_variables, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_variables.items():
            item = dict(raw_item) if isinstance(raw_item, dict) else {"type": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _merge_start_input_rule(
    rules: dict[str, dict[str, Any]],
    field: str,
    *,
    types: list[str],
    enum_values: list[Any],
    constraints: dict[str, Any],
) -> None:
    if not types and not enum_values and not constraints:
        return
    rule = rules.setdefault(field, {"types": [], "enum": [], "constraints": {}})
    for expected_type in types:
        if expected_type not in rule["types"]:
            rule["types"].append(expected_type)
    for candidate in enum_values:
        if not any(candidate == existing for existing in rule["enum"]):
            rule["enum"].append(candidate)
    rule["constraints"].update(constraints)


def _normalize_start_input_types(raw_type: Any) -> list[str]:
    aliases = {
        "str": "string",
        "string": "string",
        "text": "string",
        "paragraph": "string",
        "select": "string",
        "email": "string",
        "url": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "double": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
        "dict": "object",
        "map": "object",
        "file": "object",
        "image": "object",
        "audio": "object",
        "video": "object",
        "document": "object",
        "upload": "object",
        "upload_file": "object",
        "file_upload": "object",
        "files": "array",
        "file-list": "array",
        "file_list": "array",
        "image-list": "array",
        "image_list": "array",
        "uploads": "array",
    }
    normalized: list[str] = []
    raw_types = raw_type if isinstance(raw_type, list) else [raw_type]
    for item in raw_types:
        expected_type = aliases.get(str(item or "").strip().lower())
        if expected_type and expected_type not in normalized:
            normalized.append(expected_type)
    return normalized


def _start_enum_values(item: dict[str, Any]) -> list[Any]:
    for key in ("enum", "options", "choices", "select_options", "selectOptions"):
        if key not in item:
            continue
        raw_values = item.get(key)
        if isinstance(raw_values, list):
            return [_start_option_value(option) for option in raw_values]
    return []


def _start_input_constraints(item: dict[str, Any], *, raw_type: Any = None) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for target, keys in {
        "minLength": ("minLength", "min_length"),
        "maxLength": ("maxLength", "max_length"),
        "minimum": ("minimum", "min_value", "minValue"),
        "maximum": ("maximum", "max_value", "maxValue"),
        "exclusiveMinimum": ("exclusiveMinimum", "exclusive_minimum", "exclusiveMinimumValue"),
        "exclusiveMaximum": ("exclusiveMaximum", "exclusive_maximum", "exclusiveMaximumValue"),
        "minItems": ("minItems", "min_items"),
        "maxItems": ("maxItems", "max_items"),
    }.items():
        value = _first_mapping_value(item, *keys)
        if value is not None:
            constraints[target] = value
    raw_format = item.get("format") or item.get("input_format") or item.get("inputFormat")
    normalized_format = str(raw_format or raw_type or "").strip().lower()
    if normalized_format in {"email", "url", "uri"}:
        constraints["format"] = "url" if normalized_format == "uri" else normalized_format
    return constraints


def _first_mapping_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item.get(key)
    return None


def _start_option_value(option: Any) -> Any:
    if isinstance(option, dict):
        for key in ("value", "name", "label", "key", "id"):
            if key in option:
                return option.get(key)
    return option


def _matches_start_input_type(value: Any, expected_types: list[str]) -> bool:
    for expected_type in expected_types:
        if expected_type == "string" and isinstance(value, str):
            return True
        if expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if (
            expected_type == "number"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            return True
        if expected_type == "boolean" and isinstance(value, bool):
            return True
        if expected_type == "array" and isinstance(value, list):
            return True
        if expected_type == "object" and isinstance(value, dict):
            return True
    return False


def _validate_start_input_constraints(field: str, value: Any, constraints: dict[str, Any]) -> None:
    if not constraints:
        return
    min_length = _optional_int(constraints.get("minLength"))
    if min_length is not None and (not isinstance(value, str) or len(value) < min_length):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:minLength")
    max_length = _optional_int(constraints.get("maxLength"))
    if max_length is not None and (not isinstance(value, str) or len(value) > max_length):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:maxLength")

    minimum = _optional_float(constraints.get("minimum"))
    numeric_value = _start_numeric_value(value)
    if minimum is not None and (numeric_value is None or numeric_value < minimum):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:minimum")
    maximum = _optional_float(constraints.get("maximum"))
    if maximum is not None and (numeric_value is None or numeric_value > maximum):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:maximum")

    exclusive_minimum = _exclusive_threshold(constraints, "exclusiveMinimum", minimum)
    if exclusive_minimum is not None and (
        numeric_value is None or numeric_value <= exclusive_minimum
    ):
        raise WorkflowExecutionError(
            f"workflow_start_input_constraint_violation:{field}:exclusiveMinimum"
        )
    exclusive_maximum = _exclusive_threshold(constraints, "exclusiveMaximum", maximum)
    if exclusive_maximum is not None and (
        numeric_value is None or numeric_value >= exclusive_maximum
    ):
        raise WorkflowExecutionError(
            f"workflow_start_input_constraint_violation:{field}:exclusiveMaximum"
        )

    min_items = _optional_int(constraints.get("minItems"))
    if min_items is not None and (not isinstance(value, list) or len(value) < min_items):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:minItems")
    max_items = _optional_int(constraints.get("maxItems"))
    if max_items is not None and (not isinstance(value, list) or len(value) > max_items):
        raise WorkflowExecutionError(f"workflow_start_input_constraint_violation:{field}:maxItems")

    value_format = str(constraints.get("format") or "").strip().lower()
    if value_format == "email" and not (isinstance(value, str) and _looks_like_email(value)):
        raise WorkflowExecutionError(
            f"workflow_start_input_constraint_violation:{field}:format_email"
        )
    if value_format == "url" and not (isinstance(value, str) and _looks_like_url(value)):
        raise WorkflowExecutionError(
            f"workflow_start_input_constraint_violation:{field}:format_url"
        )


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _start_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _exclusive_threshold(
    constraints: dict[str, Any], key: str, fallback: float | None
) -> float | None:
    value = constraints.get(key)
    if isinstance(value, bool):
        return fallback if value else None
    return _optional_float(value)


def _looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return bool(parsed.scheme and parsed.netloc)


def _defaults_from_start_variables(raw_variables: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for item in _start_variable_items(raw_variables):
        name = _start_variable_name(item)
        if not name:
            continue
        has_default = any(
            key in item for key in ("default", "default_value", "defaultValue", "value")
        )
        if not has_default:
            continue
        defaults[name] = (
            item.get("default")
            if "default" in item
            else item.get("default_value")
            if "default_value" in item
            else item.get("defaultValue")
            if "defaultValue" in item
            else item.get("value")
        )
    return defaults


def _defaults_from_json_schema(raw_schema: Any) -> dict[str, Any]:
    schema = _as_dict(raw_schema)
    properties = _as_dict(schema.get("properties"))
    defaults: dict[str, Any] = {}
    for key, raw_property in properties.items():
        property_schema = _as_dict(raw_property)
        if "default" in property_schema:
            defaults[str(key)] = property_schema.get("default")
    return defaults


def _normalize_workflow_input(workflow_input: dict[str, Any]) -> dict[str, Any]:
    variables = dict(workflow_input)
    query = _first_present_value(variables, "sys.query", "query", "message", "input")
    if query is not None:
        variables.setdefault("query", query)
        variables.setdefault("message", query)
        variables.setdefault("input", query)
        variables.setdefault("sys.query", query)
        sys_payload = variables.get("sys")
        if isinstance(sys_payload, dict):
            sys_payload.setdefault("query", query)
        elif "sys" not in variables:
            variables["sys"] = {"query": query}
    return variables


def _first_present_value(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = _resolve_path(values, key) if "." in key else values.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError("workflow_condition_value_not_numeric") from exc


def _as_temporal(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min)
    return _normalize_datetime(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _execute_end(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    outputs = _end_output_items(data.get("outputs"))
    if outputs:
        result: dict[str, Any] = {}
        for item in outputs:
            item_data = _as_dict(item)
            name = str(
                item_data.get("variable")
                or item_data.get("name")
                or item_data.get("key")
                or item_data.get("output_key")
                or item_data.get("outputKey")
                or ""
            )
            if not name:
                continue
            result[name] = _resolve_end_output_value(item_data, name, variables)
        return result
    direct = _as_dict(data.get("output")) or _as_dict(data.get("result"))
    if direct:
        return {
            str(key): _resolve_end_direct_value(value, variables) for key, value in direct.items()
        }
    return {}


def _end_output_items(raw_outputs: Any) -> list[dict[str, Any]]:
    if isinstance(raw_outputs, list):
        return [_as_dict(item) for item in raw_outputs if isinstance(item, dict)]
    if isinstance(raw_outputs, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_outputs.items():
            if isinstance(raw_item, dict):
                item = dict(raw_item)
            else:
                item = {"value": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _resolve_end_output_value(
    item_data: dict[str, Any], name: str, variables: dict[str, Any]
) -> Any:
    if "value" in item_data:
        return _resolve_end_direct_value(item_data.get("value"), variables)
    selector = (
        item_data.get("value_selector")
        or item_data.get("valueSelector")
        or item_data.get("variable_selector")
        or item_data.get("variableSelector")
        or item_data.get("selector")
    )
    if selector is not None:
        return _resolve_path(variables, _selector_to_key(selector))
    resolved = _resolve_path(variables, name)
    return _resolve_value(f"{{{{{name}}}}}", variables) if resolved is None else resolved


def _resolve_end_direct_value(value: Any, variables: dict[str, Any]) -> Any:
    if _is_text_template_value(value):
        return _render_template(_text_template_to_string(value), variables)
    value_data = _as_dict(value)
    if value_data:
        selector = (
            value_data.get("value_selector")
            or value_data.get("valueSelector")
            or value_data.get("variable_selector")
            or value_data.get("variableSelector")
            or value_data.get("selector")
        )
        if selector is not None and "value" not in value_data:
            return _resolve_path(variables, _selector_to_key(selector))
    return _resolve_value(value, variables)


def _is_text_template_value(value: Any) -> bool:
    if isinstance(value, str):
        return False
    if isinstance(value, list):
        return any(isinstance(item, dict) and _is_text_template_part(item) for item in value)
    return _is_text_template_part(value)


def _is_text_template_part(value: Any) -> bool:
    if isinstance(value, str):
        return True
    if not isinstance(value, dict):
        return False
    part_type = str(value.get("type") or value.get("kind") or "").strip().lower()
    if part_type in {"text", "input_text", "paragraph", "markdown", "template"}:
        return True
    if part_type and part_type not in {"text", "input_text", "paragraph", "markdown", "template"}:
        return False
    text_keys = {"text", "content", "template", "prompt", "message"}
    return bool(set(value) & text_keys) and set(value).issubset(
        text_keys | {"type", "kind", "label", "name", "data"}
    )


def _resolve_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_template(value, variables)
    if isinstance(value, list):
        return [_resolve_structured_value(item, variables) for item in value]
    if isinstance(value, dict):
        return _resolve_structured_value(value, variables)
    return value


def _render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip().strip("#")
        resolved = _resolve_path(variables, key)
        return "" if resolved is None else str(resolved)

    return _TEMPLATE_PATTERN.sub(replace, template)


def _resolve_path(values: dict[str, Any], key: str) -> Any:
    normalized = _normalize_path_key(key)
    current: Any = values
    for part in [piece for piece in normalized.split(".") if piece]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return values.get(key)
            current = current[index]
        else:
            return values.get(key)
    return current


def _normalize_path_key(key: str) -> str:
    normalized = key.replace("#", ".")
    normalized = re.sub(r"\[(\d+)\]", r".\1", normalized)
    return normalized.strip(".")


def _first_string(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
