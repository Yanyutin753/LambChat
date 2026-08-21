# Same-Run HITL Resume Design

## Goal

Make interrupt-mode `ask_human` suspend and resume one logical Agent turn on the
same Session, Run, and Trace. A submitted answer must complete the original
pending UI item through a durable backend event, without creating a second Run
or requiring frontend history heuristics.

## User-visible result

- The chat shows one `ask_human` item before and after refresh.
- Submitting an answer closes that item with the submitted values and resumes
  generation in the same turn.
- Suspension is a waiting state, not a failed or completed event.
- Repeated submission cannot start a second resume.
- Local and ARQ execution produce the same Session/Run/Trace/event contract.

## Non-goals

- Do not port CrystalBall Task Board, Canvas, or its general-purpose human-input
  subsystem.
- Do not migrate blocking-mode approvals.
- Do not rewrite historical MongoDB events.
- Do not add a model call, dependency, queue subsystem, unbounded polling loop,
  or history scan; ARQ mode continues to use its existing queue.
- Do not change normal chat submission, blocking approvals, cancellation, steer,
  recovery, or non-HITL trace completion.

## Current problem

LambChat currently marks the suspended Trace completed and submits the answer as
a new Run. LangGraph then emits another `tool:start` with a new tool call ID.
History therefore contains an interrupted pending item plus a second successful
item. The frontend can hide this only by guessing that two calls across Runs are
the same logical action.

## Architecture

### Suspension

The interrupt remains owned by the original `session_id`, `run_id`, and
`trace_id`.

1. `ask_human` receives the framework-injected `InjectedToolCallId` (not a
   model-visible argument) and includes it in the interrupt payload. The
   Agent materializes the durable approval with `run_id`, `trace_id`,
   `interrupt_id`, and `tool_call_id` in approval metadata.
2. It persists `approval_required` on the original Trace.
3. The Agent emits nonterminal `hitl:suspended`; the existing Redis stream stays
   readable so a connected browser can receive the resumed output immediately.
4. The executor transitions the Session from `running` to `waiting_human` and
   flushes MongoDB buffers, but does not write `done`, `error`, expire the Redis
   stream, or complete the Trace.

`hitl:suspended` is not an SSE or Agent terminal event. Keeping the logical
stream open avoids a reconnect round trip in the live page. After refresh, the
existing active-run snapshot plus Redis replay reconstructs the pending item;
there is no new history query or cursor protocol.

### Answer and resume

`POST /human/{approval_id}/respond` uses prepare-before-commit for interrupt
approvals:

1. Verifies Session ownership of the original Run by requiring
   `task_status=waiting_human` and `current_run_id=approval.metadata.run_id`.
2. Persists/enqueues an inert resume attempt with a fresh private attempt ID.
   The attempt cannot execute until the approval document names that exact ID.
3. Atomically changes the approval from `pending` to its submitted result while
   recording the attempt ID and response. A failed compare-and-set makes the
   prepared attempt a no-op.
4. The accepted attempt submits checkpoint `Command(resume=...)` using that
   same logical Run, Trace, and Redis stream.
5. Transitions `waiting_human -> pending -> starting -> running` through the
   existing task state machine.
6. Persists `approval_resolved` on the original Trace with:

   ```json
   {
     "id": "approval UUID",
     "status": "approved or rejected",
     "result": {
       "status": "success or rejected",
       "message": "human response summary",
       "values": {}
     },
     "timestamp": "ISO-8601"
   }
   ```

7. Emits `human_resume_started` when a worker has actually entered the resumed
   execution attempt.

If prepare/enqueue fails, the approval remains `pending`. If the API process
dies after enqueue but before the compare-and-set, the orphan attempt observes
the missing/mismatched attempt ID and exits; the approval remains retryable. If
the process dies after the compare-and-set, the already-durable ARQ attempt can
continue on another worker. No rollback from a terminal approval to `pending`
is required in the distributed path.

### Frontend projection

`approval_resolved` is the canonical answer event for realtime and history.
For new Runs, `approval_required` and `approval_resolved` carry both the durable
approval ID and original `tool_call_id`, so the event processor updates exactly
that pending tool part. The “latest pending `ask_human` in the same assistant
turn” fallback is restricted to legacy events that predate this identity link.
It writes the structured result and sets `isPending=false`.

`human_resume_started` restores streaming state. Neither event creates a user
message or a second assistant turn. Existing GraphInterrupt compatibility
handling remains until the durable resolved event has updated the original
pending item. The response UI also calls an idempotent “ensure current Run SSE”
hook: it is a no-op when the original connection is alive and reconnects only
when a long wait or network change closed it.

### Distributed dispatch

Logical identity and execution identity are separate:

- `run_id` and `trace_id` remain unchanged and are used for persisted events,
  checkpoint identity, history, status, cancellation ownership, and the SSE
  stream.
- A resume has a fresh private `resume_attempt_id` containing the approval ID
  plus a nonce. It is used only as the ARQ job/payload identity, so it cannot
  collide with the already-finished source ARQ job or overwrite its payload.

The answer path uses one backend-aware dispatcher:

- `TASK_BACKEND=local`: wait for the source local task's completion callback,
  then register the resume attempt without replacing a live `_tasks[run_id]`
  entry.
- `TASK_BACKEND=arq`: persist a dedicated resume payload containing the source
  Run/Trace, executor configuration, and `hitl_resume`; enqueue it with the
  private attempt ID. Any ARQ worker may consume it.

The source dispatch wrapper publishes a short-lived distributed handoff marker
only after the executor has returned suspended and its heartbeat, cancellation
state, ARQ payload, and concurrency-slot cleanup have finished. The resume
worker requires that marker before starting; if the source worker crashed, it
may proceed only after the source heartbeat and lease are both absent. The wait
is bounded and notification-driven, with a single point-read crash fallback.
This prevents the old worker from clearing the new attempt's coordination
state.

After the handoff, the resume attempt atomically reacquires the same user's
normal concurrency capacity. A local response remains retryable when capacity
is full; an ARQ attempt defers without executing until capacity is available.
This prevents HITL resume from bypassing or permanently occupying normal chat
limits.

The Redis resume lock and atomic approval transition remain authoritative. ARQ
job uniqueness is a third idempotency layer, not the primary correctness check.

### Same-Run safety

- Resume uses the source Run ID from approval metadata; the Session's current
  Run must match it.
- The approval's atomic pending-to-terminal update and existing Redis resume
  lock remain the duplicate-submission guards.
- A worker still releasing the suspended execution attempt cannot race the
  resumed attempt across either local or ARQ backends.
- A stale answer never replaces a newer current Run.
- Interrupt IDs remain the keys passed to `Command(resume=...)`.
- Status and event writes are fenced by both source Run identity and approval
  identity; a delayed resume for an older approval cannot mutate a later
  interrupt in the same Run.

## Performance constraints

- No additional LLM call or Agent initialization beyond the resumed checkpoint.
- No session-event history read or unbounded MongoDB query on submission.
- Resume uses point reads by approval/session ID and one existing atomic status
  transition path.
- Reusing Run and Trace avoids creating and hydrating a second trace and avoids
  transferring duplicate history events.
- Event persistence stays on the existing buffered `DualEventWriter` path.
- A live browser keeps its existing SSE connection, so answering does not wait
  for history hydration or a second stream replay.
- Distributed handoff uses Redis point keys/notifications with a bounded
  crash-recovery check; it never scans workers, queues, streams, or traces.

## Files and boundaries

- `src/infra/task/hitl.py`: source identity, same-Run submission, resolved event
  builder, and resume lock.
- `src/infra/tool/human_tool/tool.py`: inject and persist the original
  `tool_call_id` without exposing it in the model tool schema.
- `src/infra/task/executor.py`: nonterminal suspension flush and resume marker.
- `src/infra/task/manager.py`: backend-aware resume dispatch and safe local
  handoff.
- `src/infra/task/arq_payloads.py` and `src/infra/task/arq_worker.py`: dedicated
  resume-attempt payload/job identity and distributed handoff gate.
- `src/infra/task/concurrency.py`: expose the source-attempt point check and an
  atomic no-queue capacity reacquire for resume attempts; normal submissions
  retain their existing acquire/queue/release semantics.
- `src/agents/{fast,search,team}_agent/{nodes.py,graph.py}`: propagate Trace
  identity and suppress terminal events while suspended.
- `src/api/routes/human.py`: answer/resume transaction ordering.
- `src/infra/session/dual_writer.py`: keep `hitl:suspended` nonterminal and flush
  its MongoDB event without expiring the live stream.
- `frontend/src/hooks/useAgent/{types.ts,eventProcessor.ts,eventHandlers.ts,historyLoader.ts}`:
  consume `approval_resolved` and `human_resume_started` consistently.
- `frontend/src/hooks/useApprovals.ts` and `useAgent/sseConnection.ts`: after an
  accepted interrupt answer, idempotently ensure the same Run stream is still
  connected.
- Existing adjacent backend and frontend test files receive regression cases;
  no new framework or fixture package is introduced.

## Validation

- Backend unit tests prove same Run/Trace submission, stale-Run rejection,
  prepare failure leaving approval pending, orphan-attempt no-op, post-claim
  worker continuation, resolved result shape, and suspension without terminal
  Trace completion.
- Event-stream tests prove `hitl:suspended` does not terminate replay/read and
  resumed events on the same Run remain visible without duplication.
- Frontend processor/history tests prove one completed `ask_human` item and
  preserve parallel and sequential distinct real calls; legacy fallback remains
  covered separately.
- Steer regression tests prove `WAITING_HUMAN` still rejects new steer requests,
  while a steer accepted before suspension remains FIFO/idempotent and is
  injected once under the original Run after resume.
- Run the lifecycle matrix for `local` and `arq`, including answer-on-another-
  instance, duplicate answer, source-worker cleanup race, source-worker crash,
  refresh while waiting, cancellation while waiting, and a second genuine
  `ask_human` after resume.
- Run focused Python tests, Ruff on touched Python files, focused frontend tests,
  frontend lint/build, and `git diff --check`.
- A live Yang verification requires a separately authorized deployment and a
  fresh approval flow; local tests do not claim production repair.

## Compatibility

Blocking-mode approvals keep their existing waiter notification behavior.
Existing historical two-Run sessions are not rewritten; the new frontend
`approval_resolved` support remains backward compatible, while new Runs use the
same-Run contract. Normal non-HITL tasks keep their current generated Run/Trace,
ARQ payload key, terminal events, stream TTL, concurrency, recovery, and
cancellation paths; the private resume-attempt path is entered only when the
approval metadata says `mode=interrupt`.
