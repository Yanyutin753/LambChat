# Chat Submit Flush Race Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the one-second scheduling race from immediate user-message persistence without weakening MongoDB durability.

**Architecture:** Mark a delayed flush as waiting before its asyncio task is scheduled, so an immediately-following forced flush can cancel it before coroutine entry. Keep awaiting tasks that have already entered the actual MongoDB flush, and explicitly reset state after pre-start cancellation.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio

## Global Constraints

- A successful chat submit still requires the initial user message to be durable in MongoDB.
- Do not change Redis delivery, Mongo buffer contents, trace durability checks, or arq semantics.
- Do not modify unrelated dirty workspace files.

---

### Task 1: Cancel a delayed flush before coroutine entry

**Files:**
- Modify: `src/infra/session/dual_writer.py:240-305`
- Test: `tests/infra/test_dual_writer_limits.py:379-423`

**Interfaces:**
- Consumes: `DualEventWriter.write_event(...)` and `DualEventWriter.flush_mongo_buffer(...)`.
- Produces: immediate forced-flush behavior that does not await `_MONGO_FLUSH_INTERVAL` while retaining exactly one `_do_flush()` call.

- [ ] **Step 1: Write the failing regression test**

```python
@pytest.mark.asyncio
async def test_flush_mongo_buffer_cancels_delayed_flush_before_task_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dual_writer, "_MONGO_FLUSH_INTERVAL", 60.0)
    writer = dual_writer.DualEventWriter()
    flush_calls = 0

    async def _write_to_redis_direct(stream_key: str, fields: dict[str, str]) -> bool:
        return True

    async def _fake_do_flush() -> None:
        nonlocal flush_calls
        flush_calls += 1
        writer._flush_event.set()

    writer._write_to_redis_direct = _write_to_redis_direct
    writer._do_flush = _fake_do_flush

    await writer.write_event("s1", "user:message", {"content": "hello"}, "t1", run_id="r1")
    await asyncio.wait_for(writer.flush_mongo_buffer(require_trace_id="t1"), timeout=0.1)

    assert flush_calls == 1
    assert writer._flush_task is None
    assert writer._flush_task_waiting is False
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/infra/test_dual_writer_limits.py::test_flush_mongo_buffer_cancels_delayed_flush_before_task_starts -v`

Expected: fail with `TimeoutError` because the current implementation awaits the 60-second delayed task.

- [ ] **Step 3: Implement the minimal scheduling fix**

In `write_event()`, set `self._flush_task_waiting = True` immediately before creating `_schedule_flush()`. In the cancellation branch of `_drain_scheduled_flush_task()`, explicitly restore the flag to false after the task is cancelled.

- [ ] **Step 4: Run focused and neighboring tests**

Run:

```bash
uv run pytest \
  tests/infra/test_dual_writer_limits.py::test_flush_mongo_buffer_cancels_delayed_flush_before_task_starts \
  tests/infra/test_dual_writer_limits.py::test_flush_mongo_buffer_does_not_wait_for_delayed_flush_event \
  tests/infra/test_dual_writer_limits.py::test_flush_mongo_buffer_drains_pending_delayed_flush_task \
  tests/infra/test_dual_writer_limits.py::test_flush_mongo_buffer_can_require_only_current_trace_to_be_durable \
  tests/infra/test_dual_writer_limits.py::test_terminal_events_flush_mongo_buffer_immediately -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Run the complete affected test module and lint**

Run:

```bash
uv run pytest tests/infra/test_dual_writer_limits.py -q
uv run ruff check src/infra/session/dual_writer.py tests/infra/test_dual_writer_limits.py
```

Expected: zero failures and zero lint errors.

- [ ] **Step 6: Restart the local runtime and verify the submit path**

Send a new Search Agent message and compare `/api/chat/stream` duration and the interval between trace creation and `Task submitted to arq`. The fixed one-second plateau must be absent while the user message remains present after refresh.
