# Clipboard Image Placeholder Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale zero-byte clipboard placeholders from appearing as attachments, recover embedded clipboard images when bytes are available, and reject empty attachment uploads at both client and server boundaries.

**Architecture:** Add a pure clipboard classifier shared by both paste implementations, keep generic per-file validation inside `useFileUpload`, and reject empty streams in the backend spool boundary. Paste-specific recovery remains separate from generic upload validation so file selection and drag-and-drop retain their current semantics.

**Tech Stack:** React 19, TypeScript, Lexical, Vitest, Testing Library, FastAPI, pytest.

## Global Constraints

- Work in the current checkout and preserve unrelated `markdownCodeFences` changes.
- Follow red-green-refactor for every production behavior change.
- Do not fetch arbitrary `http(s)` or `blob:` image URLs from clipboard HTML.
- Update all five existing locales: English, Chinese, Japanese, Korean, and Russian.
- Keep focused verification distinct from full frontend or backend suite results.

---

### Task 1: Clipboard payload classification

**Files:**
- Create: `frontend/src/components/chat/clipboardFiles.ts`
- Test: `frontend/src/components/chat/__tests__/clipboardFiles.test.ts`

**Interfaces:**
- Produces: `classifyClipboardFiles(data: Pick<DataTransfer, "files" | "getData">): ClipboardFileResult`
- Produces: `ClipboardFileResult = { kind: "files"; files: File[] } | { kind: "invalid-image" } | { kind: "none" }`

- [ ] **Step 1: Write failing classifier tests**

Cover literal fixtures for a non-empty native image, a zero-byte `.bin` placeholder, a placeholder plus embedded PNG data URL, remote and blob image markup, and ordinary text with no image.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts`

Expected: FAIL because `clipboardFiles.ts` does not exist.

- [ ] **Step 3: Implement minimal classifier**

Parse HTML with `DOMParser`, accept non-empty native files first, decode only `data:image/(png|jpeg|gif|webp);base64,...`, name recovered files `pasted-image.<extension>`, and return `invalid-image` for unrecoverable image markup or zero-byte file placeholders.

- [ ] **Step 4: Re-run tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts`

Expected: all classifier tests pass.

### Task 2: Rich and legacy paste integration

**Files:**
- Modify: `frontend/src/components/chat/richComposer/FilePastePlugin.tsx`
- Modify: `frontend/src/components/chat/richComposer/RichChatComposer.tsx`
- Modify: `frontend/src/components/chat/ChatInput.tsx`
- Modify: `frontend/src/hooks/usePasteHandler.tsx`
- Test: `frontend/src/components/chat/__tests__/clipboardPasteBehavior.test.tsx`
- Test: `frontend/src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx`

**Interfaces:**
- `FilePasteOptions.onInvalidImage(): void`
- `UsePasteHandlerOptions.onInvalidImagePaste?: () => void`

- [ ] **Step 1: Write failing paste behavior tests**

Prove that a zero-byte placeholder is consumed without calling `onFiles` or inserting text, a valid embedded data image reaches `onFiles`, and ordinary long text still follows the existing long-text conversion contract.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardPasteBehavior.test.tsx src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx`

Expected: invalid placeholders currently call `onFiles`, and HTML images are not recovered.

- [ ] **Step 3: Implement minimal integration**

Use `classifyClipboardFiles` in both paste paths. Consume `invalid-image`, invoke the supplied callback once, upload recovered files, and allow only `none` to continue into HTML/text or long-text handling. Wire the callback in `ChatInput` to the localized unavailable-image toast.

- [ ] **Step 4: Re-run tests and verify GREEN**

Run the same focused Vitest command and require all tests to pass.

### Task 3: Shared client-side empty-file validation

**Files:**
- Modify: `frontend/src/hooks/useFileUpload.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Test: `frontend/src/hooks/__tests__/useFileUpload.test.tsx`

**Interfaces:**
- Produces: `validateUploadFile(file: File, maxSizeMB?: number): "empty" | "too-large" | null`
- Existing `uploadFile` and `uploadFiles` call this guard before creating temporary attachments.

- [ ] **Step 1: Write failing upload validation tests**

Prove that zero-byte files create no attachment and start no hash/upload work, while a mixed batch skips the empty file and retains the valid file. Assert the consumer-visible toast text rather than private implementation calls.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/useFileUpload.test.tsx`

Expected: a zero-byte file currently creates a temporary attachment.

- [ ] **Step 3: Implement minimal validation and locale messages**

Guard both `uploadFile` and each member of `uploadFiles` before compression or temporary state. Add `fileUpload.emptyFile` and `fileUpload.clipboardImageUnavailable` to all locales.

- [ ] **Step 4: Re-run tests and verify GREEN**

Run the focused hook tests and the paste tests from Task 2.

### Task 4: Backend empty-stream rejection

**Files:**
- Modify: `src/api/routes/upload.py`
- Modify: `tests/api/routes/test_upload_memory_limits.py`

**Interfaces:**
- `_spool_upload_file_limited(...)` raises `HTTPException(status_code=400, detail="File is empty")` when no bytes are read.

- [ ] **Step 1: Write failing backend test**

Add an async upload double that returns `b""` immediately and assert the exact stable status/detail plus no usable spool result.

- [ ] **Step 2: Run test and verify RED**

Run: `uv run pytest tests/api/routes/test_upload_memory_limits.py -q`

Expected: the helper currently returns a zero-sized spool instead of raising.

- [ ] **Step 3: Implement minimal backend guard**

After the bounded read loop and before returning the spool, close it and raise the specified HTTP 400 when `total_size == 0`.

- [ ] **Step 4: Re-run test and verify GREEN**

Run the same pytest file and require all tests to pass.

### Task 5: Integrated verification

**Files:**
- Verify all files changed by Tasks 1-4.

- [ ] **Step 1: Run focused frontend tests**

Run all new and directly affected paste/upload Vitest files.

- [ ] **Step 2: Run relevant backend route tests**

Run: `uv run pytest tests/api/routes/test_upload_memory_limits.py tests/api/routes/test_upload_owner_scope.py tests/api/routes/test_upload_lifecycle.py -q`

- [ ] **Step 3: Run frontend static and production checks**

Run: `cd frontend && pnpm run lint && pnpm run build`

- [ ] **Step 4: Run repository backend checks proportional to the change**

Run: `uv run ruff check src/api/routes/upload.py tests/api/routes/test_upload_memory_limits.py` and `uv run mypy src/api/routes/upload.py`.

- [ ] **Step 5: Inspect final diff and working tree**

Confirm only the clipboard repair files and pre-existing unrelated Markdown fence files are changed. Do not stage, revert, or commit the unrelated files.
