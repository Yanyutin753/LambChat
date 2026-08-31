"""SSE 错误事件标准形状测试：error 原文 + code 稳定错误码。"""

from src.api.routes.chat_sse import _chat_sse_payload_too_large_event
from src.infra.writer.presenter_config import PresenterConfig
from src.infra.writer.presenter_events import EventPresenterMixin


class _Host(EventPresenterMixin):
    """mixin 的最小宿主。"""

    def __init__(self):
        self.config = PresenterConfig()
        self.trace_id = "t1"
        self.run_id = "r1"
        self._step_count = 0
        self._tool_calls = []


def test_presenter_error_defaults_internal_code():
    event = _Host().error("boom")
    payload = event["data"]
    assert payload["error"] == "boom"
    assert payload["code"] == "internal_error"
    assert payload["type"] == "Error"
    assert payload["trace_id"] == "t1"


def test_presenter_error_explicit_code():
    event = _Host().error("cancelled by user", error_type="CancelledError", code="task_cancelled")
    payload = event["data"]
    assert payload["code"] == "task_cancelled"
    assert payload["type"] == "CancelledError"


def test_payload_too_large_event_carries_code():
    raw = _chat_sse_payload_too_large_event("42")
    assert "event: error" in raw
    assert '"code":"event_payload_too_large"' in raw
    assert "id: 42" in raw
