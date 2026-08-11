# Attachment Lifecycle and CI Repair Implementation Plan

**Goal:** Prevent deleted or foreign attachment keys from entering conversation history, isolate deduplication per user, safely reclaim abandoned files, and restore the default-branch Lint workflow.

## Tasks

1. Add failing storage tests for owner-scoped hash lookup, strict compound-index migration, atomic attachment claims, rollback, tombstone cleanup, and non-negative counted release.
2. Implement strict `file_records` indexes and register their initialization in application startup.
3. Add owner-scoped lookup/create-race handling and delayed deletion/cleanup primitives.
4. Add failing chat-route tests for missing/foreign/deleting attachments, partial claim rollback, queue rejection, queued/direct/arq persistence, and no double claim.
5. Implement the claim-to-persist lifecycle and explicit claimed-reference propagation.
6. Add failing session cleanup tests for repeated keys across messages, then implement counted releases.
7. Add failing frontend tests proving all draft-removal paths avoid server DELETE, then remove those calls and preserve drafts on attachment validation errors.
8. Add failing external-navigation hook and exact line-budget tests, extract the hook, and run the repository large-file check.
9. Run targeted tests after each red/green loop, then complete cross-stack lint, type, build, and test verification.
10. Push incremental commits to the draft PR, inspect Actions, fix any remaining failures, and mark the PR ready when all required checks pass.
