"""Explicit session Goal controls; every endpoint enforces ownership."""

from fastapi import APIRouter, Depends

from src.api.deps import require_permissions
from src.api.routes.session import verify_session_ownership
from src.infra.goal_continuation import enqueue_goal, publish_goal
from src.infra.persistent_goal import GoalService
from src.infra.scheduler.conversation import conversation_submission
from src.infra.session.manager import SessionManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.persistent_goal import PersistentGoalCreate, PersistentGoalUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


async def _authorize(session_id, user):
    session = await SessionManager().get_session(session_id)
    if session is None:
        raise AppError(ErrorCode.SESSION_NOT_FOUND)
    verify_session_ownership(session, user)
    return session


def _response(goal):
    return {
        "goal": goal.model_dump(mode="json", exclude={"dispatch_token", "dispatch_expires_at"})
        if goal
        else None
    }


@router.get("/sessions/{session_id}/goal")
async def get_goal(
    session_id: str, user: TokenPayload = Depends(require_permissions("chat:write"))
):
    await _authorize(session_id, user)
    return _response(await GoalService().get(session_id, user.sub))


@router.put("/sessions/{session_id}/goal")
async def put_goal(
    session_id: str,
    payload: PersistentGoalCreate,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    async with conversation_submission(session_id, user.sub, allow_busy=True):
        session = await _authorize(session_id, user)
        previous = await GoalService().get(session_id, user.sub)
        goal = await GoalService().create(session_id, user.sub, payload)
        await publish_goal(goal)
        await _cancel_goal_run(session, previous)
        await enqueue_goal(goal)
        return _response(goal)


@router.patch("/sessions/{session_id}/goal")
async def update_goal(
    session_id: str,
    payload: PersistentGoalUpdate,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    async with conversation_submission(session_id, user.sub, allow_busy=True):
        session = await _authorize(session_id, user)
        service = GoalService()
        previous = await service.get(session_id, user.sub)
        goal = await service.update(session_id, user.sub, payload)
        await publish_goal(goal)
        await _cancel_goal_run(session, previous)
        latest = await service.get(session_id, user.sub)
        if latest and latest.id == goal.id and latest.version == goal.version:
            goal = latest
            await publish_goal(goal)
        await enqueue_goal(goal)
        return _response(goal)


async def _cancel_goal_run(session, goal):
    if goal and goal.current_run_id:
        from src.api.routes.hitl_interrupt_cleanup import reconcile_cancelled_hitl_approvals
        from src.infra.task.manager import get_task_manager

        task_manager = get_task_manager()
        # Cancellation metadata is fenced by this run, including queued workers with no coroutine.
        run_info = {"user_id": goal.user_id, "session_id": goal.session_id}
        if (session.metadata or {}).get("current_run_id") == goal.current_run_id:
            run_info["trace_id"] = session.metadata.get("trace_id")
            run_info["agent_id"] = session.metadata.get("agent_id")
        await task_manager.cancel_run(
            goal.current_run_id, user_id=goal.user_id, run_info_override=run_info
        )
        if (
            goal.status == "waiting_human"
            or (session.metadata or {}).get("task_status") == "waiting_human"
        ):
            await reconcile_cancelled_hitl_approvals(
                goal.session_id,
                user_id=goal.user_id,
                task_manager=task_manager,
                expected_run_id=goal.current_run_id,
            )


async def _control(session_id, user, action):
    async with conversation_submission(session_id, user.sub, allow_busy=True):
        session = await _authorize(session_id, user)
        service = GoalService()
        previous = await service.get(session_id, user.sub)
        goal = await service.control(session_id, user.sub, action)
        if goal:
            await publish_goal(goal)
            if action in {"pause", "clear"}:
                await _cancel_goal_run(session, previous)
                # Cancellation can finalize usage after the control snapshot was saved.
                latest = await service.get(session_id, user.sub)
                if (
                    latest
                    and latest.id == goal.id
                    and latest.version == goal.version
                    and latest.revision > goal.revision
                ):
                    goal = latest
                    await publish_goal(goal)
            if action == "resume":
                await enqueue_goal(goal)
        return _response(goal)


@router.post("/sessions/{session_id}/goal/pause")
async def pause_goal(
    session_id: str, user: TokenPayload = Depends(require_permissions("chat:write"))
):
    return await _control(session_id, user, "pause")


@router.post("/sessions/{session_id}/goal/resume")
async def resume_goal(
    session_id: str, user: TokenPayload = Depends(require_permissions("chat:write"))
):
    return await _control(session_id, user, "resume")


@router.post("/sessions/{session_id}/goal/clear")
async def clear_goal(
    session_id: str, user: TokenPayload = Depends(require_permissions("chat:write"))
):
    return await _control(session_id, user, "clear")
