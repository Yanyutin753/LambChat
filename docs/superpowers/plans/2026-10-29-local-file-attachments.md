# Local File Attachments Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this session. Steps use checkbox syntax.

**Goal:** Desktop file selection/drop references original paths locally and uploads for cloud execution.
**Architecture:** Native receipts authorize frontend reads; a machine-bound localFile attachment extends the existing wire contract. Reuse absolute-path sandbox tools and existing cloud uploads.
**Tech Stack:** Tauri/Rust, React/TypeScript, FastAPI/Pydantic.
**Spec:** docs/superpowers/specs/2026-10-29-local-file-attachments-design.md

## Global Constraints
- Direct original-file references; no copies, added dependencies or daemon protocol changes.
- Web/mobile remain cloud uploads; five locales; preserve current branch and existing edits.
- All local validation through scripts/run_validation.py, one worker, no busy-lock retries.

## Review Focus
- Cloud/different-machine submission must never interpret a client-local path on another computer.
- Native reads accept only selection/drop receipts, reject path substitution and changing files.
- Switching environment, removing a card, unmounting or changing account cannot resurrect attachments.
- History, queued follow-ups and steer retain path metadata; local card clicks never request upload URLs.
- A failed promotion remains visible and retryable; no missing attachment is silently sent.

### Task 1: Wire contract and model context
Files: src/kernel/schemas/agent.py, src/infra/upload/local_attachments.py, src/api/routes/chat.py, src/agents/core/node_utils.py; tests/kernel and tests/infra/upload.
- [x] Add failing tests for local schema, cloud compatibility, machine rejection and path-only model context.
- [x] Run focused pytest under shared lock and observe failures.
- [x] Add LocalFileReference and validate_local_attachments, preserve existing cloud contracts and claim logic.
- [x] Run focused tests.

### Task 2: Native selection/drop receipts
Files: frontend/src-tauri/src/commands/attachments.rs, commands/mod.rs, lib.rs, permissions and capabilities; frontend/src/services/tauri/desktopFiles.ts.
- [x] Test receipt path validation, bounded reads and changed-file rejection before implementation.
- [x] Add native picker, drop event, metadata/read-chunk/reveal commands; store receipt metadata only.
- [x] Verify commands and platform-neutral Rust logic under shared lock.

### Task 3: Composer integration
Files: frontend/src/hooks/useDesktopAttachments.ts, ChatInput.tsx, ChatInputToolbar.tsx, AttachmentCard.tsx, types/upload.ts, attachmentValidation.ts, eventProcessor.ts and locales.
- [x] Add failing tests for no-upload local selection, cloud promotion, environment/account races and wire round-trip.
- [x] Integrate native selection/drop with current attachment cards and useFileUpload replacement.
- [x] Preserve local reference fields across history and queued messages; reveal original files on card click.
- [x] Run focused frontend tests.

### Task 4: Verification and review
- [x] Finish all callers/config/docs then serially run relevant backend/frontend tests, lint, typecheck/build and native checks.
- [x] Review the complete diff for the five failure modes above; report actual verification and limits.
- [x] Keep this new change separate from immutable dev.3; do not claim it deployed until a later release.

## Verification ledger
- Wire contract: focused RED → GREEN; local paths require exact owner/machine and sandbox support; legacy cloud schema retained.
- Native: receipt traversal and changed-file tests RED → GREEN. Picker/drop receipts contain metadata only; read chunks capped at 1 MiB.
- Composer: metadata-only local selection, cloud promotion, card deletion and cross-context drop tests RED → GREEN. Original paths survive failed cloud promotion and history restoration.
- Final: fixed unresolved-environment uploads — delayed catalog / machine resolution tests RED→GREEN; environment-pending selection also rejected.
- Final: fixed media category omissions — HEIC/HEIF/AVIF/FLAC/MKV tests RED→GREEN. Ambiguous TypeScript `.ts` remains a document (RED→GREEN).
- Verification before final classification adjustment: 6,162 frontend tests, 248 backend tests, two native tests, frontend build/typecheck/lint and scoped mypy passed. Lint retains two existing unused-variable warnings.
- DESIGN checklist: existing cards/buttons, tokens, focus/disabled/error states and five locales reused; no new animation or layout system. Impeccable is not installed; source checklist performed. Native OS picker/drop/reveal and physical devices remain untested.
- Publication: dev.3 is immutable; this feature targets a separate dev.4 with incremented Android/iOS build numbers. Final rerun and real daemon acceptance recorded with release evidence outside the repository.

- Final rerun: 6,164/6,164 frontend tests, frontend typecheck/lint/build passed. The unchanged backend/native snapshot retains 248/248 backend tests, 2/2 native receipt tests and scoped mypy success.
- Real daemon: 62/62 checks passed, including outside-workspace original read/write, recovery and sustained 20-way concurrency (1,092 calls). Original-path sample read took 0.046 seconds locally; this is not a user-device/network SLA. Temporary database, user and daemon were removed.
- Acceptance used an isolated MongoDB database and an initially empty Redis database after detecting incompatible local logging configuration and default test-account permissions; only the temporary test account received the setup role. No project/production configuration was changed.
- dev.4 version preflight passed for all platform version files.
