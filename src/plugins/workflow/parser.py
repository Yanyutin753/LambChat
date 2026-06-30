"""External workflow DSL to LambChat workflow model mapper."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from src.plugins.workflow.compatibility import COMPATIBILITY_MATRIX
from src.plugins.workflow.models import WORKFLOW_MODEL_FORMAT

SUPPORTED_NODE_TYPES: dict[str, str] = {
    alias: item["internal_type"]
    for item in COMPATIBILITY_MATRIX
    if item["internal_type"]
    for alias in item["aliases"]
}

BLOCKED_BY_POLICY_TYPES = {
    alias
    for item in COMPATIBILITY_MATRIX
    if item["status"] == "blocked"
    for alias in item["aliases"]
}
CODE_NODE_POLICY = "code_execution_disabled"
LLM_CREDENTIAL_NODE_TYPES = {"llm", "parameter_extractor", "question_classifier"}
EXPLICIT_CREDENTIAL_REF_KEYS = ("credential_ref", "credentialRef")
LEGACY_CREDENTIAL_ID_KEYS = ("credential_id", "credentialId")
PROVIDER_CREDENTIAL_ID_KEYS = ("provider_credential_id", "providerCredentialId")


@dataclass(frozen=True)
class WorkflowPluginParseResult:
    internal_model: dict[str, Any]
    report: dict[str, Any]


def parse_workflow(source_payload: dict[str, Any], *, name: str) -> WorkflowPluginParseResult:
    """Convert an external workflow payload into the first LambChat workflow schema."""
    graph = _extract_graph(source_payload)
    raw_nodes = _as_list(graph.get("nodes"))
    raw_edges = _as_list(graph.get("edges"))
    nodes, supported_types, unsupported_nodes = _parse_nodes(raw_nodes)
    node_types_by_id = {str(node["id"]): str(node.get("type") or "") for node in nodes}
    edges, dangling_edge_errors, boundary_edge_errors = _parse_edges(
        raw_edges,
        known_node_ids=set(node_types_by_id),
        node_types_by_id=node_types_by_id,
    )
    credential_refs = _detect_credential_refs(nodes)

    source_version = str(
        source_payload.get("version")
        or _as_dict(source_payload.get("app")).get("version")
        or "unknown"
    )
    internal_model = {
        "format": WORKFLOW_MODEL_FORMAT,
        "source": "workflow",
        "source_version": source_version,
        "name": name,
        "source_app": _as_dict(source_payload.get("app")),
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "validation": {
            "has_unsupported_nodes": bool(unsupported_nodes),
            "dangling_edge_count": len(dangling_edge_errors),
            "boundary_edge_count": len(boundary_edge_errors),
            "runnable": not unsupported_nodes
            and not dangling_edge_errors
            and not boundary_edge_errors,
        },
    }
    warnings = []
    if not nodes:
        warnings.append("No workflow nodes were detected in this payload.")
    if unsupported_nodes:
        warnings.append("Unsupported workflow nodes were preserved as placeholders.")
    if dangling_edge_errors:
        warnings.append("Some workflow edges reference missing nodes and were marked invalid.")
    if boundary_edge_errors:
        warnings.append(
            "Some workflow edges cross entry or exit boundaries and were marked invalid."
        )
    edge_errors = [*dangling_edge_errors, *boundary_edge_errors]
    report = {
        "source": "workflow",
        "source_version": source_version,
        "workflow_id": None,
        "supported_nodes": sorted(supported_types),
        "unsupported_nodes": unsupported_nodes,
        "credential_refs_required": credential_refs,
        "warnings": warnings,
        "errors": edge_errors,
        "lossless": not unsupported_nodes and not edge_errors,
        "metadata": {"name": name, "detected_node_count": len(nodes), "edge_count": len(edges)},
    }
    return WorkflowPluginParseResult(internal_model=internal_model, report=report)


def _extract_graph(source_payload: dict[str, Any]) -> dict[str, Any]:
    workflow = _as_dict(source_payload.get("workflow"))
    workflow_graph = _as_dict(workflow.get("graph"))
    if workflow_graph:
        return workflow_graph
    if workflow.get("nodes") or workflow.get("edges"):
        return workflow
    graph = _as_dict(source_payload.get("graph"))
    if graph:
        return graph
    return source_payload


def _parse_nodes(
    raw_nodes: list[Any],
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    supported_types: set[str] = set()
    unsupported_nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_node in enumerate(raw_nodes):
        node = _as_dict(raw_node)
        node_data = _node_data_from_raw_node(node)
        node_id = str(node.get("id") or node_data.get("id") or f"node_{index + 1}")
        if node_id in seen_ids:
            node_id = f"{node_id}_{index + 1}"
        seen_ids.add(node_id)
        source_type = str(node_data.get("type") or node.get("type") or "unknown")
        normalized_source_type = source_type.strip().lower()
        mapped_type = SUPPORTED_NODE_TYPES.get(normalized_source_type)
        title = str(
            node_data.get("title") or node.get("title") or node_data.get("label") or node_id
        )
        position = _as_dict(node.get("position")) or _as_dict(node.get("positionAbsolute"))
        metadata: dict[str, Any] = {}
        if mapped_type is None:
            reason = (
                "blocked_by_policy"
                if normalized_source_type in BLOCKED_BY_POLICY_TYPES
                else "unsupported_node_type"
            )
            mapped_type = "unsupported"
            metadata = _unsupported_node_metadata(
                node_data,
                source_type=source_type,
                normalized_source_type=normalized_source_type,
                reason=reason,
            )
            unsupported_nodes.append(
                {
                    "id": node_id,
                    "type": source_type,
                    "title": title,
                    "reason": reason,
                    "metadata": metadata,
                }
            )
        else:
            supported_types.add(mapped_type)

        nodes.append(
            {
                "id": node_id,
                "type": mapped_type,
                "source_type": source_type,
                "title": title,
                "data": node_data,
                "position": position,
                "supported": mapped_type != "unsupported",
                "metadata": metadata,
            }
        )
    return nodes, supported_types, unsupported_nodes


def _node_data_from_raw_node(node: dict[str, Any]) -> dict[str, Any]:
    passthrough = {
        str(key): value
        for key, value in node.items()
        if key
        not in {
            "id",
            "type",
            "title",
            "label",
            "data",
            "position",
            "positionAbsolute",
            "width",
            "height",
            "selected",
            "dragging",
        }
    }
    return {**passthrough, **_as_dict(node.get("data"))}


def _unsupported_node_metadata(
    data: dict[str, Any],
    *,
    source_type: str,
    normalized_source_type: str,
    reason: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "unsupported_reason": reason,
        "source_type": source_type,
    }
    if reason == "blocked_by_policy":
        metadata["runtime_policy"] = "blocked_by_policy"
    if normalized_source_type == "code":
        metadata.update(_code_node_metadata(data))
    return metadata


def _code_node_metadata(data: dict[str, Any]) -> dict[str, Any]:
    source = _first_string(data, "code", "source", "script")
    metadata: dict[str, Any] = {
        "policy": CODE_NODE_POLICY,
        "source_present": bool(source),
        "source_bytes": len(source.encode("utf-8")) if source else 0,
    }
    language = _first_string(data, "language", "code_language", "codeLanguage")
    if language:
        metadata["language"] = language
    if source:
        metadata["source_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return metadata


def _parse_edges(
    raw_edges: list[Any],
    *,
    known_node_ids: set[str],
    node_types_by_id: dict[str, str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    edges: list[dict[str, Any]] = []
    dangling_errors: list[str] = []
    boundary_errors: list[str] = []
    for index, raw_edge in enumerate(raw_edges):
        edge = _as_dict(raw_edge)
        edge_data = _as_dict(edge.get("data"))
        source = _edge_string(
            edge,
            edge_data,
            "source",
            "sourceNode",
            "source_node",
            "sourceNodeId",
            "source_node_id",
            "from",
            "fromNode",
            "from_node",
            "fromNodeId",
            "from_node_id",
        )
        target = _edge_string(
            edge,
            edge_data,
            "target",
            "targetNode",
            "target_node",
            "targetNodeId",
            "target_node_id",
            "to",
            "toNode",
            "to_node",
            "toNodeId",
            "to_node_id",
        )
        edge_id = str(edge.get("id") or f"edge_{index + 1}")
        valid = bool(source and target and source in known_node_ids and target in known_node_ids)
        if not valid:
            dangling_errors.append(f"dangling_edge:{edge_id}:{source}->{target}")
        boundary_error = (
            None
            if not valid
            else _edge_boundary_error(
                edge_id=edge_id,
                source=source,
                target=target,
                node_types_by_id=node_types_by_id,
            )
        )
        if boundary_error:
            boundary_errors.append(boundary_error)
            valid = False
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "source_handle": _edge_optional_value(
                    edge,
                    edge_data,
                    "sourceHandle",
                    "source_handle",
                    "sourceHandleId",
                    "source_handle_id",
                ),
                "target_handle": _edge_optional_value(
                    edge,
                    edge_data,
                    "targetHandle",
                    "target_handle",
                    "targetHandleId",
                    "target_handle_id",
                ),
                "data": edge_data,
                "valid": valid,
            }
        )
    return edges, dangling_errors, boundary_errors


def _edge_boundary_error(
    *,
    edge_id: str,
    source: str,
    target: str,
    node_types_by_id: dict[str, str],
) -> str | None:
    source_type = node_types_by_id.get(source)
    target_type = node_types_by_id.get(target)
    if target_type == "start":
        return f"boundary_edge_targets_entry:{edge_id}:{source}->{target}"
    if source_type == "end" or (source_type == "answer" and target_type != "end"):
        return f"boundary_edge_starts_from_exit:{edge_id}:{source}->{target}"
    return None


def _edge_string(edge: dict[str, Any], edge_data: dict[str, Any], *keys: str) -> str:
    value = _edge_optional_value(edge, edge_data, *keys)
    return "" if value in (None, "") else str(value)


def _edge_optional_value(edge: dict[str, Any], edge_data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in edge and edge.get(key) not in (None, ""):
            return edge.get(key)
        if key in edge_data and edge_data.get(key) not in (None, ""):
            return edge_data.get(key)
    return None


def _detect_credential_refs(nodes: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        data = _as_dict(node.get("data"))
        refs.extend(_explicit_credential_refs(data))
        refs.extend(_derived_credential_refs(node_id, data))
        if node_type in LLM_CREDENTIAL_NODE_TYPES:
            model_data = _as_dict(data.get("model"))
            refs.extend(_explicit_credential_refs(model_data))
            refs.extend(_derived_credential_refs(node_id, model_data))
            provider = model_data.get("provider") or data.get("provider")
            if provider not in (None, ""):
                refs.append(f"{node_id}:llm_provider:{provider}")
        if node_type == "http_request":
            headers = _as_dict(data.get("headers"))
            auth_refs = _http_auth_credential_refs(data)
            refs.extend(auth_refs)
            if headers or _has_http_auth(data) or auth_refs or _has_direct_credential_data(data):
                refs.append(f"{node_id}:http_auth")
    return sorted({str(ref).strip() for ref in refs if str(ref).strip()})


def _explicit_credential_refs(data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in EXPLICIT_CREDENTIAL_REF_KEYS:
        value = data.get(key)
        if value not in (None, ""):
            refs.append(str(value).strip())
    return refs


def _derived_credential_refs(node_id: str, data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in LEGACY_CREDENTIAL_ID_KEYS:
        value = data.get(key)
        if value not in (None, ""):
            refs.append(f"{node_id}:{key}:{value}")
    for key in PROVIDER_CREDENTIAL_ID_KEYS:
        value = data.get(key)
        if value not in (None, ""):
            refs.append(f"{node_id}:provider_credential_id:{value}")
    return refs


def _http_auth_credential_refs(data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for auth_key in ("authorization", "auth"):
        auth = _as_dict(data.get(auth_key))
        refs.extend(_explicit_credential_refs(auth))
        for key in (*LEGACY_CREDENTIAL_ID_KEYS, *PROVIDER_CREDENTIAL_ID_KEYS):
            value = auth.get(key)
            if value not in (None, ""):
                refs.append(str(value).strip())
    return refs


def _has_http_auth(data: dict[str, Any]) -> bool:
    return bool(_as_dict(data.get("authorization")) or _as_dict(data.get("auth")))


def _has_direct_credential_data(data: dict[str, Any]) -> bool:
    for key in (
        *EXPLICIT_CREDENTIAL_REF_KEYS,
        *LEGACY_CREDENTIAL_ID_KEYS,
        *PROVIDER_CREDENTIAL_ID_KEYS,
    ):
        if data.get(key) not in (None, ""):
            return True
    return False


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_string(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""
