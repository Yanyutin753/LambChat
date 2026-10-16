# Conversation scheduled tasks implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Default new chat schedules to the original conversation while preserving standalone tasks.
**Architecture:** Persist coalesced pending runs in existing scheduler storage, admit them through the normal chat path with session submission fencing, and preserve run-scoped task identity. Reuse existing UI and notification delivery.
**Tech Stack:** Python, MongoDB, Redis, FastAPI, React/TypeScript.
**Spec:** docs/superpowers/specs/2026-10-16-conversation-scheduled-tasks-design.md

## Global Constraints

- Existing documents and API callers remain standalone; new chat tools default conversation.
- Preserve current checkout and unrelated changes. No new dependencies.
- Five locales; shared UI tokens. All verification uses scripts/run_validation.py, serial, workers=1.
- User explicitly chose inline implementation and waived further confirmation gates.

## Review Focus

- Admission races between human submissions and scheduled dispatch.
- One-shot tasks deferred across process restart.
- Stale runs and uncertain submissions never replay side effects.
- No session hiding/configuration loss from conversation runs.
- Quiet completion never suppresses failures or human approvals.

### Task 1: Contract and persistence

**Files:** schemas/scheduled_task.py; scheduler/service.py; scheduler/storage.py; tests/infra/scheduler/test_conversation.py.
**Interfaces:** execution_mode, target_session_id, notification_policy; coalesced pending run journal.
- [ ] Write and run failing tests for compatibility, ownership, and coalescing.
- [ ] Add schema/service validation and storage operations.
- [ ] Verify focused tests.

### Task 2: Authorized dispatch and session fencing

**Files:** scheduler/conversation.py; scheduler/runner.py; api/routes/chat.py; infra/goal_runtime.py; infra/task/executor.py.
**Interfaces:** scheduled submission context and run identity; bounded pending dispatcher; per-session admission guard.
- [ ] Write failing tests for latest session configuration, busy deferral, independent targets, and quiet completion.
- [ ] Implement durable dispatch through chat_stream, conflict guards, recovery and run-scoped notifications.
- [ ] Verify scheduler/task/API regression tests.

### Task 3: Tool and UI integration

**Files:** tool/scheduled_task/{create,helpers,update}.py; frontend scheduled task types, form, panel, session entry, locales and tests.
**Interfaces:** same task contract through creation preview, APIs and existing task controls.
- [ ] Add tests for new tool defaults and user-facing mode controls.
- [ ] Implement default conversation creation, explicit standalone option, target and notification controls, run navigation and translated quiet output.
- [ ] Verify related front/back tests.

### Task 4: Final verification and review

- [ ] Run focused backend/frontend suites, lint and build sequentially after all edits.
- [ ] Inspect rendered light/dark/narrow UI and exercise real service behavior where available.
- [ ] Review entire diff for concurrency, permissions, recovery and compatibility; fix findings.
- [ ] Report exact verification boundaries and remaining environment limitations.
