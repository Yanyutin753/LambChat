# Workspace Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Preserve discoverable files across project reassignment, workspace migration, conflicts and environment recovery on cloud and local clients.
**Architecture:** Separate project membership, versioned current execution binding, migration history and persistent file snapshots. Commit a new location only after file verification; structured writes use atomic staging and version checks, not directory task queues.
**Tech Stack:** Existing Python/FastAPI/MongoDB/storage providers, daemon Python, React/Tauri and Git.
**Spec:** docs/superpowers/specs/2026-10-27-workspace-concurrency-lifecycle-design.md

## Current implementation and acceptance (2026-10-27)

User scope refinement: keep existing files and discoverable locations, permit environment rebuild, and do not add physical migration, independent backup infrastructure or peer-chat messaging. These are excluded from this release, not pending release gates.

This initial plan is retained for traceability; the simplified implementation in the spec supersedes its physical-migration and managed-worktree tasks. Unchecked items below are not completion claims.

- Implemented: metadata-only project reassignment; retained prior workspace bindings with owner checks and compare-and-set; version-checked structured local/cloud writes; staged upload commit; no blind mutation replay after unknown remote outcomes.
- Implemented: opt-in native Cube/Daytona persistent volume descriptors, verified reattachment and canonical runtime binding. Existing legacy roots remain untouched. E2B native volumes are not enabled.
- Verified locally: Python lint and full src mypy, 1,074 backend tests passed (one skipped), frontend lint/build and 155 focused frontend tests passed. Real daemon stress acceptance: 60/60 passed, including 501-file transfer, restart/interrupted-upload recovery and sustained concurrent execution.
- Verified on real Cube: pause/resume and destroyed-runtime replacement retain both session files. Cross-runtime FUSE flock is not coherent; only a single canonical application runtime may use the volume for guarded writes.
- Not implemented: physical cross-machine migration, managed worktree archival, peer-chat messaging, independent restic backups, or file-history restore UI. Retained location records are references, not proof that files were copied. Raw shell/external writes bypass structured-file guards.
- Real Cube bulk acceptance: 2,001 files / 35,610,432 bytes were all hash-verified after runtime replacement using the same persistent volume; recovery 7.29 seconds and end-to-end 31.52 seconds in one isolated sample, not a general benchmark. Test resources and temporary binding were cleaned.
- Release state: uncommitted local changes; persistent-volume feature defaults off, no production rollout performed.

## Global Constraints

- Current branch only; preserve other changes; no worktree or automatic Git commits/releases.
- All validation via python3 scripts/run_validation.py, one worker; lock busy is blocked, never wait/retry.
- No whole-directory task queues. No claims that shell/external processes obey file locks.
- Authorization, existing files and five locales preserved; old daemon capabilities explicitly distinguished.
- Cloud unavailable: keep source binding, persist recoverable status, no pretend-success or AI-invented locations.

## Review Focus

- Interrupted/empty uploads must preserve old bytes or commit a complete empty file (Task 1).
- Concurrent migration after binding changes must not overwrite current location (Task 2).
- Project reassignment during cloud downtime must leave file references resolvable (Task 3).
- Unknown remote command outcomes must not be blindly replayed (Task 4).
- Ignored/untracked files and cross-user access must survive archive safely or fail closed (Task 5).

### Task 1: Atomic file transfer and conflict protection

**Files:** client/lambchat_sandbox/fsops.py, daemon.py; src/infra/backend/local*.py; src/infra/sandbox/relay/dispatch.py; tests/client/test_fsops.py, test_daemon.py; corresponding backend/route tests.
**Interfaces:** StreamUploadWriter.write(bytes), commit(), close() (abort); file version produced by execution host and checked at commit. Existing framed META(size), DATA, EOF contract retained.
- [ ] Write failing tests for interrupted upload, empty replacement, truncated/invalid stream, changed destination.
- [ ] Run targeted pytest through validation wrapper; observe expected failures.
- [ ] Implement same-directory staging and explicit complete-stream commit; preserve originals on cancellation/errors and update all callers/fixtures.
- [ ] Extend structured read/write/edit/delete and browser uploads with version-aware atomic commits and history; scope cloud execution-host equivalent separately from local transport.
- [ ] Run affected tests, then retain diff for final shared verification.

### Task 2: Durable migration state and immutable current location

**Files:** src/infra/backend/workspace_selection.py; src/infra/session/storage.py; new src/infra/sandbox/workspace_migrations.py; tests/infra/test_workspace_migrations.py; src/api/routes/session_workspace.py.
**Interfaces:** Current workspace identity + location_revision separate from project; migration records carry owner/session/source/destination/expected_revision/manifest/state/idempotency key. Successful CAS of binding is the commit fact, recovery reconciles journal from it.
- [ ] Test duplicate request, stale revision, unavailable source, crash before/after switch, cross-user rejection.
- [ ] Observe failures, implement persistence and migration state transitions without deleting source.
- [ ] Connect explicit workspace changes to guarded migration; destination never silently replaces existing contents.
- [ ] Verify tests including retry and cancellation recovery.

### Task 3: File location resolution and project reassignment

**Files:** src/api/routes/session.py; src/infra/session/storage.py; src/infra/revealed_file/storage.py; sandbox file routes; Search/Team backend setup; corresponding route/agent tests.
**Interfaces:** Resolve stable workspace/file identity to current location or explicit unavailable status; inject current version into agent environment, invalidate stale observations.
- [ ] Test unclassified chat with files moved into/out of project, including sleeping cloud and local offline machine; old references still resolve without changing execution target.
- [ ] Observe failures; implement recoverable project file-index synchronization and authoritative location lookup.
- [ ] Add migration history/current location read endpoints with ownership checks and explicit unavailable reasons.
- [ ] Verify both local/cloud callers and existing sessions without new metadata.

### Task 4: Runtime lifecycle and peer coordination

**Files:** src/infra/sandbox/idle_pause.py, session_manager.py; backend setup; daemon cancellation/relay; src/infra/tool and agent message middleware; dedicated frontend tool item and locales.
**Interfaces:** Run pins workspace revision and actor session separately from selected folder; peer notifications are low-trust and never auto-start idle paid runs.
- [ ] Test local run does not keep cloud alive, approval/resume uses current location, late writes rejected, unknown outcome not replayed, same-user peer messages and cross-user denial.
- [ ] Implement lifecycle guards and bounded collaboration on existing message infrastructure.
- [ ] Verify cancellation actually stops owned execution before archive and preserves source on uncertainty.

### Task 5: Managed worktrees, snapshots, recovery and UI

**Files:** new workspace execution helpers alongside client/lambchat_sandbox/fsops.py; shared server workspace migration adapter; frontend workspace controls and five locales; native workspace commands; integration tests.
**Interfaces:** Local/cloud adapter prepares isolated Git worktree or ordinary directory; persistent manifest outside disposable environment; verify/restore never overwrite changed destination.
- [ ] Read DESIGN.md/PRODUCT.md and existing controls before UI changes.
- [ ] Test Git same-name parallel changes, ordinary files, untracked/ignored protection boundaries, restore after workspace deletion, offline source recovery, permission denial.
- [ ] Implement managed creation/archive/restore with snapshot-before-cleanup and shared protocol capabilities.
- [ ] Wire project/workspace selection, migration progress/error/retry and history/file discovery; no silent legacy migration.
- [ ] Verify tests and frontend states.

### Task 6: Final integration and real environments

- [ ] All caller/config/test edits complete; run focused suites, required lint/type/build serially with wrapper.
- [ ] Real daemon E2E + concurrency/failure scenarios using isolated test directories and desktop_dev account; preserve labelled results.
- [ ] Real cloud paused/resumed/migrated/restored validation, verify bytes of pre-existing test artifacts; report inaccessible environments as unverified.
- [ ] Fresh whole-diff review, fix serious findings with failing tests first.
- [ ] Report actual guarantees and remaining external-write/backup limitations; no deployment claimed.
