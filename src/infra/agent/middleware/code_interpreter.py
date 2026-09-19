"""Optional QuickJS code interpreter middleware for Deep Agents."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
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

_PTC_FRAME_MARKER = "<code_interpreter_ptc>"


def _is_enabled_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "enable"}
    return False


def _parse_ptc_tools(raw: str) -> list[str]:
    """Parse the comma-separated PTC allowlist: strip, drop empties, dedup in order."""
    seen: dict[str, None] = {}
    for item in raw.split(","):
        name = item.strip()
        if name:
            seen.setdefault(name, None)
    return list(seen)


def _ptc_bridge_name(tool_name: str) -> str:
    """REPL bridge name for a tool: snake_case -> camelCase (`web_search` -> `webSearch`)."""
    head, *rest = tool_name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _resolve_snapshot_key(*, explicit: str, jwt_secret: str | None) -> str | None:
    """Pick the QuickJS REPL snapshot signing key.

    Explicit setting wins; otherwise derive a stable key from an explicitly
    configured JWT secret (HMAC-signed snapshots are rejected on mismatch, so
    the key must be identical across workers sharing one checkpointer). When
    neither is stable (dev default generates a random per-process JWT secret)
    signing stays off rather than invalidating snapshots across restarts.
    """
    if explicit:
        return explicit
    if jwt_secret:
        return hashlib.sha256(f"lambchat:quickjs-snapshot:{jwt_secret}".encode()).hexdigest()
    return None


def _jwt_secret_is_explicit() -> bool:
    """Whether JWT_SECRET_KEY was provided via env/config rather than randomly generated."""
    return not getattr(settings, "_jwt_secret_key_generated", False)


def _build_ptc_frame(ptc_tools: Sequence[str]) -> str:
    signatures = ", ".join(f"tools.{_ptc_bridge_name(name)}(...)" for name in ptc_tools)
    return (
        f"{_PTC_FRAME_MARKER}\n"
        "Bridged read-only tools inside this REPL.\n"
        f"{signatures} are exposed as async host functions here. Batch lookups "
        "in one eval — Promise.all over query lists, loops with filtering and "
        "aggregation — instead of one tool call per round-trip. Each bridge "
        "resolves to the tool's usual JSON **string** — JSON.parse it before "
        "field access; truncated fetch payloads are not valid whole JSON, "
        "extract fields with regex instead. Only the bridged tools are "
        "callable; the REPL itself still has no direct filesystem or network "
        "access, and everything else goes through normal tools.\n"
        "</code_interpreter_ptc>"
    )


class CodeInterpreterRoutingMiddleware(AgentMiddleware):
    """Attaches routing guidance to the REPL tool description.

    Codex-style layering: routing guidance lives on the tool the model
    chooses between, not in the system prompt. The text is static per
    session, so the tools prefix stays byte-identical across turns. When
    the eval tool is not part of the request the guidance is dropped —
    telling the model to route to an absent tool would be wrong.
    """

    _FRAME_MARKER = "<code_interpreter_routing>"

    def __init__(self, *, sandbox_active: bool, ptc_tools: Sequence[str] = ()) -> None:
        super().__init__()
        routing = _ROUTING_WITH_SANDBOX if sandbox_active else _ROUTING_WITHOUT_SANDBOX
        self._framed = (
            f"{self._FRAME_MARKER}\n"
            "Tool-routing guidance for this REPL.\n"
            f"{routing}\n"
            "</code_interpreter_routing>"
        )
        self.ptc_tools: list[str] = list(ptc_tools)
        # 上游 filter_tools_for_ptc 会静默丢弃不在请求工具集里的白名单名；
        # 指引帧按当次实际可桥接的工具生成并缓存，避免宣称不存在的桥。
        self._ptc_frame_cache: dict[frozenset[str], str] = {}

    def _ptc_frame_for(self, tool_names: frozenset[str]) -> str:
        effective = frozenset(name for name in self.ptc_tools if name in tool_names)
        if not effective:
            return ""
        frame = self._ptc_frame_cache.get(effective)
        if frame is None:
            frame = _build_ptc_frame([name for name in self.ptc_tools if name in effective])
            self._ptc_frame_cache[effective] = frame
        return frame

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
            description = base_description
            if self._FRAME_MARKER not in description:
                description = f"{description}\n\n{self._framed}"
            ptc_framed = (
                self._ptc_frame_for(frozenset(getattr(tool, "name", "") for tool in tools))
                if self.ptc_tools
                else ""
            )
            if ptc_framed and _PTC_FRAME_MARKER not in description:
                description = f"{description}\n\n{ptc_framed}"
            if description != base_description:
                tools[eval_index] = target.model_copy(update={"description": description})
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

    ptc_tools = _parse_ptc_tools(getattr(settings, "CODE_INTERPRETER_PTC_TOOLS", ""))
    ptc_allowlist: list[str | BaseTool] | None = (
        list[str | BaseTool](ptc_tools) if ptc_tools else None
    )
    snapshot_key = _resolve_snapshot_key(
        explicit=getattr(settings, "CODE_INTERPRETER_SNAPSHOT_KEY", ""),
        jwt_secret=settings.JWT_SECRET_KEY if _jwt_secret_is_explicit() else None,
    )

    interpreter_kwargs: dict[str, Any] = {
        # subagents=False：不装 JS task() 桥。开启时上游会往每次模型调用的
        # system message 注入约 9.8k 字符的 JS 子代理编排教程（dynamic
        # subagents），且 JS 内派发绕过父级 interrupt_on/HITL 审批；本项目的
        # 子代理统一走正常 task 工具。
        "subagents": False,
        # ptc：只读检索工具白名单（web_search/web_fetch 等），让模型在一次
        # eval 内并发批量调用并聚合结果；白名单工具均无 interrupt_on 门控
        # 与副作用，PTC 桥绕过 HITL 的限制对它们不构成风险。
        "ptc": ptc_allowlist,
        # snapshot_signing_key：thread 模式 REPL 快照会持久化进 checkpointer，
        # 签名后篡改的快照会被拒绝执行而非静默恢复。
        "snapshot_signing_key": snapshot_key,
    }
    if ptc_allowlist:
        # PTC 聚合场景的返回体（多路搜索结果合并去重）远大于纯算术结果，
        # 上游 4000 默认截断过紧；仅在启用白名单时放宽，仍为有界上限。
        interpreter_kwargs["max_result_chars"] = 8000

    return [
        CodeInterpreterMiddleware(**interpreter_kwargs),
        CodeInterpreterRoutingMiddleware(sandbox_active=sandbox_active, ptc_tools=ptc_tools),
    ]
