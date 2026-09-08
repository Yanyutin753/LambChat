"""HITL 恢复的 run 用量携带（issue：审批恢复后 token:usage 只记最后一段）。

agent_node 每次恢复都从节点顶部重新执行，计时锚点与 token 计数器随之清零。
resolve_run_usage_carry 从 configurable.hitl_resume 还原原 run 的起点与
先前分段的累计用量，让 token:usage 事件跨恢复累计。
"""

from src.agents.core.node_utils import resolve_run_usage_carry


def test_no_hitl_resume_falls_back_to_node_entry_time():
    started_at, prior_usage = resolve_run_usage_carry(None, default_started_at=123.5)
    assert started_at == 123.5
    assert prior_usage is None


def test_hitl_resume_carries_run_anchor_and_prior_usage():
    prior = {
        "input_tokens": 199581,
        "output_tokens": 6695,
        "total_tokens": 206276,
        "cache_creation_tokens": 10,
        "cache_read_tokens": 20,
    }
    started_at, carried = resolve_run_usage_carry(
        {"run_started_at": 111.5, "prior_usage": dict(prior)},
        default_started_at=999.0,
    )
    assert started_at == 111.5
    assert carried == prior


def test_malformed_hitl_resume_falls_back_to_defaults():
    started_at, carried = resolve_run_usage_carry(
        {"run_started_at": "not-a-number", "prior_usage": "garbage"},
        default_started_at=42.0,
    )
    assert started_at == 42.0
    assert carried is None


def test_partial_hitl_resume_still_restores_anchor():
    started_at, carried = resolve_run_usage_carry(
        {"run_started_at": 77.25},
        default_started_at=42.0,
    )
    assert started_at == 77.25
    assert carried is None
