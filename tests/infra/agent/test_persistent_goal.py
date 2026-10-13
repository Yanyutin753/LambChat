from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from src.infra.persistent_goal import GoalService, advance_goal
from src.kernel.schemas.persistent_goal import PersistentGoal, PersistentGoalCreate


class Store:
    def __init__(self):
        self.value = None

    async def get(self, session_id, user_id):
        if (
            self.value
            and self.value["session_id"] == session_id
            and self.value["user_id"] == user_id
        ):
            return deepcopy(self.value)
        return None

    async def create(self, goal):
        if self.value:
            return False
        self.value = goal.model_dump(mode="json")
        return True

    async def cas(self, goal, revision):
        if not self.value or self.value["revision"] != revision:
            return False
        self.value = goal.model_dump(mode="json")
        return True


def goal():
    return PersistentGoal(
        id="g", session_id="s", user_id="u", objective="finish", rubric="test passes"
    )


def test_defaults_and_budget_are_not_success():
    value = goal()
    assert value.limits.max_turns == 10
    assert value.limits.max_tokens == 100000
    assert value.limits.max_seconds == 3600
    value.accounting.turns = 10
    assert advance_goal(value, usage=None, verdict=None, tools=0).status == "budget_limited"


def test_unknown_usage_and_two_no_progress_turns_block_instead_of_complete():
    value = advance_goal(goal(), usage=None, verdict=None, tools=0)
    assert value.accounting.tokens is None
    assert value.status == "active"
    value = advance_goal(value, usage=None, verdict=None, tools=0)
    assert value.status == "blocked"


def test_grader_cannot_complete_without_evidence_or_with_failed_criterion():
    verdict = {"result": "satisfied", "criteria": [{"passed": True, "evidence_ids": ["proof"]}]}
    assert advance_goal(goal(), usage=10, verdict=verdict, tools=1).status != "completed"
    assert (
        advance_goal(
            goal(), usage=10, verdict=verdict, tools=1, evidence_ready=True, evidence_ids={"proof"}
        ).status
        == "completed"
    )
    verdict["criteria"][0]["passed"] = False
    assert (
        advance_goal(
            goal(), usage=10, verdict=verdict, tools=1, evidence_ready=True, evidence_ids={"proof"}
        ).status
        != "completed"
    )


def test_wall_clock_budget_overrides_grader_success():
    value = goal()
    value.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert (
        advance_goal(
            value, usage=1, verdict={"result": "satisfied"}, tools=1, evidence_ready=True
        ).status
        == "budget_limited"
    )


async def test_pause_fences_old_completion_and_resume_retains_accounting():
    service = GoalService(Store())
    value = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.reserve("s", "u", value.version)
    assert reserved.current_run_id
    paused = await service.control("s", "u", "pause")
    assert paused.status == "paused"
    assert paused.version > reserved.version
    assert (
        await service.finish(
            "s", "u", reserved.version, reserved.current_run_id, usage=1, verdict=None, tools=1
        )
        is None
    )
    resumed = await service.control("s", "u", "resume")
    assert resumed.accounting.turns == paused.accounting.turns
    assert resumed.stagnant_turns == 0
    assert await service.get("s", "other-user") is None


async def test_only_one_reservation_and_replay_keeps_same_intent():
    service = GoalService(Store())
    value = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    first = await service.reserve("s", "u", value.version)
    assert await service.reserve("s", "u", value.version) is None
    fetched = await service.get("s", "u")
    assert fetched.current_run_id == first.current_run_id
    assert fetched.continuation_sequence == 1
    assert (
        await service.finish("s", "u", first.version, "wrong-run", usage=3, verdict=None, tools=1)
        is None
    )
    completed = await service.finish(
        "s", "u", first.version, first.current_run_id, usage=3, verdict=None, tools=1
    )
    assert completed.accounting.turns == 1
    assert completed.accounting.tokens == 3
    assert (
        await service.finish(
            "s", "u", first.version, first.current_run_id, usage=3, verdict=None, tools=1
        )
        is None
    )


class RacingStore(Store):
    fail_next = False

    async def cas(self, value, revision):
        if self.fail_next:
            self.fail_next = False
            self.value["revision"] += 1
            return False
        return await super().cas(value, revision)


async def test_control_and_finish_retry_unrelated_revision_changes():
    store = RacingStore()
    service = GoalService(store)
    value = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.reserve("s", "u", value.version)
    store.fail_next = True
    finished = await service.finish(
        "s", "u", reserved.version, reserved.current_run_id, usage=5, verdict=None, tools=1
    )
    assert finished and finished.accounting.tokens == 5
    store.fail_next = True
    paused = await service.control("s", "u", "pause")
    assert paused and paused.status == "paused"


async def test_stale_timeout_control_cannot_stop_new_goal():
    service = GoalService(Store())
    value = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.reserve("s", "u", value.version)
    await service.control("s", "u", "pause")
    await service.control("s", "u", "resume")
    assert (
        await service.control(
            "s",
            "u",
            "limit",
            expected_version=reserved.version,
            expected_run_id=reserved.current_run_id,
        )
        is None
    )
    assert (await service.get("s", "u")).status == "active"


async def test_partial_usage_is_cumulative_and_finish_counts_run_once():
    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    run = await service.reserve("s", "u", created.version)
    for usage in (10, 10, 7, 16):
        saved = await service.record_usage(
            "s", "u", run.version, run.current_run_id, usage=usage, expected_goal_id=created.id
        )
    assert saved.accounting.tokens == 16
    assert saved.accounting.turns == 0
    finished = await service.finish(
        "s", "u", run.version, run.current_run_id, usage=20, verdict=None, tools=1
    )
    assert finished.accounting.tokens == 20
    assert finished.accounting.turns == 1
    replayed = await service.record_usage(
        "s",
        "u",
        run.version,
        run.current_run_id,
        usage=20,
        completed=True,
        expected_goal_id=created.id,
    )
    assert replayed.accounting.tokens == 20
    assert replayed.accounting.turns == 1


async def test_late_usage_survives_pause_but_cannot_reach_replacement_goal():
    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    run = await service.reserve("s", "u", created.version)
    await service.control("s", "u", "pause")
    saved = await service.record_usage(
        "s",
        "u",
        run.version,
        run.current_run_id,
        usage=12,
        completed=True,
        expected_goal_id=created.id,
    )
    assert saved.status == "paused"
    assert saved.accounting.tokens == 12
    assert saved.accounting.turns == 1
    resumed = await service.control("s", "u", "resume")
    assert resumed.accounting.tokens == 12
    replacement = await service.create(
        "s",
        "u",
        PersistentGoalCreate(objective="new", rubric="new", expected_revision=resumed.revision),
    )
    assert (
        await service.record_usage(
            "s",
            "u",
            run.version,
            run.current_run_id,
            usage=30,
            completed=True,
            expected_goal_id=created.id,
        )
        is None
    )
    assert (await service.get("s", "u")).id == replacement.id
    assert (await service.get("s", "u")).accounting.tokens == 0


async def test_unknown_partial_usage_stays_unknown_after_replay():
    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    run = await service.reserve("s", "u", created.version)
    await service.record_usage("s", "u", run.version, run.current_run_id, usage=None)
    saved = await service.record_usage(
        "s", "u", run.version, run.current_run_id, usage=10, completed=True
    )
    assert saved.accounting.tokens is None
    assert saved.accounting.turns == 1


async def test_resume_does_not_discard_pending_approval():
    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    run = await service.reserve("s", "u", created.version)
    waiting = await service.control(
        "s", "u", "waiting_human", expected_version=run.version, expected_run_id=run.current_run_id
    )
    resumed = await service.control("s", "u", "resume")
    assert resumed.status == "waiting_human"
    assert resumed.current_run_id == run.current_run_id
    assert resumed.version == waiting.version


async def test_failed_submission_release_cannot_clear_newer_human_run():
    service = GoalService(Store())
    await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    old = await service.attach_user_run("s", "u", "old")
    new = await service.attach_user_run("s", "u", "new")
    assert await service.release_submission("s", "u", old.version, "old") is None
    assert (await service.get("s", "u")).current_run_id == "new"
    released = await service.release_submission("s", "u", new.version, "new")
    assert released.current_run_id is None
    assert not released.intent_submitted
    assert released.accounting.turns == 0


async def test_human_binding_retries_revision_conflict():
    store = RacingStore()
    service = GoalService(store)
    await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    store.fail_next = True
    bound = await service.attach_user_run("s", "u", "human")
    assert bound.current_run_id == "human"


async def test_explicit_control_reports_repeated_cas_conflict():
    from src.kernel.errors import AppError, ErrorCode

    class AlwaysRacingStore(Store):
        async def cas(self, goal, revision):
            self.value["revision"] += 1
            return False

    service = GoalService(AlwaysRacingStore())
    await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    with pytest.raises(AppError) as error:
        await service.control("s", "u", "pause")
    assert error.value.error_code == ErrorCode.GOAL_CONFLICT


async def test_replayed_usage_does_not_write_or_churn_revision():
    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    run = await service.reserve("s", "u", goal.version)
    first = await service.record_usage("s", "u", run.version, run.current_run_id, usage=5)
    replayed = await service.record_usage("s", "u", run.version, run.current_run_id, usage=5)
    assert replayed.revision == first.revision


@pytest.mark.parametrize("references", [[], ["unknown"]])
def test_each_passed_criterion_requires_current_verified_original(references):
    verdict = {
        "result": "satisfied",
        "criteria": [
            {"name": "calculation", "passed": True, "evidence_ids": ["current"]},
            {"name": "second requirement", "passed": True, "evidence_ids": references},
        ],
    }
    assert (
        advance_goal(
            goal(), usage=1, verdict=verdict, tools=1, evidence_ready=True, evidence_ids={"current"}
        ).status
        != "completed"
    )
