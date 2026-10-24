# Share file consent and owner image access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Restore the owner's generated images and let a share owner explicitly allow attachments and generated files.

**Architecture:** Reuse existing file ownership checks and revocable share-bound capabilities. Add one `allow_files` boolean to session/project share create, update, storage and responses; absent values default to false. Investigate the reported production session before changing owner authorization.

**Tech Stack:** FastAPI/Pydantic/MongoDB, React/TypeScript, existing Checkbox and five locales.

**Spec:** User confirmed one “允许访问附件和生成文件” switch, default off; own images fail inside the original chat.

## Global Constraints

- Current shared branch; preserve concurrent changes; no worktree, stash or branch switch.
- One validation process via `python3 scripts/run_validation.py`; no busy-lock retries or queued validation.
- No anonymous owner files, cross-owner grants, desktop capture sharing or stable-channel promotion.
- Share changes invalidate existing capabilities through the current share version check.
- New UI uses existing components and zh/en/ja/ko/ru translations.

## Review Focus

- Historical generated files without a current file record: prove original ownership, deny guessed foreign keys.
- Share switch off, including old records: no file capability; remove embedded application file tokens.
- Disable/delete a share: previously issued tokens fail immediately, all variants remain protected.
- Authenticated shares: the page remains login-gated; media retain existing short-lived bearer capability transport.
- Project partial shares, cancelled edits and failed saves: consent state and selected scope remain correct.

### Task 1: Diagnose and restore owner images

**Files:** `src/infra/upload/access.py`, `src/infra/upload/shared_files.py`, ownership helpers and targeted tests if confirmed necessary.

- [x] Read only the supplied production session's ownership evidence and current render/download path.
- [x] Add the smallest reproducer for the confirmed cause and run it RED through the validation wrapper.
- [x] Fix the shared authorization/render path once; retain foreign-owner, capture and deletion checks.
- [x] Run targeted GREEN including the relevant denial cases.

### Task 2: Persist and enforce explicit file consent

**Files:** `src/kernel/schemas/share.py`, `src/infra/share/storage.py`, `src/api/routes/share.py`, `src/infra/upload/shared_files.py`, `src/infra/upload/access.py`, share/upload tests.

- [x] Add failing tests for defaults, create/update/list round trips, disabled shares, revoked tokens and authenticated visibility.
- [x] Run RED, then add `allow_files: bool = False`; updates preserve it when absent.
- [x] Sanitize embedded application file tokens; only issue share capabilities when consent is true and ownership is verified.
- [x] Run targeted GREEN; synchronize existing explicit-consent fixtures.

### Task 3: Expose the switch and finish release

**Files:** `frontend/src/types/share.ts`, both existing share dialogs, their tests and five locale files.

- [x] Add behavior tests for default off, enable/create, existing-share edit/save and reset; run RED.
- [ ] Add the existing Checkbox with clear access/download description and busy/error behavior.
- [x] After all edits, run serial full gates and independent review; inspect narrow/light/dark UI.
- [ ] PR to develop, complete CI, staging real conversation/share/file checks, promote to main, deploy explicit immutable image.
- [ ] Tag the verified main merge as the next unused dev release; complete native builds, signatures and release regression. Keep stable latest unchanged.
