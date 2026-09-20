"""延迟工具发现指引：MCP-Atlas 失败归因（2026-09-20）显示模型宁可反复用
原生 ls/glob 搜空工作区、然后宣布「数据不可用」，也不按域搜索延迟工具
（git_git_status 等）。指引必须显式要求下结论前先按域搜工具。"""

from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE


def test_guide_requires_domain_search_before_declaring_unavailable() -> None:
    lowered = DEFERRED_TOOL_SEARCH_GUIDE.lower()
    assert "search_tools" in lowered
    assert "unavailable" in lowered or "not available" in lowered
    assert "domain" in lowered or "git" in lowered
