"""Dispatch discovered personas through the existing task tool."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.infra.agent.middleware.prompt_injection import SectionPromptMiddleware

logger = logging.getLogger(__name__)

PERSONA_DISPATCH_POLICY = """## Role Discovery Before Delegation
Before delegating a new task, use `search_persona_presets` to find roles by capability.
Compare the returned descriptions and tags with the task; broaden or rephrase a
search that may have missed a suitable role. For a suitable result, call `task`
with its returned `subagent_type` (`persona:<id>`). The server loads that role's
original system prompt for the subagent; do not invent or copy a replacement prompt.
Include the concrete objective, scope, dependencies, evidence and acceptance criteria.
Only use `general-purpose` when successful searches found no suitable role; explain
the capability gap in the assignment. Search errors and permission failures are not
empty results. Do not create or save personas or teams just to execute a task.
Run independent assignments in parallel, sequence dependencies, and verify handoffs.
A repeated task call starts a new conversation. To continue an existing subagent,
use send_subagent_message with its returned subagent_id; its role and history are
retained. A running recipient gets the message before its next model call. Use
background=true on task when you need to send instructions while it runs, and
wait_subagent before synthesizing its final result. Existing conversations do not
need a new role search; role access is checked again when they resume.
"""


class PersonaSubagentMiddleware(SectionPromptMiddleware):
    """Resolve each dispatch independently; never share mutable role execution state."""

    def __init__(self, *, build_task_tool: Callable[[str], Awaitable[BaseTool]]) -> None:
        super().__init__(sections=[PERSONA_DISPATCH_POLICY])
        self._build_task_tool = build_task_tool

    @staticmethod
    def _search_results(state: dict) -> list[dict]:
        results: list[dict[str, Any]] = []
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage) and message.name not in {
                "evidence_context",
                "task_context",
                "subagent_context",
                "subagent_message",
                "subagent_update",
            }:
                break
            if (
                isinstance(message, ToolMessage)
                and message.name == "task"
                and message.status == "error"
                and not results
            ):
                return []
            if not isinstance(message, ToolMessage) or message.name != "search_persona_presets":
                continue
            try:
                if not isinstance(message.content, str):
                    if not results:
                        return []
                    continue
                result = json.loads(message.content)
            except (TypeError, ValueError):
                if not results:
                    return []
                continue
            if isinstance(result, dict) and result.get("success") is True:
                results.append(result)
            elif not results:
                return []
        return results

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        call = request.tool_call
        if call["name"] != "task":
            return await handler(request)
        role_type = call.get("args", {}).get("subagent_type", "")
        results = self._search_results(request.state)
        error = None
        if not results:
            error = "Search roles with search_persona_presets successfully before delegating. Search failures do not authorize generic fallback."
        elif role_type.startswith("persona:"):
            preset_id = role_type.removeprefix("persona:")
            discovered_ids = {
                preset.get("id")
                for result in results
                for preset in result.get("presets", [])
                if isinstance(preset, dict)
            }
            if not preset_id or preset_id not in discovered_ids:
                error = "Select a role ID returned by search_persona_presets for this task."
            else:
                try:
                    tool = await self._build_task_tool(preset_id)
                except Exception:
                    logger.warning("Failed to load discovered subagent role", exc_info=True)
                    error = "The selected role could not be loaded. Search again or report the blocker; do not silently switch to a generic role."
                else:
                    return await handler(request.override(tool=tool))
        elif role_type != "general-purpose":
            error = (
                "Use a discovered persona role; built-in specialists do not replace role discovery."
            )
        elif results[0].get("presets"):
            error = "Search found roles. Select a suitable discovered role or refine the search to confirm no matching role before generic fallback."
        if error:
            return ToolMessage(content=error, name="task", tool_call_id=call["id"], status="error")
        return await handler(request)


def add_persona_discovery(
    middleware: list, tools: list, deferred_manager, task_tool: BaseTool
) -> None:
    """Expose authorized role search and fail closed even when it is unavailable."""
    role_search = next((tool for tool in tools if tool.name == "search_persona_presets"), None)
    if role_search is None and deferred_manager is not None:
        role_search = deferred_manager.get_tool("search_persona_presets")
    if role_search is not None and role_search not in tools:
        tools.append(role_search)

    async def build_task_tool(preset_id: str):
        return task_tool

    task_tool.description = task_tool.description.split("\nAvailable subagent types:\n")[0] + (
        "\nUse a persona:<id> returned by search_persona_presets. "
        "Only use general-purpose after a successful search finds no matching role."
    )
    middleware.append(PersonaSubagentMiddleware(build_task_tool=build_task_tool))
