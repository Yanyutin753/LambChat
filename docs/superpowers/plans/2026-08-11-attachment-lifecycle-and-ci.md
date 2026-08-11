# Attachment Lifecycle and CI Repair Implementation Plan

**Goal:** Prevent deleted or foreign attachment keys from entering conversation history, isolate deduplication per user, safely reclaim abandoned files, and restore the default-branch Lint workflow.

## Tasks

1. Use red-green-refactor to implement strict owner-scoped `file_records` indexes, hash lookup/create-race handling, atomic claim/rollback primitives, and delayed tombstone cleanup.
2. Use red-green-refactor to integrate claim-before-admission into queued, direct, and arq chat submission, including rejection/error rollback and explicit no-double-claim propagation.
3. Use red-green-refactor to count attachment references once per message and release the full accumulated count when clearing a session.
4. Use red-green-refactor to make all frontend draft-removal paths local-only and preserve composer content on invalid-attachment responses.
5. Use red-green-refactor to extract external-navigation resolution into a tested hook and enforce the exact 1000-line CI budget.
6. Run targeted tests after every loop, complete cross-stack lint/type/build/test verification, push incremental commits to the draft PR, inspect Actions, and mark the PR ready when all required checks pass.
