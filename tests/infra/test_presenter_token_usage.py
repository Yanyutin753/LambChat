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


def test_present_approval_required_keeps_tool_identity() -> None:
    presenter = create_presenter(session_id="session-1", agent_id="search", agent_name="Search")

    event = presenter.present_ask_human(
        approval_id="approval-1",
        question="需要确认",
        tool_call_id="call-1",
        interrupt_id="interrupt-1",
    )

    assert event["data"]["id"] == "approval-1"
    assert event["data"]["tool_call_id"] == "call-1"
    assert event["data"]["interrupt_id"] == "interrupt-1"


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

    async def set_run_recommend_questions(self, **kwargs):
        self.recommend_questions = kwargs
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


async def test_publish_recommend_questions_persists_run_field_and_sends_websocket(
    monkeypatch,
) -> None:
    writer = _FakeDualWriter()
    websocket_messages = []

    class _WebSocketManager:
        async def send_to_user_with_broadcast(self, user_id, message):
            websocket_messages.append((user_id, message))
            return 1

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: _WebSocketManager(),
    )
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
        user_id="user-1",
    )

    await presenter.publish_recommend_questions(["问题一？", "问题二？"])

    assert writer.recommend_questions == {
        "session_id": "session-1",
        "run_id": "run-1",
        "questions": ["问题一？", "问题二？"],
    }
    assert websocket_messages == [
        (
            "user-1",
            {
                "type": "recommend:questions",
                "data": {
                    "session_id": "session-1",
                    "run_id": "run-1",
                    "questions": ["问题一？", "问题二？"],
                },
            },
        )
    ]
    assert not [event for event in writer.events if event["event_type"] == "recommend:questions"]


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
    import json

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
