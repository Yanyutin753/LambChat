# Steer 消息可靠性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make steer delivery observable, idempotent, cancellable by identity, and safe across stream races.

**Architecture:** Extend the existing queue and SSE protocol with stable IDs and explicit outcomes. Keep the current queue abstraction so local development remains dependency-free; isolate persistence behind the same methods for a later Redis adapter.

**Tech Stack:** Python/FastAPI/pytest, React/TypeScript/Vitest, existing SSE event pipeline.

**Spec:** `docs/superpowers/specs/2026-08-20-steer-reliability-design.md`

## Global Constraints

- Preserve unrelated user changes in the worktree.
- Use TDD: each behavior starts with a failing test.
- Keep backward compatibility for clients sending only `message`.
- Do not auto-send a steer as a normal message for transport/auth/server failures.

### Task 1: Identity-based queue contract

**Files:** `src/infra/task/steer.py`, `tests/infra/task/test_steer_queue.py`

- [ ] Add failing tests for `SteerItem`, duplicate ID enqueue, ID cancellation, and drain/requeue preserving IDs.
- [ ] Implement typed queue items and atomic methods `enqueue(session_id, item)`, `remove(session_id, message_id, message=None)`, `drain`, and `requeue_front`.
- [ ] Run the focused pytest file and then the middleware tests.

### Task 2: API and middleware propagation

**Files:** `src/api/routes/chat.py`, `src/infra/agent/middleware/steer.py`, `tests/api/routes/test_chat_steer.py`, `tests/infra/agent/test_steer_middleware.py`

- [ ] Add failing tests proving response IDs, idempotent retry, ID cancellation, and event `run_id` propagation.
- [ ] Implement optional request ID, stable response statuses, compatibility fallback, and per-item event persistence.
- [ ] Run the focused backend tests.

### Task 3: Frontend state machine and race handling

**Files:** `frontend/src/hooks/useAgent/steerQueue.ts`, `frontend/src/utils/mergeSteers.ts`, `frontend/src/hooks/useAgent/eventHandlers.ts`, related tests.

- [ ] Add failing Vitest cases for duplicate content, duplicate event IDs, stale run events, and transport failure remaining retryable.
- [ ] Implement ID-based reconciliation, explicit status, and event guards without changing ordinary message sending.
- [ ] Run focused Vitest tests.

### Task 4: Verification

- [ ] Run backend steer tests, frontend steer tests, frontend build, and lint.
- [ ] Inspect diff to ensure no unrelated user edits were overwritten.
