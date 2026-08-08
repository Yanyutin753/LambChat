# Deepagents v0.7 Migration Design

## Goal

Migrate LambChat from `deepagents` 0.6.x to the latest 0.7 release, currently 0.7.5, while preserving todo planning, tenant-isolated storage, sandbox file operations, and existing agent event behavior.

## Scope

The migration covers:

- pinning `deepagents>=0.7.5,<0.8` and refreshing the lockfile;
- restoring `TodoListMiddleware` explicitly for the main fast, search, and team agents and their configured subagents;
- replacing runtime backend factory callables with concrete `BackendProtocol` instances;
- adopting the v0.7 `ls`, `glob`, `grep`, and `ReadResult` contracts in LambChat's custom backends and backend consumers;
- updating tests and parsing assumptions for `No files found` and the v0.7 read-file line-number format;
- identifying integration behavior that cannot be verified without live E2B, Daytona, CubeSandbox, or persistent-store services.

The migration does not add LambChat-specific agent capabilities, redesign prompts, change tenant namespace semantics, or provide continued runtime support for deepagents 0.6.x. Deepagents 0.7 itself adds a built-in `delete` filesystem tool; LambChat will adopt it only with the same workflow path scoping and structured-result guarantees as the other file operations.

## Dependency Policy

`pyproject.toml` will require `deepagents>=0.7.5,<0.8`. The upper bound prevents a future 0.8 breaking release from entering routine lockfile refreshes. `uv.lock` will be regenerated with `uv`.

`deepagents-backends` remains at its current compatible constraint unless dependency resolution or tests demonstrate that a change is required. Its latest published release is 0.2.0 and declares `deepagents>=0.5.2`.

## Todo Planning Preservation

LambChat consumes `write_todos` events in `src/infra/agent/events/tool_events.py`, exposes todo updates through the presenter, and documents todo planning in agent prompts. Deepagents 0.7 no longer installs `TodoListMiddleware` by default, so LambChat must install it explicitly from `langchain.agents.middleware`.

Each production `create_deep_agent` call for the fast, search, and team agents will receive one `TodoListMiddleware` in its caller middleware list. Each custom subagent middleware list will also receive one instance so subagent behavior remains equivalent to the old default. The middleware will not be added to the memory compaction agent because that graph neither presents todo events nor asks the model to plan with `write_todos`.

Tests will verify the middleware is passed from the correct import location, appears exactly once in each relevant stack, and keeps the `todos` state channel available.

## Concrete Backend Construction

The functions in `src/infra/backend/deepagent.py` currently return callables that are immediately invoked by agent nodes. They will instead construct and return concrete `CompositeBackend` instances:

- the in-memory backend uses a concrete `StateBackend` default;
- the persistent backend uses a concrete `StoreBackend` wrapped by `WorkflowScopedBackend`;
- the sandbox backend uses the provided sandbox instance directly.

Every `StoreBackend` will have an explicit namespace callable. Existing namespace meanings remain unchanged:

- memories: `(assistant_id, "memories")`;
- workflow files: `(assistant_id, "workflow", workflow_session_id)`.

Skills continue to route through `SkillsStoreBackend`, and sandbox composites continue to set `artifacts_root` to the sandbox working directory. Agent node variables, imports, tests, and backend lookup comments will be renamed from “factory” to “backend” where they refer to a concrete object.

## Backend Protocol Migration

LambChat will use the v0.7 structured operations directly:

- `ls` and `als` return `LsResult`;
- `glob` and `aglob` return `GlobResult`;
- `grep` and `agrep` return `GrepResult`, accept keyword-only `max_count`, and preserve the `truncated` flag;
- `read` and `aread` return upstream `ReadResult` with raw file content and valid pagination metadata.
- `delete` and `adelete` return `DeleteResult` when the selected backend supports deletion.

Removed helper APIs such as `ls_info`, `als_info`, `glob_info`, `aglob_info`, `grep_raw`, and `agrep_raw` will no longer be used as public backend contracts. Custom backends may keep private helper methods for implementation reuse, but all cross-component calls will use the v0.7 methods.

`WorkflowScopedBackend` will unwrap a structured result, remap successful paths into its workflow prefix, and return a new structured result while preserving errors and truncation. It will pass `max_count` through to grep calls. Its `delete` and `adelete` implementations will strip the public workflow prefix before delegating and will prefix only the successful returned path, ensuring the v0.7 delete tool cannot escape the session-scoped store namespace through this wrapper.

`SkillsStoreBackend`, `E2BBackend`, `DaytonaBackend`, and `CubeSandboxBackend` will return v0.7 result objects directly. E2B and Daytona timeout behavior will move into their `grep`/`agrep` implementations so the safety limit is not lost when `grep_raw` disappears. Artifact-delivery and project/file tools will consume `result.entries` or `result.matches` and surface `result.error` rather than probing removed helpers.

## ReadResult and Tool Output Boundaries

`src/infra/backend/protocol_compat.py` will stop constructing a string-like or extended `ReadResult`. It will re-export the v0.7 protocol types and retain only LambChat-specific helpers that are still necessary, such as extended upload/download error casting and a raw-content-to-string helper.

Backends will no longer call `format_content_with_line_numbers` or pass `rendered_content`. For text reads they will return the raw requested window plus consistent `start_line`, `end_line`, `next_offset`, and `total_lines` values. Deepagents filesystem middleware remains responsible for model-facing line numbering and pagination notices.

At the tool boundary, empty `ls` and `glob` results must render as `No files found`. LambChat code will not parse this output as a Python list. Tests that exercise backend methods continue to assert structured empty lists, while tests that exercise deepagents tools assert the model-facing string.

Any logic that recognizes numbered read rows will be updated to the v0.7 two-space separator and variable-width marker format rather than a fixed-width `cat -n` gutter. If no LambChat parser depends on the old gutter, the audit result will be recorded without adding unnecessary compatibility code.

## Error Handling

Structured backend errors remain errors in `LsResult`, `GlobResult`, `GrepResult`, `ReadResult`, and `DeleteResult`; they are not converted into empty results. Path remapping occurs only for successful entries, matches, or deleted paths. Partial grep/glob results preserve `truncated=True`.

Invalid read pagination combinations will be prevented at the backend boundary so upstream `ReadResult.__post_init__` validation cannot fail during agent execution. Binary content retains its existing encoding behavior.

## Testing Strategy

Implementation follows red-green-refactor cycles:

1. Dependency and agent-construction tests fail until the v0.7 constraint and explicit todo middleware are present.
2. Backend-construction tests fail until creators return concrete instances with explicit namespaces.
3. Protocol tests fail on removed helper calls, missing `max_count`, lost truncation, invalid `ReadResult` data, or incorrectly scoped deletion.
4. Tool-boundary tests fail until empty list/glob output is `No files found` and read output matches v0.7 formatting.
5. Existing E2B, Daytona, CubeSandbox, skills-store, artifact-delivery, reveal-project, transfer-file, and agent-node tests provide regression coverage.

Verification will include focused pytest suites, Ruff on changed Python files, Mypy or the repository typecheck target where practical, dependency consistency checks, and a broader pytest run. Failures caused solely by unavailable external services or credentials will be separated from code failures.

## Manual Review and Deployment Notes

The following require manual or environment-backed verification after the code migration:

- real E2B and Daytona command execution, globbing, grep timeout, and file pagination;
- CubeSandbox SDK response shapes against a live sandbox;
- persistent `StoreBackend` reads and writes against the configured LangGraph store;
- deployed sandbox templates and snapshots, which are not rebuilt by a Python dependency update;
- any third-party behavior in `deepagents-backends` not covered by LambChat's local tests.

These items will be reported as manual review rather than represented as locally verified.
