from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from src.infra.llm.retry import ainvoke_with_retry


@pytest.mark.parametrize(
    "metadata",
    [
        {"stop_reason": "max_tokens"},
        {"finish_reason": "length"},
        {"incomplete_details": {"reason": "max_output_tokens"}},
    ],
)
async def test_output_limited_reasoning_preserves_response_without_identical_retry(metadata):
    response = AIMessage(
        content=[{"type": "thinking", "thinking": "Incomplete reasoning"}],
        response_metadata=metadata,
        usage_metadata={"input_tokens": 100, "output_tokens": 32, "total_tokens": 132},
    )
    model = AsyncMock()
    model.ainvoke.return_value = response

    result = await ainvoke_with_retry(model, "Original task", max_retries=2, retry_delay=0)

    assert result is response
    assert result.usage_metadata["output_tokens"] == 32
    assert model.ainvoke.await_count == 1


async def test_output_limited_reasoning_uses_existing_fallback_without_primary_retry(monkeypatch):
    response = AIMessage(
        content="",
        response_metadata={"stop_reason": "max_tokens"},
        usage_metadata={"input_tokens": 100, "output_tokens": 32, "total_tokens": 132},
    )
    primary, fallback = AsyncMock(), AsyncMock()
    primary.ainvoke.return_value = response
    fallback.ainvoke.return_value = AIMessage(content="Completed with the alternate model")
    get_model = AsyncMock(return_value=fallback)
    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)

    result = await ainvoke_with_retry(
        primary, "Original task", max_retries=2, retry_delay=0, fallback_model="alternate"
    )

    assert result.content == "Completed with the alternate model"
    assert primary.ainvoke.await_count == 1
    assert fallback.ainvoke.await_count == 1
    assert response.usage_metadata["output_tokens"] == 32
    get_model.assert_awaited_once_with(model="alternate", thinking=None)
