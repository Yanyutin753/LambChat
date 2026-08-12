from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.api.routes import chat
from src.infra.task.concurrency import ConcurrencyResponse, ConcurrencyResult
from src.infra.upload.file_record import AttachmentClaimError
from src.kernel.schemas.agent import AgentRequest


def _attachment(key: str, *, attachment_id: str = "attachment-1") -> dict[str, Any]:
    return {
        "id": attachment_id,
        "key": key,
        "name": "notes.txt",
        "type": "document",
        "mimeType": "text/plain",
        "size": 12,
        "url": f"https://files.example/{key}",
    }


class _FileRecords:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.claims: list[tuple[list[str], str]] = []
        self.releases: list[tuple[list[str], str]] = []

    async def claim_owned_references(self, keys: list[str], uploaded_by: str) -> list[str]:
        self.claims.append((keys, uploaded_by))
        if self.reject or len(keys) > 100:
            raise AttachmentClaimError()
        return list(keys)

    async def release_owned_references(self, keys: list[str], uploaded_by: str) -> int:
        self.releases.append((keys, uploaded_by))
        return len(keys)


class _Limiter:
    def __init__(self, result: ConcurrencyResult) -> None:
        self.result = result
        self.acquire_calls: list[dict[str, Any]] = []
        self.release_calls: list[tuple[str, str, bool]] = []
        self.remove_calls: list[tuple[str, str]] = []

    async def acquire(self, **kwargs: Any) -> ConcurrencyResponse:
        self.acquire_calls.append(kwargs)
        return ConcurrencyResponse(
            result=self.result,
            queue_position=1,
            max_concurrent=1,
            active_count=1,
            queue_length=1,
        )

    async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
        self.release_calls.append((user_id, run_id, dequeue))

    async def remove_queued_run(self, user_id: str, run_id: str) -> int:
        self.remove_calls.append((user_id, run_id))
        return 1

    async def mark_queued_run_ready(self, user_id: str, run_id: str) -> bool:
        return True


class _Executor:
    async def ensure_session(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def _update_session_status(self, *args: Any, **kwargs: Any) -> None:
        return None


class _TaskManager:
    def __init__(self) -> None:
        self._executor = _Executor()
        self._run_info: dict[str, dict[str, Any]] = {}
        self.submit_calls: list[dict[str, Any]] = []
        self.submit_arq_calls: list[dict[str, Any]] = []
        self.fail_submit = False

    async def submit(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_calls.append(kwargs)
        if self.fail_submit:
            raise RuntimeError("submission failed")
        return kwargs["run_id"], kwargs["trace_id"]

    async def submit_arq(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_arq_calls.append(kwargs)
        return kwargs["run_id"], kwargs["trace_id"]


class _Presenter:
    calls: list[tuple[Any, ...]] = []
    fail_emit = False

    def __init__(self, config: Any) -> None:
        self.config = config
        self.trace_id = config.trace_id or "trace-1"

    async def _ensure_trace(self) -> None:
        return None

    async def emit_user_message(
        self,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        enabled_skills: list[str] | None = None,
        attachment_references_claimed: bool = False,
        schedule_search_index: bool = True,
    ) -> None:
        self.calls.append(
            (
                message,
                attachments,
                enabled_skills,
                attachment_references_claimed,
                schedule_search_index,
            )
        )
        if self.fail_emit:
            raise RuntimeError("message save failed")


async def _invoke_chat(
    monkeypatch: pytest.MonkeyPatch,
    *,
    attachments: list[dict[str, Any]] | None,
    limiter_result: ConcurrencyResult,
    task_backend: str = "local",
    reject_claim: bool = False,
    file_records: _FileRecords | None = None,
    limiter: _Limiter | None = None,
    task_manager: _TaskManager | None = None,
    metadata_failure: bool = False,
) -> tuple[Any, _FileRecords, _Limiter, _TaskManager]:
    file_records = file_records or _FileRecords(reject=reject_claim)
    limiter = limiter or _Limiter(limiter_result)
    task_manager = task_manager or _TaskManager()

    async def _noop_async(*args: Any, **kwargs: Any) -> None:
        return None

    async def _update_config(*args: Any, **kwargs: Any) -> None:
        if metadata_failure:
            raise RuntimeError("metadata failed")

    monkeypatch.setattr(chat, "FileRecordStorage", lambda: file_records, raising=False)
    monkeypatch.setattr(chat, "resolve_persona_request", _noop_async)
    monkeypatch.setattr(chat, "validate_agent_model_access", _noop_async)
    monkeypatch.setattr(chat, "validate_team_agent_request", lambda *args: None)
    monkeypatch.setattr(chat, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(chat, "_get_language", lambda request: "en")
    monkeypatch.setattr(chat, "_update_session_config", _update_config)
    monkeypatch.setattr(chat, "Presenter", _Presenter, raising=False)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _Presenter)
    monkeypatch.setattr(chat.settings, "TASK_BACKEND", task_backend)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: limiter,
    )
    monkeypatch.setattr("src.infra.task.manager._generate_run_id", lambda: "run-1")

    request = AgentRequest(message="hello", attachments=attachments)
    result = await chat.chat_stream(
        request,
        SimpleNamespace(headers={}),
        user=SimpleNamespace(sub="owner-1", roles=["member"]),
    )
    return result, file_records, limiter, task_manager


@pytest.mark.asyncio
@pytest.mark.parametrize("unclaimable_state", ["foreign", "tombstoned"])
async def test_invalid_attachments_return_same_422_before_limiter(
    monkeypatch: pytest.MonkeyPatch,
    unclaimable_state: str,
) -> None:
    del unclaimable_state
    file_records = _FileRecords(reject=True)
    limiter = _Limiter(ConcurrencyResult.STARTED)
    task_manager = _TaskManager()

    with pytest.raises(HTTPException) as exc_info:
        await _invoke_chat(
            monkeypatch,
            attachments=[_attachment("unavailable")],
            limiter_result=ConcurrencyResult.STARTED,
            file_records=file_records,
            limiter=limiter,
            task_manager=task_manager,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"error": "invalid_attachments"}
    assert limiter.acquire_calls == []
    assert task_manager.submit_calls == []
    assert task_manager.submit_arq_calls == []


@pytest.mark.asyncio
async def test_pre_admission_setup_failure_happens_before_attachment_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    limiter = _Limiter(ConcurrencyResult.STARTED)

    def _fail_agent_name(agent_id: str) -> str:
        raise RuntimeError(f"unknown agent: {agent_id}")

    monkeypatch.setattr(chat, "resolve_agent_name", _fail_agent_name)

    with pytest.raises(RuntimeError, match="unknown agent"):
        await _invoke_chat(
            monkeypatch,
            attachments=[_attachment("key-1")],
            limiter_result=ConcurrencyResult.STARTED,
            file_records=file_records,
            limiter=limiter,
        )

    assert file_records.claims == []
    assert file_records.releases == []
    assert limiter.acquire_calls == []


@pytest.mark.asyncio
async def test_attachment_overflow_is_rejected_before_limiter_without_truncating_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    limiter = _Limiter(ConcurrencyResult.STARTED)
    attachments = [
        _attachment(f"key-{index}", attachment_id=f"attachment-{index}") for index in range(101)
    ]

    with pytest.raises(HTTPException) as exc_info:
        await _invoke_chat(
            monkeypatch,
            attachments=attachments,
            limiter_result=ConcurrencyResult.STARTED,
            file_records=file_records,
            limiter=limiter,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"error": "invalid_attachments"}
    assert len(file_records.claims[0][0]) == 101
    assert limiter.acquire_calls == []


@pytest.mark.asyncio
async def test_direct_chat_claims_duplicate_attachment_key_once_and_propagates_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, file_records, limiter, task_manager = await _invoke_chat(
        monkeypatch,
        attachments=[
            _attachment("key-1", attachment_id="attachment-1"),
            _attachment("key-1", attachment_id="attachment-2"),
        ],
        limiter_result=ConcurrencyResult.STARTED,
    )

    assert result["status"] == "pending"
    assert file_records.claims == [(["key-1"], "owner-1")]
    assert limiter.acquire_calls[0]["task_context"]["attachment_references_claimed"] is True
    assert task_manager.submit_calls[0]["attachment_references_claimed"] is True
    assert file_records.releases == []


@pytest.mark.asyncio
async def test_empty_attachment_list_performs_no_file_record_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, file_records, _limiter, task_manager = await _invoke_chat(
        monkeypatch,
        attachments=[],
        limiter_result=ConcurrencyResult.STARTED,
    )

    assert file_records.claims == []
    assert file_records.releases == []
    assert task_manager.submit_calls[0]["attachment_references_claimed"] is False


@pytest.mark.asyncio
async def test_rejected_queue_releases_preclaimed_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _invoke_chat(
            monkeypatch,
            attachments=[_attachment("key-1")],
            limiter_result=ConcurrencyResult.REJECTED_QUEUE,
        )

    assert exc_info.value.status_code == 429
    file_records = chat.FileRecordStorage()
    assert file_records.releases == [(["key-1"], "owner-1")]


@pytest.mark.asyncio
async def test_queued_chat_passes_preclaimed_flag_to_presenter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Presenter.calls = []

    result, file_records, _limiter, _task_manager = await _invoke_chat(
        monkeypatch,
        attachments=[_attachment("key-1")],
        limiter_result=ConcurrencyResult.QUEUED,
    )

    assert result["status"] == "queued"
    assert file_records.claims == [(["key-1"], "owner-1")]
    assert _Presenter.calls == [
        (
            "hello",
            [
                AgentRequest(message="x", attachments=[_attachment("key-1")])
                .attachments[0]
                .model_dump()
            ],
            None,
            True,
            True,
        )
    ]
    assert file_records.releases == []


@pytest.mark.asyncio
async def test_arq_chat_propagates_preclaimed_flag_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, file_records, _limiter, task_manager = await _invoke_chat(
        monkeypatch,
        attachments=[_attachment("key-1")],
        limiter_result=ConcurrencyResult.STARTED,
        task_backend="arq",
    )

    assert file_records.claims == [(["key-1"], "owner-1")]
    assert task_manager.submit_arq_calls[0]["attachment_references_claimed"] is True
    assert file_records.releases == []


@pytest.mark.asyncio
async def test_queued_save_failure_removes_only_the_acquired_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    limiter = _Limiter(ConcurrencyResult.QUEUED)
    _Presenter.fail_emit = True

    try:
        with pytest.raises(RuntimeError, match="message save failed"):
            await _invoke_chat(
                monkeypatch,
                attachments=[_attachment("key-1")],
                limiter_result=ConcurrencyResult.QUEUED,
                file_records=file_records,
                limiter=limiter,
            )
    finally:
        _Presenter.fail_emit = False

    assert limiter.remove_calls == [("owner-1", "run-1")]
    assert limiter.release_calls == []
    assert file_records.releases == []


@pytest.mark.asyncio
async def test_direct_submission_failure_releases_only_the_acquired_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter(ConcurrencyResult.STARTED)
    task_manager = _TaskManager()
    task_manager.fail_submit = True

    with pytest.raises(RuntimeError, match="submission failed"):
        await _invoke_chat(
            monkeypatch,
            attachments=[_attachment("key-1")],
            limiter_result=ConcurrencyResult.STARTED,
            limiter=limiter,
            task_manager=task_manager,
        )

    assert limiter.release_calls == [("owner-1", "run-1", True)]
    assert limiter.remove_calls == []


@pytest.mark.asyncio
async def test_queued_post_persistence_metadata_failure_retains_claim_and_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_records = _FileRecords()
    limiter = _Limiter(ConcurrencyResult.QUEUED)

    with pytest.raises(RuntimeError, match="metadata failed"):
        await _invoke_chat(
            monkeypatch,
            attachments=[_attachment("key-1")],
            limiter_result=ConcurrencyResult.QUEUED,
            file_records=file_records,
            limiter=limiter,
            metadata_failure=True,
        )

    assert file_records.releases == []
    assert limiter.remove_calls == []
    assert limiter.release_calls == []
