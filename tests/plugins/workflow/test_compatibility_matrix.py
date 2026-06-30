from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.plugins.workflow.compatibility import (
    COMPATIBILITY_MATRIX,
    compatibility_matrix_payload,
    node_types_for_catalog,
)
from src.plugins.workflow.executor import MinimalWorkflowExecutor, WorkflowExecutionPaused
from src.plugins.workflow.parser import SUPPORTED_NODE_TYPES, parse_workflow
from src.plugins.workflow.policy import build_http_request_policy

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "workflow"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture_name", "expected_types", "lossless", "unsupported_reasons"),
    [
        ("answer_text_parts.json", ["start", "answer"], True, []),
        ("end_text_parts.json", ["start", "end"], True, []),
        ("simple_llm.json", ["start", "llm", "answer"], True, []),
        ("llm_prompt_messages.json", ["start", "llm", "answer"], True, []),
        ("llm_message_parts.json", ["start", "llm", "answer"], True, []),
        ("llm_generation_params.json", ["start", "llm", "answer"], True, []),
        ("condition_branch.json", ["start", "condition", "answer", "answer"], True, []),
        ("condition_nested_groups.json", ["start", "condition", "answer", "answer"], True, []),
        ("http_request.json", ["start", "http_request", "answer"], True, []),
        ("http_request_descriptors.json", ["start", "http_request", "answer"], True, []),
        ("tool_call.json", ["start", "tool_call", "answer"], True, []),
        ("tool_call_parameter_descriptors.json", ["start", "tool_call", "answer"], True, []),
        (
            "template_aggregator.json",
            ["start", "template_transform", "variable_aggregator", "answer"],
            True,
            [],
        ),
        (
            "variable_aggregator_groups.json",
            ["start", "variable_aggregator", "answer"],
            True,
            [],
        ),
        ("template_transform_parts.json", ["start", "template_transform", "answer"], True, []),
        ("data_transform.json", ["start", "template_transform", "answer"], True, []),
        ("variable_assign_aliases.json", ["start", "variable_assign", "answer"], True, []),
        ("list_operator.json", ["start", "list_operator", "answer"], True, []),
        ("list_operator_sort.json", ["start", "list_operator", "answer"], True, []),
        ("list_operator_sum.json", ["start", "list_operator", "answer"], True, []),
        ("list_operator_pluck.json", ["start", "list_operator", "answer"], True, []),
        ("list_operator_filter.json", ["start", "list_operator", "list_operator", "answer"], True, []),
        ("list_operator_predicates.json", ["start", "list_operator", "list_operator", "answer"], True, []),
        ("document_extractor.json", ["start", "document_extractor", "answer"], True, []),
        ("document_extractor_nested_payload.json", ["start", "document_extractor", "answer"], True, []),
        ("parameter_extractor.json", ["start", "parameter_extractor", "answer"], True, []),
        (
            "parameter_extractor_selector_alias.json",
            ["start", "parameter_extractor", "answer"],
            True,
            [],
        ),
        (
            "question_classifier.json",
            ["start", "question_classifier", "answer", "answer"],
            True,
            [],
        ),
        (
            "question_classifier_selector_alias.json",
            ["start", "question_classifier", "answer", "answer"],
            True,
            [],
        ),
        ("unsupported_code.json", ["start", "unsupported"], False, ["blocked_by_policy"]),
        ("unsupported_sub_workflow.json", ["start", "sub_workflow"], True, []),
        ("unsupported_human_approval.json", ["start", "human_approval"], True, []),
        ("human_approval_resume.json", ["start", "human_approval", "answer"], True, []),
        (
            "knowledge_retrieval.json",
            ["start", "knowledge_retrieval", "answer"],
            True,
            [],
        ),
        ("iteration.json", ["start", "iteration"], True, []),
        ("iteration_template_parts.json", ["start", "iteration", "answer"], True, []),
        ("dynamic_runtime_options.json", ["start", "knowledge_retrieval", "iteration"], True, []),
    ],
)
def test_workflow_fixture_compatibility_matrix(
    fixture_name: str,
    expected_types: list[str],
    lossless: bool,
    unsupported_reasons: list[str],
) -> None:
    result = parse_workflow(_fixture(fixture_name), name=fixture_name)

    nodes = result.internal_model["graph"]["nodes"]
    assert [node["type"] for node in nodes] == expected_types
    assert result.report["lossless"] is lossless
    assert [item["reason"] for item in result.report["unsupported_nodes"]] == unsupported_reasons
    assert result.report["metadata"]["detected_node_count"] == len(expected_types)


def test_workflow_condition_fixture_preserves_branch_handles() -> None:
    result = parse_workflow(_fixture("condition_branch.json"), name="Condition")

    edges = result.internal_model["graph"]["edges"]
    handles = {edge["id"]: edge["source_handle"] for edge in edges}

    assert handles["e2"] == "true"
    assert handles["e3"] == "false"


def test_workflow_nested_condition_fixture_executes_group_routing() -> None:
    result = parse_workflow(_fixture("condition_nested_groups.json"), name="Nested Condition")

    matched = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"tier": "pro", "region": "eu", "status": "active"},
    )
    fallback = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"tier": "pro", "region": "apac", "status": "active"},
    )
    blocked = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"tier": "pro", "region": "us", "status": "blocked"},
    )

    assert matched.output == {"answer": "Eligible"}
    assert fallback.output == {"answer": "Fallback"}
    assert blocked.output == {"answer": "Fallback"}


@pytest.mark.asyncio
async def test_workflow_llm_message_parts_fixture_executes_text_flattening() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "fixture ok"}

    result = parse_workflow(_fixture("llm_message_parts.json"), name="LLM Message Parts")
    execution = await MinimalWorkflowExecutor().execute_async(
        result.internal_model,
        workflow_input={"message": "What changed?", "context": "Fixture coverage."},
        llm_invoker=invoke_llm,
    )

    assert requests[0]["messages"] == [
        {"role": "user", "content": "Question: What changed?\nContext: Fixture coverage."},
        {"role": "assistant", "content": "Ready."},
    ]
    assert execution.output == {"answer": "fixture ok"}


def test_workflow_variable_assign_alias_fixture_executes_assignment_lists() -> None:
    result = parse_workflow(_fixture("variable_assign_aliases.json"), name="Variable Assign Aliases")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"items": [{"title": "Alpha"}, {"title": "Beta"}], "name": "LambChat"},
    )

    assert execution.output == {"answer": "Hello LambChat / Alpha / Beta"}


def test_workflow_template_transform_parts_fixture_executes_text_parts() -> None:
    result = parse_workflow(_fixture("template_transform_parts.json"), name="Template Parts")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"name": "Ada", "team": "Core"},
    )

    assert execution.output == {"answer": "Hello Ada from Core"}


def test_workflow_data_transform_fixture_executes_as_template_transform() -> None:
    result = parse_workflow(_fixture("data_transform.json"), name="Data Transform")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"name": "LambChat"},
    )

    assert result.internal_model["graph"]["nodes"][1]["source_type"] == "data-transform"
    assert result.internal_model["graph"]["nodes"][1]["type"] == "template_transform"
    assert result.report["supported_nodes"] == ["answer", "start", "template_transform"]
    assert execution.output == {"answer": "Summary for LambChat"}


def test_workflow_variable_aggregator_groups_fixture_executes_wrapped_selectors() -> None:
    result = parse_workflow(_fixture("variable_aggregator_groups.json"), name="Aggregator Groups")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "profile": {"display_name": "Ada"},
            "account": {"label": "Fallback"},
        },
    )

    assert execution.output == {"answer": "Ada"}


def test_workflow_answer_text_parts_fixture_executes_text_parts() -> None:
    result = parse_workflow(_fixture("answer_text_parts.json"), name="Answer Parts")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"name": "Ada", "team": "Core"},
    )

    assert execution.output == {"answer": "Hello Ada from Core"}


def test_workflow_end_text_parts_fixture_executes_text_parts() -> None:
    result = parse_workflow(_fixture("end_text_parts.json"), name="End Parts")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"name": "Ada", "team": "Core"},
    )

    assert execution.output == {"summary": "Hello Ada from Core", "items": ["alpha", "beta"]}


def test_workflow_iteration_template_parts_fixture_executes_item_template() -> None:
    result = parse_workflow(_fixture("iteration_template_parts.json"), name="Iteration Parts")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={"items": [{"name": "alpha"}, {"name": "beta"}]},
    )

    finished = next(
        event
        for event in execution.events
        if event["node_id"] == "loop" and event["event_type"] == "node_finished"
    )

    assert finished["payload"]["output"]["rendered_items"] == ["0:alpha", "1:beta"]
    assert execution.output == {"answer": "2"}


@pytest.mark.asyncio
async def test_workflow_human_approval_resume_fixture_pauses_and_resumes_to_downstream_answer() -> None:
    result = parse_workflow(_fixture("human_approval_resume.json"), name="Human Approval")

    with pytest.raises(WorkflowExecutionPaused) as exc_info:
        await MinimalWorkflowExecutor().execute_async(
            result.internal_model,
            workflow_input={"name": "LambChat"},
        )

    pause = exc_info.value
    assert str(pause) == "workflow_human_approval_paused:approval"
    assert pause.pending_approval == {
        "node_id": "approval",
        "title": "Manager approval",
        "instructions": "Approve LambChat before continuing.",
        "assignee": "manager",
        "output_key": "approval",
    }
    assert pause.pause_state["variables"]["name"] == "LambChat"

    resumed = await MinimalWorkflowExecutor().resume_async(
        result.internal_model,
        resume_state=pause.pause_state,
        approval_response={"approved": True, "comment": "OK"},
    )

    assert resumed.output == {"answer": "Approved=True comment=OK"}
    assert [event["event_type"] for event in resumed.events] == [
        "human_approval_resumed",
        "node_finished",
        "node_started",
        "node_finished",
    ]


def test_workflow_list_operator_sort_fixture_executes_sort() -> None:
    result = parse_workflow(_fixture("list_operator_sort.json"), name="List Operator Sort")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "items": [
                {"name": "beta", "score": 2},
                {"name": "alpha", "score": 3},
                {"name": "gamma", "score": 1},
            ]
        },
    )

    assert execution.output == {"answer": "alpha"}


def test_workflow_list_operator_sum_fixture_executes_numeric_aggregation() -> None:
    result = parse_workflow(_fixture("list_operator_sum.json"), name="List Operator Sum")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "items": [
                {"name": "alpha", "score": 3},
                {"name": "beta", "score": "2.5"},
                {"name": "ignored"},
            ]
        },
    )

    assert execution.output == {"answer": "5.5"}


def test_workflow_list_operator_pluck_fixture_executes_field_extraction() -> None:
    result = parse_workflow(_fixture("list_operator_pluck.json"), name="List Operator Pluck")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "items": [
                {"profile": {"name": "alpha"}},
                {"profile": {"name": "beta"}},
                {"profile": {}},
            ]
        },
    )

    assert execution.output == {"answer": "alpha/beta"}


def test_workflow_list_operator_filter_fixture_executes_item_conditions() -> None:
    result = parse_workflow(_fixture("list_operator_filter.json"), name="List Operator Filter")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "min_score": 2,
            "items": [
                {"name": "alpha", "score": 1, "active": True},
                {"name": "beta", "score": 3, "active": True},
                {"name": "gamma", "score": 4, "active": False},
                {"name": "delta", "score": "2.5", "active": True},
            ],
        },
    )

    assert execution.output == {"answer": "beta/delta"}


def test_workflow_list_operator_predicate_fixture_executes_find_and_count() -> None:
    result = parse_workflow(_fixture("list_operator_predicates.json"), name="List Operator Predicates")

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "min_score": 2,
            "items": [
                {"name": "alpha", "score": 1, "active": True},
                {"name": "beta", "score": 3, "active": True},
                {"name": "gamma", "score": 4, "active": False},
                {"name": "delta", "score": "2.5", "active": True},
            ],
        },
    )

    assert execution.output == {"answer": "beta/2"}


def test_workflow_document_extractor_nested_fixture_executes_workflow_payload_unwrap() -> None:
    result = parse_workflow(
        _fixture("document_extractor_nested_payload.json"),
        name="Nested Document Extractor",
    )

    execution = MinimalWorkflowExecutor().execute(
        result.internal_model,
        workflow_input={
            "attachments": [
                {"name": "alpha.pdf", "file": {"metadata": {"extracted_text": "Alpha"}}},
                {"name": "beta.pdf", "document": {"pages": [{"page_content": "Beta 1"}, {"text": "Beta 2"}]}},
            ]
        },
    )

    assert execution.output == {"answer": "2:Alpha\nBeta 1\nBeta 2"}


def test_workflow_parser_accepts_edge_node_id_and_data_handle_aliases() -> None:
    result = parse_workflow(
        {
            "version": "0.3.0",
            "workflow": {
                "graph": {
                    "nodes": [
                        {"id": "start", "data": {"type": "start"}},
                        {"id": "branch", "data": {"type": "if-else"}},
                        {"id": "answer", "data": {"type": "answer", "answer": "ok"}},
                    ],
                    "edges": [
                        {
                            "id": "e1",
                            "source_node_id": "start",
                            "target_node_id": "branch",
                        },
                        {
                            "id": "e2",
                            "sourceNodeId": "branch",
                            "targetNodeId": "answer",
                            "data": {"source_handle_id": "true"},
                        },
                    ],
                }
            },
        },
        name="Edge aliases",
    )

    edges = result.internal_model["graph"]["edges"]

    assert result.report["lossless"] is True
    assert result.report["errors"] == []
    assert edges[0]["source"] == "start"
    assert edges[0]["target"] == "branch"
    assert edges[1]["source"] == "branch"
    assert edges[1]["target"] == "answer"
    assert edges[1]["source_handle"] == "true"


def test_workflow_parser_preserves_top_level_node_runtime_fields() -> None:
    result = parse_workflow(
        {
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {
                        "id": "start",
                        "type": "start",
                        "variables": [
                            {"field_name": "topic", "type": "string", "required": True}
                        ],
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "answer": "Topic: {{topic}}",
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer"}],
            },
        },
        name="Top-level node fields",
    )

    nodes = {node["id"]: node for node in result.internal_model["graph"]["nodes"]}

    assert result.report["lossless"] is True
    assert nodes["start"]["data"]["variables"] == [
        {"field_name": "topic", "type": "string", "required": True}
    ]
    assert nodes["answer"]["data"]["answer"] == "Topic: {{topic}}"


def test_workflow_parser_preserves_recent_runtime_compatibility_fields() -> None:
    llm_result = parse_workflow(_fixture("llm_prompt_messages.json"), name="LLM messages")
    llm_params_result = parse_workflow(
        _fixture("llm_generation_params.json"),
        name="LLM generation params",
    )
    http_result = parse_workflow(
        _fixture("http_request_descriptors.json"),
        name="HTTP descriptors",
    )
    tool_result = parse_workflow(
        _fixture("tool_call_parameter_descriptors.json"),
        name="Tool descriptors",
    )
    extractor_result = parse_workflow(
        _fixture("parameter_extractor_selector_alias.json"),
        name="Extractor selector",
    )
    classifier_result = parse_workflow(
        _fixture("question_classifier_selector_alias.json"),
        name="Classifier selector",
    )
    dynamic_result = parse_workflow(
        _fixture("dynamic_runtime_options.json"),
        name="Dynamic options",
    )

    llm_node = llm_result.internal_model["graph"]["nodes"][1]
    llm_params_node = llm_params_result.internal_model["graph"]["nodes"][1]
    http_node = http_result.internal_model["graph"]["nodes"][1]
    tool_node = tool_result.internal_model["graph"]["nodes"][1]
    extractor_node = extractor_result.internal_model["graph"]["nodes"][1]
    classifier_node = classifier_result.internal_model["graph"]["nodes"][1]
    dynamic_nodes = {node["id"]: node for node in dynamic_result.internal_model["graph"]["nodes"]}

    assert llm_node["data"]["prompt_template"][1]["template"] == "Question: {{message}}"
    assert llm_params_node["data"]["model_parameters"]["top_p"] == 0.8
    assert llm_params_node["data"]["model_parameters"]["frequencyPenalty"] == 0.2
    assert http_node["data"]["header_parameters"][0]["name"] == "X-Tenant"
    assert http_node["data"]["query_parameters"][1]["default"] == 3
    assert http_node["data"]["request_body"] == {"mode": "{{mode}}"}
    assert tool_node["data"]["tool_configurations"][1]["value_selector"] == ["sys", "user_id"]
    assert extractor_node["data"]["variable_selector"] == ["payload", "message"]
    assert classifier_node["data"]["variable_selector"] == ["payload", "message"]
    assert dynamic_nodes["knowledge"]["data"]["top_k_selector"] == ["retrieval", "limit"]
    assert dynamic_nodes["knowledge"]["data"]["scoreThreshold"] == "{{retrieval.threshold}}"
    assert dynamic_nodes["loop"]["data"]["max_items_selector"] == ["limits", "max"]


def test_workflow_fixtures_report_credential_references() -> None:
    llm_result = parse_workflow(_fixture("simple_llm.json"), name="Simple LLM")
    http_result = parse_workflow(_fixture("http_request.json"), name="HTTP")

    assert "llm:llm_provider:openai" in llm_result.report["credential_refs_required"]
    assert "llm:provider_credential_id:openai-main" in llm_result.report["credential_refs_required"]
    assert http_result.report["credential_refs_required"] == ["http:http_auth"]


def test_workflow_parser_reports_runtime_credential_reference_aliases() -> None:
    result = parse_workflow(
        {
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {}},
                    {
                        "id": "llm",
                        "type": "llm",
                        "data": {
                            "credential_ref": "llm-top-level",
                            "model": {
                                "provider": "openai",
                                "credential_ref": "llm-model-alias",
                                "provider_credential_id": "openai-nested",
                            },
                        },
                    },
                    {
                        "id": "extract",
                        "type": "parameter-extractor",
                        "data": {
                            "model": {
                                "provider": "anthropic",
                                "providerCredentialId": "anthropic-camel",
                            },
                        },
                    },
                    {
                        "id": "http",
                        "type": "http-request",
                        "data": {
                            "url": "https://example.com/status",
                            "authorization": {"credential_ref": "http-auth-alias"},
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "llm"},
                    {"id": "e2", "source": "llm", "target": "extract"},
                    {"id": "e3", "source": "extract", "target": "http"},
                ],
            },
        },
        name="Credential aliases",
    )

    assert result.report["credential_refs_required"] == [
        "extract:llm_provider:anthropic",
        "extract:provider_credential_id:anthropic-camel",
        "http-auth-alias",
        "http:http_auth",
        "llm-model-alias",
        "llm-top-level",
        "llm:llm_provider:openai",
        "llm:provider_credential_id:openai-nested",
    ]


@pytest.mark.parametrize(
    ("fixture_name", "available_tools", "expected_error"),
    [
        ("answer_text_parts.json", None, None),
        ("end_text_parts.json", None, None),
        ("condition_branch.json", None, None),
        ("condition_nested_groups.json", None, None),
        ("tool_call.json", {"workflow_list"}, None),
        ("tool_call_parameter_descriptors.json", {"workflow_list"}, None),
        ("template_aggregator.json", None, None),
        ("variable_aggregator_groups.json", None, None),
        ("template_transform_parts.json", None, None),
        ("data_transform.json", None, None),
        ("variable_assign_aliases.json", None, None),
        ("list_operator.json", None, None),
        ("list_operator_sort.json", None, None),
        ("list_operator_sum.json", None, None),
        ("list_operator_pluck.json", None, None),
        ("list_operator_filter.json", None, None),
        ("list_operator_predicates.json", None, None),
        (
            "parameter_extractor.json",
            None,
            "workflow_parameter_extractor_node_not_allowed:extract:workflow_llm_invoker_unavailable",
        ),
        (
            "parameter_extractor_selector_alias.json",
            None,
            "workflow_parameter_extractor_node_not_allowed:extract:workflow_llm_invoker_unavailable",
        ),
        (
            "question_classifier.json",
            None,
            "workflow_question_classifier_node_not_allowed:classify:workflow_llm_invoker_unavailable",
        ),
        (
            "question_classifier_selector_alias.json",
            None,
            "workflow_question_classifier_node_not_allowed:classify:workflow_llm_invoker_unavailable",
        ),
        ("tool_call.json", set(), "workflow_tool_not_available:workflow_list"),
        (
            "tool_call_parameter_descriptors.json",
            set(),
            "workflow_tool_not_available:workflow_list",
        ),
        ("iteration.json", None, None),
        ("iteration_template_parts.json", None, None),
        ("document_extractor.json", None, None),
        ("document_extractor_nested_payload.json", None, None),
        ("simple_llm.json", None, "workflow_llm_node_not_allowed:llm:workflow_llm_invoker_unavailable"),
        (
            "llm_prompt_messages.json",
            None,
            "workflow_llm_node_not_allowed:llm:workflow_llm_invoker_unavailable",
        ),
        (
            "llm_message_parts.json",
            None,
            "workflow_llm_node_not_allowed:llm:workflow_llm_invoker_unavailable",
        ),
        (
            "llm_generation_params.json",
            None,
            "workflow_llm_node_not_allowed:llm:workflow_llm_invoker_unavailable",
        ),
        (
            "knowledge_retrieval.json",
            None,
            "workflow_knowledge_retrieval_node_not_allowed:knowledge:workflow_knowledge_retriever_unavailable",
        ),
        (
            "dynamic_runtime_options.json",
            None,
            "workflow_knowledge_retrieval_node_not_allowed:knowledge:workflow_knowledge_retriever_unavailable",
        ),
        (
            "http_request.json",
            None,
            "workflow_http_node_not_allowed:http:workflow_http_policy_disabled",
        ),
        (
            "http_request_descriptors.json",
            None,
            "workflow_http_node_not_allowed:http:workflow_http_policy_disabled",
        ),
        ("unsupported_code.json", None, "workflow_code_node_blocked_by_policy:code"),
        (
            "unsupported_sub_workflow.json",
            None,
            "workflow_sub_workflow_node_not_allowed:subflow:workflow_sub_workflow_refs_unavailable",
        ),
        ("unsupported_human_approval.json", None, None),
        ("human_approval_resume.json", None, None),
    ],
)
def test_workflow_fixture_static_publish_matrix(
    fixture_name: str,
    available_tools: set[str] | None,
    expected_error: str | None,
) -> None:
    parse_result = parse_workflow(_fixture(fixture_name), name=fixture_name)

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        available_tool_names=available_tools,
    )

    if expected_error is None:
        assert validation.errors == []
    else:
        assert expected_error in validation.errors


def test_workflow_http_fixture_static_publish_accepts_allowlisted_host() -> None:
    parse_result = parse_workflow(_fixture("http_request.json"), name="HTTP")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        http_policy=build_http_request_policy(
            policy="allowlist",
            allowlist=["example.com"],
        ),
    )

    assert validation.errors == []


def test_workflow_http_descriptor_fixture_static_publish_accepts_allowlisted_host() -> None:
    parse_result = parse_workflow(_fixture("http_request_descriptors.json"), name="HTTP descriptors")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        http_policy=build_http_request_policy(
            policy="allowlist",
            allowlist=["example.com"],
        ),
    )

    assert validation.errors == []


def test_workflow_llm_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(_fixture("simple_llm.json"), name="Simple LLM")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_llm_prompt_messages_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(_fixture("llm_prompt_messages.json"), name="LLM messages")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_llm_generation_params_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(_fixture("llm_generation_params.json"), name="LLM params")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_parameter_extractor_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(_fixture("parameter_extractor.json"), name="Extractor")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_parameter_extractor_selector_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(
        _fixture("parameter_extractor_selector_alias.json"),
        name="Extractor selector",
    )

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_question_classifier_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(_fixture("question_classifier.json"), name="Classifier")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_question_classifier_selector_fixture_static_publish_accepts_available_llm_runtime() -> None:
    parse_result = parse_workflow(
        _fixture("question_classifier_selector_alias.json"),
        name="Classifier selector",
    )

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        llm_available=True,
    )

    assert validation.errors == []


def test_workflow_knowledge_retrieval_fixture_static_publish_accepts_available_retriever() -> None:
    parse_result = parse_workflow(_fixture("knowledge_retrieval.json"), name="Knowledge")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        knowledge_available=True,
    )

    assert validation.errors == []


def test_workflow_dynamic_runtime_options_fixture_accepts_available_guarded_runtimes() -> None:
    parse_result = parse_workflow(_fixture("dynamic_runtime_options.json"), name="Dynamic")

    validation = MinimalWorkflowExecutor().validate_static(
        parse_result.internal_model,
        knowledge_available=True,
    )

    assert validation.errors == []


def test_workflow_code_fixture_preserves_auditable_blocked_metadata() -> None:
    parse_result = parse_workflow(_fixture("unsupported_code.json"), name="Code")

    code_node = parse_result.internal_model["graph"]["nodes"][1]
    metadata = code_node["metadata"]

    assert code_node["type"] == "unsupported"
    assert code_node["source_type"] == "code"
    assert metadata["policy"] == "code_execution_disabled"
    assert metadata["language"] == "python3"
    assert metadata["source_bytes"] == len("def main(inputs):\n    return inputs".encode("utf-8"))
    assert len(metadata["source_sha256"]) == 64
    assert parse_result.report["unsupported_nodes"][0]["metadata"] == metadata


def test_compatibility_catalog_drives_parser_aliases() -> None:
    for item in COMPATIBILITY_MATRIX:
        internal_type = item["internal_type"]
        if internal_type is None:
            for alias in item["aliases"]:
                assert alias not in SUPPORTED_NODE_TYPES
            continue
        for alias in item["aliases"]:
            assert SUPPORTED_NODE_TYPES[alias] == internal_type


def test_node_type_catalog_exposes_guarded_and_blocked_matrix_items() -> None:
    payload = compatibility_matrix_payload()
    catalog = node_types_for_catalog()

    assert payload["summary"]["total"] == len(COMPATIBILITY_MATRIX)
    assert payload["summary"]["guarded"] >= 1
    assert any(item["type"] == "question_classifier" and item["status"] == "guarded" for item in catalog)
    assert any(item["type"] == "list_operator" and item["status"] == "supported" for item in catalog)
    assert any(item["type"] == "iteration" and item["status"] == "supported" for item in catalog)
    assert any(item["type"] == "document_extractor" and item["status"] == "supported" for item in catalog)
    assert any(
        item["type"] == "template_transform" and "data-transform" in item["source_types"]
        for item in catalog
    )
    assert any(item["type"] == "knowledge_retrieval" and item["status"] == "guarded" for item in catalog)
    assert any(item["type"] == "sub_workflow" and item["status"] == "guarded" for item in catalog)
    assert any(
        item["source_type"] == "code" and item["status"] == "blocked"
        for item in payload["items"]
    )
    assert any(item["source_type"] == "sub-workflow" and item["status"] == "guarded" for item in payload["items"])
    assert any(
        item["source_type"] == "human-approval" and item["status"] == "guarded"
        for item in payload["items"]
    )
