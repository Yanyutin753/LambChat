"""Bind opt-in Goals to runs and enforce their authority at execution boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from src.infra.channel.chat_lease import ChatLease
from src.infra.goal import GoalSpec
from src.infra.goal_continuation import GOAL_DISPATCH, enqueue_goal, publish_goal
from src.infra.persistent_goal import GoalService
from src.infra.task.exceptions import TaskInterruptedError
from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
SUBMISSION_GOAL: ContextVar[Any] = ContextVar("submission_goal", default=None)
SUBMISSION_ACCEPTED: ContextVar[bool] = ContextVar("submission_accepted", default=False)
GOAL_LEASE_RENEW_SECONDS = 15
GOAL_LEASE_TTL_SECONDS = 60
GOAL_RUN_LEASE: ContextVar[Any] = ContextVar("goal_run_lease", default=None)


_OBSERVATION_METADATA = {"tool_call_id", "call_id", "run_id", "trace_id", "request_id", "timestamp"}


def _normalize_observation(value):
    if isinstance(value, str):
        try:
            return _normalize_observation(json.loads(value))
        except (ValueError, TypeError):
            return value
    if isinstance(value, dict):
        return {
            key: _normalize_observation(item)
            for key, item in value.items()
            if key not in _OBSERVATION_METADATA
        }
    if isinstance(value, list):
        return [_normalize_observation(item) for item in value]
    return value


def _observation_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class GoalRunMetrics:
    def __init__(self):
        self.tokens: int | None = None
        self.tool_count = 0
        self.seen_tools: set[str] = set()
        self.tool_inputs: dict[str, dict] = {}
        self.observations: set[str] = set()
        self.seen_models: set[str] = set()
        self.pending_models: set[str] = set()
        self.main_models: set[str] = set()
        self.main_output_limited = False
        self.model_tokens = 0
        self.unknown_model_usage = False
        self.enforce = None

    def observe(self, event: dict) -> None:
        name, data = event.get("event"), event.get("data", {})
        if not isinstance(data, dict):
            return
        if name == "token:usage" and isinstance(data.get("total_tokens"), int):
            self.tokens = max(self.tokens or 0, data["total_tokens"])
        identity = str(data.get("tool_call_id") or data.get("id") or "")
        if name == "tool:start" and identity:
            self.tool_inputs[identity] = {
                "tool": data.get("tool"),
                "args": _normalize_observation(data.get("args")),
            }
        if name == "tool:result":
            identity = str(data.get("tool_call_id") or data.get("id") or "")
            if identity and identity not in self.seen_tools:
                self.seen_tools.add(identity)
                self.tool_count += 1
            from src.infra.agent.events.tool_outputs import detect_tool_error

            result = _normalize_observation(data.get("result"))
            failed, _ = detect_tool_error(result, result)
            if data.get("success") is False or data.get("error") or failed:
                return
            if isinstance(result, dict) and (
                result.get("success") is False or result.get("isError") is True
            ):
                return
            if result is not None:
                self.observations.add(
                    _observation_digest(
                        {
                            **self.tool_inputs.get(identity, {"tool": data.get("tool")}),
                            "result": result,
                        }
                    )
                )

    @property
    def progress_signature(self) -> str:
        return _observation_digest(sorted(self.observations)) if self.observations else ""


class GoalUsageCallback(AsyncCallbackHandler):
    run_inline = True
    raise_error = True

    def __init__(self, metrics: GoalRunMetrics):
        self.metrics = metrics

    async def on_llm_error(self, error, *, run_id, **kwargs):
        identity = str(run_id)
        self.metrics.pending_models.discard(identity)
        if identity not in self.metrics.seen_models:
            # A failed stream can incur unreported cost before a successful retry.
            self.metrics.seen_models.add(identity)
            self.metrics.unknown_model_usage = True

    async def on_llm_end(self, response, *, run_id, **kwargs):
        identity = str(run_id)
        self.metrics.pending_models.discard(identity)
        if identity in self.metrics.seen_models:
            return
        self.metrics.seen_models.add(identity)
        if identity in self.metrics.main_models:
            from src.infra.llm.retry import _empty_answer, _is_output_limit_response

            for generations in response.generations:
                for generation in generations:
                    message = getattr(generation, "message", None)
                    if message is not None:
                        if _is_output_limit_response(message) and _empty_answer(message):
                            self.metrics.main_output_limited = True
                        elif not _empty_answer(message):
                            self.metrics.main_output_limited = False
        usages = [
            getattr(getattr(generation, "message", None), "usage_metadata", None)
            for generations in response.generations
            for generation in generations
        ]
        known = [
            usage["total_tokens"]
            for usage in usages
            if usage and isinstance(usage.get("total_tokens"), int)
        ]
        if not known:
            self.metrics.unknown_model_usage = True
        else:
            self.metrics.model_tokens += sum(known)
            self.metrics.tokens = max(self.metrics.tokens or 0, self.metrics.model_tokens)
        await self._enforce()

    async def _enforce(self):
        if self.metrics.enforce is not None:
            await self.metrics.enforce()

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        await self._enforce()
        self.metrics.pending_models.add(str(run_id))
        metadata = kwargs.get("metadata") or {}
        if not (
            "rubric_grader_configured_model" in metadata
            or metadata.get("lc_source") in {"summarization", "recommendation"}
            or metadata.get("lambchat_subagent_id")
            or metadata.get("internal_tool_call")
        ):
            self.metrics.main_models.add(str(run_id))

    async def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        await self.on_chat_model_start(serialized, [], run_id=run_id, **kwargs)

    async def on_tool_start(self, serialized, input_str, **kwargs):
        await self._enforce()


def _run_goal(value) -> dict:
    return {
        "objective": value.objective,
        "rubric": value.rubric,
        # Persistent goals revise in the next durable turn, not inside one message.
        "max_iterations": 1,
        "_persistent_id": value.id,
        "_persistent_version": value.version,
        "_scope_version": f"{value.id}:{value.version}",
    }


async def bind_submission_goal(
    request, metadata: dict, session_id: str, user_id: str, run_id: str, *, service=None
):
    from src.infra.scheduler.conversation import SCHEDULED_SUBMISSION

    if SCHEDULED_SUBMISSION.get():
        return None, run_id
    dispatch = GOAL_DISPATCH.get()
    if dispatch is None and not metadata.get("persistent_goal_id"):
        return request.goal.model_dump() if request.goal else None, run_id
    service = service or GoalService()
    current = await service.get(session_id, user_id)
    if dispatch is not None:
        if (
            current is None
            or current.version != dispatch.version
            or current.status != "active"
            or current.current_run_id != dispatch.current_run_id
            or current.dispatch_token != dispatch.dispatch_token
        ):
            raise AppError(ErrorCode.GOAL_CONFLICT)
        request.goal = GoalSpec(objective=current.objective, rubric=current.rubric)
        active = _run_goal(current)
        active["_continuation"] = {
            "goal_id": current.id,
            "objective": current.objective,
            "turn": current.accounting.turns + 1,
            "initial": current.continuation_sequence == 1 and current.accounting.turns == 0,
        }
        return active, str(current.current_run_id)
    if request.goal is not None:
        if current and current.status == "active":
            await service.control(session_id, user_id, "pause")
        return request.goal.model_dump(), run_id
    current = await service.attach_user_run(session_id, user_id, run_id)
    if current:
        SUBMISSION_GOAL.set((session_id, user_id, current.version, run_id))
        request.goal = GoalSpec(objective=current.objective, rubric=current.rubric)
        return _run_goal(current), run_id
    return None, run_id


async def rollback_submission_goal(*, service=None):
    identity = SUBMISSION_GOAL.get()
    if identity and not SUBMISSION_ACCEPTED.get():
        await (service or GoalService()).release_submission(*identity)


async def submit_chat_with_goal(submit, request, http_request, agent_id, user):
    token = SUBMISSION_GOAL.set(None)
    accepted = SUBMISSION_ACCEPTED.set(False)
    try:
        return await submit(request, http_request, agent_id=agent_id, user=user)
    except BaseException:
        await rollback_submission_goal()
        raise
    finally:
        SUBMISSION_ACCEPTED.reset(accepted)
        SUBMISSION_GOAL.reset(token)


async def restore_goal_for_run(session, run_id: str, *, service=None):
    if not (session.metadata or {}).get("persistent_goal_id"):
        return None
    current = await (service or GoalService()).get(session.id, session.user_id)
    if current is not None and not any(item.run_id == run_id for item in current.run_accounting):
        # A cleared Goal reference remains for display; later ordinary chat runs
        # have no Goal authority to restore.
        if not run_id.startswith("goal-"):
            return None
    if (
        current is None
        or current.id != session.metadata["persistent_goal_id"]
        or current.current_run_id != run_id
        or current.status not in {"active", "waiting_human"}
    ):
        raise GoalRunAdmissionError("Goal was paused or superseded")
    return _run_goal(current)


class GoalRunAlreadyOwnedError(TaskInterruptedError):
    """A duplicate runner must leave the owner's task lifecycle untouched."""


class BackgroundLeaseCallback(AsyncCallbackHandler):
    """Fail closed at model/tool boundaries after a detached runner loses ownership."""

    run_inline = True
    raise_error = True

    def __init__(self, lease_state):
        self.lease_state = lease_state

    async def _check(self):
        if (
            self.lease_state["failure"]
            or asyncio.get_running_loop().time() >= self.lease_state["expires_at"]
        ):
            raise TaskInterruptedError("Background execution lease was lost or expired")

    async def on_chat_model_start(self, serialized, messages, **kwargs):
        await self._check()

    async def on_llm_start(self, serialized, prompts, **kwargs):
        await self._check()

    async def on_tool_start(self, serialized, input_str, **kwargs):
        await self._check()

    async def on_llm_end(self, response, **kwargs):
        await self._check()


class GoalRunAdmissionError(TaskInterruptedError):
    """A stale Goal payload was refused before acquiring task lifecycle state."""


def execution_guard_callbacks(presenter) -> list[Any]:
    callbacks: list[Any] = []
    lease_state = GOAL_RUN_LEASE.get()
    if lease_state is not None and lease_state.get("kind") == "background":
        callbacks.append(BackgroundLeaseCallback(lease_state))
    metrics = getattr(presenter, "persistent_goal_metrics", None)
    if metrics is not None:
        callbacks.append(GoalUsageCallback(metrics))
    return callbacks


async def validate_goal_admission(arguments):
    goal = arguments.get("active_goal")
    if not goal or not goal.get("_persistent_id"):
        return
    current = await GoalService().get(arguments["session_id"], arguments["user_id"])
    if (
        current is None
        or current.id != goal["_persistent_id"]
        or current.version != goal.get("_persistent_version")
        or current.session_id != arguments["session_id"]
        or current.user_id != arguments["user_id"]
        or current.current_run_id != arguments["run_id"]
        or current.status not in {"active", "waiting_human"}
        or (current.status == "waiting_human" and not arguments.get("hitl_resume"))
    ):
        raise GoalRunAdmissionError("Goal was paused or superseded before admission")


@asynccontextmanager
async def goal_run_lease(
    active_goal, run_id, *, reuse=False, install_context=True, background_identity=None
):
    if active_goal and active_goal.get("_persistent_id"):
        key = f"goal:runner:{active_goal['_persistent_id']}:{run_id}"
        kind = "goal"
    elif background_identity:
        user_id, session_id = background_identity
        identity = hashlib.sha256(f"{user_id}\0{session_id}".encode()).hexdigest()
        key = f"background:runner:{identity}:{run_id}"
        kind = "background"
    else:
        yield None
        return
    current = GOAL_RUN_LEASE.get()
    if reuse and current is not None and current["key"] == key:
        if current["failure"] or asyncio.get_running_loop().time() >= current["expires_at"]:
            raise TaskInterruptedError("Goal execution lease was lost or expired")
        yield current
        return
    lease = ChatLease(key, ttl=GOAL_LEASE_TTL_SECONDS)
    acquired = False
    renewal = None
    context_token = None
    owner = asyncio.current_task()
    assert owner is not None
    lease_state: dict[str, Any] = {
        "key": key,
        "failure": "",
        "expires_at": 0.0,
        "owner": owner,
        "standalone": not install_context,
        "kind": kind,
    }

    async def renew_lease():
        while True:
            await asyncio.sleep(GOAL_LEASE_RENEW_SECONDS)
            try:
                renewed = await asyncio.wait_for(lease.renew(), 5)
                if not renewed:
                    raise TaskInterruptedError("Goal execution lease was lost")
                lease_state["expires_at"] = (
                    asyncio.get_running_loop().time() + GOAL_LEASE_TTL_SECONDS
                )
            except Exception:
                lease_state["failure"] = "Goal execution lease was lost or unavailable"
                lease_state["owner"].cancel()
                return

    async def release_lease():
        if renewal is not None:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
        if acquired:
            try:
                await asyncio.wait_for(lease.release(), 5)
            except Exception:
                logger.exception("Goal execution lease release failed; awaiting expiry")

    lease_state["release"] = release_lease

    try:
        try:
            acquired = await asyncio.wait_for(lease.acquire(), 5)
        except Exception as error:
            raise TaskInterruptedError("Goal execution lease is unavailable") from error
        if not acquired:
            raise GoalRunAlreadyOwnedError("Goal execution lease already has an owner")
        lease_state["expires_at"] = asyncio.get_running_loop().time() + GOAL_LEASE_TTL_SECONDS
        if install_context:
            context_token = GOAL_RUN_LEASE.set(lease_state)
        renewal = asyncio.create_task(renew_lease())
        yield lease_state
    except asyncio.CancelledError:
        if lease_state["failure"]:
            raise TaskInterruptedError(lease_state["failure"]) from None
        raise
    finally:
        try:
            if not lease_state.get("transferred"):
                await release_lease()
        finally:
            if context_token is not None:
                GOAL_RUN_LEASE.reset(context_token)


def with_goal_run_lease(function):
    signature = inspect.signature(function)

    @wraps(function)
    async def owned(*args, **kwargs):
        arguments = signature.bind(*args, **kwargs).arguments
        from src.infra.scheduler.conversation import (
            SCHEDULED_SUBMISSION,
            execute_conversation_schedule,
        )
        from src.infra.task.background_tasks import execute_background_stream

        background = (
            (arguments["user_id"], arguments["session_id"])
            if arguments.get("executor")
            in (execute_background_stream, execute_conversation_schedule)
            else None
        )
        try:
            async with goal_run_lease(
                arguments.get("active_goal"),
                arguments["run_id"],
                reuse=True,
                background_identity=background,
            ):
                if arguments.get("executor") is execute_conversation_schedule:
                    from src.infra.scheduler.conversation import validate_scheduled_run_admission

                    await validate_scheduled_run_admission(
                        arguments["session_id"], arguments["user_id"], arguments["run_id"]
                    )
                await validate_goal_admission(arguments)
                dispatch_token = GOAL_DISPATCH.set(None)
                token = (
                    SCHEDULED_SUBMISSION.set(None)
                    if arguments.get("executor") is execute_conversation_schedule
                    else None
                )
                try:
                    return await function(*args, **kwargs)
                finally:
                    GOAL_DISPATCH.reset(dispatch_token)
                    if token is not None:
                        SCHEDULED_SUBMISSION.reset(token)
        except GoalRunAlreadyOwnedError:
            raise
        except Exception as error:
            claim = arguments.get("recovery_claim")
            if claim:
                from src.infra.task.recovery import restore_recovery_claim

                await restore_recovery_claim(
                    arguments["self"]._storage,
                    arguments["session_id"],
                    arguments["run_id"],
                    claim,
                    recoverable=not isinstance(error, GoalRunAdmissionError),
                )
            raise

    return owned


def with_goal_submission_lease(function):
    signature = inspect.signature(function)

    @wraps(function)
    async def owned(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        goal = bound.arguments.get("active_goal")
        from src.infra.scheduler.conversation import execute_conversation_schedule
        from src.infra.task.background_tasks import execute_background_stream

        background = (
            (bound.arguments["user_id"], bound.arguments["session_id"])
            if bound.arguments.get("executor")
            in (execute_background_stream, execute_conversation_schedule)
            else None
        )
        if (not goal or not goal.get("_persistent_id")) and background is None:
            return await function(*args, **kwargs)
        if not bound.arguments.get("run_id"):
            from src.infra.task.run_ids import generate_run_id

            bound.arguments["run_id"] = generate_run_id()
        manager = bound.arguments["self"]
        async with goal_run_lease(
            goal, bound.arguments["run_id"], background_identity=background
        ) as lease_state:
            await validate_goal_admission(bound.arguments)
            result = await function(*bound.args, **bound.kwargs)
            task = manager._tasks[result[0]]
            lease_state["owner"] = task
            lease_state["transferred"] = True

            def release_after_completion(_task):
                cleanup = asyncio.create_task(lease_state["release"]())
                manager._release_tasks.add(cleanup)
                cleanup.add_done_callback(manager._on_release_task_done)

            task.add_done_callback(release_after_completion)
            return result

    return owned


async def guarded_goal_stream(
    source, *, active_goal: dict | None, session_id: str, user_id: str, presenter, hitl_resume=None
):
    if not active_goal or not active_goal.get("_persistent_id"):
        async for event in source:
            yield event
        return
    entered = False
    try:
        async with goal_run_lease(
            active_goal, presenter.run_id, reuse=True, install_context=False
        ) as lease_state:
            entered = True
            guarded = _guarded_goal_stream(
                source,
                active_goal=active_goal,
                session_id=session_id,
                user_id=user_id,
                presenter=presenter,
                hitl_resume=hitl_resume,
                lease_state=lease_state,
            )
            try:
                async for event in guarded:
                    yield event
                    if lease_state["standalone"]:
                        lease_state["owner"] = asyncio.current_task()
            finally:
                # Keep ownership while both the runtime and host finish cleanup.
                try:
                    await guarded.aclose()
                finally:
                    await source.aclose()
    finally:
        if not entered:
            await source.aclose()


async def _guarded_goal_stream(
    source, *, active_goal: dict, session_id: str, user_id: str, presenter, hitl_resume, lease_state
):
    service = GoalService()
    metrics = GoalRunMetrics()
    presenter.persistent_goal_metrics = metrics
    version = active_goal["_persistent_version"]
    run_id = presenter.run_id
    value = await service.get(session_id, user_id)

    def valid(record):
        return (
            record is not None
            and record.id == active_goal["_persistent_id"]
            and record.version == version
            and record.current_run_id == run_id
            and record.status in {"active", "waiting_human"}
        )

    if value is None or not valid(value):
        raise TaskInterruptedError("Goal was paused or superseded")
    if value.status == "waiting_human":
        if not hitl_resume:
            raise TaskInterruptedError("Goal is waiting for human approval")
        value.status = "active"
        value = await service._save(value)
        if value is None:
            raise TaskInterruptedError("Goal approval resume authority changed")
    previous = next(
        (
            item
            for item in value.run_accounting
            if item.run_id == run_id and item.version == version
        ),
        None,
    )
    if previous and (previous.tokens is None or previous.tokens > 0):
        metrics.tokens = previous.tokens
        metrics.model_tokens = previous.tokens or 0
        metrics.unknown_model_usage = previous.tokens is None
    fenced = {"expected_version": version, "expected_run_id": run_id}

    async def checkpoint_usage(*, completed=False):
        return await service.record_usage(
            session_id,
            user_id,
            version,
            run_id,
            usage=None if metrics.unknown_model_usage else metrics.tokens,
            completed=completed,
            expected_goal_id=active_goal["_persistent_id"],
        )

    async def enforce():
        if lease_state["failure"] or asyncio.get_running_loop().time() >= lease_state["expires_at"]:
            raise TaskInterruptedError("Goal execution lease was lost or expired")
        current = await service.get(session_id, user_id)
        if current is None or not valid(current):
            raise TaskInterruptedError("Goal was paused or superseded")
        if metrics.seen_models:
            current = await checkpoint_usage() or current
            if current is None or not valid(current):
                raise TaskInterruptedError("Goal was paused or superseded")

    metrics.enforce = enforce
    current_owner = asyncio.current_task()
    assert current_owner is not None
    owner: asyncio.Task[Any] = current_owner
    stop_reason = ""

    async def watchdog():
        nonlocal stop_reason
        while True:
            await asyncio.sleep(0.25)
            try:
                await asyncio.wait_for(enforce(), 5)
            except TaskInterruptedError as error:
                stop_reason = str(error)
                owner.cancel()
                return
            except Exception:
                logger.warning("Goal watchdog check failed", exc_info=True)
                stop_reason = "Goal authority could not be verified"
                owner.cancel()
                return

    watchdog_task = asyncio.create_task(watchdog())
    try:
        async for event in source:
            metrics.observe(event)
            await enforce()
            yield event
            resumed_owner = asyncio.current_task()
            assert resumed_owner is not None
            owner = resumed_owner
    except asyncio.CancelledError:
        if stop_reason or lease_state["failure"]:
            raise TaskInterruptedError(stop_reason or lease_state["failure"]) from None
        current = await service.get(session_id, user_id)
        if valid(current):
            paused = await service.control(session_id, user_id, "pause", **fenced)
            if paused:
                await publish_goal(paused, presenter)
        raise
    except TaskInterruptedError:
        raise
    except Exception as error:
        current = await service.get(session_id, user_id)
        if valid(current):
            from src.infra.llm.quota import is_quota_error

            blocked = await service.control(
                session_id, user_id, "pause" if is_quota_error(error) else "block", **fenced
            )
            if blocked:
                await publish_goal(blocked, presenter)
        raise
    else:
        metrics.unknown_model_usage |= bool(metrics.pending_models)
        if getattr(presenter, "hitl_suspended", False):
            await checkpoint_usage()
            waiting = await service.control(session_id, user_id, "waiting_human", **fenced)
            if waiting:
                await publish_goal(waiting, presenter)
        else:
            evidence_clock = getattr(presenter, "goal_evidence_clock", None)
            current_proof = evidence_clock is None or (
                evidence_clock.active_writes == 0
                and (evidence_clock.token, evidence_clock.generation)
                == getattr(presenter, "goal_evidence_clock_snapshot", None)
            )
            finished = await service.finish(
                session_id,
                user_id,
                version,
                run_id,
                usage=None if metrics.unknown_model_usage else metrics.tokens,
                verdict=getattr(presenter, "goal_verdict", None),
                tools=metrics.tool_count,
                main_output_limited=metrics.main_output_limited,
                progress_signature=metrics.progress_signature,
                evidence_ready=current_proof
                and bool(getattr(presenter, "goal_evidence_ready", False)),
                evidence_ids=getattr(presenter, "goal_evidence_ids", []) if current_proof else [],
            )
            if finished:
                await publish_goal(finished, presenter)
                if finished.status == "active":
                    await enqueue_goal(finished)
    finally:
        watchdog_task.cancel()
        await asyncio.gather(watchdog_task, return_exceptions=True)
        # Cancellation can finalize this stream before a provider's terminal callback arrives.
        metrics.unknown_model_usage |= bool(metrics.pending_models)
        # Includes cancellation and supersession; late usage can only
        # reach the same Goal identity's registered run and never replace its state.
        try:
            accounted = await checkpoint_usage(
                completed=not getattr(presenter, "hitl_suspended", False)
            )
            if accounted and accounted.status == "paused":
                await publish_goal(accounted, presenter)
        except Exception:
            logger.exception("Goal terminal usage could not be persisted")
