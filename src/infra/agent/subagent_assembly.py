"""Shared persistent-subagent assembly for search and team agents."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

import deepagents.graph as deepagents_graph
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import SubAgent, create_sub_agent
from langgraph.graph.state import CompiledStateGraph

from src.agents.core.subagent_prompts import SUBAGENT_PROMPT
from src.infra.agent.middleware import summarization_fallback_patch
from src.infra.agent.middleware.evidence import EvidenceMiddleware
from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
from src.infra.agent.subagent_sessions import SubagentSessions


async def refresh_subagent_context(context: Any) -> Any:
    """Reuse the agent's authorization loaders instead of retaining a stale tool snapshot."""
    fresh = type(context)(
        **{
            field: getattr(context, field)
            for field in (
                "session_id",
                "agent_id",
                "user_id",
                "disabled_tools",
                "disabled_skills",
                "enabled_skills",
                "disabled_mcp_tools",
                "enabled_mcp_servers",
                "auto_mode",
            )
        }
    )
    await fresh.setup()
    await fresh.get_tools()
    return fresh


def assemble_subagent_sessions(
    *,
    session_id: str,
    user_id: str,
    specs: dict[str, Any],
    model: Any,
    backend: Any,
    tools: list,
    checkpointer: Any,
    store: Any,
    system_prompt: str,
    fallback_model: Any,
    thinking: Any,
    resolve_spec: Callable[[str], Awaitable[dict]] | None = None,
    child_middleware: Callable[[], list] | None = None,
) -> tuple[SubagentSessions, SubagentSessionMiddleware]:
    async def build_graph(role_type, inbox):
        spec = await resolve_spec(role_type) if resolve_spec else specs.get(role_type)
        if spec is None or "runnable" in spec:
            raise ValueError("Unknown or opaque compiled subagent cannot be continued")
        extra_middleware = child_middleware() if child_middleware else []
        for middleware in extra_middleware:
            if isinstance(middleware, EvidenceMiddleware):
                middleware.run_id = f"{middleware.run_id}:subagent:{inbox.subagent_id}"
        with summarization_fallback_patch(fallback_model, thinking):
            child_model = spec.get("model", model)
            child_graph = create_sub_agent(
                cast(
                    SubAgent,
                    {
                        **spec,
                        "system_prompt": (
                            f"{system_prompt}\n\n{spec.get('system_prompt', '')}"
                            if spec.get("mode") == "fork"
                            else spec.get("system_prompt", SUBAGENT_PROMPT)
                        ),
                        "model": child_model,
                        "tools": spec.get("tools", tools),
                        "middleware": [
                            FilesystemMiddleware(backend=backend),
                            PatchToolCallsMiddleware(),
                            *spec.get("middleware", []),
                            *extra_middleware,
                            inbox,
                            deepagents_graph.create_summarization_middleware(child_model, backend),
                        ],
                    },
                )
            )
            return cast(CompiledStateGraph, child_graph).builder.compile(
                checkpointer=checkpointer, store=store, name=role_type
            )

    sessions = SubagentSessions(
        session_id=session_id,
        user_id=user_id,
        build_graph=build_graph,
        checkpointer=checkpointer,
        fork_types=frozenset(name for name, spec in specs.items() if spec.get("mode") == "fork"),
    )
    return sessions, SubagentSessionMiddleware(sessions, available_agents=specs)
