"""Agent execution and run-scoped Goal events, shared by local and ARQ workers."""

import asyncio
from contextlib import aclosing
from datetime import datetime, timezone

from src.agents.core import AgentFactory
from src.agents.team_agent import member_config
from src.infra.goal_runtime import guarded_goal_stream
from src.infra.logging.context import TraceContext
from src.infra.session.storage import SessionStorage
from src.infra.task.cancellation import _close_agent_safely
from src.infra.utils.datetime import utc_now_iso
from src.kernel.errors import AppError, ErrorCode


async def _execute_agent_stream(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter=None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
    attachments: list[dict] | None = None,
    disabled_skills: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    persona_system_prompt: str | None = None,
    disabled_mcp_tools: list[str] | None = None,
    enabled_mcp_servers: list[str] | None = None,
    team_id: str | None = None,
    active_goal: dict | None = None,
    recommendation_input: str | None = None,
    auto_mode: bool = False,
    hitl_resume: dict | None = None,
    interrupted_resume: bool = False,
    base_url: str = "",
):
    """执行 Agent 并流式输出事件（供 TaskManager 调用）"""
    from src.infra.task.manager import TaskInterruptedError

    run_id = presenter.run_id if presenter else None
    agent = None
    allow_search_handoff = False
    if agent_id == "search" and (
        hitl_resume is not None or "_handoff_usage" in (agent_options or {})
    ):
        try:
            await member_config.resolve_team_member_agent_id("search", user_id=user_id)
        except ValueError:
            raise AppError(ErrorCode.FORBIDDEN) from None
    if agent_id == "quick" and presenter is not None and user_id:
        try:
            allow_search_handoff = (
                await member_config.resolve_team_member_agent_id("search", user_id=user_id)
                == "search"
            )
        except ValueError:
            # An unavailable/unauthorized Search must not become an escalation path.
            allow_search_handoff = False

    async def execute():
        nonlocal agent, agent_options
        current_agent_id = agent_id
        while True:
            agent = await AgentFactory.get(current_agent_id)
            handoff = None
            source = agent.stream(
                message,
                session_id,
                user_id=user_id,
                presenter=presenter,
                disabled_tools=disabled_tools,
                agent_options=agent_options,
                attachments=attachments,
                disabled_skills=disabled_skills,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                disabled_mcp_tools=disabled_mcp_tools,
                enabled_mcp_servers=enabled_mcp_servers,
                team_id=team_id,
                active_goal=active_goal,
                auto_mode=auto_mode,
                goal_started_at=started_at,
                recommendation_input=recommendation_input,
                hitl_resume=hitl_resume,
                interrupted_resume=interrupted_resume,
                base_url=base_url,
                allow_search_handoff=allow_search_handoff,
            )
            async with aclosing(source):
                async for event in source:
                    if event.get("event") != "agent:handoff":
                        yield event
                        continue
                    if (
                        current_agent_id != "quick"
                        or not allow_search_handoff
                        or event.get("data", {}).get("agent_id") != "search"
                    ):
                        raise AppError(ErrorCode.INTERNAL_ERROR)
                    handoff = event["data"]
            if handoff is None:
                return
            if not isinstance(run_id, str) or not run_id:
                raise AppError(ErrorCode.INTERNAL_ERROR)
            from src.infra.task.manager import BackgroundTaskManager

            await BackgroundTaskManager.check_interrupt(run_id)
            try:
                await member_config.resolve_team_member_agent_id("search", user_id=user_id)
            except ValueError:
                raise AppError(ErrorCode.FORBIDDEN) from None
            saved = await SessionStorage().update_metadata_for_run(
                session_id,
                run_id,
                {
                    "agent_handoff": {
                        **handoff,
                        "run_id": run_id,
                        "trace_id": presenter.trace_id,
                        "attachments": attachments,
                    }
                },
                expected_statuses=["running", "starting"],
            )
            if not saved:
                raise TaskInterruptedError("Agent handoff run is no longer active")
            await BackgroundTaskManager.check_interrupt(run_id)
            agent_options = {**(agent_options or {}), "_handoff_usage": handoff}
            current_agent_id = "search"
            # Quick's base stream clears TraceContext when its graph finishes.
            TraceContext.set(trace_id=presenter.trace_id)
            TraceContext.set_request_context(
                session_id=session_id, run_id=run_id, user_id=user_id, trace_id=presenter.trace_id
            )
            yield {
                "event": "status",
                "data": {
                    "stage": "agent_handoff",
                    "target_agent_id": "search",
                    "timestamp": utc_now_iso(),
                },
            }

    started_at: str | None = None
    goal_end_emitted = False
    if active_goal is not None:
        started_at = (
            hitl_resume.get("goal_started_at") if hitl_resume is not None else None
        ) or datetime.now(timezone.utc).isoformat()
        if hitl_resume is None:
            yield {
                "event": "goal:start",
                "data": {"goal": active_goal, "started_at": started_at},
            }

    try:
        source = execute()
        guarded = guarded_goal_stream(
            source,
            active_goal=active_goal,
            session_id=session_id,
            user_id=user_id,
            presenter=presenter,
            hitl_resume=hitl_resume,
        )
        async with aclosing(source), aclosing(guarded):
            async for event in guarded:
                if event.get("event") == "goal:end":
                    goal_end_emitted = True
                yield event

        if (
            active_goal is not None
            and not goal_end_emitted
            and not getattr(presenter, "hitl_suspended", False)
        ):
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
    except (asyncio.CancelledError, TaskInterruptedError):
        # 取消/中断时，调用 agent.close 清理资源
        if run_id and agent is not None:
            await _close_agent_safely(agent, run_id)
        # agent 的 finally 块可能已发 goal:end，此处再 yield 确保不遗漏（Presenter 有去重）
        if active_goal is not None and not goal_end_emitted:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
        raise
