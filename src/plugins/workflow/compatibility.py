"""Workflow node compatibility catalog for import, runtime, and UI reporting."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

CompatibilityStatus = Literal["supported", "guarded", "blocked"]


class WorkflowNodeCompatibility(TypedDict):
    source_type: str
    internal_type: str | None
    status: CompatibilityStatus
    aliases: list[str]
    runtime: str
    publish_requirements: list[str]
    notes: list[str]


COMPATIBILITY_MATRIX: list[WorkflowNodeCompatibility] = [
    {
        "source_type": "start",
        "internal_type": "start",
        "status": "supported",
        "aliases": ["start"],
        "runtime": "local",
        "publish_requirements": [],
        "notes": ["Workflow entry node."],
    },
    {
        "source_type": "end",
        "internal_type": "end",
        "status": "supported",
        "aliases": ["end"],
        "runtime": "local",
        "publish_requirements": [],
        "notes": [
            "Terminal output node.",
            "Supports structured outputs plus text-part descriptor values.",
        ],
    },
    {
        "source_type": "answer",
        "internal_type": "answer",
        "status": "supported",
        "aliases": ["answer", "output"],
        "runtime": "local",
        "publish_requirements": [],
        "notes": [
            "Renders answer text with workflow variables.",
            "Accepts string answers, text-part arrays, and text descriptor objects.",
        ],
    },
    {
        "source_type": "condition",
        "internal_type": "condition",
        "status": "supported",
        "aliases": ["condition", "if-else", "if_else"],
        "runtime": "local",
        "publish_requirements": [],
        "notes": [
            "Supports boolean and case branch handles with fallback routing.",
            "Supports nested AND/OR condition groups, including rules/children aliases and negated groups.",
            "Supports scalar, string, presence, boolean, membership, regex, numeric, and ISO date/time comparisons.",
        ],
    },
    {
        "source_type": "variable_assign",
        "internal_type": "variable_assign",
        "status": "supported",
        "aliases": ["variable_assign", "variable-assigner", "assigner"],
        "runtime": "local",
        "publish_requirements": [],
        "notes": [
            "Assigns static, templated, structured, or selector-backed variables.",
            "Accepts variables/items plus imported variable_assignments and list-shaped assignments.",
        ],
    },
    {
        "source_type": "template-transform",
        "internal_type": "template_transform",
        "status": "supported",
        "aliases": [
            "template-transform",
            "template_transform",
            "template",
            "data-transform",
            "data_transform",
            "data transform",
        ],
        "runtime": "local",
        "publish_requirements": ["template"],
        "notes": [
            "Renders a template into an output variable.",
            "Covers imported data-transform nodes that produce rendered text from workflow variables.",
            "Accepts string templates, text-part arrays, and text descriptor objects.",
        ],
    },
    {
        "source_type": "variable-aggregator",
        "internal_type": "variable_aggregator",
        "status": "supported",
        "aliases": ["variable-aggregator", "variable_aggregator", "aggregator"],
        "runtime": "local",
        "publish_requirements": ["selectors"],
        "notes": [
            "Aggregates selector descriptors or selector mappings using first-non-empty or list modes."
        ],
    },
    {
        "source_type": "list-operator",
        "internal_type": "list_operator",
        "status": "supported",
        "aliases": ["list-operator", "list_operator", "list operator", "list"],
        "runtime": "local",
        "publish_requirements": ["input selector"],
        "notes": [
            "Supports bounded local list operations: first, last, count, join, slice, item-at, reverse, unique, field pluck, filter, find, any/all/none predicates, match counts, sort, and numeric aggregations."
        ],
    },
    {
        "source_type": "document-extractor",
        "internal_type": "document_extractor",
        "status": "supported",
        "aliases": [
            "document-extractor",
            "document_extractor",
            "document extractor",
            "doc-extractor",
        ],
        "runtime": "local",
        "publish_requirements": ["input selector"],
        "notes": [
            "Extracts text from file metadata or document payloads already supplied to the workflow.",
            "Unwraps common nested imported file/document envelopes and page/chunk lists when extracted text is already present.",
            "Does not fetch remote URLs, read local files, or perform OCR.",
        ],
    },
    {
        "source_type": "llm",
        "internal_type": "llm",
        "status": "guarded",
        "aliases": ["llm"],
        "runtime": "llm_invoker",
        "publish_requirements": ["llm runtime", "prompt or messages"],
        "notes": [
            "Uses LambChat model resolution; publish does not call the model.",
            "Accepts string prompts and imported prompt_template/message entries with role/name aliases.",
            "Flattens text-only message content arrays and ignores non-text multimodal parts.",
            "Passes common imported generation parameters from direct fields, model fields, or nested parameter maps.",
        ],
    },
    {
        "source_type": "parameter-extractor",
        "internal_type": "parameter_extractor",
        "status": "guarded",
        "aliases": ["parameter-extractor", "parameter_extractor", "parameter extractor"],
        "runtime": "llm_invoker",
        "publish_requirements": ["llm runtime", "query or prompt"],
        "notes": [
            "LLM-backed JSON parameter extraction.",
            "Supports query, variable, input, and generic selector aliases for extractor input.",
        ],
    },
    {
        "source_type": "question-classifier",
        "internal_type": "question_classifier",
        "status": "guarded",
        "aliases": [
            "question-classifier",
            "question_classifier",
            "question classifier",
            "classifier",
        ],
        "runtime": "llm_invoker",
        "publish_requirements": ["llm runtime", "classes", "fallback branch for multi-edge graphs"],
        "notes": [
            "LLM-backed single-label classification with source-handle routing.",
            "Supports query, variable, input, and generic selector aliases for classifier input.",
        ],
    },
    {
        "source_type": "tool",
        "internal_type": "tool_call",
        "status": "guarded",
        "aliases": ["tool", "tool_call", "tool-call"],
        "runtime": "internal_tool_registry",
        "publish_requirements": ["tool name available to user"],
        "notes": [
            "Routes only through LambChat internal tools available to the caller.",
            "Accepts dict arguments and imported parameter descriptor lists from tool_configurations/tool_parameters.",
        ],
    },
    {
        "source_type": "http-request",
        "internal_type": "http_request",
        "status": "guarded",
        "aliases": ["http_request", "http-request"],
        "runtime": "http_policy",
        "publish_requirements": ["HTTP_NODE_POLICY=allowlist", "static allowlisted host"],
        "notes": [
            "Blocks local/private hosts and disabled-by-default HTTP execution.",
            "Accepts dict or descriptor-list headers/query params plus request_body/requestBody aliases.",
        ],
    },
    {
        "source_type": "code",
        "internal_type": None,
        "status": "blocked",
        "aliases": ["code"],
        "runtime": "blocked_by_policy",
        "publish_requirements": ["CODE_NODE_POLICY currently blocks execution"],
        "notes": ["Preserved as unsupported placeholder during import."],
    },
    {
        "source_type": "sub-workflow",
        "internal_type": "sub_workflow",
        "status": "guarded",
        "aliases": ["sub-workflow", "sub_workflow", "sub workflow"],
        "runtime": "nested_workflow_runner",
        "publish_requirements": [
            "owned child workflow",
            "published or pinned child version",
            "cycle checks",
        ],
        "notes": [
            "Runs an owned LambChat workflow as a nested call.",
            "Requires static dependency validation and bounded nesting depth.",
            "Does not import or execute external app ids directly.",
        ],
    },
    {
        "source_type": "human-approval",
        "internal_type": "human_approval",
        "status": "guarded",
        "aliases": ["human-approval", "human_approval", "human approval", "approval"],
        "runtime": "workflow_pause_resume",
        "publish_requirements": ["durable run pause", "resume API"],
        "notes": [
            "Pauses the workflow run with pending approval metadata and durable executor state.",
            "Notification and dedicated approval UI remain separate integration work.",
        ],
    },
    {
        "source_type": "knowledge-retrieval",
        "internal_type": "knowledge_retrieval",
        "status": "guarded",
        "aliases": ["knowledge-retrieval", "knowledge_retrieval", "retrieval"],
        "runtime": "memory_retriever",
        "publish_requirements": ["memory backend", "query selector or query template"],
        "notes": [
            "Maps to LambChat memory recall.",
            "Supports literal, templated, and selector-based top_k/score_threshold options.",
            "Optional KNOWLEDGE_DATASET_MAPPINGS maps imported dataset ids to LambChat memory types; unmapped ids remain visible as unresolved metadata.",
        ],
    },
    {
        "source_type": "iteration",
        "internal_type": "iteration",
        "status": "supported",
        "aliases": ["iteration", "loop", "foreach", "for-each", "for_each"],
        "runtime": "local",
        "publish_requirements": ["iterator selector"],
        "notes": [
            "Supports bounded local iteration over list variables with optional item templates.",
            "Item templates may be strings, text-part arrays, or text descriptor objects.",
            "Iteration limits may be literal, templated, or selector-based.",
        ],
    },
]


def compatibility_summary() -> dict[str, int]:
    summary = {"supported": 0, "guarded": 0, "blocked": 0, "total": len(COMPATIBILITY_MATRIX)}
    for item in COMPATIBILITY_MATRIX:
        summary[item["status"]] += 1
    return summary


def node_types_for_catalog() -> list[dict[str, Any]]:
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for item in COMPATIBILITY_MATRIX:
        internal_type = item["internal_type"]
        if not internal_type or internal_type in seen:
            continue
        seen.add(internal_type)
        nodes.append(
            {
                "type": internal_type,
                "status": item["status"],
                "runtime": item["runtime"],
                "source_types": item["aliases"],
                "publish_requirements": item["publish_requirements"],
            }
        )
    return nodes


def compatibility_matrix_payload() -> dict[str, Any]:
    return {
        "summary": compatibility_summary(),
        "items": COMPATIBILITY_MATRIX,
    }
