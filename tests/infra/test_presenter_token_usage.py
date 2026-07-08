import json

from src.infra.agent import AgentEventProcessor
from src.infra.writer.present import create_presenter
from src.infra.writer.presenter_config import _extract_attachment_keys


def test_present_token_usage_includes_model_identifiers() -> None:
    presenter = create_presenter(session_id="session-1", agent_id="search", agent_name="Search")

    event = presenter.present_token_usage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        duration=1.2,
        model_id="b715de30-38",
        model="openai/gpt-4.1",
    )

    assert event["event"] == "token:usage"
    assert event["data"]["model_id"] == "b715de30-38"
    assert event["data"]["model"] == "openai/gpt-4.1"


def test_present_recommend_questions_builds_frontend_event() -> None:
    presenter = create_presenter(session_id="session-1", agent_id="search", agent_name="Search")

    event = presenter.present_recommend_questions(
        [
            "如何预防胫骨内侧压力综合征？",
            {"content": "赛前减量期具体怎么做？", "upload": {"ctnm": 2}},
        ]
    )

    assert event["event"] == "recommend:questions"
    assert event["data"]["questions"] == [
        "如何预防胫骨内侧压力综合征？",
        {"content": "赛前减量期具体怎么做？", "upload": {"ctnm": 2}},
    ]


def test_present_user_message_bounds_persisted_attachments() -> None:
    presenter = create_presenter(session_id="session-1", agent_id="search", agent_name="Search")

    event = presenter.present_user_message(
        "hello",
        attachments=[{"key": f"file-{index}", "name": f"file-{index}"} for index in range(150)],
    )

    assert len(event["data"]["attachments"]) == 100


def test_extract_attachment_keys_bounds_unique_keys() -> None:
    keys = _extract_attachment_keys([{"key": f"file-{index}"} for index in range(150)])

    assert len(keys) == 100


class _FakeDualWriter:
    def __init__(self) -> None:
        self.events = []
        self.completed = []

    async def create_trace(self, **kwargs):
        return True

    async def write_event(self, **kwargs):
        self.events.append(kwargs)
        return True

    async def flush_mongo_buffer(self):
        return None

    async def complete_trace(self, trace_id: str, status: str, metadata=None):
        self.completed.append((trace_id, status, metadata))
        return True


async def test_complete_writes_zero_token_usage_when_missing(monkeypatch) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.complete("error")

    usage_events = [event for event in writer.events if event["event_type"] == "token:usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["data"]["input_tokens"] == 0
    assert usage_events[0]["data"]["output_tokens"] == 0
    assert usage_events[0]["data"]["total_tokens"] == 0


async def test_emit_recommend_questions_is_idempotent(monkeypatch) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.emit_recommend_questions(["下一步我应该怎么做？"])
    await presenter.emit_recommend_questions(["下一步我应该怎么做？"])

    recommend_events = [
        event for event in writer.events if event["event_type"] == "recommend:questions"
    ]
    assert len(recommend_events) == 1
    assert recommend_events[0]["data"]["questions"] == ["下一步我应该怎么做？"]


async def test_complete_does_not_duplicate_existing_token_usage(monkeypatch) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.emit(presenter.present_token_usage(input_tokens=2, output_tokens=3))
    await presenter.complete("completed")

    usage_events = [event for event in writer.events if event["event_type"] == "token:usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["data"]["input_tokens"] == 2
    assert usage_events[0]["data"]["output_tokens"] == 3


async def test_done_event_writes_zero_token_usage_first_in_same_trace(monkeypatch) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.save_event(presenter.done())

    assert [event["event_type"] for event in writer.events] == ["token:usage", "done"]
    assert [event["trace_id"] for event in writer.events] == ["trace-1", "trace-1"]
    assert [event["run_id"] for event in writer.events] == ["run-1", "run-1"]


async def test_done_event_is_persisted_once(monkeypatch) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.emit(presenter.done())
    await presenter.emit(presenter.done())

    assert [event["event_type"] for event in writer.events] == ["token:usage", "done"]


async def test_save_event_offloads_legacy_string_data_parse(monkeypatch) -> None:
    from src.infra.writer import presenter_storage

    writer = _FakeDualWriter()
    calls = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    monkeypatch.setattr(presenter_storage, "run_blocking_io", fake_run_blocking_io)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    await presenter.save_event({"event": "message", "data": '{"text": "hello"}'})

    assert calls == [json.loads]
    assert writer.events[0]["data"] == {"text": "hello"}


async def test_agent_workflow_tool_result_is_persisted_as_structured_failed_outlet(
    monkeypatch,
) -> None:
    writer = _FakeDualWriter()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="chat-run-1",
        trace_id="trace-1",
    )
    processor = AgentEventProcessor(presenter)
    workflow_result = {
        "plugin_id": "workflow",
        "workflow_id": "wf-chat",
        "run_id": "workflow-run-1",
        "version_id": "wfv-1",
        "status": "failed",
        "error": "workflow_run_not_found",
        "interface": {
            "entry": {
                "type": "tool",
                "tool": "workflow_run",
                "argument": "input",
                "schema_tool": "workflow_get_schema",
                "schema_field": "input_schema",
            },
            "exit": {
                "type": "object",
                "field": "output",
                "schema_tool": "workflow_get_schema",
                "schema_field": "output_schema",
            },
            "debug": {
                "tool": "workflow_get_run",
                "workflow_id": "wf-chat",
                "run_id": "workflow-run-1",
                "events_field": "events",
            },
        },
        "next_action": {
            "type": "handle_terminal_error",
            "field": "error",
            "reason": "workflow_run_failed",
            "tool": "workflow_get_run",
        },
    }

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "workflow_get_run",
            "run_id": "tool-call-workflow",
            "data": {
                "input": {
                    "workflow_id": "wf-chat",
                    "run_id": "workflow-run-1",
                }
            },
            "metadata": {},
        }
    )
    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "workflow_get_run",
            "run_id": "tool-call-workflow",
            "data": {"output": json.dumps(workflow_result)},
            "metadata": {},
        }
    )

    assert [event["event_type"] for event in writer.events] == ["tool:start", "tool:result"]
    persisted_result = writer.events[1]
    assert persisted_result["session_id"] == "session-1"
    assert persisted_result["trace_id"] == "trace-1"
    assert persisted_result["run_id"] == "chat-run-1"
    assert persisted_result["data"]["tool"] == "workflow_get_run"
    assert persisted_result["data"]["tool_call_id"] == "tool-call-workflow"
    assert persisted_result["data"]["success"] is False
    assert persisted_result["data"]["error"] == "workflow_run_not_found"
    assert persisted_result["data"]["result"]["plugin_id"] == "workflow"
    assert persisted_result["data"]["result"]["status"] == "failed"
    assert persisted_result["data"]["result"]["interface"]["entry"]["tool"] == "workflow_run"
    assert (
        persisted_result["data"]["result"]["interface"]["debug"]["tool"] == "workflow_get_run"
    )
    assert persisted_result["data"]["result"]["next_action"]["tool"] == "workflow_get_run"
