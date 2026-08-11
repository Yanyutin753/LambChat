# Attachment Lifecycle and CI Repair Implementation Plan

**Goal:** Prevent deleted or foreign attachment keys from entering conversation history, isolate deduplication per user, safely reclaim abandoned files, and restore the default-branch Lint workflow.

## Task 1: Owner-scoped attachment storage

Use red-green-refactor to implement strict owner-scoped `file_records` indexes, hash lookup/create-race handling, atomic claim/rollback primitives, and delayed tombstone cleanup. Create the `(uploaded_by, hash)` unique index before removing the legacy globally unique hash index; startup must await the migration and fail closed. Unknown or foreign keys must never cause storage deletion.

## Task 2: Claim-before-persist chat lifecycle

Use red-green-refactor to integrate claim-before-admission into queued, direct, and arq chat submission, including queue rejection and pre-persistence error rollback. Propagate an explicit already-claimed flag so Presenter never increments the same references twice. Invalid attachments must return a non-leaking 422 before any user-message event is persisted.

## Task 3: Counted session reference release

Use red-green-refactor to count each attachment key once per user message and release the full accumulated count when clearing a session. Repeated keys within one message count once; the same key used in multiple messages counts once per message; counts must never become negative.

## Task 4: Local-only frontend draft removal

Use red-green-refactor to make every chat, long-text, rich-composer, and scheduled-task draft-removal path local-only. Upload cancellation may abort an in-flight request, but removal of an uploaded draft attachment must not call server DELETE. Preserve composer content and attachments when the backend reports invalid attachments.

## Task 5: Restore the CI line budget

Use red-green-refactor to extract external-navigation target derivation and trace-to-run resolution from `ChatAppContent.tsx` into a tested `useExternalNavigationTarget` hook. Add a source test using the same newline-counting rule as CI and keep `ChatAppContent.tsx` at or below 1000 lines with meaningful margin.

## Task 6: Full verification and PR readiness

Run targeted tests after every loop, then complete cross-stack Ruff, MyPy, backend tests, frontend tests, lint, build, and large-file verification. Push incremental commits to Draft PR #209, inspect its GitHub Actions checks, fix remaining failures, and mark the PR ready only when required checks pass.
