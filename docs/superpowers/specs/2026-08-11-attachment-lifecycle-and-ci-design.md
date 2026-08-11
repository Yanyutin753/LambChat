# Attachment Lifecycle and CI Repair Design

**Date:** 2026-08-11
**Status:** Approved

## Problem

Content-hash deduplication currently reuses one globally unique storage key. Draft attachment removal calls the delete API, while persisted reference counts are not incremented until after the user message is saved. An unreferenced duplicate can therefore be physically deleted before another draft submits it, leaving a missing object in conversation history. Hash lookup and deletion are also not owner-scoped.

The default-branch `Lint` workflow additionally fails because `ChatAppContent.tsx` is 1015 lines under the repository's line-counting script, exceeding the 1000-line limit.

## Safety invariants

- A user message must never be persisted with an attachment that was not atomically claimed by that user.
- Object cleanup and attachment claiming must be mutually exclusive.
- Hash deduplication, lookup, deletion, and cleanup must not cross user boundaries.
- Removing an attachment from a client draft must not immediately delete shared backing storage.
- Reference increments and session cleanup decrements must use the same per-message counting semantics.
- CI repair must preserve the 1000-line rule rather than weakening it.

## Backend design

`file_records` will migrate from a globally unique `hash` index to a unique compound `(uploaded_by, hash)` index. Startup will await this migration and fail closed if it cannot establish the ownership constraint. The compound index is created before the legacy unique hash index is removed.

Hash lookup and stale-record deletion will require `uploaded_by`. Unknown or foreign keys will return the same not-found response and will never trigger object deletion.

Before concurrency admission, the chat route will atomically claim each unique owned attachment key by incrementing its reference count only when it is not being deleted. Partial claims are rolled back. Queue rejection or failure before message persistence also releases the claim. Once the user message is persisted, the reference remains even if agent execution fails. Presenter receives an explicit already-claimed flag so references are never double-counted.

Draft and released objects use delayed cleanup. Records carry a cleanup deadline; DELETE schedules cleanup instead of deleting immediately. A cleaner atomically tombstones eligible zero-reference records before deleting storage. Claim excludes tombstoned records, so either claim wins and cleanup cannot proceed, or cleanup wins and submission fails before history is written.

Session cleanup will count a key once per user message and release the accumulated count, fixing repeated use of the same file in one session.

## Frontend design

All composer and scheduled-task draft removal paths will become local-only operations. Upload cancellation still aborts an in-flight request, but removing an uploaded attachment will not call the storage DELETE endpoint.

Invalid-attachment submission responses keep the draft content and attachment cards visible so the user can re-upload instead of silently losing input. The frontend extracts the stable `invalid_attachments` error code from the backend's structured `422` response and displays a localized, actionable error telling the user that an attachment is unavailable and must be removed or uploaded again. It must not expose the raw JSON error object or silently send the remaining text without the attachment.

## CI design

The cohesive external-navigation state and trace-to-run resolution effect will move from `ChatAppContent.tsx` into `useExternalNavigationTarget.ts`. This gives meaningful margin below 1000 lines and retains the existing line-size policy.

## Verification

Tests cover owner-scoped dedupe and index migration, atomic claims and rollback paths, delayed cleanup arbitration, per-message reference release counts, all frontend removal paths, structured invalid-attachment error extraction/localization, draft preservation, external-navigation hook behavior, and the exact CI line-count rule. Final verification runs relevant targeted suites followed by backend tests, frontend tests/build/lint, Ruff, MyPy, and the large-file check.
