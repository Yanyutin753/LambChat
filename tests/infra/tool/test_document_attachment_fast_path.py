"""Direct parsing must keep the same attachment and file authority as downloads."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.tool import document_parse_tool as module
from src.infra.upload.file_record import FileRecordStorage


@pytest.fixture
def document(monkeypatch):
    from src.infra.session.storage import SessionStorage
    from src.infra.session.trace_storage import TraceStorage

    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=True)
    )
    session = SimpleNamespace(user_id="owner", is_active=True)
    monkeypatch.setattr(SessionStorage, "get_by_session_id", AsyncMock(return_value=session))
    monkeypatch.setattr(SessionStorage, "get_by_id", AsyncMock(return_value=None))
    record = {"key": "document/owner/real.pdf", "uploaded_by": "owner"}
    lookup = AsyncMock(return_value=record)
    monkeypatch.setattr(FileRecordStorage, "find_by_key", lookup)
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "src.infra.upload.access._owns_generated_file", AsyncMock(return_value=False)
    )
    history = []

    async def events(_self, session_id, **kwargs):
        for item in history:
            yield {"data": {"attachments": [item]}}

    monkeypatch.setattr(TraceStorage, "iter_session_events_for_cleanup", events)
    attachment = {"id": "file-1", "key": record["key"], "url": "https://wrong.example/evil.pdf"}
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "session_id": "session",
                "context": SimpleNamespace(user_id="owner"),
                "base_url": "https://app.example",
                "attachments": [attachment],
            }
        }
    )
    requests = []

    class Response:
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        async def aiter_bytes(self):
            yield b"%PDF-1.4 test"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url):
            requests.append(url)
            assert url.startswith("https://app.example/api/upload/file/document/owner/real.pdf?")
            assert "file_token=" in url
            return Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: Client())
    parse = AsyncMock(return_value={"markdown": "Invoice 317", "engine": "test", "images": []})
    monkeypatch.setattr(module, "execute_document_parse", parse)
    return SimpleNamespace(
        runtime=runtime,
        session=session,
        record=record,
        lookup=lookup,
        attachment=attachment,
        history=history,
        requests=requests,
        parse=parse,
    )


async def test_parse_id_reads_owned_attachment_without_sandbox(document):
    result = json.loads(
        await module.document_parse.coroutine(attachment_id="file-1", runtime=document.runtime)
    )
    assert result["success"] is True
    assert result["markdown"] == "Invoice 317"
    assert len(document.requests) == 1
    assert "file_token" not in json.dumps(result)
    assert document.parse.call_args.kwargs["data"] == b"%PDF-1.4 test"


async def test_parse_id_can_read_authorized_earlier_turn(document):
    document.history.append(document.attachment)
    document.runtime.config["configurable"]["attachments"] = []
    result = json.loads(
        await module.document_parse.coroutine(attachment_id="file-1", runtime=document.runtime)
    )
    assert result["success"] is True


@pytest.mark.parametrize(
    "failure",
    [
        "unknown",
        "foreign_session",
        "inactive",
        "foreign_file",
        "deleted",
        "ambiguous",
        "both",
        "missing",
        "lookup_error",
    ],
)
async def test_parse_id_denies_before_download_or_provider(document, failure):
    if failure == "unknown":
        document.runtime.config["configurable"]["attachments"] = []
    elif failure == "foreign_session":
        document.session.user_id = "other"
    elif failure == "inactive":
        document.session.is_active = False
    elif failure == "foreign_file":
        document.lookup.return_value = None
    elif failure == "deleted":
        document.record["deleting_at"] = "now"
    elif failure == "ambiguous":
        document.runtime.config["configurable"]["attachments"].append(
            {**document.attachment, "key": "other"}
        )
    elif failure == "lookup_error":
        document.lookup.side_effect = RuntimeError("lookup secret")
    args = {"attachment_id": "file-1"} if failure != "missing" else {}
    if failure == "both":
        args["url"] = "https://external.example/a.pdf"
    result = json.loads(await module.document_parse.coroutine(runtime=document.runtime, **args))
    assert result.get("error")
    assert "secret" not in json.dumps(result)
    assert document.requests == []
    document.parse.assert_not_awaited()


def test_model_schema_accepts_id_without_url_or_runtime():
    schema = module.document_parse.tool_call_schema.model_json_schema()
    assert "attachment_id" in schema["properties"]
    assert "runtime" not in schema["properties"]
    assert "url" not in schema.get("required", [])


@pytest.mark.parametrize("source", ["attachment", "url"])
async def test_uploaded_document_requires_current_file_read_before_download(
    document, monkeypatch, source
):
    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=False)
    )
    args = (
        {"attachment_id": "file-1"}
        if source == "attachment"
        else {"url": "/api/upload/file/document/owner/real.pdf"}
    )
    result = json.loads(await module.document_parse.coroutine(**args, runtime=document.runtime))
    assert "error" in result
    assert document.requests == []
    document.parse.assert_not_awaited()
