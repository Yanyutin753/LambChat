# Chat Submit Flush Race Design

## Goal

Remove the fixed one-second delay from immediate user-message persistence while preserving the existing guarantee that the user message reaches MongoDB before `/api/chat/stream` returns success.

## Root Cause

`DualEventWriter.write_event()` queues the event and creates a task that sleeps for one second before flushing the MongoDB buffer. The immediate user-message path then calls `flush_mongo_buffer(require_trace_id=...)` for durability.

There is a scheduling window between `asyncio.create_task()` and the first instruction of `_schedule_flush()`. During that window `_flush_task_waiting` is still false, so `_drain_scheduled_flush_task()` treats the newly-created delayed task as an active flush and awaits it, including its one-second sleep.

## Design

Publish the delayed task's waiting state synchronously before calling `asyncio.create_task()`. A forced flush can then cancel a delayed task even when the task has not started running.

After cancellation, explicitly clear the waiting flag. This is required because a task cancelled before its coroutine starts does not execute the coroutine's `finally` block. The forced flush then calls `_do_flush()` itself, retaining the current durability behavior.

When the scheduled task has already finished sleeping and entered `_do_flush()`, `_flush_task_waiting` remains false. A concurrent forced flush will continue awaiting that active write rather than cancelling it, preserving serialization and preventing duplicate or lost writes.

## Scope

- Modify only delayed Mongo flush scheduling and draining state.
- Add a regression test that forces the pre-start scheduling window through the real `write_event()` path.
- Retain Redis-first delivery, Mongo buffering, trace-scoped durability checks, and terminal event behavior.

## Non-goals

- Do not move user-message persistence into the background.
- Do not change search-index updates, task payload persistence, arq enqueueing, MCP caching, or agent graph construction.
- Do not introduce graph or request-state caching.

## Verification

The regression test uses a long delayed-flush interval, writes one event, and immediately forces a flush without yielding to the new task. It must finish within 100ms and execute exactly one real flush. Existing delayed-flush, trace durability, terminal-event, and buffer failure tests must remain green.
