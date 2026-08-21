# Same-Run HITL Resume Implementation Plan

**Goal:** Resume interrupt-mode `ask_human` on the original Session, Run,
Trace, and Redis stream in both local and ARQ task backends, while projecting
one durable tool result in realtime and history.

**Constraints:** Normal chat, blocking approvals, cancellation, steer,
recovery, and non-HITL terminal behavior remain unchanged. Implement each task
test-first and keep the existing storage, queue, and event abstractions.

## Task 1: Persist exact HITL identity

**Files:**
- Modify `src/infra/tool/human_tool/tool.py`
- Modify `src/infra/task/hitl.py`
- Modify `src/agents/{fast,search,team}_agent/nodes.py`
- Test `tests/infra/tool/test_human_tool_interrupt.py`
- Test `tests/infra/task/test_hitl_resume.py`

1. Add failing tests proving the injected tool call ID enters the interrupt
   payload and approval metadata contains `run_id`, `trace_id`, `interrupt_id`,
   and `tool_call_id`.
2. Run the focused tests and observe RED.
3. Inject `InjectedToolCallId` without changing the model-visible schema;
   propagate Trace identity and event identity.
4. Run focused tests to GREEN.

## Task 2: Dispatch resume on the original Run/Trace

**Files:**
- Modify `src/infra/task/hitl.py`
- Modify `src/infra/task/manager.py`
- Modify `src/infra/task/arq_payloads.py`
- Modify `src/infra/task/arq_worker.py`
- Test `tests/infra/task/test_hitl_resume.py`
- Test `tests/infra/task/test_arq_submission.py`
- Test `tests/infra/task/test_arq_worker.py`

1. Add failing local tests for source-task handoff and exact Run/Trace reuse.
2. Add failing ARQ tests for a private resume-attempt payload/job ID whose
   payload retains the logical source Run/Trace and `hitl_resume`.
3. Implement one backend-aware manager path. Preserve normal ARQ defaults.
4. Add a bounded source-worker release fence and crash-safe point fallback.
5. Reacquire normal user concurrency capacity before the resumed attempt runs;
   local mode remains retryable and ARQ defers when capacity is full.
6. Run the focused backend tests to GREEN.

## Task 3: Make suspension nonterminal

**Files:**
- Modify `src/infra/task/executor.py`
- Modify `src/agents/{fast,search,team}_agent/graph.py`
- Modify `src/infra/session/dual_writer.py` only if its current terminal helper
  needs an explicit regression guard
- Test adjacent executor, graph source, state-machine, and writer tests

1. Add failing tests proving a suspended execution writes no `done`, does not
   complete/expire the Trace, flushes persisted events, and leaves
   `hitl:suspended` nonterminal.
2. Suppress graph `done` and executor `complete()` only when suspended.
3. Return a suspension outcome to local/ARQ dispatch cleanup.
4. Run focused tests to GREEN and verify normal completion tests unchanged.

## Task 4: Commit approval result durably and project it exactly

**Files:**
- Modify `src/api/routes/human.py`
- Modify `src/infra/task/hitl.py`
- Modify `src/infra/storage/mongodb.py` if the existing CAS cannot store the
  attempt identity
- Modify `frontend/src/hooks/useAgent/{types.ts,eventProcessor.ts,eventHandlers.ts,historyLoader.ts}`
- Modify `frontend/src/hooks/useApprovals.ts` and its caller only if reconnect
  is required after a dead stream
- Test adjacent backend route/storage and frontend processor/history tests

1. Add failing route tests for prepare failure, duplicate response, exact
   attempt claim, and accepted response.
2. Emit `approval_resolved` with approval/tool/interrupt identities and the
   blocking-compatible structured result before resumed model output.
3. Add failing frontend tests for exact tool-call update, refresh projection,
   parallel calls, sequential calls, and legacy fallback.
4. Implement the minimum event handling and idempotent stream ensure hook.
5. Run focused backend/frontend tests to GREEN.

## Task 5: Regression and completion verification

1. Run all focused HITL, human route, task lifecycle, ARQ, event writer, and
   frontend Agent tests.
2. Run steer API/middleware/history regressions across the suspension boundary.
3. Run Ruff on touched Python files.
4. Run frontend lint and production build.
5. Run `git diff --check`, inspect the actual diff, and report any broader
   suite/environment boundary honestly.
6. Do not commit, push, or deploy without separate authorization.
