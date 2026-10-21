"""Output-limited extraction must recover once without retaining partial memories."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from src.infra.memory import extraction

_MEMORY = (
    '{"memories":[{"raw_memory":"Alpha uses PostgreSQL, due 2027-04-16.",'
    '"context":"project"}],"rollout_summary":"Alpha decision","rollout_slug":"alpha"}'
)


class InvocationReceipt(AsyncCallbackHandler):
    def __init__(self):
        self.prompts = []
        self.usage = []

    async def on_chat_model_start(self, serialized, messages, **kwargs):
        self.prompts.append(messages[0])

    async def on_llm_end(self, response, **kwargs):
        self.usage.append(response.generations[0][0].message.usage_metadata)


@pytest.fixture
def setup_extraction(monkeypatch):
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_SYSTEMONE_MODE", "off")
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_SYSTEMONE_CONTEXT_SHADOW", False)
    monkeypatch.setattr(extraction.settings, "NATIVE_MEMORY_MAX_TOKENS", 4000)
    monkeypatch.setattr(extraction, "source_watermark", AsyncMock(return_value=None))
    monkeypatch.setattr(
        extraction,
        "load_session_transcript",
        AsyncMock(
            return_value=[
                {"run_id": "r1", "user": "Alpha uses PostgreSQL.", "assistant": "Confirmed."},
                {"run_id": "r2", "user": "Due 2027-04-16.", "assistant": "Confirmed deadline."},
            ]
        ),
    )

    def setup(responses):
        receipt = InvocationReceipt()
        model = FakeMessagesListChatModel(responses=responses, callbacks=[receipt])
        monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(return_value=model))
        backend = SimpleNamespace(
            retain=AsyncMock(return_value={"success": True, "memory_id": "m1"}),
        )
        return backend, receipt

    return setup


def _response(content, metadata=None, *, output_tokens=100):
    return AIMessage(
        content=content,
        response_metadata=metadata or {},
        usage_metadata={
            "input_tokens": 200,
            "output_tokens": output_tokens,
            "total_tokens": 200 + output_tokens,
        },
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"stop_reason": "max_tokens"},
        {"finish_reason": "length"},
        {"incomplete_details": {"reason": "max_output_tokens"}},
    ],
)
async def test_output_limit_retries_compactly_with_all_evidence_and_accounts_both_calls(
    setup_extraction, metadata
):
    backend, receipt = setup_extraction(
        [_response("", metadata, output_tokens=4000), _response(_MEMORY)]
    )

    outcome = await extraction.extract_session_memory(
        backend, None, "u1", {"session_id": "s1", "metadata": {"project_id": "alpha"}}
    )

    assert outcome.status == "succeeded"
    assert len(receipt.prompts) == 2
    first, retry = receipt.prompts
    assert first[0].content == retry[0].content
    assert first[1].content in retry[1].content
    assert first[1].content != retry[1].content
    assert [usage["output_tokens"] for usage in receipt.usage] == [4000, 100]
    assert backend.retain.await_args.args[1] == "Alpha uses PostgreSQL, due 2027-04-16."
    assert backend.retain.await_args.kwargs["source_refs"] == [
        {"session_id": "s1", "run_id": "r1"},
        {"session_id": "s1", "run_id": "r2"},
    ]
    assert backend.retain.await_args.kwargs["project_id"] == "alpha"


async def test_repeated_output_limit_is_terminal_even_when_partial_json_parses(setup_extraction):
    backend, receipt = setup_extraction(
        [
            _response(_MEMORY, {"stop_reason": "max_tokens"}),
            _response(_MEMORY, {"finish_reason": "length"}),
        ]
    )

    outcome = await extraction.extract_session_memory(backend, None, "u1", {"session_id": "s1"})

    assert outcome.status == "failed"
    assert outcome.error == "output_truncated"
    assert outcome.retryable is False
    assert len(receipt.prompts) == 2
    backend.retain.assert_not_awaited()


async def test_output_limited_noop_cannot_silently_skip_memories(setup_extraction):
    backend, receipt = setup_extraction(
        [_response('{"memories":[]}', {"finish_reason": "length"}), _response(_MEMORY)]
    )

    outcome = await extraction.extract_session_memory(backend, None, "u1", {"session_id": "s1"})

    assert outcome.status == "succeeded"
    assert len(receipt.prompts) == 2
    backend.retain.assert_awaited_once()


async def test_malformed_completed_response_does_not_trigger_output_limit_recovery(
    setup_extraction,
):
    backend, receipt = setup_extraction([_response("not JSON", {"finish_reason": "stop"})])

    outcome = await extraction.extract_session_memory(backend, None, "u1", {"session_id": "s1"})

    assert outcome.status == "failed"
    assert outcome.error == "unparseable_output"
    assert len(receipt.prompts) == 1
    backend.retain.assert_not_awaited()
