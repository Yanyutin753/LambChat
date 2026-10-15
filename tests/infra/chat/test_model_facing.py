from src.infra.chat.model_facing import append_required_skills_prompt
from src.infra.chat.session_baseline import assemble_first_turn_message


def test_required_skills_explain_inline_references_and_file_tool_usage():
    raw = "先 [引用技能：preview-budget-plan] 制定预算，再 [引用技能：lambchat-coding] 实现。"
    message = append_required_skills_prompt(raw, ["preview-budget-plan", "lambchat-coding"])

    assert message.startswith(raw + "\n\n")
    assert "1. preview-budget-plan: /skills/preview-budget-plan/SKILL.md" in message
    assert "2. lambchat-coding: /skills/lambchat-coding/SKILL.md" in message
    assert "[引用技能：name]" in message
    assert "read_file" in message
    assert "not shell" in message
    assert "not tool names" in message
    assert "surrounding text" in message
    assert "listed order" in message


def test_required_skills_deduplicate_without_reordering_selection():
    message = append_required_skills_prompt(
        "review then write", ["reviewer", "", "writer", "reviewer"]
    )
    assert message.count("/skills/reviewer/SKILL.md") == 1
    assert message.count("/skills/writer/SKILL.md") == 1
    assert message.index("1. reviewer:") < message.index("2. writer:")
    assert append_required_skills_prompt("hello", [""]) == "hello"


def test_inline_markers_alone_do_not_enable_skills():
    raw = "这是引用文本 [引用技能：unselected]"
    assert append_required_skills_prompt(raw, None) == raw
    assert append_required_skills_prompt(raw, []) == raw
    message = append_required_skills_prompt(raw, ["writer"])
    assert "/skills/unselected/" not in message
    assert "/skills/writer/SKILL.md" in message


async def test_first_turn_assembly_retains_inline_order_and_required_skills():
    raw = "前文 [引用技能：writer] 中段 [引用技能：reviewer] 结尾"
    message, injected_context = await assemble_first_turn_message(
        raw_message=raw,
        user_timezone="Asia/Shanghai",
        enabled_skills=["writer", "reviewer"],
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_timestamp=False,
        last_tc_signature=None,
    )
    assert message.startswith(raw + "\n\n")
    assert message.index("1. writer:") < message.index("2. reviewer:")
    assert injected_context is False
