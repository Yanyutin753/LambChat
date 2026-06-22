import io
import json
import logging

from src.infra.logging.config import setup_logging
from src.infra.logging.context import TraceContext
from src.infra.logging.filter import TraceFilter
from src.infra.logging.formatter import build_log_formatter
from src.kernel.config import settings

DEFAULT_LOG_FORMAT = type(settings).model_fields["LOG_FORMAT"].default


def teardown_function() -> None:
    TraceContext.clear()
    TraceContext.clear_request_context()


def test_trace_context_tracks_request_id_with_trace_info() -> None:
    TraceContext.set(
        trace_id="trace-1",
        span_id="span-1",
        parent_span_id="parent-1",
        request_id="req-1",
    )

    info = TraceContext.get()

    assert info.request_id == "req-1"
    assert info.trace_id == "trace-1"
    assert info.span_id == "span-1"
    assert info.parent_span_id == "parent-1"
    assert info.format() == "request_id=req-1 trace_id=trace-1 span_id=span-1"


def test_trace_filter_injects_request_and_business_context() -> None:
    TraceContext.set(trace_id="trace-1", span_id="span-1", request_id="req-1")
    TraceContext.set_request_context(
        request_id="req-1",
        session_id="session-1",
        run_id="run-1",
        user_id="user-1",
        trace_id="trace-1",
    )
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert TraceFilter().filter(record) is True

    assert record.request_id == "req-1"
    assert record.trace_id == "trace-1"
    assert record.span_id == "span-1"
    assert record.parent_span_id == "-"
    assert record.session_id == "session-1"
    assert record.run_id == "run-1"
    assert record.user_id == "user-1"
    assert record.trace_info == "request_id=req-1 trace_id=trace-1 span_id=span-1"
    assert (
        record.trace_context == "request_id=req-1 trace_id=trace-1 span_id=span-1 "
        "user_id=user-1 session_id=session-1 run_id=run-1 "
    )


def test_trace_filter_uses_safe_fallbacks_when_context_is_missing() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert TraceFilter().filter(record) is True

    assert record.request_id == "-"
    assert record.trace_id == "-"
    assert record.span_id == "-"
    assert record.parent_span_id == "-"
    assert record.session_id == "-"
    assert record.run_id == "-"
    assert record.user_id == "-"
    assert record.trace_info == "-"
    assert record.trace_context == ""


def test_trace_filter_uses_request_context_trace_id_as_fallback() -> None:
    TraceContext.set_request_context(trace_id="trace-from-request-context")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert TraceFilter().filter(record) is True

    assert record.trace_id == "trace-from-request-context"


def test_default_log_format_exposes_request_id() -> None:
    assert "%(trace_context)s" in DEFAULT_LOG_FORMAT


def test_default_log_format_renders_with_trace_filter() -> None:
    TraceContext.set(trace_id="trace-1", span_id="span-1", request_id="req-1")
    TraceContext.set_request_context(
        session_id="session-1",
        run_id="run-1",
        user_id="user-1",
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(TraceFilter())
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    logger = logging.getLogger("test.request_id_formatter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info("hello")
    finally:
        logger.handlers = []
        logger.propagate = True

    output = stream.getvalue()
    assert "request_id=req-1" in output
    assert "trace_id=trace-1" in output
    assert "span_id=span-1" in output
    assert "user_id=user-1" in output
    assert "session_id=session-1" in output
    assert "run_id=run-1" in output


def test_default_log_format_hides_missing_trace_context() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(TraceFilter())
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    logger = logging.getLogger("test.missing_context_formatter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info("hello")
    finally:
        logger.handlers = []
        logger.propagate = True

    output = stream.getvalue()
    assert "request_id=-" not in output
    assert "trace_id=-" not in output
    assert "span_id=-" not in output
    assert "user_id=-" not in output
    assert "session_id=-" not in output
    assert "run_id=-" not in output
    assert "test.missing_context_formatter - hello" in output


def test_json_log_format_renders_structured_trace_context() -> None:
    TraceContext.set(trace_id="trace-1", span_id="span-1", request_id="req-1")
    TraceContext.set_request_context(session_id="session-1", run_id="run-1", user_id="user-1")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(TraceFilter())
    handler.setFormatter(build_log_formatter("json", settings.LOG_DATE_FORMAT))
    logger = logging.getLogger("test.json_formatter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info("hello %s", "json")
    finally:
        logger.handlers = []
        logger.propagate = True

    payload = json.loads(stream.getvalue())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json_formatter"
    assert payload["message"] == "hello json"
    assert payload["request_id"] == "req-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["span_id"] == "span-1"
    assert payload["user_id"] == "user-1"
    assert payload["session_id"] == "session-1"
    assert payload["run_id"] == "run-1"


def test_setup_logging_accepts_json_log_format(monkeypatch) -> None:
    original_handlers = list(logging.getLogger().handlers)
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")

    try:
        setup_logging()
        logging.getLogger("test.setup_json_formatter").info("json startup")
    finally:
        logging.getLogger().handlers = original_handlers
