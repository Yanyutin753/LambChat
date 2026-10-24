from pathlib import Path

import pytest

from src.agents.core.node_utils import build_human_message
from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.document_parse_tool import get_document_parse_tool


def test_search_guide_does_not_request_discovery_for_already_loaded_tools():
    from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE

    assert "Call already-loaded tools directly" in DEFERRED_TOOL_SEARCH_GUIDE
    assert "schemas are not loaded" not in DEFERRED_TOOL_SEARCH_GUIDE


@pytest.mark.parametrize(
    "filename",
    [
        "report.pdf",
        "REPORT.PDF",
        "report.docx",
        "slides.pptx",
        "legacy.doc",
        "legacy.ppt",
        "text.odt",
    ],
)
def test_attached_document_exposes_authorized_parser_before_first_model_call(filename):
    tool = get_document_parse_tool()
    manager = DeferredToolManager([], "session", deferred_system_tools=[tool])
    before = manager.get_deferred_stubs_string()
    manager.discover_attachment_tools([{"name": filename, "id": "file-1"}])
    assert manager.get_discovered_tools() == [tool]
    manager.discover_attachment_tools([{"name": filename}])
    assert manager.discovered_names == ["document_parse"]
    assert manager.get_deferred_stubs_string() == before
    assert manager.fork_for_scope("subagent").get_discovered_tools() == [tool]


@pytest.mark.parametrize(
    "case", ["disabled", "policy_removed", "mcp_impostor", "image", "no_attachments"]
)
def test_attachment_discovery_never_bypasses_tool_policy_or_promotes_unrelated_tools(case):
    tool = get_document_parse_tool()
    manager = DeferredToolManager(
        [tool] if case == "mcp_impostor" else [],
        "session",
        deferred_system_tools=[] if case in {"policy_removed", "mcp_impostor"} else [tool],
        disabled_tools=["document_parse"] if case == "disabled" else [],
    )
    manager.discover_attachment_tools(
        []
        if case == "no_attachments"
        else [{"name": "image.png" if case == "image" else "file.pdf"}]
    )
    assert manager.get_discovered_tools() == []


def test_document_attachment_hint_prefers_direct_parse_to_sandbox_download():
    message = build_human_message(
        "Read this",
        [
            {
                "id": "file-1",
                "key": "uploads/a.pdf",
                "name": "a.pdf",
                "url": "/api/upload/file/uploads/a.pdf",
                "type": "document",
            }
        ],
    )
    assert "document_parse(attachment_id=" in str(message.content)
    assert "without downloading" in str(message.content)


@pytest.mark.parametrize("agent", ["search_agent", "team_agent"])
def test_agent_discovers_document_tool_after_permission_filtering_before_subagent_forks(agent):
    source = (Path(__file__).parents[3] / "src" / "agents" / agent / "nodes.py").read_text()
    call = source.index("context.deferred_manager.discover_attachment_tools(attachments)")
    assert source.index("prepared = await prepare_agent_inputs(") < call
    assert call < source.index("fork_for_scope(")
