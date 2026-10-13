# Agent Capabilities Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration and superpowers:dispatching-parallel-agents for independent domains. The user explicitly approved the design and direct execution without further confirmation.

**Goal:** Deliver all six approved capabilities in the existing worktree with integrated behavior and serial verification.
**Architecture:** Retain the existing run Goal, tools, checkpoints, auth and task manager. Add session Goal persistence and bounded continuation, evidence references, structured read-only PTC, reusable subagent conversations and compact searchable directories.
**Tech Stack:** Python/FastAPI/LangGraph/deepagents/QuickJS/MongoDB/Redis/arq; React/TypeScript/pnpm.
**Spec:** `docs/superpowers/specs/2026-10-13-agent-capabilities-design.md`.

## Global Constraints

- Latest origin/develop baseline; no changes to the original dirty workspace.
- No additional design/plan approval: explicitly waived by user.
- New behavior and bug fixes use targeted observed RED tests; mechanical extractions retain existing behavior and are regression checked. Root alone executes validation via scripts/run_validation.py, single worker/job; exit 75 means stop validation, no queuing/retries.
- Complete callers, config, UI and zh/en/ja/ko/ru before final build/lint/typecheck.
- Permissions and approval remain authoritative; PTC known read-only tools only; evidence is untrusted data.
- Defaults: Goal 10 turns/100000 tokens/3600 seconds; PTC 32 calls/60 seconds/8000 output chars/3 hosts; child concurrency 3, execution timeout 600 seconds.

## Review Focus

- Cancel/pause racing with queued continuation cannot restart the user's work.
- Stale worker/Goal versions cannot overwrite a newer objective or verdict.
- Missing usage, grader failure, unavailable evidence and all-skipped evaluation never count as success.
- PTC and child communication retain user/trace attribution and do not bypass authorization.
- Session fork/delete, role revocation and checkpoint recovery do not clone live ownership or replay uncertain writes.

### Task 1: Agent evaluation baseline
Files: `scripts/eval_agent_capabilities.py`, capability evaluation fixtures and `tests/infra/agent/test_capability_evaluation.py`.
Produces: versioned case/results JSON with deterministic assertions; trace and explicitly configured live modes; A/B comparison by identical case IDs/version.
- [x] Write tests: fail/error/skip exit status; unknown usage; mismatched A/B; nine cases; redaction; explicit live URL/auth.
- [x] Root observes RED; implement and observe GREEN through validation wrapper.

### Task 2: Structured read-only PTC
Files: `src/infra/agent/middleware/code_interpreter.py`, PTC adapter, interpreter tests.
Produces: native `{ok,data,sources,truncated,error}` bridge, bounded concurrency/lifetime; original tools unchanged.
- [x] Write tests with actual QuickJS host calls: valid/non-JSON, truncation, partial failure, cancel, audit, disallowed tool.
- [x] Root observes RED; implement adapters through upstream explicit BaseTool API; root observes GREEN.

### Task 3: Evidence state and handoff
Files: `src/infra/agent/evidence.py`, evidence middleware, three agent node assembly, main context and report handoff, evidence tests.
Produces: checkpoint evidence references, current scope/version and compact model/grader index; no copied raw output or privileged arbitrary file reads.
- [x] RED: collect success/error refs; stale scope/file checks; repeated compression survives index; forbidden references.
- [x] Implement automatic tool recording and grader evidence prompt; integrate all agent modes; GREEN targeted tests.

### Task 4: Persistent Goal lifecycle, dispatcher, UI
Files: new persistent Goal schemas/store/service/continuation, chat Goal routes, task execution/recovery integration, session API, goalCommands/ActiveGoalBar/useAgent, five locales; API/storage/dispatch/UI tests.
Consumes: Task 3 evidence and existing rubric verdict/usage events.
Produces: opt-in session Goal API and user commands; CAS fenced bounded arq continuations; `goal:updated` stream and reload state.
- [x] RED: ordinary Goal unchanged; ownership; lifecycle; dual-worker fencing; enqueue crash recovery; pause/user-message race; budget and stagnation; fork/deletion; UI commands/controls.
- [x] Implement through existing task manager and session concurrency; add grader event callback and usage accounting; wire controls/reload/stream; GREEN per affected surface.

### Task 5: Reusable subagent lifecycle
Files: PR #871 subagent core/tool/middleware dependency subset; shared assembly helper; fast/search/team nodes; dedicated tool Items/renderers and locales; relevant tests.
Consumes: existing retry/role/tool discovery/backend/checkpointer and Task 3 evidence.
Produces: all three agent modes start/send/wait/list/cancel; queued/running states, concurrency 3, bounded wait and execution time, recovery ownership.
- [x] Establish current PR merge state and import only required dependency code/callers/tests if absent.
- [x] RED: concurrency, queue cancel, timeout, parent cancel, approval, ID idempotency, recovery/authorization, frontend status/events and dedicated tool routing.
- [x] Implement bounded lifecycle and shared assembly; audit parent/child events; GREEN tests.

### Task 6: Grouped tool and skill discovery
Files: deferred manager, skill loader/search, related inventory/search/restore/fork tests.
Produces: grouped inventory above thresholds with full authorized search, stable loaded schemas, exact selection.
- [x] RED: 20/100/500 fixtures, grouped size, exact search, uncategorized, disabled, restore/fork.
- [x] Implement compact group descriptors with unchanged execution names; GREEN tests.

### Task 7: Integrated verification and review
- [x] Finish every call site/config/locale; no partial helpers advertised as support.
- [x] Serial relevant backend/frontend suites, ruff/mypy and frontend lint/build; local sandbox E2E when sandbox chain changes.
- [x] Run trace fixtures and available isolated live probes; document unconfigured advanced live hooks and unrun A/B explicitly.
- [x] Fresh whole-branch review, fix important findings with RED/GREEN; final serial checks after relevant edits.
- [x] Commit completed changes and document results; no merge/deploy without user instruction.


### Task 8: Source-grounded polling efficiency
User explicitly requested this extension after approving Tasks 1–7.
- [x] Pin and inspect Codex open-source status/mailbox wait, process poll and MCP error handling.
- [x] RED/GREEN longer bounded subagent wait, timeout distinction, terminal/unknown guidance and repeated report/status deduplication.
- [x] RED/GREEN unchanged/failed Goal observations stop automatic empty continuation; meaningful changes reset stagnation.
- [x] RED/GREEN sanitized scoped unavailable MCP discovery and correct frontend parsing.
- [x] RED/GREEN foreground-only status refresh with network failure backoff; ordinary Goal reduced-motion clear.
- [x] Include all new behavior in final serial gates and isolated live proof.


### Task 9: Independent background work and completion reminders
User explicitly requested foreground-independent work and automatic task/conversation completion reminders.
- [x] Review official completion notification settings and pinned open-source terminal child/process watchers.
- [x] Add explicit foreground detach without cancellation; keep Stop independent.
- [x] Add dedicated start_background_task with independent owned session, deterministic admission identity, existing authorized chat and ARQ queue, bounded recovery and depth limit.
- [x] Preserve parent restrictions and revalidate roles/model/persona/team at execution; fence stale resumes before lifecycle writes.
- [x] Add user-scoped completion journal, cursor pagination, live/catch-up dedupe and approval wording; suppress premature Goal completion.
- [x] Verify outage reconciliation, whole integrated suites and actual separate-worker/API independence.

Local task execution proves foreground independence only. ARQ uses the existing durable queue and recovery path; process crash safety for arbitrary in-flight writes must remain conservative. Notification permission and actual OS delivery are separate from persisted completion and websocket/API proof.

### Task 10: Distributed ownership and local daemon verification
User explicitly added that all capabilities must support distributed deployment and the local daemon.
- [x] Audit shared Mongo/Redis state, replica ownership, authorization and recovery paths for all six capabilities and detached work.
- [x] RED/GREEN fence original and recovery background dispatches with one renewable execution owner; losing dispatches cannot mutate lifecycle or release another worker's slot.
- [x] Verify real separate workers and cross-process Goal/background ownership using the distributed configuration.
- [x] Verify local daemon connected to one API replica while authorized requests arrive through another; keep machine/user/session isolation.
- [x] Run full local daemon/sandbox E2E (47/47); fix macOS bundle metadata regression with observed RED/GREEN.
- [x] Finish any new callers/tests, then rerun final serial affected gates and document exact proof boundaries.


### Task 11: Background conversation UX
User explicitly requested additional source-grounded UX improvements.
- [x] Inspect pinned Codex inactive-thread approval/notification/side-context paths and current LambChat callers.
- [x] RED/GREEN accessible notification actions and run-specific navigation.
- [x] RED/GREEN one status mapping for sidebar/recent chats, including queued/starting/recovering and translated attention labels.
- [x] Confirm background detach with a return action through the existing notification surface; Stop remains separate.
- [x] Browser fixture review: five languages, light/dark, narrow/wide, keyboard open/dismiss, no horizontal overflow.
- [x] Final serial frontend tests/lint/build and focused backend resume regression.
