from types import SimpleNamespace

from src.infra.tool.backend_utils import get_session_id_from_runtime, get_trace_id_from_runtime


class _Runtime:
    def __init__(self, configurable):
        self.config = {"configurable": configurable}


def test_get_trace_id_from_runtime_prefers_explicit_configurable_value() -> None:
    runtime = _Runtime(
        {
            "trace_id": "trace-config",
            "presenter": SimpleNamespace(trace_id="trace-presenter"),
            "context": SimpleNamespace(trace_id="trace-context"),
        }
    )

    assert get_trace_id_from_runtime(runtime) == "trace-config"


def test_get_trace_id_from_runtime_falls_back_to_presenter_then_context() -> None:
    assert (
        get_trace_id_from_runtime(
            _Runtime({"presenter": SimpleNamespace(trace_id="trace-presenter")})
        )
        == "trace-presenter"
    )
    assert (
        get_trace_id_from_runtime(_Runtime({"context": SimpleNamespace(trace_id="trace-context")}))
        == "trace-context"
    )


def test_get_session_id_from_runtime_prefers_config_then_presenter_then_context() -> None:
    assert get_session_id_from_runtime(_Runtime({"session_id": "session-config"})) == (
        "session-config"
    )
    assert (
        get_session_id_from_runtime(
            _Runtime({"presenter": SimpleNamespace(session_id="session-presenter")})
        )
        == "session-presenter"
    )
    assert (
        get_session_id_from_runtime(
            _Runtime({"context": SimpleNamespace(session_id="session-context")})
        )
        == "session-context"
    )
