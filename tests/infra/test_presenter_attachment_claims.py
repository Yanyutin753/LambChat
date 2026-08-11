from __future__ import annotations

from typing import Any

import pytest

from src.infra.writer.present import Presenter, PresenterConfig


class _FileRecords:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def claim_owned_references(self, keys: list[str], uploaded_by: str) -> list[str]:
        self.calls.append(("claim", keys, uploaded_by))
        return list(keys)

    async def release_owned_references(self, keys: list[str], uploaded_by: str) -> int:
        self.calls.append(("release", keys, uploaded_by))
        return len(keys)

    async def add_references(self, keys: list[str]) -> int:
        raise AssertionError(f"legacy add_references called for {keys}")


class _SessionStorage:
    async def append_user_message_search_content(self, session_id: str, content: str) -> None:
        return None


def _presenter() -> Presenter:
    return Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="search",
            user_id="owner-1",
            run_id="run-1",
            trace_id="trace-1",
        )
    )


@pytest.mark.asyncio
async def test_non_preclaimed_presenter_claims_before_saving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    order: list[str] = []

    async def _save_event(event: dict[str, Any], **kwargs: Any) -> None:
        order.append("save")

    original_claim = file_records.claim_owned_references

    async def _claim(keys: list[str], uploaded_by: str) -> list[str]:
        order.append("claim")
        return await original_claim(keys, uploaded_by)

    file_records.claim_owned_references = _claim  # type: ignore[method-assign]
    presenter = _presenter()
    monkeypatch.setattr("src.infra.writer.present.FileRecordStorage", lambda: file_records)
    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _SessionStorage)
    monkeypatch.setattr(presenter, "save_event", _save_event)

    await presenter.emit_user_message("hello", attachments=[{"key": "key-1"}])

    assert order == ["claim", "save"]
    assert file_records.calls == [("claim", ["key-1"], "owner-1")]


@pytest.mark.asyncio
async def test_preclaimed_presenter_does_not_claim_again(monkeypatch: pytest.MonkeyPatch) -> None:
    file_records = _FileRecords()
    presenter = _presenter()

    async def _save_event(event: dict[str, Any], **kwargs: Any) -> None:
        return None

    monkeypatch.setattr("src.infra.writer.present.FileRecordStorage", lambda: file_records)
    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _SessionStorage)
    monkeypatch.setattr(presenter, "save_event", _save_event)

    await presenter.emit_user_message(
        "hello",
        attachments=[{"key": "key-1"}, {"key": "key-1"}],
        attachment_references_claimed=True,
    )

    assert file_records.calls == []


@pytest.mark.asyncio
async def test_user_message_save_failure_releases_exact_owned_claim_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    presenter = _presenter()

    async def _fail_save(event: dict[str, Any], **kwargs: Any) -> None:
        raise RuntimeError("mongo unavailable")

    monkeypatch.setattr("src.infra.writer.present.FileRecordStorage", lambda: file_records)
    monkeypatch.setattr(presenter, "save_event", _fail_save)

    with pytest.raises(RuntimeError, match="mongo unavailable"):
        await presenter.emit_user_message(
            "hello",
            attachments=[{"key": "key-1"}, {"key": "key-1"}],
            attachment_references_claimed=True,
        )

    assert file_records.calls == [("release", ["key-1"], "owner-1")]


@pytest.mark.asyncio
async def test_post_persistence_search_failure_retains_attachment_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    presenter = _presenter()

    async def _save_event(event: dict[str, Any], **kwargs: Any) -> None:
        return None

    class _FailingSessionStorage:
        async def append_user_message_search_content(self, session_id: str, content: str) -> None:
            raise RuntimeError("search metadata unavailable")

    monkeypatch.setattr("src.infra.writer.present.FileRecordStorage", lambda: file_records)
    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _FailingSessionStorage)
    monkeypatch.setattr(presenter, "save_event", _save_event)

    await presenter.emit_user_message(
        "hello",
        attachments=[{"key": "key-1"}],
        attachment_references_claimed=True,
    )

    assert file_records.calls == []


@pytest.mark.asyncio
async def test_user_message_flush_failure_releases_preclaim_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    presenter = _presenter()

    class _FailingWriter:
        async def create_trace(self, **kwargs: Any) -> bool:
            return True

        async def write_event(self, **kwargs: Any) -> bool:
            return True

        async def flush_mongo_buffer(self, *, require_empty: bool = False) -> None:
            assert require_empty is True
            raise RuntimeError("mongo flush failed")

    async def _get_writer() -> _FailingWriter:
        return _FailingWriter()

    async def _trace_metadata() -> dict[str, Any]:
        return {}

    monkeypatch.setattr("src.infra.writer.present.FileRecordStorage", lambda: file_records)
    monkeypatch.setattr(presenter, "_get_dual_writer", _get_writer)
    monkeypatch.setattr(presenter, "_build_trace_metadata", _trace_metadata)

    with pytest.raises(RuntimeError, match="mongo flush failed"):
        await presenter.emit_user_message(
            "hello",
            attachments=[{"key": "key-1"}],
            attachment_references_claimed=True,
        )

    assert file_records.calls == [("release", ["key-1"], "owner-1")]
