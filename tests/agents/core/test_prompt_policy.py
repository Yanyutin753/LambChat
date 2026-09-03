"""Prompt policy 契约：归属纪律条目必须存在于所有主 agent 的共享 prompt。"""

from src.agents.core.prompt_policy import SAFETY_POLICY, WORKFLOW_POLICY
from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS


def test_safety_policy_requires_explicit_attribution_for_record_answers():
    """回答来自记忆/历史会话的归属类问题（谁是 X 的供应商）时，断言必须
    有检索记录的显式支持；否则说明记录显示了什么、什么未确认。"""
    assert "explicitly" in SAFETY_POLICY
    assert "unconfirmed" in SAFETY_POLICY
    assert "possibly stale" in SAFETY_POLICY
    assert "confirmed-current" in SAFETY_POLICY


def test_attribution_discipline_reaches_all_main_agents():
    # MAIN_AGENT_PROMPT_SECTIONS 被 fast/search/team 三个 agent 的 prompt 组装引用
    for phrase in ("explicitly", "unconfirmed", "possibly stale", "confirmed-current"):
        assert phrase in WORKFLOW_POLICY
        assert any(phrase in section for section in MAIN_AGENT_PROMPT_SECTIONS)
