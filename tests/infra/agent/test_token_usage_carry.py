"""token:usage 跨 HITL 恢复累计（issue：审批恢复后只记最后一段）。

恢复分段重新执行 agent_node 时，AgentEventProcessor 计数器从零开始，
先前分段的用量经 seed_usage 并入，emit_token_usage 输出 run 累计值；
usage_logs 取 trace 最后一个 token:usage，自然拿到全量 token 与费用。
"""

from unittest.mock import AsyncMock, MagicMock

from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import Presenter


def _make_processor(emitted: list[dict]) -> AgentEventProcessor:
    presenter = MagicMock(spec=Presenter)
    presenter.emit = AsyncMock(side_effect=lambda e: emitted.append(e))
    presenter.present_token_usage = MagicMock(
        side_effect=lambda **kw: {"event": "token:usage", "data": kw}
    )
    return AgentEventProcessor(presenter)


def test_seed_usage_merges_prior_segment_counters():
    processor = _make_processor([])
    processor.seed_usage(
        {
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "cache_creation_tokens": 3,
            "cache_read_tokens": 7,
        }
    )
    # 本分段统计到的增量（模拟 process_event 累加）
    processor.total_input_tokens += 50
    processor.total_output_tokens += 10

    assert processor.usage_totals() == {
        "input_tokens": 1050,
        "output_tokens": 110,
        "total_tokens": 1100,
        "cache_creation_tokens": 3,
        "cache_read_tokens": 7,
    }


def test_seed_usage_ignores_empty_or_malformed_payload():
    processor = _make_processor([])
    processor.seed_usage(None)
    processor.seed_usage({})
    processor.seed_usage({"input_tokens": "x"})  # type: ignore[dict-item]

    assert processor.usage_totals() == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
    }


async def test_emit_token_usage_outputs_cumulative_totals_with_seeded_usage():
    emitted: list[dict] = []
    processor = _make_processor(emitted)
    processor.seed_usage({"input_tokens": 199581, "output_tokens": 6695})
    processor.total_input_tokens += 60358
    processor.total_output_tokens += 1063

    ok = await processor.emit_token_usage(duration=349.1)

    assert ok is True
    assert len(emitted) == 1
    data = emitted[0]["data"]
    assert data["input_tokens"] == 259939
    assert data["output_tokens"] == 7758
    assert data["total_tokens"] == 267697
    assert data["duration"] == 349.1


async def test_emit_token_usage_emits_with_seeded_usage_even_without_segment_llm_calls():
    """零 LLM 分段（挂起即恢复）也要刷新累计值，避免终态回退到分段口径。"""
    emitted: list[dict] = []
    processor = _make_processor(emitted)
    processor.seed_usage({"input_tokens": 500, "output_tokens": 5, "total_tokens": 505})

    ok = await processor.emit_token_usage(duration=2.0)

    assert ok is True
    assert emitted[0]["data"]["total_tokens"] == 505
