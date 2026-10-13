"""Deterministic evaluation and isolated live API contract regression tests."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from src.infra.agent.capability_evaluation import (
    compare_reports,
    evaluate_trace,
    load_cases,
    load_traces,
    report_success,
    run_live_case,
    validate_live_target,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "agent_capabilities" / "v1.json"


def case(assertions=None):
    return {
        "case_id": "example",
        "input": "hello",
        "assertions": assertions or [{"kind": "final_contains", "value": "42"}],
    }


def trace(**kwargs):
    return {
        "case_id": "example",
        "user_id": "test-user",
        "session_id": "session-1",
        "events": [{"event_type": "complete", "data": {}}],
        "final": "42",
        **kwargs,
    }


def test_nine_versioned_cases_have_controlled_material_and_mechanical_assertions():
    suite = load_cases(FIXTURES)
    assert suite["version"] == "2"
    assert len(suite["cases"]) == 9
    assert len({item["case_id"] for item in suite["cases"]}) == 9
    assert all(
        item["assertions"] and item["controlled_material"] and item["capability"]
        for item in suite["cases"]
    )


def test_unknown_usage_is_null_and_judge_cannot_override_failure():
    result = evaluate_trace(
        case(), trace(final="wrong", judge={"outcome": "pass"}), user_id="test-user"
    )
    assert result["outcome"] == "fail"
    assert result["failure_stage"] == "assertion"
    assert result["tokens"] == {"input": None, "output": None, "total": None}


def test_missing_terminal_is_error_and_empty_assertions_invalid():
    assert (
        evaluate_trace(case(), trace(events=[]), user_id="test-user")["failure_stage"]
        == "execution"
    )
    with pytest.raises(ValueError, match="assertions"):
        evaluate_trace({"case_id": "example", "assertions": []}, trace(), user_id="test-user")


def test_trace_cannot_include_another_user_or_session_events():
    with pytest.raises(ValueError, match="owner"):
        evaluate_trace(case(), trace(user_id="other"), user_id="test-user")
    with pytest.raises(ValueError, match="session"):
        evaluate_trace(
            case(),
            trace(events=[{"event_type": "complete", "session_id": "other"}]),
            user_id="test-user",
        )


def test_jsonl_diagnostics_and_duplicate_trace_rejected(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps(trace()) + "\n{bad\n")
    with pytest.raises(ValueError, match="line 2"):
        load_traces(path)
    path = path.with_suffix(".json")
    path.write_text(json.dumps([trace(), trace()]))
    with pytest.raises(ValueError, match="duplicate"):
        load_traces(path)


def test_empty_or_all_skip_report_does_not_succeed_and_comparison_checks_version():
    assert not report_success([])
    assert not report_success([{"outcome": "skip"}])
    assert not report_success([{"outcome": "pass"}, {"outcome": "error"}])
    report = {"suite_version": "1", "results": [{"case_id": "example", "outcome": "pass"}]}
    with pytest.raises(ValueError, match="version"):
        compare_reports(report, {**report, "suite_version": "2"})
    with pytest.raises(ValueError, match="case"):
        compare_reports(report, {"suite_version": "1", "results": []})
    assert compare_reports(report, report)["cases"][0]["changed"] is False


def test_real_event_assertions_count_calls_and_effects_without_exposing_secrets():
    data = trace(
        events=[
            {
                "event_type": "tool:start",
                "data": {"tool_call_id": "a", "name": "search", "authorization": "secret"},
            },
            {"event_type": "tool:end", "data": {"tool_call_id": "a", "effect_id": "write-1"}},
            {"event_type": "tool:end", "data": {"tool_call_id": "b", "effect_id": "write-1"}},
            {"event_type": "complete", "data": {}},
        ]
    )
    result = evaluate_trace(case([{"kind": "no_duplicate_effects"}]), data, user_id="test-user")
    assert result["outcome"] == "fail"
    assert result["tool_calls"] == 1
    assert result["duplicate_effects"] == 1
    assert "secret" not in json.dumps(result)


def test_invalid_grader_is_error_not_pass():
    result = evaluate_trace(case(), trace(judge={"outcome": "banana"}), user_id="test-user")
    assert result["outcome"] == "error"
    assert result["failure_stage"] == "grader"


@pytest.mark.parametrize(
    "url",
    [
        "https://lambchat.com",
        "https://api.lambchat.com",
        "http://127.0.0.1:8000/other",
        "http://user:password@localhost:8000",
    ],
)
def test_live_target_requires_explicit_isolated_test_target(url):
    with pytest.raises(ValueError):
        validate_live_target(url, isolated=True)


def test_live_target_requires_isolation_acknowledgement():
    with pytest.raises(ValueError):
        validate_live_target("http://localhost:8021", isolated=False)
    assert validate_live_target("http://localhost:8021", isolated=True) == "http://localhost:8021"


async def test_live_creates_session_submits_json_then_reads_run_scoped_sse_and_cleans_up():
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST" and request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/api/chat/stream":
            assert json.loads(request.content)["session_id"] == "session-1"
            assert request.url.params["agent_id"] == "fast"
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            assert request.url.params["run_id"] == "run-1"
            return httpx.Response(
                200,
                text='event: message:chunk\ndata: {"content":"42"}\n\nevent: complete\ndata: {}\n\n',
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": True})
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client, case(), user_id="test-user", agent_id="fast", timeout=1
        )
    assert result["outcome"] == "pass"
    assert requests[-1].method == "DELETE"


@pytest.mark.parametrize("failure, stage", [(401, "authentication"), ("timeout", "timeout")])
async def test_live_failures_have_distinct_attribution(failure, stage):
    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(failure, json={"detail": "unauthorized"})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client, case(), user_id="test-user", agent_id="fast", timeout=1
        )
    assert result["outcome"] == "error"
    assert result["failure_stage"] == stage


async def test_live_hook_steers_only_the_new_session_on_observed_event():
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/api/chat/stream":
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200,
                text='event: tool:start\ndata: {}\n\nevent: message:chunk\ndata: {"content":"42"}\n\nevent: complete\ndata: {}\n\n',
            )
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client,
            {**case(), "requires_live_hook": True},
            user_id="test-user",
            agent_id="fast",
            timeout=1,
            hooks=[
                {
                    "on_event": "tool:start",
                    "path": "/api/chat/sessions/{session_id}/steer",
                    "body": {"message": "42"},
                }
            ],
        )
    assert result["outcome"] == "pass"
    assert "/api/chat/sessions/session-1/steer" in paths


def test_usage_snapshots_are_not_double_counted_and_missing_resume_usage_is_unknown():
    events = [
        {
            "event_type": "token:usage",
            "run_id": "r1",
            "data": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        },
        {
            "event_type": "token:usage",
            "run_id": "r1",
            "data": {"input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
        },
        {"event_type": "complete", "run_id": "r1", "data": {}},
    ]
    result = evaluate_trace(case(), trace(events=events), user_id="test-user")
    assert result["tokens"]["total"] == 10
    events.append({"event_type": "complete", "run_id": "r2", "data": {}})
    assert (
        evaluate_trace(case(), trace(events=events), user_id="test-user")["tokens"]["total"] is None
    )


async def test_controlled_setup_runs_before_model_submission():
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/__eval__/setup":
            body = json.loads(request.content)
            assert body["session_id"] == "session-1"
            assert body["controlled_material"] == {"value": 42}
            return httpx.Response(200, json={"ready": True})
        if request.url.path == "/api/chat/stream":
            assert paths[-2] == "/__eval__/setup"
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200,
                text='event: message:chunk\ndata: {"content":"42"}\n\nevent: complete\ndata: {}\n\n',
            )
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client,
            {**case(), "controlled_material": {"value": 42}},
            user_id="test-user",
            agent_id="fast",
            timeout=1,
            hooks=[{"on_event": "session_created", "path": "/__eval__/setup"}],
        )
    assert result["outcome"] == "pass"


async def test_mismatched_created_session_owner_is_never_used_or_deleted():
    methods = []

    def respond(request):
        methods.append(request.method)
        return httpx.Response(200, json={"id": "foreign-session", "user_id": "other"})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client, case(), user_id="test-user", agent_id="fast", timeout=1
        )
    assert result["outcome"] == "error"
    assert methods == ["POST"]


@pytest.mark.parametrize("boundary", ["text_id", "tool:start", "run:resumed", "steer:message"])
def test_final_assertions_ignore_intermediate_correct_draft(boundary):
    events = [{"event_type": "message:chunk", "data": {"content": "42", "text_id": "draft"}}]
    if boundary != "text_id":
        events.append({"event_type": boundary, "data": {}})
    events.extend(
        [
            {
                "event_type": "message:chunk",
                "data": {
                    "content": "wrong",
                    "text_id": "final" if boundary == "text_id" else "draft",
                },
            },
            {"event_type": "complete", "data": {}},
        ]
    )
    assert (
        evaluate_trace(case(), trace(final=None, events=events), user_id="test-user")["outcome"]
        == "fail"
    )


def test_final_after_steering_ignores_old_constraints_and_joins_fragmented_chunks():
    events = [
        {"event_type": "message:chunk", "data": {"content": "red", "text_id": "draft"}},
        {"event_type": "steer:message", "data": {"content": "only blue"}},
        {"event_type": "message:chunk", "data": {"content": "bl", "text_id": "final"}},
        {"event_type": "message:chunk", "data": {"content": "ue", "text_id": "final"}},
        {"event_type": "message:chunk", "data": {"content": "red", "depth": 1, "text_id": "child"}},
        {"event_type": "complete", "data": {}},
    ]
    assertions = [
        {"kind": "final_contains", "value": "blue"},
        {"kind": "final_not_contains", "value": "red"},
    ]
    assert (
        evaluate_trace(case(assertions), trace(final=None, events=events), user_id="test-user")[
            "outcome"
        ]
        == "pass"
    )


def test_only_last_controlled_run_answer_is_final_but_all_run_evidence_and_usage_remain():
    events = [
        {
            "event_type": "message:chunk",
            "run_id": "r1",
            "data": {"content": "red", "text_id": "answer"},
        },
        {"event_type": "tool:start", "run_id": "r1", "data": {}},
        {
            "event_type": "token:usage",
            "run_id": "r1",
            "data": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        },
        {"event_type": "complete", "run_id": "r1", "data": {}},
        {
            "event_type": "message:chunk",
            "run_id": "r2",
            "data": {"content": "bl", "text_id": "answer"},
        },
        {
            "event_type": "message:chunk",
            "run_id": "r2",
            "data": {"content": "ue", "text_id": "answer"},
        },
        {
            "event_type": "token:usage",
            "run_id": "r2",
            "data": {"input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
        },
        {"event_type": "complete", "run_id": "r2", "data": {}},
    ]
    assertions = [
        {"kind": "final_contains", "value": "blue"},
        {"kind": "final_not_contains", "value": "red"},
        {"kind": "event_count", "event_type": "tool:start"},
    ]
    result = evaluate_trace(case(assertions), trace(final=None, events=events), user_id="test-user")
    assert result["outcome"] == "pass"
    assert result["tool_calls"] == 1
    assert result["tokens"] == {"input": 6, "output": 9, "total": 15}


def test_no_duplicate_effects_cannot_pass_without_an_external_write_witness():
    result = evaluate_trace(
        {
            **case([{"kind": "no_duplicate_effects"}]),
            "controlled_material": {"effect_id": "write-once"},
        },
        trace(),
        user_id="test-user",
    )
    assert result["outcome"] == "error"
    assert result["failure_stage"] == "fixture_evidence"


def test_artifact_claim_in_sse_is_not_a_verified_content_readback():
    result = evaluate_trace(
        case([{"kind": "artifact_equals", "field": "data.content", "value": "42"}]),
        trace(
            events=[
                {
                    "event_type": "artifact:result",
                    "data": {
                        "content": "42",
                        "artifact": {"id": "file:result.json", "path": "/workspace/result.json"},
                    },
                },
                {"event_type": "complete", "data": {}},
            ]
        ),
        user_id="test-user",
    )
    assert result["outcome"] == "error"
    assert result["failure_stage"] == "fixture_evidence"


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"approved": True, "response": "{}"}, "pass"),
        ({"approved": True, "unexpected": "value"}, "error"),
    ],
)
async def test_live_approval_hook_uses_only_supported_query_parameters(params, expected):
    approval_requests = []

    def respond(request):
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/api/chat/stream":
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200,
                text='event: approval_required\ndata: {"id":"approval-1"}\n\nevent: message:chunk\ndata: {"content":"42"}\n\nevent: complete\ndata: {}\n\n',
            )
        if request.url.path == "/human/approval-1/respond":
            approval_requests.append(request)
            if request.url.params.get("approved") != "true":
                return httpx.Response(422, json={"detail": "approved query parameter required"})
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client,
            case(),
            user_id="test-user",
            agent_id="fast",
            timeout=1,
            hooks=[
                {
                    "on_event": "approval_required",
                    "path": "/human/{approval_id}/respond",
                    "params": params,
                }
            ],
        )
    assert result["outcome"] == expected
    if expected == "pass":
        assert len(approval_requests) == 1
        assert dict(approval_requests[0].url.params) == {"approved": "true", "response": "{}"}
    else:
        assert result["failure_stage"] == "protocol"
        assert not approval_requests


def test_effect_witness_requires_the_expected_committed_write_and_reports_duplicates():
    spec = {
        **case([{"kind": "no_duplicate_effects"}]),
        "controlled_material": {"effect_id": "write-once"},
    }
    witness = {
        "kind": "effect_counts",
        "user_id": "test-user",
        "session_id": "session-1",
        "effects": [{"effect_id": "write-once", "attempt_count": 2, "committed_count": 1}],
    }
    assert (
        evaluate_trace(spec, trace(fixture_evidence=[witness]), user_id="test-user")["outcome"]
        == "pass"
    )
    witness["effects"][0]["committed_count"] = 2
    result = evaluate_trace(spec, trace(fixture_evidence=[witness]), user_id="test-user")
    assert result["outcome"] == "fail"
    assert result["duplicate_effects"] == 1
    witness["effects"][0]["committed_count"] = 0
    assert (
        evaluate_trace(spec, trace(fixture_evidence=[witness]), user_id="test-user")["outcome"]
        == "fail"
    )


def test_artifact_witness_must_match_original_event_identity_and_content_hash():
    spec = case([{"kind": "artifact_equals", "field": "data.content", "value": "42"}])
    events = [
        {
            "event_type": "artifact:result",
            "data": {
                "artifact": {"id": "file:result.json", "path": "/workspace/result.json"},
                "success": True,
            },
        },
        {"event_type": "complete", "data": {}},
    ]
    witness = {
        "kind": "artifact_readback",
        "user_id": "test-user",
        "session_id": "session-1",
        "artifact_id": "file:result.json",
        "path": "/workspace/result.json",
        "content": "42",
        "content_sha256": hashlib.sha256(b"42").hexdigest(),
    }
    assert (
        evaluate_trace(spec, trace(events=events, fixture_evidence=[witness]), user_id="test-user")[
            "outcome"
        ]
        == "pass"
    )
    for field, value in (
        ("artifact_id", "unrelated"),
        ("content_sha256", "wrong"),
        ("session_id", "other-session"),
        ("user_id", "other-user"),
    ):
        with pytest.raises(ValueError, match="witness"):
            evaluate_trace(
                spec,
                trace(events=events, fixture_evidence=[{**witness, field: value}]),
                user_id="test-user",
            )


@pytest.mark.parametrize("foreign_owner", [False, True])
async def test_live_collects_scoped_external_effect_witness(foreign_owner):
    observed = []

    def respond(request):
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/api/chat/stream":
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            return httpx.Response(200, text="event: complete\ndata: {}\n\n")
        if request.url.path == "/__eval__/effects":
            body = json.loads(request.content)
            observed.append(body)
            return httpx.Response(
                200,
                json={
                    "witness": {
                        "kind": "effect_counts",
                        "session_id": "session-1",
                        "user_id": "other" if foreign_owner else "test-user",
                        "effects": [
                            {"effect_id": "write", "attempt_count": 1, "committed_count": 1}
                        ],
                    }
                },
            )
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client,
            {
                **case([{"kind": "no_duplicate_effects"}]),
                "controlled_material": {"effect_id": "write"},
            },
            user_id="test-user",
            agent_id="fast",
            timeout=1,
            hooks=[
                {
                    "on_event": "complete",
                    "path": "/__eval__/effects",
                    "collect": "effect_counts",
                }
            ],
        )
    assert result["outcome"] == ("error" if foreign_owner else "pass")
    assert observed[0]["session_id"] == "session-1"
    assert observed[0]["observed_event"]["run_id"] == "run-1"


def _compression_result(summary_events):
    compression = next(
        item
        for item in load_cases(FIXTURES)["cases"]
        if item["case_id"] == "compression_continuation"
    )
    return evaluate_trace(
        compression,
        trace(
            case_id=compression["case_id"],
            final="CAP-731",
            events=[*summary_events, {"event_type": "complete", "data": {}}],
        ),
        user_id="test-user",
    )


def _summary_chunk(identity, content):
    # Current presenter wire schema: multiple chunks share the model message ID.
    return {
        "event_type": "summary",
        "data": {"summary_id": identity, "content": content, "depth": 0},
    }


def test_compression_two_chunks_of_one_summary_do_not_satisfy_two_summaries():
    events = [
        _summary_chunk("summary-one", "first chunk "),
        _summary_chunk("summary-one", "second chunk"),
        # One successful compression does not prove two completed cycles.
        _summary_stats("1700000000000-0"),
    ]
    assert _compression_result(events)["outcome"] == "fail"


def test_compression_unfinished_summary_streams_do_not_prove_two_completions():
    events = [
        _summary_chunk("first-partial", "partial"),
        _summary_chunk("second-partial", "partial"),
    ]
    assert _compression_result(events)["outcome"] == "fail"


def test_compression_unidentified_chunks_do_not_prove_completion():
    events = [_summary_chunk(None, "first"), _summary_chunk(None, "second")]
    assert _compression_result(events)["outcome"] == "fail"


def test_generic_event_count_keeps_counting_individual_frames():
    result = evaluate_trace(
        case([{"kind": "event_count", "event_type": "summary", "min_count": 2}]),
        trace(
            events=[
                _summary_chunk("same", "first"),
                _summary_chunk("same", "second"),
                {"event_type": "complete", "data": {}},
            ]
        ),
        user_id="test-user",
    )
    assert result["outcome"] == "pass"


def _summary_stats(identity, *, run_id="run-1", **data):
    return {
        "event_type": "summary",
        "id": identity,
        "run_id": run_id,
        "data": {"summary_id": None, "content": "", "freed_tokens": 200, **data},
    }


def test_compression_counts_two_distinct_completed_stats_without_summary_ids():
    assert (
        _compression_result(
            [
                _summary_stats("1700000000000-0"),
                _summary_stats("1700000000000-1"),
            ]
        )["outcome"]
        == "pass"
    )


def test_compression_scopes_durable_ids_to_the_original_run():
    assert (
        _compression_result(
            [
                _summary_stats("1700000000000-0"),
                _summary_stats("1700000000000-0", run_id="run-2"),
            ]
        )["outcome"]
        == "pass"
    )


@pytest.mark.parametrize(
    "second",
    [
        _summary_stats("1700000000000-0"),
        _summary_stats(None),
        {key: value for key, value in _summary_stats("1700000000000-1").items() if key != "id"},
        _summary_stats("heartbeat"),
        _summary_stats("0-0"),
        _summary_stats("18446744073709551616-0"),
        _summary_stats("1700000000000-1", run_id=""),
        _summary_stats("1700000000000-1", run_id=" "),
        _summary_stats("1700000000000-1", run_id=None),
        _summary_stats("1700000000000-1", depth=1),
        _summary_stats("1700000000000-1", freed_tokens=True),
        _summary_stats("1700000000000-1", freed_tokens=0),
        _summary_stats("1700000000000-1", freed_tokens=-1),
        _summary_stats("1700000000000-1", freed_tokens="200"),
        _summary_stats("1700000000000-1", freed_tokens=1.5),
    ],
)
def test_compression_does_not_count_duplicate_or_invalid_completion_stats(second):
    assert _compression_result([_summary_stats("1700000000000-0"), second])["outcome"] == "fail"


@pytest.mark.parametrize(
    "second_id, expected",
    [
        ("1700000000000-1", "pass"),
        ("1700000000000-0", "fail"),
        (None, "fail"),
    ],
)
async def test_live_summary_count_preserves_original_sse_ids(monkeypatch, second_id, expected):
    from src.infra.agent import capability_evaluation as evaluation

    captured = []
    original_evaluate = evaluation.evaluate_trace

    def capture(case, record, **kwargs):
        captured.extend(record["events"])
        return original_evaluate(case, record, **kwargs)

    monkeypatch.setattr(evaluation, "evaluate_trace", capture)

    def respond(request):
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "session-1", "user_id": "test-user"})
        if request.url.path == "/api/chat/stream":
            return httpx.Response(200, json={"session_id": "session-1", "run_id": "run-1"})
        if request.url.path.endswith("/stream"):
            frames = []
            for identity in ("1700000000000-0", second_id):
                event = _summary_stats(identity)
                frame = f"event: summary\ndata: {json.dumps(event['data'])}\n"
                if identity is not None:
                    frame += f"id: {identity}\n"
                frames.append(frame + "\n")
            return httpx.Response(
                200, text="".join(frames) + "id: 1700000000000-2\n\nevent: complete\ndata: {}\n\n"
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": True})
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        base_url="http://localhost:8021", transport=httpx.MockTransport(respond)
    ) as client:
        result = await run_live_case(
            client,
            case([{"kind": "summary_count", "min_count": 2}]),
            user_id="test-user",
            agent_id="fast",
            timeout=1,
        )
    assert result["outcome"] == expected
    assert captured[0]["id"] == "1700000000000-0"
    assert captured[1].get("id") == second_id
    assert "id" not in captured[2]
    assert all(event["run_id"] == "run-1" for event in captured)


@pytest.mark.parametrize(
    "tool,success",
    [("reveal_file", True), ("other", True), ("reveal_file", False), ("reveal_file", None)],
)
def test_reveal_file_readback_requires_successful_original_tool_result(tool, success):
    spec = case([{"kind": "artifact_equals", "field": "data.content", "value": "42"}])
    event = {
        "event_type": "tool:result",
        "data": {
            "tool": tool,
            "success": success,
            "result": {
                "key": "revealed_files/result.json",
                "_meta": {"path": "/workspace/result.json"},
            },
        },
    }
    witness = {
        "kind": "artifact_readback",
        "user_id": "test-user",
        "session_id": "session-1",
        "artifact_id": "revealed_files/result.json",
        "path": "/workspace/result.json",
        "content": "42",
        "content_sha256": hashlib.sha256(b"42").hexdigest(),
    }
    record = trace(
        events=[event, {"event_type": "complete", "data": {}}], fixture_evidence=[witness]
    )
    if tool == "reveal_file" and success is True:
        assert evaluate_trace(spec, record, user_id="test-user")["outcome"] == "pass"
        witness["path"] = "/workspace/other.json"
    with pytest.raises(ValueError, match="artifact witness"):
        evaluate_trace(spec, record, user_id="test-user")


def test_insufficient_evidence_fixture_requires_unambiguous_exact_reply():
    spec = next(
        item for item in load_cases(FIXTURES)["cases"] if item["case_id"] == "insufficient_evidence"
    )
    assert "Reply exactly EVIDENCE_MISSING and nothing else" in spec["input"]
    assert {"kind": "final_not_contains", "value": "tests passed"} in spec["assertions"]


@pytest.mark.parametrize(
    "result,expected", [({"success": False}, "fail"), ({"success": True}, "pass"), ("done", "pass")]
)
def test_tool_success_requires_successful_structured_result(result, expected):
    spec = case([{"kind": "tool_succeeded", "tool": "web_fetch"}])
    record = trace(
        events=[
            {
                "event_type": "tool:result",
                "data": {"tool": "web_fetch", "success": True, "result": result},
            },
            {"event_type": "done", "data": {}},
        ]
    )
    assert evaluate_trace(spec, record, user_id="test-user")["outcome"] == expected


def test_fallback_fixture_checks_provider_result_not_transport_success():
    spec = next(
        item
        for item in load_cases(FIXTURES)["cases"]
        if item["case_id"] == "tool_failure_alternative"
    )
    assert spec["assertions"][0]["field"] == "data.result.success"
