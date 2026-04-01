import os

os.environ["DEBUG"] = "false"

from src.agents.core.subagent_prompts import WORKFLOW_SECTION
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.infra.tool.reveal_file_tool import reveal_file


def test_fast_agent_prompt_requires_reveal_file_for_user_visible_files():
    assert (
        "If the user asks to see/open/show a file, you MUST call `reveal_file`."
        in FAST_SYSTEM_PROMPT
    )
    assert "Returning only a file path is NOT sufficient." in FAST_SYSTEM_PROMPT
    assert "The user cannot directly access the isolated filesystem." in FAST_SYSTEM_PROMPT


def test_search_agent_prompt_requires_reveal_file_for_user_visible_files():
    assert (
        "If the user asks to see/open/show a file, you MUST call `reveal_file`." in WORKFLOW_SECTION
    )
    assert "Returning only a file path is NOT sufficient." in WORKFLOW_SECTION
    assert "The user cannot directly access the isolated filesystem." in WORKFLOW_SECTION


def test_reveal_file_tool_description_explains_isolated_filesystem_requirement():
    description = reveal_file.description

    assert "用户要求查看、打开、显示文件时，必须调用此工具" in description
    assert "只回复文件路径或文件名是不够的" in description
    assert "用户无法直接访问隔离环境中的文件系统" in description
