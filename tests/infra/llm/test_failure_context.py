"""失败上下文在包装层上的可观测性与错误分类(issue #1123 / #1140)。

`with_structured_output` 返回的 RunnableSequence/RunnableParallel 会把模型
元数据(名称/provider/协议/quota 标注)遮住,重试日志整体退化为
``model=unknown provider=unknown``;这里锁定解包链与 429/风控分类行为。
"""

import httpx
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from src.infra.llm.retry import (
    content_moderation_message,
    is_rate_limit_model_error,
    model_failure_context,
    model_failure_reason,
)


class _Questions(BaseModel):
    questions: list[str]


def _status_error(status_code: int, message: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://unit.invalid/v1/messages")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        message or f"HTTP {status_code}", request=request, response=response
    )


def test_structured_output_wrapper_keeps_model_labels():
    class _QuotaAnthropic(ChatAnthropic):
        quota_provider: str | None = None
        quota_model_config_id: str | None = None

    model = _QuotaAnthropic(model="glm-5.3", api_key="test-only", base_url="https://unit.invalid")
    model.quota_provider = "zai"
    model.quota_model_config_id = "cfg-1"
    wrapper = model.with_structured_output(_Questions, method="json_schema", include_raw=True)

    context = model_failure_context(wrapper)

    assert "model=glm-5.3" in context
    assert "provider=zai" in context
    assert "model_config_id=cfg-1" in context
    assert "protocol=" in context
    assert "protocol=unknown" not in context


def test_rate_limit_classification_distinguishes_429_from_other_transients():
    assert is_rate_limit_model_error(_status_error(429))
    assert not is_rate_limit_model_error(_status_error(500))
    assert model_failure_reason(_status_error(429)) == "rate_limit"
    assert model_failure_reason(_status_error(500)) == "transient"
    assert model_failure_reason(_status_error(401)) == "auth"
    assert model_failure_reason(_status_error(400)) == "error"
    assert model_failure_reason(None) == "invalid_output"


def test_content_moderation_message_maps_deepseek_risk_rejection():
    upstream = _status_error(
        400,
        "Error code: 400 - {'error': {'message': 'Content Exists Risk (request_id: 0xabc)', "
        "'type': 'invalid_request_error'}}",
    )

    message = content_moderation_message(upstream)

    assert message is not None
    assert "safety policy" in message
    assert "request_id" not in message


def test_content_moderation_message_ignores_ordinary_bad_requests():
    assert content_moderation_message(_status_error(400, "max_tokens is too large")) is None
    assert content_moderation_message(_status_error(429, "rate limited")) is None
