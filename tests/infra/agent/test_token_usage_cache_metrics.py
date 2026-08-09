import pytest

from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import create_presenter


class _Response:
    def __init__(self, *, usage_metadata=None, response_metadata=None, metadata=None):
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}
        self.metadata = metadata or {}


def _processor() -> AgentEventProcessor:
    return AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )


def test_token_usage_counts_openai_cached_tokens_as_cache_read() -> None:
    processor = AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )
    response = _Response(
        usage_metadata={
            "input_tokens": 1200,
            "output_tokens": 30,
            "input_token_details": {"cached_tokens": 900},
        }
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_input_tokens == 1200
    assert processor.total_cache_read_tokens == 900


def test_token_usage_counts_openai_response_metadata_cached_tokens() -> None:
    processor = AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )
    response = _Response(
        usage_metadata=None,
        response_metadata={
            "token_usage": {
                "prompt_tokens": 2000,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 1536},
            }
        },
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_input_tokens == 2000
    assert processor.total_output_tokens == 50
    assert processor.total_cache_read_tokens == 1536


def test_token_usage_counts_gemini_cached_content_tokens_as_cache_read() -> None:
    processor = AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )
    response = _Response(
        usage_metadata={
            "input_tokens": 1500,
            "output_tokens": 40,
            "input_token_details": {"cached_content_token_count": 1000},
        }
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_input_tokens == 1500
    assert processor.total_cache_read_tokens == 1000


def test_token_usage_counts_minimax_anthropic_passive_cache_tokens() -> None:
    processor = AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )
    response = _Response(
        usage_metadata={
            "input_tokens": 108,
            "output_tokens": 91,
            "cache_creation_input_tokens": 12000,
            "cache_read_input_tokens": 14813,
        }
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_input_tokens == 108
    assert processor.total_output_tokens == 91
    assert processor.total_cache_creation_tokens == 12000
    assert processor.total_cache_read_tokens == 14813


def test_token_usage_does_not_double_count_duplicate_cache_fields() -> None:
    processor = AgentEventProcessor(
        create_presenter(session_id="session-1", agent_id="search", agent_name="Search")
    )
    response = _Response(
        usage_metadata={
            "input_tokens": 108,
            "input_token_details": {
                "cache_creation_input_tokens": 12000,
                "cache_read": 14813,
            },
            "cache_creation_input_tokens": 12000,
            "cache_read_input_tokens": 14813,
        }
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_cache_creation_tokens == 12000
    assert processor.total_cache_read_tokens == 14813


@pytest.mark.parametrize(
    "field",
    ["prompt_cache_hit_tokens", "cached_content_token_count", "total_cached_tokens"],
)
def test_token_usage_reads_raw_provider_cache_hit_aliases(field: str) -> None:
    processor = _processor()
    response = _Response(
        usage_metadata={"input_tokens": 2000},
        response_metadata={"usage": {field: 1536}},
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_input_tokens == 2000
    assert processor.total_cache_read_tokens == 1536


def test_token_usage_reads_openai_cache_write_tokens() -> None:
    processor = _processor()
    response = _Response(
        usage_metadata={"input_tokens": 2000},
        response_metadata={"usage": {"cache_write_tokens": 1024}},
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_cache_creation_tokens == 1024


def test_standard_cache_usage_wins_without_double_counting_raw_alias() -> None:
    processor = _processor()
    response = _Response(
        usage_metadata={
            "input_tokens": 2000,
            "input_token_details": {"cache_read": 1536},
        },
        response_metadata={"usage": {"prompt_cache_hit_tokens": 1536}},
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_cache_read_tokens == 1536


def test_token_usage_falls_back_to_response_metadata_nested_details() -> None:
    processor = _processor()
    response = _Response(
        usage_metadata={"input_tokens": 2000},
        response_metadata={
            "token_usage": {
                "prompt_tokens_details": {
                    "cached_tokens": 1536,
                }
            }
        },
    )

    processor._handle_token_usage({"data": {"output": response}})

    assert processor.total_cache_read_tokens == 1536
