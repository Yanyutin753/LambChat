from __future__ import annotations

from typing import Annotated

from langchain.tools import ToolRuntime
from langchain.tools import tool as lc_tool
from langchain_core.tools import InjectedToolArg

from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.tool_search_tool import ToolSearchTool


class _FakeTool:
    def __init__(self, name: str, description: str, server: str = "server") -> None:
        self.name = name
        self.description = description
        self.server = server

    @property
    def args(self) -> dict:
        # 模拟 BaseTool.args 公开 schema 面：MCP dict 直传，模型取 JSON schema。
        args_schema = getattr(self, "args_schema", None)
        if isinstance(args_schema, dict):
            return args_schema
        if args_schema is not None:
            return args_schema.model_json_schema()
        return {}


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

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(getattr(func, "__name__", "unknown"))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        tool_search_tool, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

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


@lc_tool
async def _parse_probe_tool(
    url: Annotated[str, "doc url"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Probe tool with injected runtime arg."""
    return "ok"


async def test_search_tools_formats_schema_for_injected_runtime_tools() -> None:
    """InjectedToolArg 参数不能让 schema 生成失败（#815）。

    带注入 runtime 的工具，原始 args_schema 含 CallableSchema，直接
    model_json_schema() 会抛错；搜索结果必须改用已过滤注入参数的公开
    schema，保证参数契约可见。工具须在模块级定义（闭包内装饰器无法
    解析字符串注解，得到空 schema）。
    """
    from src.infra.tool.tool_search import ToolSearchResult
    from src.infra.tool.tool_search_tool import _format_tool_result

    assert "url" in _parse_probe_tool.args
    assert "runtime" not in _parse_probe_tool.args

    result = _format_tool_result(
        ToolSearchResult(
            name=_parse_probe_tool.name,
            description=_parse_probe_tool.description,
            score=1.0,
            tool=_parse_probe_tool,
        )
    )

    assert '"url"' in result
    assert '"runtime"' not in result
