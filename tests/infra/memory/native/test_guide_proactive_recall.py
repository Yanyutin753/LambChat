"""Memory guide must nudge proactive recall for project-convention questions."""

from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS


def test_guides_trigger_recall_for_project_convention_questions() -> None:
    # 无提示时模型对"这个项目怎么装依赖"类问题容易直接泛答；
    # 指南需点名项目约定/依赖/历史决策类问题先召回。
    for guide in (NATIVE_MEMORY_GUIDE, NATIVE_MEMORY_GUIDE_VFS):
        assert "conventions" in guide
        assert "recall first" in guide
