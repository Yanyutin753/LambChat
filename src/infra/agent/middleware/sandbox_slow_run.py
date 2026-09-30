"""Slow-run concept-first guidance on the sandbox `execute` tool.

Codex-style layering (same discipline as the code-interpreter routing frame and
the sandbox workspace context): behavioral guidance for a specific tool lives
on that tool's description, not in the system prompt. The frame is fully
static, so the tools prefix stays byte-identical across the turns of one
conversation and across sessions.

Why not only in PROGRESS_POLICY: deepagents 0.7.19 harness profiles replace
non-fork subagent system prompts with the shared behavior guide, so policy
blocks never reach the subagents that inherit `execute`. The tool description
is the only channel every `execute` holder sees at the decision point.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.tools import BaseTool

_EXECUTE_TOOL_NAME = "execute"

_FRAME_MARKER = "<slow_sandbox_run_guidance>"

_FRAME = (
    f"{_FRAME_MARKER}\n"
    "Tool-usage guidance for long runs. When this command may take a while "
    "(package installs, training, long builds) and the question is conceptual, "
    "send the user the conceptual answer as text BEFORE calling, then call and "
    "append the run's results.\n"
    "</slow_sandbox_run_guidance>"
)


class SandboxSlowRunMiddleware(AgentMiddleware):
    """Appends the concept-first guidance to the `execute` tool description.

    Idempotent (frame-marker guard, tail-only append) and a no-op when
    `execute` is absent, so sandbox-less sessions carry no dead guidance.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        tools = list(request.tools)
        target_index = next(
            (
                index
                for index, tool in enumerate(tools)
                if getattr(tool, "name", "") == _EXECUTE_TOOL_NAME
            ),
            None,
        )
        if target_index is None:
            return await handler(request)
        target = tools[target_index]
        if isinstance(target, BaseTool):
            base_description = target.description or ""
            if _FRAME_MARKER not in base_description:
                tools[target_index] = target.model_copy(
                    update={"description": f"{base_description}\n\n{_FRAME}"}
                )
                request = request.override(tools=tools)
        return await handler(request)
