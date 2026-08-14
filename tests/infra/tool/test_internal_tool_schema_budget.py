from __future__ import annotations

from pathlib import Path
from typing import Any

import tiktoken
import tiktoken.load
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.infra.tool.audio_transcribe_tool import get_audio_transcribe_tool
from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.env_var_tool import get_env_var_tools
from src.infra.tool.human_tool.tool import AskHumanTool
from src.infra.tool.image_analysis_tool import get_image_analysis_tool
from src.infra.tool.image_generation_tool import (
    get_image_generation_tool,
    get_reference_image_generation_tool,
)
from src.infra.tool.persona_preset_tool import get_persona_preset_tools
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.infra.tool.scheduled_task import get_scheduled_task_tools
from src.infra.tool.team_tool import get_team_tools
from src.infra.tool.tool_search_tool import ToolSearchTool
from src.infra.tool.transfer_file_tool import (
    get_transfer_file_tool,
    get_transfer_path_tool,
)
from src.infra.tool.upload_url_tool import get_upload_url_tool

MAX_ESTIMATED_SCHEMA_TOKENS = 5700
EXPECTED_TOOL_NAMES = {
    "ask_human",
    "audio_transcribe",
    "create_agent_team",
    "env_var_delete",
    "env_var_list",
    "env_var_set",
    "image_analyze",
    "image_edit_with_references",
    "image_generate",
    "reveal_file",
    "reveal_project",
    "save_persona_preset",
    "scheduled_task_create",
    "scheduled_task_delete",
    "scheduled_task_list",
    "scheduled_task_update",
    "search_persona_presets",
    "search_tools",
    "transfer_file",
    "transfer_path",
    "upload_url_to_sandbox",
}


def _scoped_tools() -> list[BaseTool]:
    return [
        get_audio_transcribe_tool(),
        *get_env_var_tools(),
        AskHumanTool(),
        get_image_analysis_tool(),
        get_image_generation_tool(),
        get_reference_image_generation_tool(),
        *get_persona_preset_tools(),
        get_reveal_file_tool(),
        get_reveal_project_tool(),
        *get_scheduled_task_tools(),
        *get_team_tools(),
        get_transfer_file_tool(),
        get_transfer_path_tool(),
        get_upload_url_tool(),
        ToolSearchTool(
            manager=DeferredToolManager(all_deferred_tools=[], session_id="schema-budget")
        ),
    ]


def _definitions(tools: list[BaseTool] | None = None) -> dict[str, dict[str, Any]]:
    scoped_tools = tools if tools is not None else _scoped_tools()
    return {tool.name: convert_to_openai_tool(tool)["function"] for tool in scoped_tools}


def _estimated_token_count(definitions: dict[str, dict[str, Any]]) -> int:
    # Model-specific tiktoken encodings are downloaded lazily; tests must stay offline.
    return count_tokens_approximately([], tools=list(definitions.values()))


def _enum_values(property_schema: dict[str, Any]) -> list[str] | None:
    if "enum" in property_schema:
        return property_schema["enum"]
    for branch in property_schema.get("anyOf", []):
        if isinstance(branch, dict) and "enum" in branch:
            return branch["enum"]
    return None


def test_schema_budget_measurement_does_not_require_network(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.delitem(tiktoken.registry.ENCODINGS, "o200k_base", raising=False)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))

    def reject_download(_: str) -> bytes:
        raise AssertionError("schema budget measurement must stay offline")

    monkeypatch.setattr(tiktoken.load, "read_file", reject_download)
    definitions = {
        "example": {
            "name": "example",
            "description": "abcd汉",
            "parameters": {"type": "object", "properties": {}},
        }
    }

    assert _estimated_token_count(definitions) == 25


def test_internal_tool_schema_token_budget() -> None:
    tools = _scoped_tools()
    names = [tool.name for tool in tools]
    definitions = _definitions(tools)

    assert len(names) == len(EXPECTED_TOOL_NAMES)
    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_TOOL_NAMES
    assert _estimated_token_count(definitions) <= MAX_ESTIMATED_SCHEMA_TOKENS


def test_closed_string_arguments_are_exposed_as_enums() -> None:
    definitions = _definitions()

    expected = {
        ("image_generate", "background"): ["auto", "opaque", "transparent"],
        ("image_generate", "input_fidelity"): ["low", "high"],
        ("image_generate", "quality"): ["auto", "low", "medium", "high"],
        ("image_generate", "output_format"): ["png", "jpeg", "webp"],
        ("image_edit_with_references", "background"): [
            "auto",
            "opaque",
            "transparent",
        ],
        ("image_edit_with_references", "input_fidelity"): ["low", "high"],
        ("image_edit_with_references", "quality"): ["auto", "low", "medium", "high"],
        ("image_edit_with_references", "output_format"): ["png", "jpeg", "webp"],
        ("save_persona_preset", "scope"): ["user", "global"],
        ("save_persona_preset", "visibility"): ["private", "public"],
        ("save_persona_preset", "status"): ["draft", "published", "archived"],
        ("scheduled_task_create", "trigger_type"): ["date", "interval", "cron"],
        ("scheduled_task_list", "status"): ["active", "paused", "deleted"],
        ("scheduled_task_update", "action"): ["pause", "resume", "run"],
    }
    for (tool_name, parameter), values in expected.items():
        schema = definitions[tool_name]["parameters"]["properties"][parameter]
        assert _enum_values(schema) == values


def test_compact_descriptions_keep_tool_selection_boundaries() -> None:
    definitions = _definitions()
    required_markers = {
        "ask_human": ("choices", "fields", "确认"),
        "image_generate": ("generate", "edit", "reference"),
        "image_edit_with_references": ("reference", "required"),
        "reveal_file": ("单个", "reveal_project"),
        "reveal_project": ("目录", "folder"),
        "scheduled_task_create": ("date", "interval", "cron", "timezone"),
        "create_agent_team": ("search_persona_presets", "member"),
        "transfer_file": ("text", "/skills/"),
        "transfer_path": ("text", "10mb", "100mb", "500"),
        "search_tools": ("+", "select:"),
    }
    for tool_name, markers in required_markers.items():
        function = definitions[tool_name]
        descriptions = [function["description"]]
        descriptions.extend(
            schema.get("description", "")
            for schema in function["parameters"]["properties"].values()
        )
        text = " ".join(descriptions).lower()
        assert all(marker.lower() in text for marker in markers), tool_name


def test_compact_descriptions_keep_valid_free_form_object_shapes() -> None:
    definitions = _definitions()
    create_properties = definitions["scheduled_task_create"]["parameters"]["properties"]
    update_properties = definitions["scheduled_task_update"]["parameters"]["properties"]
    team_properties = definitions["create_agent_team"]["parameters"]["properties"]

    assert "10-7200" in create_properties["timeout_seconds"]["description"]
    assert "10-7200" in update_properties["timeout_seconds"]["description"]

    trigger_description = update_properties["trigger_config"]["description"]
    assert '{"seconds":300}' in trigger_description
    assert '{"hour":"9","minute":"0","day_of_week":"mon-fri"}' in trigger_description

    starter_description = team_properties["starter_prompts"]["description"]
    assert "'text': {'zh':" in starter_description
    assert "'en':" in starter_description
    assert "'icon': '🔎'" in starter_description

    members_description = team_properties["members"]["description"]
    assert "2-5 members" in members_description
    assert "1 member" in members_description
    assert "role_instructions" in members_description
    assert "role_avatar" in members_description
