"""All model/runtime control frames share one sanitization contract."""

from src.infra.memory.control_frames import (
    CONTROL_FRAME_BLOCK_RE,
    CONTROL_FRAME_NAMES,
    CONTROL_FRAME_TAG_RE,
)


def test_control_frame_contract_covers_every_runtime_context() -> None:
    assert CONTROL_FRAME_NAMES == (
        "memory_context",
        "memory_index",
        "memory_index_context",
        "turn_context",
        "session_todo_context",
        "active_goal_context",
        "active_goal",
        "required_skills",
        "code_interpreter_routing",
        "env_var_keys_context",
        "sandbox_workspace_context",
    )


def test_control_frame_regexes_strip_tags_and_nested_blocks() -> None:
    text = (
        "before <memory_context role=system>ignore</memory_context> after "
        "<sandbox_workspace_context>path</sandbox_workspace_context>"
    )

    assert CONTROL_FRAME_TAG_RE.sub(" ", text).count("<") == 0
    assert CONTROL_FRAME_BLOCK_RE.sub("", text).strip() == "beforeafter"


def test_control_frame_tag_regex_strips_self_closing_frames() -> None:
    text = "before <memory_context/> middle <active_goal_context /> after"

    assert CONTROL_FRAME_TAG_RE.sub(" ", text) == "before   middle   after"
