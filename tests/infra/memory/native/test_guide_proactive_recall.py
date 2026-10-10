"""Memory guide must nudge proactive recall for project-convention questions."""

from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS


def test_guides_trigger_recall_for_project_convention_questions() -> None:
    # 无提示时模型对"这个项目怎么装依赖"类问题容易直接泛答；
    # 指南需点名项目约定/依赖/历史决策类问题先召回。
    for guide in (NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS):
        assert "conventions" in guide
        assert "recall first" in guide


def test_guides_respect_gui_only_scope_and_skip_transient_screen_memory() -> None:
    for guide in (NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS):
        assert "User tool restrictions override memory" in guide
        assert "GUI-only tasks: use live state" in guide
        assert "do not recall or retain screen positions" in guide


def test_guides_disallow_workflow_memory_during_gui_only_tasks() -> None:
    for guide in (NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS):
        assert "GUI-only tasks: use live state; no memory tools" in guide
