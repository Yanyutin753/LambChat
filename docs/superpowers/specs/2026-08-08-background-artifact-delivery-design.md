# Background Artifact Delivery Design

## Goal

Remove automatic artifact bookkeeping from the main Agent tool-call critical path without changing the visible artifact contract. Sandbox workspace snapshots, automatic file reveal/upload, and multi-file delivery should run as bounded background work. Before the terminal `done` event, the middleware gets one short, bounded opportunity to finish outstanding work so artifact events keep their existing ordering.

The user-visible priorities are:

1. `execute`, `write_file`, `edit_file`, and `upload_url_to_sandbox` return their real tool results without waiting for automatic artifact delivery.
2. Generated-file cards continue to appear before `done` whenever background work completes within the bounded final drain.
3. Snapshot, reveal, upload, or event-emission failures never fail the originating Agent tool call.
4. No background artifact event is emitted after `done`.

## Current Problem

`ArtifactDeliveryMiddleware.awrap_tool_call()` currently performs automatic work inline:

- `execute` waits for a workspace snapshot before the command, another snapshot after the command, and then automatic reveal/upload.
- `write_file`, `edit_file`, and `upload_url_to_sandbox` wait for automatic reveal/upload after the underlying tool already succeeded.
- Multiple staged artifacts are delivered with a serial `for` loop.
- `aafter_agent()` also reveals remaining artifacts serially.

These operations are convenience and presentation work, but their latency is added to the main Agent reasoning/tool loop.

## Scope

The change covers all automatic artifact paths owned by `ArtifactDeliveryMiddleware`:

- shell-created or shell-modified file detection for `execute`;
- direct paths returned or supplied by `write_file`, `edit_file`, and `upload_url_to_sandbox`;
- file URLs discovered in the final assistant state;
- delivery of multiple pending artifacts;
- task failure, cancellation, deduplication, and terminal draining.

Explicit `reveal_file` and `reveal_project` calls remain foreground operations. Their returned URL or project payload is the requested tool result and may be needed by the next model step. Correctness-sensitive transformations in other middleware are also out of scope.

## Chosen Architecture

Add a private, per-middleware background coordinator dedicated to artifact work. A coordinator belongs to one `ArtifactDeliveryMiddleware` instance, so main-Agent and subagent runs do not share limits, queues, mutable artifact state, or failure budgets.

The coordinator owns:

- a tracked set of `asyncio.Task` objects;
- a semaphore limiting reveal/upload concurrency to four operations per run;
- snapshot sequencing state;
- normalized-path delivery state used to coalesce duplicates;
- `schedule()` and bounded `drain()` lifecycle methods.

Tasks are never untracked fire-and-forget tasks. Every task consumes its exception in a done callback, removes itself from the tracked set, and logs failures with the artifact path or operation name. Cancellation is handled separately from ordinary failures.

## Data Flow

### Agent start and shell snapshots

`abefore_agent()` schedules an initial workspace baseline snapshot and returns immediately. This normally overlaps the first model call.

When `execute` starts, the middleware schedules a paired pre-command snapshot before invoking the real tool handler, but it does not await that snapshot in the wrapper. After the real handler returns successfully, it schedules a background pipeline that:

1. resolves the best available pre-command baseline;
2. captures the post-command workspace snapshot;
3. advances the rolling baseline;
4. computes up to the existing changed-file limit;
5. filters ignored and sensitive paths;
6. stages and delivers changed files.

Snapshot jobs are sequenced inside the coordinator to prevent multiple automatic scans from corrupting the rolling baseline. Shell-created artifact detection remains best effort, matching the current behavior when globbing fails or exceeds limits. Direct file tools and explicit reveal remain the reliable paths when an exact file must be delivered.

### Direct file tools

After a successful `write_file`, `edit_file`, or `upload_url_to_sandbox` result, the middleware derives the path synchronously, stages it, schedules background delivery, and immediately returns the original `ToolMessage`. Failed tool results schedule nothing.

### Multiple artifacts

Artifacts with different normalized paths may reveal concurrently up to the coordinator limit. Repeated staging of the same path is coalesced. A per-path generation marker prevents an older in-flight delivery from marking a newer version as revealed; if a path changes while it is being delivered, the newest generation is queued once more.

### Agent completion

`aafter_agent()` first stages file URLs found in assistant messages, then calls the coordinator's bounded drain. The drain waits only for already-started artifact work. It does not accept new work after closing begins.

The final drain timeout is three seconds. If it expires, remaining tasks are cancelled and gathered before `aafter_agent()` returns. This preserves the invariant that no artifact task can emit after the Agent's terminal `done` event. Completed artifact events retain their existing payload and presenter behavior.

## Failure and Backpressure Policy

- Snapshot failure: log at debug level, advance no invalid baseline, and do not affect the tool result.
- Reveal/upload/event failure: log with path context and keep the existing failed-artifact event behavior when a presenter is available.
- Concurrency: allow at most four reveal/upload operations per run so a command creating many files cannot saturate storage or sandbox APIs.
- Final-drain timeout: cancel and gather remaining work, log the number and operation names, and allow Agent completion.
- Task scheduling during close: reject and close the coroutine cleanly rather than leaking an un-awaited coroutine.
- No presenter: preserve existing reveal/file-library side effects; only presenter event emission is skipped.

## Compatibility

The following contracts do not change:

- original tool results and errors;
- artifact payload schema and `artifact:result` event name;
- ignored/sensitive path filtering;
- changed-file cap;
- explicit reveal behavior;
- automatic delivery descriptions and priorities;
- main-Agent and subagent middleware registration.

The only intended ordering change is that automatic artifact work may complete during a later Agent/model step instead of before the originating tool result is returned. All completed artifact events still precede terminal `done`.

## Test Strategy

Regression tests will prove the behavioral boundary, not implementation details:

1. A blocked reveal does not delay successful `write_file`, `edit_file`, or `upload_url_to_sandbox` tool results.
2. A blocked post-command snapshot does not delay a successful `execute` result.
3. Background snapshot completion still detects and delivers created and modified files.
4. Multiple changed files begin delivery concurrently within the configured limit.
5. Repeated staging of one path does not emit duplicate stale deliveries.
6. Failed direct tools and failed commands schedule no automatic delivery.
7. Snapshot and reveal exceptions do not propagate into the Agent tool call.
8. `aafter_agent()` drains completed work before returning.
9. Drain timeout cancels and gathers outstanding tasks, leaving no task that can emit after completion.
10. Explicit `reveal_file` and `reveal_project` remain foreground and continue marking paths as revealed.
11. Existing sensitive/ignored-path, payload, file-library, main-Agent, and subagent tests remain green.

Focused verification will run `tests/infra/agent/test_artifact_delivery_middleware.py`, followed by the related agent middleware tests and Ruff on changed Python files.

## Rollout Notes

The implementation must avoid touching the unrelated, already-dirty sandbox MCP removal work in the checkout. No configuration or frontend change is required. If the bounded final drain proves too short in production, its value can be promoted to configuration later; this change should begin with one conservative internal constant rather than expanding the settings surface prematurely.
