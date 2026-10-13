"""CAS-fenced session Goal lifecycle, independent of task dispatch transport."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal

from pymongo.errors import DuplicateKeyError

from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.persistent_goal import (
    GoalRunAccounting,
    GoalStatus,
    PersistentGoal,
    PersistentGoalCreate,
)


def _record_run_usage(
    goal: PersistentGoal, run: GoalRunAccounting, usage: int | None, *, completed: bool
) -> None:
    previous = run.tokens
    if previous is None or usage is None:
        run.tokens = None
        goal.accounting.tokens = None
    else:
        run.tokens = max(previous, usage)
        if goal.accounting.tokens is not None:
            goal.accounting.tokens += run.tokens - previous
    if completed and not run.completed:
        goal.accounting.turns += 1
        run.completed = True


def advance_goal(
    goal: PersistentGoal,
    *,
    usage: int | None,
    verdict: dict | None,
    tools: int,
    evidence_ready: bool = False,
    now: datetime | None = None,
    progress_signature: str = "",
    evidence_ids: Sequence[str] = (),
) -> PersistentGoal:
    result = goal.model_copy(deep=True)
    if result.current_run_id:
        run = next(
            (
                item
                for item in result.run_accounting
                if item.run_id == result.current_run_id and item.version == result.version
            ),
            None,
        )
        if run is None:
            run = GoalRunAccounting(run_id=result.current_run_id, version=result.version)
            result.run_accounting.append(run)
        _record_run_usage(result, run, usage, completed=True)
    else:
        result.accounting.turns += 1
        previous = result.accounting.tokens
        result.accounting.tokens = (
            previous + usage if previous is not None and usage is not None else None
        )
    result.last_verdict = verdict
    # Invocation counts include failures and repeated polling; only changed
    # successful observations demonstrate progress.
    progress = bool(progress_signature and progress_signature != goal.last_progress_signature)
    result.stagnant_turns = 0 if progress else result.stagnant_turns + 1
    if progress_signature:
        result.last_progress_signature = progress_signature
    elapsed = ((now or datetime.now(timezone.utc)) - result.started_at).total_seconds()
    if (
        result.accounting.turns >= result.limits.max_turns
        or elapsed >= result.limits.max_seconds
        or (
            result.accounting.tokens is not None
            and result.accounting.tokens >= result.limits.max_tokens
        )
    ):
        result.status = "budget_limited"
    elif (
        evidence_ready
        and verdict
        and verdict.get("result") == "satisfied"
        and verdict.get("criteria")
        and all(
            c.get("passed") is True
            and c.get("evidence_ids")
            and isinstance(c["evidence_ids"], list)
            and all(isinstance(ref, str) and ref in evidence_ids for ref in c["evidence_ids"])
            for c in verdict["criteria"]
        )
    ):
        result.status = "completed"
    elif result.stagnant_turns >= 2 or (verdict and verdict.get("result") == "failed"):
        result.status = "blocked"
    result.current_run_id = None
    result.intent_submitted = False
    result.dispatch_token = None
    result.dispatch_expires_at = None
    return result


class GoalStore:
    @property
    def collection(self):
        from src.infra.storage.mongodb import get_mongo_client
        from src.kernel.config import settings

        return get_mongo_client()[settings.MONGODB_DB]["persistent_goals"]

    async def get(self, session_id: str, user_id: str) -> dict | None:
        return await self.collection.find_one({"_id": session_id, "user_id": user_id})

    async def create(self, goal: PersistentGoal) -> bool:
        try:
            await self.collection.insert_one(
                {"_id": goal.session_id, **goal.model_dump(mode="json")}
            )
            return True
        except DuplicateKeyError:
            return False

    async def cas(self, goal: PersistentGoal, revision: int) -> bool:
        result = await self.collection.replace_one(
            {"_id": goal.session_id, "user_id": goal.user_id, "revision": revision},
            {"_id": goal.session_id, **goal.model_dump(mode="json")},
        )
        return bool(result.modified_count)


class GoalService:
    def __init__(self, store: Any = None):
        self.store = store or GoalStore()

    async def get(self, session_id: str, user_id: str) -> PersistentGoal | None:
        data = await self.store.get(session_id, user_id)
        return PersistentGoal.model_validate(data) if data else None

    async def _save(self, value: PersistentGoal) -> PersistentGoal | None:
        old = value.revision
        value.revision += 1
        return value if await self.store.cas(value, old) else None

    async def create(
        self, session_id: str, user_id: str, payload: PersistentGoalCreate
    ) -> PersistentGoal:
        existing = await self.get(session_id, user_id)
        value = PersistentGoal(
            session_id=session_id,
            user_id=user_id,
            **payload.model_dump(exclude={"expected_revision"}),
        )
        if existing:
            if payload.expected_revision != existing.revision:
                raise AppError(ErrorCode.GOAL_CONFLICT)
            # Retain retired run identities so recovery cannot treat them as ordinary chat.
            value.run_accounting = existing.run_accounting
            value.version = existing.version + 1
            value.revision = existing.revision
            saved = await self._save(value)
        else:
            saved = value if await self.store.create(value) else None
        if saved is None:
            raise AppError(ErrorCode.GOAL_CONFLICT)
        return saved

    async def control(
        self,
        session_id: str,
        user_id: str,
        action: Literal["pause", "resume", "clear", "waiting_human", "block", "limit"],
        *,
        expected_version: int | None = None,
        expected_run_id: str | None = None,
    ) -> PersistentGoal | None:
        authority = None
        fenced = expected_version is not None or expected_run_id is not None
        for _ in range(3):
            value = await self.get(session_id, user_id)
            if value is None:
                return None
            if (expected_version is not None and value.version != expected_version) or (
                expected_run_id is not None and value.current_run_id != expected_run_id
            ):
                return None
            if authority is not None and (value.id, value.version) != authority:
                if fenced:
                    return None
                raise AppError(ErrorCode.GOAL_CONFLICT)
            authority = (value.id, value.version)
            if action == "resume" and value.status == "waiting_human":
                return value
            statuses: dict[str, GoalStatus] = {
                "pause": "paused",
                "resume": "active",
                "clear": "cleared",
                "waiting_human": "waiting_human",
                "block": "blocked",
                "limit": "budget_limited",
            }
            value.status = statuses[action]
            if action != "waiting_human":
                value.version += 1
                value.current_run_id = None
                value.intent_submitted = False
                value.dispatch_token = None
                value.dispatch_expires_at = None
            if action == "resume":
                value.stagnant_turns = 0
            saved = await self._save(value)
            if saved is not None:
                return saved
        raise AppError(ErrorCode.GOAL_CONFLICT)

    async def reserve(self, session_id: str, user_id: str, version: int) -> PersistentGoal | None:
        value = await self.get(session_id, user_id)
        if (
            value is None
            or value.version != version
            or value.status != "active"
            or value.current_run_id
        ):
            return None
        elapsed = (datetime.now(timezone.utc) - value.started_at).total_seconds()
        if (
            value.accounting.turns >= value.limits.max_turns
            or elapsed >= value.limits.max_seconds
            or (
                value.accounting.tokens is not None
                and value.accounting.tokens >= value.limits.max_tokens
            )
        ):
            value.status = "budget_limited"
        else:
            value.continuation_sequence += 1
            value.current_run_id = f"goal-{value.id}-{value.version}-{value.continuation_sequence}"
            value.run_accounting.append(
                GoalRunAccounting(run_id=value.current_run_id, version=value.version)
            )
            value.intent_submitted = False
        return await self._save(value)

    async def finish(
        self, session_id: str, user_id: str, version: int, run_id: str, **kwargs: Any
    ) -> PersistentGoal | None:
        for _ in range(3):
            value = await self.get(session_id, user_id)
            if (
                value is None
                or value.version != version
                or value.current_run_id != run_id
                or value.status not in {"active", "waiting_human"}
            ):
                return None
            value.status = "active"
            updated = advance_goal(value, **kwargs)
            saved = await self._save(updated)
            if saved is not None:
                return saved
        raise AppError(ErrorCode.GOAL_CONFLICT)

    async def attach_user_run(
        self, session_id: str, user_id: str, run_id: str
    ) -> PersistentGoal | None:
        authority = None
        for _ in range(3):
            value = await self.get(session_id, user_id)
            if value is None or value.status != "active":
                return None
            if authority is not None and (value.id, value.version) != authority:
                raise AppError(ErrorCode.GOAL_CONFLICT)
            authority = (value.id, value.version)
            # A human turn supersedes any previously queued automatic intent.
            value.version += 1
            value.current_run_id = run_id
            value.intent_submitted = True
            value.dispatch_token = None
            value.dispatch_expires_at = None
            value.run_accounting.append(GoalRunAccounting(run_id=run_id, version=value.version))
            saved = await self._save(value)
            if saved is not None:
                return saved
        raise AppError(ErrorCode.GOAL_CONFLICT)

    async def record_usage(
        self,
        session_id: str,
        user_id: str,
        version: int,
        run_id: str,
        *,
        usage: int | None,
        completed: bool = False,
        expected_goal_id: str | None = None,
    ) -> PersistentGoal | None:
        for _ in range(3):
            value = await self.get(session_id, user_id)
            if value is None or (expected_goal_id is not None and value.id != expected_goal_id):
                return None
            # Runs are registered before dispatch, so late cleanup can account
            # for work after pause without changing the new lifecycle authority.
            run = next(
                (
                    item
                    for item in value.run_accounting
                    if item.run_id == run_id and item.version == version
                ),
                None,
            )
            if run is None:
                return None
            before = (run.tokens, run.completed, value.accounting.tokens, value.accounting.turns)
            _record_run_usage(value, run, usage, completed=completed)
            if before == (
                run.tokens,
                run.completed,
                value.accounting.tokens,
                value.accounting.turns,
            ):
                return value
            saved = await self._save(value)
            if saved is not None:
                return saved
        raise AppError(ErrorCode.GOAL_CONFLICT)

    async def release_submission(
        self, session_id: str, user_id: str, version: int, run_id: str
    ) -> PersistentGoal | None:
        for _ in range(3):
            value = await self.get(session_id, user_id)
            if value is None or value.version != version or value.current_run_id != run_id:
                return None
            value.current_run_id = None
            value.intent_submitted = False
            value.dispatch_token = None
            value.dispatch_expires_at = None
            value.run_accounting = [
                item
                for item in value.run_accounting
                if item.run_id != run_id or item.tokens != 0 or item.completed
            ]
            saved = await self._save(value)
            if saved is not None:
                return saved
        raise AppError(ErrorCode.GOAL_CONFLICT)
