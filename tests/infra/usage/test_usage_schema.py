from src.kernel.schemas.usage import UsageLog


def test_usage_api_retains_per_counter_unknown_fields():
    payload = UsageLog.model_validate(
        {
            "trace_id": "cancelled-trace",
            "session_id": "session",
            "user_id": "owner",
            "input_tokens": 42,
            "output_tokens": 0,
            "usage_incomplete": True,
            "unknown_usage_fields": ["output_tokens", "total_tokens"],
        }
    ).model_dump()
    assert payload["unknown_usage_fields"] == ["output_tokens", "total_tokens"]
    assert payload["input_tokens"] == 42
