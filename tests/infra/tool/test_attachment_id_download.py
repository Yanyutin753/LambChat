import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.tool import upload_url_tool as module
from src.infra.upload.file_record import FileRecordStorage


@pytest.fixture
def download(monkeypatch):
    from src.infra.session.storage import SessionStorage
    from src.infra.session.trace_storage import TraceStorage

    async def authorize(url, *args, **kwargs):
        return url

    monkeypatch.setattr(module, "authorize_file_url", authorize)
    session = SimpleNamespace(user_id="owner", is_active=True)
    monkeypatch.setattr(SessionStorage, "get_by_session_id", AsyncMock(return_value=session))
    monkeypatch.setattr(SessionStorage, "get_by_id", AsyncMock(return_value=None))
    record = {"key": "document/owner/real.pptx", "uploaded_by": "owner"}
    lookup = AsyncMock(return_value=record)
    monkeypatch.setattr(FileRecordStorage, "find_by_key", lookup)
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=False))
    monkeypatch.setattr(module, "_resolve_storage_direct_url", AsyncMock(return_value=None))
    fetch = AsyncMock(return_value=(True, "success"))
    monkeypatch.setattr(module, "_execute_sandbox_download", fetch)
    history = []

    async def events(_self, session_id, **kwargs):
        assert session_id == "session"
        assert kwargs["event_types"] == ["user:message"]
        for attachment in history:
            yield {"data": {"attachments": [attachment]}}

    monkeypatch.setattr(TraceStorage, "iter_session_events_for_cleanup", events)
    attachment = {
        "id": "file-1",
        "key": record["key"],
        "url": "https://wrong.example/document/owneR/typo.pptx",
    }
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "session_id": "session",
                "context": SimpleNamespace(user_id="owner"),
                "base_url": "https://app.example",
                "attachments": [attachment],
                "backend": SimpleNamespace(aexecute=AsyncMock()),
            }
        }
    )
    return SimpleNamespace(
        runtime=runtime,
        attachment=attachment,
        history=history,
        session=session,
        record=record,
        fetch=fetch,
        lookup=lookup,
    )


async def invoke(download, **kwargs):
    return json.loads(
        await module.upload_url_to_sandbox.coroutine(
            attachment_id="file-1",
            file_path="/workspace/report.pptx",
            runtime=download.runtime,
            **kwargs,
        )
    )


async def test_id_uses_owned_storage_key_instead_of_attachment_url(download):
    assert (await invoke(download))["success"] is True
    assert (
        download.fetch.call_args.args[1]
        == "https://app.example/api/upload/file/document/owner/real.pptx"
    )
    download.lookup.assert_awaited_with("document/owner/real.pptx", "owner")


async def test_id_resolves_earlier_turn_after_runtime_attachments_disappear(download):
    download.history.append(download.attachment)
    download.runtime.config["configurable"]["attachments"] = []
    assert (await invoke(download))["success"] is True


async def test_lookup_failure_returns_recoverable_error_without_downloading(download):
    download.lookup.side_effect = RuntimeError("storage unavailable")
    result = await invoke(download)
    assert result["success"] is False
    assert "retry" in result["error"]
    download.fetch.assert_not_awaited()


def test_model_schema_accepts_id_without_exposing_runtime():
    schema = module.upload_url_to_sandbox.tool_call_schema.model_json_schema()
    assert "attachment_id" in schema["properties"]
    assert "runtime" not in schema["properties"]
    assert not schema.get("required")


async def test_missing_arguments_list_owned_current_and_historical_ids_without_urls(download):
    download.history.append({**download.attachment, "id": "old-file", "name": "older.pptx"})
    result = json.loads(await module.upload_url_to_sandbox.coroutine(runtime=download.runtime))
    assert result["success"] is True
    assert {a["id"] for a in result["attachments"]} == {"old-file", "file-1"}
    assert "https://" not in json.dumps(result)
    assert "key" not in json.dumps(result)
    download.fetch.assert_not_awaited()


@pytest.mark.parametrize(
    "failure", ["unknown", "foreign_session", "foreign_file", "deleted", "ambiguous", "both"]
)
async def test_invalid_id_never_starts_download(download, failure):
    if failure == "unknown":
        download.runtime.config["configurable"]["attachments"] = []
    elif failure == "foreign_session":
        download.session.user_id = "someone-else"
    elif failure == "foreign_file":
        download.lookup.return_value = None
    elif failure == "deleted":
        download.record["deleting_at"] = "now"
    elif failure == "ambiguous":
        download.runtime.config["configurable"]["attachments"].append(
            {**download.attachment, "key": "another"}
        )
    result = await invoke(
        download, **({"url": "https://elsewhere/file"} if failure == "both" else {})
    )
    assert result["success"] is False
    download.fetch.assert_not_awaited()
