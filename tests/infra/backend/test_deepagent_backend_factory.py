from __future__ import annotations

from src.infra.backend.deepagent import create_persistent_backend_factory


def _namespace_for(factory):
    backend = factory(None)
    return backend.default._backend._namespace(None)


def test_persistent_backend_filesystem_namespace_is_scoped_by_session_id() -> None:
    first = create_persistent_backend_factory(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-1",
    )
    second = create_persistent_backend_factory(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-2",
    )

    assert _namespace_for(first) == ("assistant-user-1", "workflow", "session-1")
    assert _namespace_for(second) == ("assistant-user-1", "workflow", "session-2")


class _FakeStore:
    def __init__(self) -> None:
        self.items: dict[tuple[tuple[str, ...], str], object] = {}

    def get(self, namespace, key):
        return self.items.get((namespace, key))

    def put(self, namespace, key, value):
        self.items[(namespace, key)] = value


def test_persistent_backend_exposes_session_workflow_as_initial_path() -> None:
    factory = create_persistent_backend_factory(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-1",
    )
    backend = factory(None)
    backend.default._backend._store = _FakeStore()

    result = backend.write("/workflow/session-1/report.md", "hello")

    assert result.path == "/workflow/session-1/report.md"
    assert backend.default._backend._get_store().get(
        ("assistant-user-1", "workflow", "session-1"),
        "/report.md",
    )
