from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.plugins.workflow import chat_integration


def _patch_workflow_service_factory(monkeypatch: pytest.MonkeyPatch, service: object) -> None:
    async def _create_service():
        return service

    monkeypatch.setattr(chat_integration, "create_workflow_service", _create_service)


def _expected_interface(
    *,
    workflow_id: str,
    version_id: str | None,
    run_id: str | None,
) -> dict:
    return {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "schema_tool": "workflow_get_schema",
            "schema_field": "input_schema",
        },
        "exit": {
            "type": "workflow.output",
            "field": "output",
            "schema_tool": "workflow_get_schema",
            "schema_field": "output_schema",
        },
        "debug": {
            "tool": "workflow_get_run",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "events_field": "events",
        },
    }


def test_selected_workflow_id_from_plugin_options_accepts_session_and_task_keys() -> None:
    assert (
        chat_integration.selected_workflow_id_from_plugin_options(
            {"workflow": {"SELECTED_WORKFLOW_ID": "wf-session"}}
        )
        == "wf-session"
    )
    assert (
        chat_integration.selected_workflow_id_from_plugin_options(
            {"workflow": {"WORKFLOW_ID": "wf-task"}}
        )
        == "wf-task"
    )
    assert (
        chat_integration.selected_workflow_id_from_plugin_options(
            {"workflow": {"SELECTED_WORKFLOW_ID": "  ", "WORKFLOW_ID": " wf-task "}}
        )
        == "wf-task"
    )


def test_selected_workflow_version_id_from_plugin_options_accepts_session_and_task_keys() -> None:
    assert (
        chat_integration.selected_workflow_version_id_from_plugin_options(
            {"workflow": {"SELECTED_WORKFLOW_VERSION_ID": "wfv-session"}}
        )
        == "wfv-session"
    )
    assert (
        chat_integration.selected_workflow_version_id_from_plugin_options(
            {"workflow": {"WORKFLOW_VERSION_ID": "wfv-task"}}
        )
        == "wfv-task"
    )


def test_selected_workflow_version_id_stays_in_selected_workflow_scope() -> None:
    assert (
        chat_integration.selected_workflow_version_id_from_plugin_options(
            {
                "workflow": {
                    "SELECTED_WORKFLOW_ID": "wf-session",
                    "WORKFLOW_ID": "wf-task",
                    "WORKFLOW_VERSION_ID": "wfv-task",
                }
            }
        )
        is None
    )
    assert (
        chat_integration.selected_workflow_version_id_from_plugin_options(
            {
                "workflow": {
                    "SELECTED_WORKFLOW_ID": "  ",
                    "SELECTED_WORKFLOW_VERSION_ID": "  ",
                    "WORKFLOW_ID": "wf-task",
                    "WORKFLOW_VERSION_ID": " wfv-task ",
                }
            }
        )
        == "wfv-task"
    )
    assert (
        chat_integration.selected_workflow_version_id_from_plugin_options(
            {
                "workflow": {
                    "SELECTED_WORKFLOW_VERSION_ID": "  ",
                    "WORKFLOW_VERSION_ID": " wfv-task ",
                }
            }
        )
        == "wfv-task"
    )


def test_scheduled_workflow_input_from_plugin_options_accepts_json_object_and_string() -> None:
    assert chat_integration.scheduled_workflow_input_from_plugin_options(
        {"workflow": {"WORKFLOW_INPUT_JSON": {"topic": "nightly", "count": 3}}}
    ) == {"topic": "nightly", "count": 3}
    assert chat_integration.scheduled_workflow_input_from_plugin_options(
        {"workflow": {"WORKFLOW_INPUT_JSON": '{"topic":"nightly"}'}}
    ) == {"topic": "nightly"}
    assert (
        chat_integration.scheduled_workflow_input_from_plugin_options(
            {"workflow": {"WORKFLOW_INPUT_JSON": "[1,2]"}}
        )
        == {}
    )


def test_workflow_input_from_plugin_options_accepts_session_input_and_keeps_call_scope() -> None:
    assert chat_integration.session_workflow_input_from_plugin_options(
        {"workflow": {"SELECTED_WORKFLOW_INPUT_JSON": '{"topic":"chat"}'}}
    ) == {"topic": "chat"}
    assert chat_integration.workflow_input_from_plugin_options(
        {
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-chat",
                "WORKFLOW_ID": "wf-task",
                "WORKFLOW_INPUT_JSON": {"topic": "nightly", "count": 3},
                "SELECTED_WORKFLOW_INPUT_JSON": {"topic": "chat"},
            }
        }
    ) == {"topic": "chat"}


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_uses_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            assert workflow_id == "wf-1"
            assert kwargs == {"owner_user_id": "user-1", "version_id": "wfv-selected"}
            return {
                "input_schema": {
                    "type": "object",
                    "required": ["topic"],
                    "properties": {
                        "topic": {"type": "string"},
                        "count": {"type": "integer"},
                        "attachment": {"type": "object", "x-lambchat-input-kind": "file"},
                        "optional_note": {"type": "string"},
                    },
                }
            }

        async def run_workflow(self, **kwargs):
            calls.append(kwargs)
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-1",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-1",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-selected",
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert result == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
        "version_id": "wfv-1",
        "status": "succeeded",
        "output": {"answer": "ok"},
        "error": None,
        "pause": {},
        "interface": _expected_interface(
            workflow_id="wf-1",
            version_id="wfv-1",
            run_id="wfr-1",
        ),
        "next_action": {
            "type": "use_output",
            "field": "output",
            "reason": "workflow_run_succeeded",
        },
    }
    assert calls[0]["workflow_input"] == {
        "message": "hello",
        "input": "hello",
        "query": "hello",
        "sys.query": "hello",
        "sys": {"query": "hello"},
        "topic": "hello",
    }
    assert calls[0]["version_id"] == "wfv-selected"
    assert calls[0]["user"].sub == "user-1"


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_fills_nested_required_entry_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {
                "input_schema": {
                    "type": "object",
                    "required": ["profile", "tags", "files"],
                    "properties": {
                        "profile": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "age": {"type": "integer"},
                            },
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "object", "x-lambchat-input-kind": "file"},
                        },
                        "metadata": {
                            "type": "object",
                            "required": ["topic"],
                            "properties": {"topic": {"type": "string"}},
                        },
                    },
                }
            }

        async def run_workflow(self, **kwargs):
            calls.append(kwargs)
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-1",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    _patch_workflow_service_factory(monkeypatch, _Service())

    await chat_integration.run_selected_workflow_for_message(
        plugin_options={"workflow": {"SELECTED_WORKFLOW_ID": "wf-1"}},
        message="hello nested",
        user_id="user-1",
    )

    assert calls[0]["workflow_input"] == {
        "message": "hello nested",
        "input": "hello nested",
        "query": "hello nested",
        "sys.query": "hello nested",
        "sys": {"query": "hello nested"},
        "profile": {"name": "hello nested"},
        "tags": ["hello nested"],
    }


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_attaches_io_contract_and_output_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {"input_schema": {"type": "object", "properties": {}}}

        async def run_workflow(self, **kwargs):
            calls.append({"stage": "run", **kwargs})
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-run",
                status="succeeded",
                output={"answer": 42, "trace": "kept"},
                error=None,
            )
            return run, []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            calls.append({"stage": "contract", "workflow_id": workflow_id, **kwargs})
            return {
                "workflow_id": workflow_id,
                "version_id": kwargs["version_id"],
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {
                    "type": "object",
                    "required": ["answer", "summary"],
                    "properties": {
                        "answer": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            }

    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-1",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-selected",
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert result["io_contract"]["version_id"] == "wfv-run"
    assert result["output_contract"] == {
        "valid": False,
        "schema_field": "output_schema",
        "declared_fields": ["answer", "summary"],
        "declared_field_paths": ["answer", "summary"],
        "required_fields": ["answer", "summary"],
        "required_field_paths": ["answer", "summary"],
        "missing_required": ["summary"],
        "type_mismatches": [{"field": "answer", "expected": "string", "actual": "int"}],
        "extra_fields": ["trace"],
    }
    assert calls[1] == {
        "stage": "contract",
        "workflow_id": "wf-1",
        "owner_user_id": "user-1",
        "version_id": "wfv-run",
    }


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_keeps_result_when_io_contract_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {"input_schema": {"type": "object", "properties": {}}}

        async def run_workflow(self, **kwargs):
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-run",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            raise LookupError("workflow_contract_not_found")

    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={"workflow": {"SELECTED_WORKFLOW_ID": "wf-1"}},
        message="hello",
        user_id="user-1",
    )

    assert result["status"] == "succeeded"
    assert result["output"] == {"answer": "ok"}
    assert "io_contract" not in result
    assert "output_contract" not in result


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_resolves_user_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            calls.append({"stage": "schema", **kwargs})
            return {"input_schema": {"type": "object", "properties": {}}}

        async def run_workflow(self, **kwargs):
            calls.append({"stage": "run", **kwargs})
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-1",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    async def workflow_access(user_id: str):
        assert user_id == "user-1"
        return ["user", "workflow-operator"], False

    monkeypatch.setattr("src.infra.mcp.quota.resolve_user_mcp_access", workflow_access)
    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={"workflow": {"SELECTED_WORKFLOW_ID": "wf-1"}},
        message="hello",
        user_id="user-1",
    )

    assert result["status"] == "succeeded"
    assert [call["stage"] for call in calls] == ["schema", "run"]
    assert calls[0]["owner_user_id"] == "user-1"
    user = calls[1]["user"]
    assert user.sub == "user-1"
    assert user.roles == ["user", "workflow-operator"]
    assert user.permissions == ["workflow:read", "workflow:run"]


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_keeps_base_input_when_schema_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            raise LookupError("workflow_version_not_found")

        async def run_workflow(self, **kwargs):
            calls.append(kwargs)
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-1",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    _patch_workflow_service_factory(monkeypatch, _Service())

    await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "WORKFLOW_ID": "wf-1",
                "WORKFLOW_VERSION_ID": "wfv-task",
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert calls[0]["version_id"] == "wfv-task"
    assert calls[0]["workflow_input"] == {
        "message": "hello",
        "input": "hello",
        "query": "hello",
        "sys.query": "hello",
        "sys": {"query": "hello"},
    }


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_merges_scheduled_task_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                }
            }

        async def run_workflow(self, **kwargs):
            calls.append(kwargs)
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-task",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    _patch_workflow_service_factory(monkeypatch, _Service())

    await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "WORKFLOW_ID": "wf-1",
                "WORKFLOW_VERSION_ID": "wfv-task",
                "WORKFLOW_INPUT_JSON": {"query": "explicit query", "topic": "nightly"},
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert calls[0]["workflow_input"]["message"] == "hello"
    assert calls[0]["workflow_input"]["input"] == "hello"
    assert calls[0]["workflow_input"]["query"] == "explicit query"
    assert calls[0]["workflow_input"]["topic"] == "nightly"


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_merges_session_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                }
            }

        async def run_workflow(self, **kwargs):
            calls.append(kwargs)
            run = SimpleNamespace(
                run_id="wfr-1",
                version_id="wfv-chat",
                status="succeeded",
                output={"answer": "ok"},
                error=None,
            )
            return run, []

    _patch_workflow_service_factory(monkeypatch, _Service())

    await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-1",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-chat",
                "SELECTED_WORKFLOW_INPUT_JSON": {
                    "query": "explicit chat query",
                    "topic": "chat topic",
                },
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert calls[0]["workflow_input"]["message"] == "hello"
    assert calls[0]["workflow_input"]["input"] == "hello"
    assert calls[0]["workflow_input"]["query"] == "explicit chat query"
    assert calls[0]["workflow_input"]["topic"] == "chat topic"


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_returns_failed_result_when_run_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {"input_schema": {"type": "object", "properties": {}}}

        async def run_workflow(self, **kwargs):
            raise LookupError("workflow_not_found")

    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-missing",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-missing",
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert result == {
        "plugin_id": "workflow",
        "workflow_id": "wf-missing",
        "run_id": None,
        "version_id": "wfv-missing",
        "status": "failed",
        "output": {},
        "error": "workflow_not_found",
        "interface": _expected_interface(
            workflow_id="wf-missing",
            version_id="wfv-missing",
            run_id=None,
        ),
        "next_action": {
            "type": "handle_terminal_error",
            "field": "error",
            "reason": "workflow_run_failed",
        },
    }


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_redacts_unstructured_run_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {"input_schema": {"type": "object", "properties": {}}}

        async def run_workflow(self, **kwargs):
            raise RuntimeError("database password=secret-token host=https://internal.example")

    _patch_workflow_service_factory(monkeypatch, _Service())

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={"workflow": {"SELECTED_WORKFLOW_ID": "wf-1"}},
        message="hello",
        user_id="user-1",
    )

    assert result == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "run_id": None,
        "version_id": None,
        "status": "failed",
        "output": {},
        "error": "workflow_pre_run_failed",
        "interface": _expected_interface(
            workflow_id="wf-1",
            version_id=None,
            run_id=None,
        ),
        "next_action": {
            "type": "handle_terminal_error",
            "field": "error",
            "reason": "workflow_run_failed",
        },
    }


@pytest.mark.asyncio
async def test_run_selected_workflow_for_message_returns_failed_result_when_service_factory_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _create_service():
        raise RuntimeError("database password=secret-token host=https://internal.example")

    monkeypatch.setattr(chat_integration, "create_workflow_service", _create_service)

    result = await chat_integration.run_selected_workflow_for_message(
        plugin_options={
            "workflow": {
                "SELECTED_WORKFLOW_ID": "wf-1",
                "SELECTED_WORKFLOW_VERSION_ID": "wfv-1",
            }
        },
        message="hello",
        user_id="user-1",
    )

    assert result == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "run_id": None,
        "version_id": "wfv-1",
        "status": "failed",
        "output": {},
        "error": "workflow_pre_run_failed",
        "interface": _expected_interface(
            workflow_id="wf-1",
            version_id="wfv-1",
            run_id=None,
        ),
        "next_action": {
            "type": "handle_terminal_error",
            "field": "error",
            "reason": "workflow_run_failed",
        },
    }


def test_safe_workflow_pre_run_error_preserves_stable_workflow_codes_only() -> None:
    assert chat_integration.safe_workflow_pre_run_error(LookupError("workflow_not_found")) == "workflow_not_found"
    assert (
        chat_integration.safe_workflow_pre_run_error(ValueError("workflow_version_not_publishable:import_errors"))
        == "workflow_version_not_publishable:import_errors"
    )
    assert (
        chat_integration.safe_workflow_pre_run_error(ValueError("workflow_http_host_not_allowlisted:internal.example"))
        == "workflow_pre_run_failed"
    )
    assert chat_integration.safe_workflow_pre_run_error(RuntimeError("token=abc123")) == "workflow_pre_run_failed"


def test_workflow_result_context_prefers_answer_text() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-1",
            "run_id": "wfr-1",
            "status": "succeeded",
            "output": {"answer": "Hello"},
            "interface": _expected_interface(
                workflow_id="wf-1",
                version_id="wfv-1",
                run_id="wfr-1",
            ),
            "next_action": {
                "type": "use_output",
                "field": "output",
                "reason": "workflow_run_succeeded",
            },
        }
    )

    assert "workflow_id: wf-1" in text
    assert "output: Hello" in text
    assert "interface: entry=workflow_run.input schema=workflow_get_schema.input_schema exit=output" in text
    assert "output_schema=workflow_get_schema.output_schema" in text
    assert "next_action: use_output reason=workflow_run_succeeded field=output" in text
    assert "debug: use workflow_get_run with workflow_id and run_id to inspect events" in text


def test_workflow_result_context_includes_sanitized_error() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-missing",
            "run_id": None,
            "status": "failed",
            "output": {},
            "error": "workflow_not_found",
        }
    )

    assert "workflow_id: wf-missing" in text
    assert "status: failed" in text
    assert "output: {}" in text
    assert "error: workflow_not_found" in text
    assert "workflow_get_run" not in text


def test_workflow_result_context_includes_output_contract_guidance() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-1",
            "run_id": "wfr-1",
            "status": "succeeded",
            "output": {"answer": 42},
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": ["answer", "summary"],
                    "properties": {
                        "answer": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                }
            },
            "output_contract": {
                "valid": False,
                "missing_required": ["summary"],
                "type_mismatches": [{"field": "answer", "expected": "string", "actual": "int"}],
            },
        }
    )

    assert "outputs: answer:string, summary:string" in text
    assert "output_contract: invalid" in text
    assert "missing_required_outputs: ['summary']" in text
    assert "type_mismatched_outputs: [{'field': 'answer', 'expected': 'string', 'actual': 'int'}]" in text


def test_workflow_result_context_prefers_nested_output_contract_value() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-1",
            "run_id": "wfr-1",
            "status": "succeeded",
            "output": {
                "answer": "Generic answer",
                "report": {"summary": "Nested report summary"},
            },
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": ["report"],
                    "properties": {
                        "answer": {"type": "string"},
                        "report": {
                            "type": "object",
                            "required": ["summary"],
                            "properties": {"summary": {"type": "string"}},
                        },
                    },
                }
            },
        }
    )

    assert "output: Nested report summary" in text
    assert "outputs: report.summary:string, answer:string" in text


def test_workflow_result_context_includes_human_approval_resume_action() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-approval",
            "run_id": "wfr-approval",
            "status": "paused",
            "output": {},
            "next_action": {
                "type": "await_human_approval",
                "tool": "workflow_get_run",
                "reason": "workflow_run_paused_human_approval",
                "field": "pause.pending_approval",
                "resume": {
                    "tool": "workflow_resume",
                    "arguments": {
                        "workflow_id": "wf-approval",
                        "run_id": "wfr-approval",
                    },
                },
            },
        }
    )

    assert (
        "next_action: await_human_approval reason=workflow_run_paused_human_approval "
        "field=pause.pending_approval tool=workflow_get_run"
    ) in text
    assert "resume: workflow_resume(workflow_id=wf-approval, run_id=wfr-approval)" in text
    assert "debug: use workflow_get_run with workflow_id and run_id to inspect events" in text


def test_workflow_result_context_includes_inspect_action_for_running_workflow() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-running",
            "run_id": "wfr-running",
            "status": "running",
            "output": {},
            "next_action": {
                "type": "inspect_run",
                "tool": "workflow_get_run",
                "reason": "workflow_run_running",
            },
        }
    )

    assert "next_action: inspect_run reason=workflow_run_running tool=workflow_get_run" in text
    assert "inspect: workflow_get_run" in text


def test_workflow_result_context_bounds_large_output_values() -> None:
    text = chat_integration.workflow_result_context(
        {
            "workflow_id": "wf-large",
            "run_id": "wfr-large",
            "status": "succeeded",
            "output": {"answer": "x" * 2500},
            "error": "workflow_" + "e" * 2500,
        }
    )

    assert "output: " + "x" * 2000 in text
    assert "[truncated 500 chars]" in text
    assert "error: workflow_" in text
    assert "debug: use workflow_get_run" in text
    assert len(text) < 4300
