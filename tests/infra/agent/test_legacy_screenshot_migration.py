import pytest

from scripts.migrate_cua_screenshots_private import legacy_capture_keys


def test_migration_only_attributes_computer_use_screenshots():
    def event(tool, url):
        return {
            "event_type": "tool:result",
            "data": {"tool": tool, "result": {"screenshot": {"url": url}}},
        }

    assert legacy_capture_keys(
        [
            event("computer_use", "/api/upload/file/tool_binaries/old.png"),
            event("computer_use", "/api/upload/file/tool_binaries/old.png"),
            event("mcp_tool", "/api/upload/file/tool_binaries/mcp.png"),
            event(
                "computer_use", "https://foreign.example/api/upload/file/tool_binaries/foreign.png"
            ),
            event("computer_use", "/api/upload/file/tool_binaries/../other.png"),
        ]
    ) == {"tool_binaries/old.png"}


@pytest.mark.parametrize("apply", [False, True])
async def test_migration_quarantines_conflicts_and_keeps_dry_run_read_only(monkeypatch, apply):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from scripts.migrate_cua_screenshots_private import migrate
    from src.infra.session.storage import SessionStorage
    from src.infra.storage.s3 import service
    from src.infra.upload.file_record import FileRecordStorage

    monkeypatch.setattr(
        service, "get_or_init_storage", AsyncMock(return_value=SimpleNamespace(is_local=True))
    )

    def doc(session):
        return {
            "session_id": session,
            "events": [
                {
                    "event_type": "tool:result",
                    "data": {
                        "tool": "computer_use",
                        "result": {"screenshot": {"url": "/api/upload/file/tool_binaries/old.png"}},
                    },
                }
            ],
        }

    async def docs():
        yield doc("one")
        yield doc("two")

    async def empty():
        if False:
            yield None

    traces = SimpleNamespace(
        collection=SimpleNamespace(find=lambda query, projection: docs()),
        chunks_collection=SimpleNamespace(find=lambda query, projection: empty()),
    )
    monkeypatch.setattr("src.infra.session.trace_storage.get_trace_storage", lambda: traces)
    sessions = SimpleNamespace(
        acquire_trace_write=AsyncMock(return_value=True),
        release_trace_write=AsyncMock(),
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"user_id": "owner"})),
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    files = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock()),
        initialize_indexes=AsyncMock(),
    )
    monkeypatch.setattr(FileRecordStorage, "__new__", lambda cls: files)
    result = await migrate(apply=apply)
    assert result == {
        "apply": apply,
        "captures": 2,
        "registered": 2 if apply else 0,
        "unattributed": 1,
    }
    if apply:
        files.initialize_indexes.assert_awaited_once()
        sessions.acquire_trace_write.assert_awaited_once_with("one")
        sessions.release_trace_write.assert_awaited_once_with("one")
        assert (
            files.collection.update_one.call_args.args[1]["$set"]["uploaded_by"]
            == "__unattributed__"
        )
    else:
        files.initialize_indexes.assert_not_awaited()
        files.collection.update_one.assert_not_awaited()
        sessions.acquire_trace_write.assert_not_awaited()
