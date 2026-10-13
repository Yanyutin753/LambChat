from types import SimpleNamespace

from src.infra.goal_continuation import dispatch_goal
from src.infra.persistent_goal import GoalService
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_persistent_goal import Store


async def test_dispatch_rechecks_idle_and_authorization_before_reserved_submission():
    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )
    session = SimpleNamespace(user_id="u", metadata={"task_status": "running"})
    calls = []

    async def load_session(s):
        return session

    async def load_user(u):
        return SimpleNamespace(sub="u", permissions=["chat:write"])

    async def submit(reserved, sess, user):
        calls.append(reserved.current_run_id)

    async def queued(s, u):
        return False

    assert (
        await dispatch_goal(
            "s",
            "u",
            value.version,
            service=service,
            load_session=load_session,
            load_user=load_user,
            submit=submit,
            has_pending=queued,
        )
        is None
    )
    assert not calls
    session.metadata["task_status"] = "completed"
    reserved = await dispatch_goal(
        "s",
        "u",
        value.version,
        service=service,
        load_session=load_session,
        load_user=load_user,
        submit=submit,
        has_pending=queued,
    )
    assert calls == [reserved.current_run_id]
    assert (await service.get("s", "u")).intent_submitted
    assert (
        await dispatch_goal(
            "s",
            "u",
            value.version,
            service=service,
            load_session=load_session,
            load_user=load_user,
            submit=submit,
            has_pending=queued,
        )
        is None
    )
    assert len(calls) == 1


async def test_paused_goal_or_pending_user_input_never_submits():
    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )

    async def pending(*args):
        return True

    async def fail(*args):
        raise AssertionError("must not submit")

    async def session(*args):
        return SimpleNamespace(user_id="u", metadata={"task_status": "completed"})

    assert (
        await dispatch_goal(
            "s",
            "u",
            value.version,
            service=service,
            has_pending=pending,
            load_session=session,
            load_user=fail,
            submit=fail,
        )
        is None
    )
    await service.control("s", "u", "pause")
    assert (
        await dispatch_goal(
            "s",
            "u",
            value.version,
            service=service,
            has_pending=fail,
            load_session=fail,
            load_user=fail,
            submit=fail,
        )
        is None
    )


async def test_unconfirmed_intent_reuses_run_id_and_revalidates_after_pause_race():
    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )
    intent = await service.reserve("s", "u", value.version)

    async def sess(*args):
        return SimpleNamespace(user_id="u", metadata={"task_status": "completed"})

    async def user(*args):
        await service.control("s", "u", "pause")
        return SimpleNamespace(sub="u", permissions=["chat:write"])

    async def pending(*args):
        return False

    async def fail(*args):
        raise AssertionError("pause must fence old intent")

    assert (
        await dispatch_goal(
            "s",
            "u",
            value.version,
            service=service,
            load_session=sess,
            load_user=user,
            has_pending=pending,
            submit=fail,
        )
        is None
    )
    assert intent.current_run_id


async def test_permission_revoked_or_deleted_session_blocks_goal():
    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )

    async def deleted(*args):
        return None

    await dispatch_goal("s", "u", value.version, service=service, load_session=deleted)
    assert (await service.get("s", "u")).status == "cleared"


async def test_finished_run_without_committed_verdict_blocks_instead_of_replaying(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr("src.infra.goal_continuation.publish_goal", AsyncMock())
    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )
    reserved = await service.reserve("s", "u", value.version)
    reserved.intent_submitted = True
    await service._save(reserved)

    async def finished(*args):
        return SimpleNamespace(
            user_id="u",
            metadata={"task_status": "completed", "current_run_id": reserved.current_run_id},
        )

    async def fail(*args):
        raise AssertionError("uncertain result cannot replay")

    async def queued(*args):
        return False

    await dispatch_goal(
        "s",
        "u",
        value.version,
        service=service,
        load_session=finished,
        submit=fail,
        has_pending=queued,
    )
    assert (await service.get("s", "u")).status == "blocked"


async def test_scanner_permission_loss_publishes_durable_blocked_goal(monkeypatch):
    from unittest.mock import AsyncMock

    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )
    observed = []

    async def publish(goal):
        durable = await service.get("s", "u")
        assert durable.status == "blocked"
        assert durable.revision == goal.revision
        observed.append(goal)

    monkeypatch.setattr("src.infra.goal_continuation.publish_goal", publish)
    await dispatch_goal(
        "s",
        "u",
        value.version,
        service=service,
        load_session=AsyncMock(return_value=SimpleNamespace(user_id="u", metadata={})),
        load_user=AsyncMock(return_value=SimpleNamespace(sub="u", permissions=[])),
        has_pending=AsyncMock(return_value=False),
    )
    assert len(observed) == 1
    assert observed[0].status == "blocked"


async def test_scanner_uncertain_finished_run_publishes_durable_blocked_goal(monkeypatch):
    from unittest.mock import AsyncMock

    service = GoalService(Store())
    value = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="checked")
    )
    run = await service.reserve("s", "u", value.version)
    observed = []

    async def publish(goal):
        durable = await service.get("s", "u")
        assert durable.status == "blocked"
        assert durable.revision == goal.revision
        observed.append(goal)

    monkeypatch.setattr("src.infra.goal_continuation.publish_goal", publish)
    await dispatch_goal(
        "s",
        "u",
        value.version,
        service=service,
        load_session=AsyncMock(
            return_value=SimpleNamespace(
                user_id="u",
                metadata={"task_status": "completed", "current_run_id": run.current_run_id},
            )
        ),
        has_pending=AsyncMock(return_value=False),
    )
    assert len(observed) == 1
    assert observed[0].status == "blocked"
