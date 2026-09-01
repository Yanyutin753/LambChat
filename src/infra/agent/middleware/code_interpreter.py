"""Optional QuickJS code interpreter middleware for Deep Agents."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

_EVAL_TOOL_NAME = "eval"

_ROUTING_WITH_SANDBOX = (
    "Use this REPL for exact computation — arithmetic, date/time derivation, "
    "regex and JSON transforms, small algorithm checks. It returns in "
    "milliseconds without starting the sandbox. Use `execute` only when the "
    "task needs files, shell, Python, package installs, or network access; "
    "never boot the sandbox just to compute a value."
)

_ROUTING_WITHOUT_SANDBOX = (
    "Use this REPL for exact computation instead of mental math — arithmetic, "
    "date/time derivation, regex and JSON transforms, small algorithm checks. "
    "It has no filesystem, network, or real clock; do not attempt file or "
    "network work through it."
)


def _is_enabled_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "enable"}
    return False


class CodeInterpreterRoutingMiddleware(AgentMiddleware):
    """Attaches routing guidance to the REPL tool description.

    Codex-style layering: routing guidance lives on the tool the model
    chooses between, not in the system prompt. The text is static per
    session, so the tools prefix stays byte-identical across turns. When
    the eval tool is not part of the request the guidance is dropped —
    telling the model to route to an absent tool would be wrong.
    """

    _FRAME_MARKER = "<code_interpreter_routing>"

    def __init__(self, *, sandbox_active: bool) -> None:
        super().__init__()
        routing = _ROUTING_WITH_SANDBOX if sandbox_active else _ROUTING_WITHOUT_SANDBOX
        self._framed = (
            f"{self._FRAME_MARKER}\n"
            "Tool-routing guidance for this REPL.\n"
            f"{routing}\n"
            "</code_interpreter_routing>"
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        tools = list(request.tools)
        eval_index = next(
            (
                index
                for index, tool in enumerate(tools)
                if getattr(tool, "name", "") == _EVAL_TOOL_NAME
            ),
            None,
        )
        if eval_index is None:
            return await handler(request)
        target = tools[eval_index]
        if isinstance(target, BaseTool):
            base_description = target.description or ""
            if self._FRAME_MARKER not in base_description:
                tools[eval_index] = target.model_copy(
                    update={"description": f"{base_description}\n\n{self._framed}"}
                )
                request = request.override(tools=tools)
        return await handler(request)


def create_code_interpreter_middleware(
    agent_options: dict[str, Any] | None,
    *,
    sandbox_active: bool = False,
) -> list[Any]:
    """Create interpreter and routing middleware when globally and per-run enabled."""
    if not getattr(settings, "ENABLE_CODE_INTERPRETER", False):
        return []

    if not _is_enabled_value((agent_options or {}).get("enable_code_interpreter")):
        return []

    try:
        from langchain_quickjs import CodeInterpreterMiddleware
    except ImportError:
        logger.warning(
            "Code interpreter requested but langchain_quickjs is not installed; skipping"
        )
        return []

    return [
        # subagents=False：不装 JS task() 桥。开启时上游会往每次模型调用的
        # system message 注入约 9.8k 字符的 JS 子代理编排教程（dynamic
        # subagents），且 JS 内派发绕过父级 interrupt_on/HITL 审批；本项目的
        # REPL 定位是纯计算（见上方路由文案），子代理统一走正常 task 工具。
        CodeInterpreterMiddleware(subagents=False),
        CodeInterpreterRoutingMiddleware(sandbox_active=sandbox_active),
    ]
