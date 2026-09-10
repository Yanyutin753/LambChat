"""生图多模型目录：解析 IMAGE_GENERATION_MODELS 设置并生成按次可选的工具 schema。

设置热更新 + 工具按请求经工厂重建，新模型上线只需在设置面板加一条
{name, description}，无需改代码发版。
"""

from __future__ import annotations

from typing import Any, Literal, cast

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

DEFAULT_IMAGE_GENERATION_MODEL = "gpt-image-2"

# 单模型（IMAGE_GENERATION_MODELS 为空）时的通用参数说明；多模型清单非空时工厂
# 会用带各模型描述的目录文案覆盖该字段。
MODEL_PARAM_DESCRIPTION = "Image model name; omit for default."

# 按清单缓存已构建的动态工具，避免每请求重建 pydantic 模型；清单（含描述）
# 变化即生成新 key，设置热更新后工厂立即可见。
_dynamic_tool_cache: dict[tuple[str, tuple[tuple[str, str], ...]], BaseTool] = {}


def resolve_model_choices() -> list[tuple[str, str]]:
    """解析 IMAGE_GENERATION_MODELS 多模型清单为 (name, description) 列表。

    条目缺 name 跳过并告警；重名去重（首个保留）；非 list 配置视为空。
    """
    raw = getattr(settings, "IMAGE_GENERATION_MODELS", None)
    if not isinstance(raw, (list, tuple)):
        if raw:
            logger.warning(
                "[image_generate] IMAGE_GENERATION_MODELS expects a JSON array, got %s; ignored",
                type(raw).__name__,
            )
        return []

    choices: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            name, description = entry.strip(), ""
        elif isinstance(entry, dict):
            name = str(entry.get("name", "") or "").strip()
            description = str(entry.get("description", "") or "").strip()
        else:
            name, description = "", ""
        if not name:
            logger.warning(
                "[image_generate] skipping IMAGE_GENERATION_MODELS entry without a name: %r",
                entry,
            )
            continue
        if name in seen:
            continue
        seen.add(name)
        choices.append((name, description))
    return choices


def _format_model_catalog(choices: list[tuple[str, str]]) -> str:
    parts = []
    for name, description in choices:
        parts.append(f"{name} ({description})" if description else name)
    return "; ".join(parts)


def resolve_model(requested: str | None = None) -> str:
    """清单非空：首个为默认，requested 必须命中清单（否则报错列出全部可选模型）。

    清单为空：回落旧单模型设置 IMAGE_GENERATION_MODEL；此时 requested 也必须
    与其一致，避免「用户点名新模型却被旧模型静默代画」。
    """
    requested_name = str(requested or "").strip()
    choices = resolve_model_choices()
    if not choices:
        model = getattr(settings, "IMAGE_GENERATION_MODEL", "") or DEFAULT_IMAGE_GENERATION_MODEL
        model = str(model).strip() or DEFAULT_IMAGE_GENERATION_MODEL
        if not requested_name or requested_name == model:
            return model
        raise ValueError(
            f"Unknown image model '{requested_name}'. Available models: {model} "
            "(multi-model selection requires IMAGE_GENERATION_MODELS to be configured)"
        )

    if not requested_name:
        return choices[0][0]
    for name, _ in choices:
        if name == requested_name:
            return name
    raise ValueError(
        f"Unknown image model '{requested_name}'. "
        f"Available models: {_format_model_catalog(choices)}"
    )


def _model_catalog_description(choices: list[tuple[str, str]]) -> str:
    lines = [f"Image model to use; omit for the default ({choices[0][0]})."]
    for name, description in choices:
        lines.append(f"- {name}: {description}" if description else f"- {name}")
    return "\n".join(lines)


def _build_dynamic_model_tool(base_tool: BaseTool, choices: list[tuple[str, str]]) -> BaseTool:
    names = tuple(name for name, _ in choices)
    model_annotation: Any = Literal[names]  # type: ignore[misc]
    # 静态 @tool 产物必为 StructuredTool，其 args_schema 为 pydantic v2 模型
    structured = cast("StructuredTool", base_tool)
    dynamic_args = create_model(
        f"{base_tool.name}_dynamic_args",
        __base__=cast("type[BaseModel]", base_tool.args_schema),
        model=(
            model_annotation,
            Field(default=names[0], description=_model_catalog_description(choices)),
        ),
    )
    return StructuredTool(
        name=base_tool.name,
        description=base_tool.description,
        args_schema=dynamic_args,
        func=structured.func,
        coroutine=structured.coroutine,
    )


def tool_with_dynamic_model_catalog(base_tool: BaseTool) -> BaseTool:
    """清单非空时返回 model 参数为枚举（描述内嵌目录）的工具，否则原样返回。"""
    choices = resolve_model_choices()
    if not choices:
        return base_tool
    key = (base_tool.name, tuple(choices))
    tool = _dynamic_tool_cache.get(key)
    if tool is None:
        tool = _build_dynamic_model_tool(base_tool, choices)
        _dynamic_tool_cache[key] = tool
    return tool
