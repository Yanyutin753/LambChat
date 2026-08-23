"""ask_human 挂起时 run 尚未完成（waiting_human），自动记忆捕获必须推迟到
run 最终完成的那一轮，否则会在挂起瞬间白发起一次记忆评估 LLM 调用，且
source_refs 会指向没有最终回答的 run。"""

from src.agents.core.node_utils import resolve_auto_memory_capture_text


def test_suspended_run_defers_memory_capture() -> None:
    assert (
        resolve_auto_memory_capture_text(
            hitl_suspended=True,
            user_input="记住我偏好深色主题",
        )
        is None
    )


def test_finished_run_captures_user_input() -> None:
    assert (
        resolve_auto_memory_capture_text(
            hitl_suspended=False,
            user_input="记住我偏好深色主题",
        )
        == "记住我偏好深色主题"
    )


def test_final_resume_round_falls_back_to_recommendation_input() -> None:
    # 恢复轮 message 为空，原始用户消息经 resume_context.recommendation_input 透传
    assert (
        resolve_auto_memory_capture_text(
            hitl_suspended=False,
            user_input="",
            recommendation_input="帮我部署到生产环境",
        )
        == "帮我部署到生产环境"
    )


def test_user_input_takes_priority_over_recommendation_input() -> None:
    assert (
        resolve_auto_memory_capture_text(
            hitl_suspended=False,
            user_input="本轮新消息",
            recommendation_input="旧消息",
        )
        == "本轮新消息"
    )


def test_blank_inputs_capture_nothing() -> None:
    assert (
        resolve_auto_memory_capture_text(
            hitl_suspended=False,
            user_input="   ",
            recommendation_input=None,
        )
        is None
    )
