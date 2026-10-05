"""Reuse task identities when a durable channel delivery is retried."""

from __future__ import annotations

from typing import Any

from src.infra.channel.inbox_worker import current_delivery
from src.kernel.config import settings


def delivery_session(default: str) -> str:
    context = current_delivery.get()
    return str(context.checkpoint.get("session_id") or default) if context else default


async def submit_channel_task(
    manager: Any, *, channel_delivery: dict | None = None, **kwargs: Any
) -> tuple[str, str]:
    if channel_delivery:
        kwargs["session_metadata"] = {
            **(kwargs.get("session_metadata") or {}),
            "channel_delivery": channel_delivery,
        }
    context = current_delivery.get()
    if context:
        checkpoint = context.checkpoint
        if checkpoint.get("run_id"):
            # Metadata is written before persistence/enqueue: it is only intent.
            from src.infra.session.trace_storage import get_trace_storage
            from src.infra.task.heartbeat import TaskHeartbeat

            run_id = str(checkpoint["run_id"])
            kwargs["trace_id"] = checkpoint.get("trace_id") or kwargs.get("trace_id")
            events = await get_trace_storage().get_session_events(
                checkpoint["session_id"], run_id=run_id, completed_only=False
            )
            task = getattr(manager, "_tasks", {}).get(run_id)
            live = task is not None and not task.done()
            live = live or not await TaskHeartbeat().is_stale(run_id)
            if events:
                kwargs["trace_id"] = events[0].get("trace_id") or checkpoint.get("trace_id")
                # Only Mongo persistence permits skipping the input. A Redis-only
                # write must be persisted again (same run-stable message_id), or
                # a crash during Mongo flush would permanently lose chat history.
                kwargs["user_message_written"] = any(
                    event.get("event_type") == "user:message" for event in events
                )
            # chat's goal:start and BaseGraphAgent's metadata are emitted before
            # astream_events receives the input. Neither proves graph execution.
            # Retain other execution/terminal events conservatively: restarting
            # the original input after a tool side effect would repeat work.
            pregraph_events = {"user:message", "metadata", "goal:start"}
            started = any(event.get("event_type") not in pregraph_events for event in events)
            if not live and not started:
                from src.infra.session.manager import SessionManager

                session = await SessionManager().get_session(checkpoint["session_id"])
                metadata = getattr(session, "metadata", None) or {}
                started = metadata.get("current_run_id") == run_id and (
                    metadata.get("task_status")
                    in {"waiting_human", "completed", "cancelled", "cancelling", "expired"}
                    or (
                        metadata.get("task_status") == "failed"
                        and metadata.get("task_recoverable") is False
                    )
                )
            if not live and not started and settings.TASK_BACKEND == "arq":
                from arq.jobs import Job, JobStatus

                from src.infra.task.arq_payloads import TaskArqPayloadStore

                pool = await manager._get_arq_pool()
                live = await Job(run_id, pool).status() != JobStatus.not_found
                if not live:
                    payload = await TaskArqPayloadStore().load(run_id)
                    if payload:
                        # An ambiguous enqueue is safe to repeat with the same
                        # job identity and already-persisted original payload.
                        await pool.enqueue_job("run_agent_task", run_id, _job_id=run_id)
                        live = True
                        kwargs["trace_id"] = payload.get("trace_id")
            if live or started:
                trace_id = kwargs.get("trace_id") or checkpoint.get("trace_id") or ""
                await context.save(submitted=True, trace_id=trace_id)
                checkpoint["reattached"] = True
                return run_id, str(trace_id)
        else:
            from src.infra.task.run_ids import generate_run_id

            await context.save(session_id=kwargs["session_id"], run_id=generate_run_id())
        # An accepted submit only proves create_task/enqueue returned. If the
        # executor died before consuming the input, retry that original input;
        # a hidden continuation instruction would lose the user's request.
        checkpoint.pop("reattached", None)
        kwargs.update(
            session_id=checkpoint["session_id"],
            run_id=checkpoint["run_id"],
            write_user_message_immediately=True,
        )
    if settings.TASK_BACKEND == "arq":
        kwargs.pop("executor", None)
        result = await manager.submit_arq(executor_key="agent_stream", **kwargs)
    else:
        result = await manager.submit(**kwargs)
    if context:
        await context.save(submitted=True, trace_id=result[1])
    return result


def _latest_attempt(events: list[dict]) -> list[dict]:
    start = 0
    for index, event in enumerate(events):
        if event.get("event_type") == "run:resumed":
            start = index
    return events[start:]


async def _recover_channel_run(session_id: str, run_id: str, *, error: bool) -> bool:
    from src.infra.session.manager import SessionManager
    from src.infra.task.heartbeat import TaskHeartbeat
    from src.infra.task.manager import get_task_manager

    session = await SessionManager().get_session(session_id)
    metadata = getattr(session, "metadata", None) or {}
    if str(metadata.get("current_run_id") or "") != run_id:
        return False
    if metadata.get("task_status") in {
        "waiting_human",
        "cancelling",
        "cancelled",
        "completed",
        "expired",
    }:
        return False
    if (
        error
        and not metadata.get("task_recoverable")
        and metadata.get("task_status")
        not in {"pending", "queued", "starting", "running", "recovering"}
    ):
        return False
    if metadata.get("task_recoverable") is False and metadata.get("task_status") in {
        "failed",
        "completed",
        "cancelled",
    }:
        return False
    manager = get_task_manager()
    task = getattr(manager, "_tasks", {}).get(run_id)
    if task is not None and not task.done():
        return error
    if not await TaskHeartbeat().is_stale(run_id):
        return error
    if settings.TASK_BACKEND == "arq":
        from arq.jobs import Job, JobStatus

        pool = await manager._get_arq_pool()
        if await Job(run_id, pool).status() in {JobStatus.queued, JobStatus.deferred}:
            return error
    # Existing recovery owns the distributed lock, heartbeat recheck, retry
    # limit and original session configuration/trace snapshot.
    await manager._resume_interrupted_run(session, run_id, "channel_reconnect")
    return True


async def read_channel_events(session_id: str, run_id: str):
    """Replay completed traces even after the transient Redis stream expires."""
    from src.infra.session.dual_writer import get_dual_writer

    context = current_delivery.get()
    terminal = {"done", "complete", "error"}
    if context and context.checkpoint.get("reattached"):
        from src.infra.session.trace_storage import get_trace_storage

        events = _latest_attempt(
            await get_trace_storage().get_session_events(
                session_id, run_id=run_id, completed_only=False
            )
        )
        if events and events[-1].get("event_type") in terminal:
            if events[-1].get("event_type") == "error" and await _recover_channel_run(
                session_id, run_id, error=True
            ):
                raise RuntimeError("Channel task is recovering")
            for event in events:
                yield event
            return
        if await _recover_channel_run(session_id, run_id, error=False):
            raise RuntimeError("Channel task is recovering")
    completed = False
    async for event in get_dual_writer().read_from_redis(session_id, run_id):
        if event.get("event_type") in terminal:
            if (
                context
                and event.get("event_type") == "error"
                and await _recover_channel_run(session_id, run_id, error=True)
            ):
                raise RuntimeError("Channel task is recovering")
            completed = True
        yield event
    if context and not completed:
        await _recover_channel_run(session_id, run_id, error=False)
        raise RuntimeError("Channel reply stream ended before task completion")
