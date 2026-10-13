"""Agent execution and run-scoped Goal events, shared by local and ARQ workers."""

import asyncio
from datetime import datetime, timezone

from src.agents.core import AgentFactory
from src.infra.goal_runtime import guarded_goal_stream
from src.infra.task.cancellation import _close_agent_safely


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
    base_url: str = "",
):
    """执行 Agent 并流式输出事件（供 TaskManager 调用）"""
    from src.infra.task.manager import TaskInterruptedError

    run_id = presenter.run_id if presenter else None

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
        agent = await AgentFactory.get(agent_id)
        async for event in guarded_goal_stream(
            agent.stream(
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
                base_url=base_url,
            ),
            active_goal=active_goal,
            session_id=session_id,
            user_id=user_id,
            presenter=presenter,
            hitl_resume=hitl_resume,
        ):
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
        if run_id:
            await _close_agent_safely(agent, run_id)
        # agent 的 finally 块可能已发 goal:end，此处再 yield 确保不遗漏（Presenter 有去重）
        if active_goal is not None and not goal_end_emitted:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
        raise
