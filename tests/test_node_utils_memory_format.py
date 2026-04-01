import os

os.environ["DEBUG"] = "false"

from src.agents.core import node_utils


def test_schedule_auto_retain_labels_user_and_assistant_messages(monkeypatch):
    captured = {}
    monkeypatch.setattr(node_utils.settings, "ENABLE_MEMORY", True)

    def fake_schedule_auto_retain(
        *,
        user_id: str,
        conversation_summary: str,
        context: str | None = None,
        session_id: str | None = None,
    ) -> None:
        captured["user_id"] = user_id
        captured["conversation_summary"] = conversation_summary
        captured["context"] = context
        captured["session_id"] = session_id

    monkeypatch.setattr("src.infra.memory.tools.schedule_auto_retain", fake_schedule_auto_retain)

    node_utils.schedule_auto_retain(
        "我是杨洋，是一名程序员",
        "你好，杨洋！很高兴认识你。\n我已经记住了你的身份信息。",
        "user-1",
        session_id="session-1",
    )

    assert captured["user_id"] == "user-1"
    assert captured["context"] == "conversation_turn"
    assert captured["session_id"] == "session-1"
    assert captured["conversation_summary"] == (
        "User: 我是杨洋，是一名程序员\n\n"
        "Assistant: 你好，杨洋！很高兴认识你。\n我已经记住了你的身份信息。"
    )
