from __future__ import annotations

from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.tool_search_tool import ToolSearchTool


class _FakeTool:
    def __init__(self, name: str, description: str, server: str = "server") -> None:
        self.name = name
        self.description = description
        self.server = server


class _HugeArgsSchema:
    @classmethod
    def model_json_schema(cls):
        return {
            "type": "object",
            "properties": {
                "choice": {
                    "type": "string",
                    "description": "Pick one generated option.",
                    "enum": [f"option-{idx:05d}" for idx in range(5000)],
                }
            },
            "required": ["choice"],
        }


class _SemanticArgsSchema:
    @classmethod
    def model_json_schema(cls):
        return {
            "title": "Annotation-only title",
            "description": "Annotation-only top-level description",
            "examples": [{"mode": "quick"}],
            "type": "object",
            "properties": {
                "mode": {"$ref": "#/$defs/Mode"},
            },
            "required": ["mode"],
            "additionalProperties": False,
            "$defs": {
                "Mode": {
                    "oneOf": [
                        {"type": "string", "const": "quick"},
                        {"type": "string", "const": "deep"},
                    ]
                }
            },
            "oneOf": [{"required": ["mode"]}],
            "anyOf": [{"type": "object"}],
            "allOf": [{"additionalProperties": False}],
        }


async def test_search_tools_caps_oversized_schema_output() -> None:
    tool = _FakeTool("server:huge_schema", "huge schema test tool")
    tool.args_schema = _HugeArgsSchema
    manager = DeferredToolManager(all_deferred_tools=[tool], session_id="session-1")
    search_tool = ToolSearchTool(manager=manager, search_limit=5)

    result = await search_tool._arun("select:server:huge_schema")

    assert len(result) < 20_000
    assert "schema truncated" in result
    assert "option-00000" in result
    assert "option-04999" not in result


async def test_search_tools_offloads_search_and_schema_formatting(
    monkeypatch,
) -> None:
    from src.infra.tool import tool_search_tool

    calls: list[str] = []
    tool = _FakeTool("server:huge_schema", "huge schema test tool")
    tool.args_schema = _HugeArgsSchema
    manager = DeferredToolManager(all_deferred_tools=[tool], session_id="session-1")
    search_tool = ToolSearchTool(manager=manager, search_limit=5)

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(getattr(func, "__name__", "unknown"))
        return func(*args, **kwargs)

    monkeypatch.setattr(tool_search_tool, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = await search_tool._arun("select:server:huge_schema")

    assert "Found 1 tool(s)" in result
    assert calls == ["_search_and_format_tool_results"]


async def test_search_tools_returns_compact_callable_schema_without_ranking_noise() -> None:
    tool = _FakeTool("system:semantic", "Semantic schema test", server="")
    tool.args_schema = _SemanticArgsSchema
    manager = DeferredToolManager(all_deferred_tools=[tool], session_id="session-1")
    search_tool = ToolSearchTool(manager=manager, search_limit=5)

    result = await search_tool._arun("select:system:semantic")

    assert "Loaded 1 new; 0 already available." in result
    assert "call it directly next" in result
    assert '"type":"object"' in result
    assert '"properties":{"mode":{"$ref":"#/$defs/Mode"}}' in result
    assert '"required":["mode"]' in result
    assert '"additionalProperties":false' in result
    assert '"$defs"' in result
    assert '"oneOf"' in result
    assert '"anyOf"' in result
    assert '"allOf"' in result
    assert "Annotation-only title" not in result
    assert "Annotation-only top-level description" not in result
    assert '"examples"' not in result
    assert "score:" not in result
    assert '\n  "' not in result
