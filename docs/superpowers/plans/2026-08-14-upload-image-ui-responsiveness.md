# Upload Image UI Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move expensive image preparation off the UI thread where supported, preserve uploads on older browsers, reduce upload-progress rerenders, and represent server-side processing accurately.

**Architecture:** Dedicated Vite workers perform image compression and embedded clipboard-image decoding. The existing upload hook owns a bounded compatibility fallback and a per-upload progress controller that emits at most once per 100ms, while `MessageAttachment.uploadStage` drives explicit preparing, uploading, and processing labels. Existing backend upload, owner-scoped dedupe, attachment lifecycle, and top-level attachment ownership remain unchanged.

**Tech Stack:** React 19, TypeScript, Vite module workers, Web Worker APIs, OffscreenCanvas, Vitest, Testing Library, i18next.

## Global Constraints

- Do not add a third-party image compression dependency.
- Do not modify backend object storage, file records, upload limits, or attachment lifecycle code.
- Preserve zero-byte clipboard rejection and never fetch remote `<img>` URLs.
- Update all new user-visible copy in `en`, `zh`, `ja`, `ko`, and `ru` locales.
- Preserve unrelated workspace changes; do not commit or push without explicit authorization.
- Use fake timers for progress timing tests and verify every behavior through a RED then GREEN cycle.

## File Structure

- Create `frontend/src/workers/imageCompressionWorker.ts`: worker-only bitmap decode, OffscreenCanvas resize, and bounded image encoding.
- Modify `frontend/src/utils/imageCompression.ts`: worker client, AbortSignal lifecycle, original-file and bounded main-thread fallbacks.
- Create `frontend/src/utils/__tests__/imageCompression.test.ts`: worker path, unsupported path, abort, and fallback behavior.
- Create `frontend/src/workers/clipboardImageWorker.ts`: decode only prevalidated inline data-image URLs into Blob data.
- Modify `frontend/src/components/chat/clipboardFiles.ts`: synchronous classification without synchronous Base64 byte conversion, plus asynchronous decode client.
- Modify `frontend/src/components/chat/richComposer/FilePastePlugin.tsx`: consume embedded-image pastes immediately and upload after asynchronous decode.
- Modify clipboard and paste workflow tests under `frontend/src/components/chat/**/__tests__/`.
- Create `frontend/src/hooks/uploadProgress.ts`: isolated throttled upload-stage controller.
- Create `frontend/src/hooks/__tests__/uploadProgress.test.ts`: deterministic fake-timer tests.
- Modify `frontend/src/types/upload.ts`: add client-only `UploadStage` and `uploadStage`.
- Modify `frontend/src/hooks/useFileUpload.ts`: immediate preparing state, bounded image fallback, hash-worker degradation, progress-stage integration, and cleanup.
- Modify `frontend/src/hooks/__tests__/useFileUpload.test.tsx`: hook lifecycle and progress-stage regressions.
- Modify `frontend/src/components/common/AttachmentCard.tsx`: stage-aware labels.
- Create `frontend/src/components/common/__tests__/AttachmentCardUploadStage.test.tsx`: stage presentation coverage.
- Modify five `frontend/src/i18n/locales/*.json` files with `preparing` and `serverProcessing` copy.

---

### Task 1: Worker-Based Image Compression With Safe Fallback

**Files:**
- Create: `frontend/src/workers/imageCompressionWorker.ts`
- Modify: `frontend/src/utils/imageCompression.ts`
- Create: `frontend/src/utils/__tests__/imageCompression.test.ts`

**Interfaces:**
- Produces: `compressImageFile(file: File, options?: CompressOptions): Promise<File>` where `CompressOptions` retains `maxDimension`, `targetSizeKB`, and `skipBelowKB`, and adds `signal?: AbortSignal` plus `fallback?: "original" | "main-thread"`.
- Produces: an internal worker response union `{ ok: true; blob: Blob; mimeType: string; extension: string } | { ok: false; code: "unsupported" | "failed"; message: string }`.
- Consumes: no new dependency; Vite resolves `new URL("../workers/imageCompressionWorker.ts", import.meta.url)`.

- [ ] **Step 1: Write failing worker-client tests**

Create jsdom tests with a fake Worker that records the posted File and returns a smaller Blob. Assert that the returned File preserves the base name, uses the worker MIME type, terminates the worker, and never calls `document.createElement("canvas")`.

```ts
test("compresses supported images in a worker without creating a DOM canvas", async () => {
  vi.stubGlobal("Worker", SuccessfulCompressionWorker);
  const createElement = vi.spyOn(document, "createElement");
  const input = new File([new Uint8Array(300 * 1024)], "photo.webp", {
    type: "image/webp",
  });

  const output = await compressImageFile(input);

  expect(output.name).toBe("photo.jpg");
  expect(output.type).toBe("image/jpeg");
  expect(SuccessfulCompressionWorker.terminations).toBe(1);
  expect(createElement).not.toHaveBeenCalledWith("canvas");
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/utils/__tests__/imageCompression.test.ts`

Expected: FAIL because the current implementation creates a DOM canvas and has no worker response handling.

- [ ] **Step 3: Implement the worker compression path**

Implement `imageCompressionWorker.ts` using `createImageBitmap`, `OffscreenCanvas`, and `convertToBlob`. Preserve PNG; convert other supported raster formats to JPEG. Replace the current linear quality loop with a bounded binary search of at most four encodes between `0.2` and `0.85`, retaining the smallest candidate at or below 1 MiB and otherwise the smallest candidate produced.

In `imageCompression.ts`, retain the existing skip rules for files below 200 KiB, GIF, and SVG. Start one module Worker per compression, attach `message`, `error`, and AbortSignal listeners, and always terminate and detach listeners before resolving or rejecting.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/utils/__tests__/imageCompression.test.ts`

Expected: PASS with no unhandled worker or jsdom errors.

- [ ] **Step 5: Add failing fallback and abort tests**

Cover these independent behaviors:

```ts
test("returns the original image when worker compression is unsupported", async () => {
  vi.stubGlobal("Worker", UnsupportedCompressionWorker);
  const input = imageFile(300 * 1024);
  await expect(compressImageFile(input, { fallback: "original" })).resolves.toBe(input);
});

test("uses the bounded main-thread fallback only when explicitly requested", async () => {
  vi.stubGlobal("Worker", UnsupportedCompressionWorker);
  const input = imageFile(300 * 1024);
  const output = await compressImageFile(input, { fallback: "main-thread" });
  expect(output.size).toBeLessThan(input.size);
});

test("aborting compression terminates the worker and rejects with AbortError", async () => {
  const controller = new AbortController();
  const promise = compressImageFile(imageFile(300 * 1024), { signal: controller.signal });
  controller.abort();
  await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  expect(PendingCompressionWorker.terminations).toBe(1);
});
```

- [ ] **Step 6: Run fallback tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/utils/__tests__/imageCompression.test.ts`

Expected: FAIL because fallback selection and AbortSignal are not implemented yet.

- [ ] **Step 7: Implement original, main-thread, and abort fallbacks**

Extract the existing DOM Canvas algorithm into a private `compressImageOnMainThread`. Invoke it only for `fallback: "main-thread"`; otherwise return the original File when the worker reports unsupported/failed or Worker construction throws. Abort must never enter a fallback.

- [ ] **Step 8: Run Task 1 tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/utils/__tests__/imageCompression.test.ts`

Expected: all Task 1 tests pass.

---

### Task 2: Asynchronous Embedded Clipboard Image Decoding

**Files:**
- Create: `frontend/src/workers/clipboardImageWorker.ts`
- Modify: `frontend/src/components/chat/clipboardFiles.ts`
- Modify: `frontend/src/components/chat/richComposer/FilePastePlugin.tsx`
- Modify: `frontend/src/components/chat/__tests__/clipboardFiles.test.ts`
- Modify: `frontend/src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`

**Interfaces:**
- Produces: clipboard result union member `{ kind: "embedded-image"; source: string; mimeType: "image/png" | "image/jpeg" | "image/gif" | "image/webp" }`.
- Produces: `decodeEmbeddedClipboardImage(source: string, mimeType: EmbeddedImageMimeType, signal?: AbortSignal): Promise<File>`.
- Consumes: `FilePasteOptions.onFiles` and `FilePasteOptions.onInvalidImage` without changing their public signatures.

- [ ] **Step 1: Change the clipboard unit test to require deferred decoding**

Replace the existing synchronous recovered-file assertion with:

```ts
test("classifies an embedded image without decoding bytes synchronously", () => {
  const atobSpy = vi.spyOn(globalThis, "atob");
  const result = classifyClipboardFiles(
    clipboardData({ html: `<img src="${PNG_DATA_URL}">` }),
  );

  expect(result).toEqual({
    kind: "embedded-image",
    source: PNG_DATA_URL,
    mimeType: "image/png",
  });
  expect(atobSpy).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the clipboard test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts`

Expected: FAIL because classification currently calls `atob` and returns `kind: "files"`.

- [ ] **Step 3: Implement metadata-only classification**

Change the embedded-data regex to return only the validated full source and MIME type. Keep pure-string HTML scanning, non-empty native File preference, zero-byte invalidation, and remote/blob URL rejection unchanged.

- [ ] **Step 4: Run the clipboard test and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts`

Expected: all clipboard classification tests pass.

- [ ] **Step 5: Add failing asynchronous decoder and paste workflow tests**

Add a fake clipboard worker test proving `decodeEmbeddedClipboardImage` returns `pasted-image.png` and terminates its worker. Add a no-Worker test whose stubbed `fetch(PNG_DATA_URL)` returns a PNG Blob. Update the rich composer workflow test to use `waitFor` and assert the paste event is prevented immediately but `onFiles` is called only after decode resolves. Add a rejection test asserting `onInvalidImage` fires and no text fallback runs.

- [ ] **Step 6: Run decoder and workflow tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`

Expected: FAIL because the decoder, worker, and embedded-image branch do not exist.

- [ ] **Step 7: Implement worker decode and local data-URL fallback**

The worker must call `fetch(source).then(response => response.blob())` only after the main thread has validated the source as an allowed inline data-image URL. The main-thread fallback uses the same local data-URL conversion. Validate that the returned Blob is non-empty and has the expected MIME type before constructing the File. Never call fetch for `http:`, `https:`, or `blob:` sources.

In `FilePastePlugin`, call `event.preventDefault()` immediately for `embedded-image`, then asynchronously decode. On success, validate count 1 and forward `[file]`; on failure call `onInvalidImage`. Track cancellation during effect cleanup so a late decode cannot call stale options.

- [ ] **Step 8: Run Task 2 tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/chat/__tests__/clipboardFiles.test.ts src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`

Expected: all Task 2 tests pass.

---

### Task 3: Throttled Upload Progress and Explicit Processing Stage

**Files:**
- Create: `frontend/src/hooks/uploadProgress.ts`
- Create: `frontend/src/hooks/__tests__/uploadProgress.test.ts`
- Modify: `frontend/src/types/upload.ts`
- Modify: `frontend/src/hooks/useFileUpload.ts`
- Modify: `frontend/src/hooks/__tests__/useFileUpload.test.tsx`

**Interfaces:**
- Produces: `export type UploadStage = "preparing" | "uploading" | "processing"` and optional `MessageAttachment.uploadStage?: UploadStage`.
- Produces: `createUploadProgressController(onUpdate, intervalMs = 100)` returning `{ report(progress: number): void; dispose(): void }`.
- The controller callback receives `{ progress: number; stage: "uploading" | "processing" }`; uploading progress is clamped to `1..99`, while an input of 100 emits `{ progress: 99, stage: "processing" }` immediately.

- [ ] **Step 1: Write failing progress controller tests with fake timers**

```ts
test("coalesces repeated and high-frequency upload progress", () => {
  vi.useFakeTimers();
  const updates: UploadProgressUpdate[] = [];
  const controller = createUploadProgressController((update) => updates.push(update));

  controller.report(10);
  controller.report(10);
  controller.report(11);
  controller.report(12);
  expect(updates).toEqual([{ progress: 10, stage: "uploading" }]);

  vi.advanceTimersByTime(100);
  expect(updates).toEqual([
    { progress: 10, stage: "uploading" },
    { progress: 12, stage: "uploading" },
  ]);
});

test("switches to processing immediately instead of emitting 100 percent", () => {
  const updates: UploadProgressUpdate[] = [];
  const controller = createUploadProgressController((update) => updates.push(update));
  controller.report(100);
  expect(updates).toEqual([{ progress: 99, stage: "processing" }]);
});
```

- [ ] **Step 2: Run the controller test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/uploadProgress.test.ts`

Expected: FAIL because `uploadProgress.ts` does not exist.

- [ ] **Step 3: Implement the minimal progress controller**

Emit the first distinct value immediately, retain only the latest trailing value during the 100ms window, ignore duplicates, and clear pending timers in `dispose`. A 100% report cancels the pending timer and emits processing immediately once.

- [ ] **Step 4: Run the controller test and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/uploadProgress.test.ts`

Expected: all controller tests pass.

- [ ] **Step 5: Add failing hook-stage and cleanup tests**

Extend the upload API mock so a test can capture `onProgress`, hold the upload promise, and expose an abort spy. Cover:

- a temporary image attachment appears immediately with `uploadStage: "preparing"` before compression resolves;
- progress 35 produces uploading stage and progress 35;
- progress 100 produces processing stage and visible progress 99;
- resolving the API promise replaces the temporary attachment and removes all client-only upload fields;
- cancelling during preparing aborts the compression signal and removes the attachment;
- hash Worker construction failure skips `checkFile` and still invokes `uploadFile`;
- unmount/cancel disposes pending progress timers so advancing fake timers causes no state update.

- [ ] **Step 6: Run the hook tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/useFileUpload.test.tsx`

Expected: the new assertions fail because temporary attachments are created after compression, no stages exist, and progress is unthrottled.

- [ ] **Step 7: Implement staged upload orchestration**

Refactor the per-file promise chain into one internal async task with a temp ID created before image preparation. Store a composite cancel function per temp ID that aborts an `AbortController`, aborts XHR once available, and disposes the progress controller.

For images, preserve the empty-file check, calculate the effective role limit, and use worker compression by default. If worker compression is unavailable, directly upload originals within the limit. Only choose `fallback: "main-thread"` for an otherwise rejected image below a hard preparation ceiling of `max(limitBytes, min(limitBytes * 2, 50 MiB))`; revalidate the processed File against the actual role limit before hashing/uploading. Non-image validation remains unchanged.

Make client hash lookup optional: if Worker construction or hashing fails, proceed to upload without `/api/upload/check`; the server remains authoritative for hashing and dedupe. Integrate `createUploadProgressController` into XHR callbacks and dispose it before every terminal state.

- [ ] **Step 8: Run Task 3 tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/uploadProgress.test.ts src/hooks/__tests__/useFileUpload.test.tsx`

Expected: all Task 3 tests pass without act warnings or leaked fake timers.

---

### Task 4: Stage-Aware Attachment Card and Localized Copy

**Files:**
- Modify: `frontend/src/components/common/AttachmentCard.tsx`
- Create: `frontend/src/components/common/__tests__/AttachmentCardUploadStage.test.tsx`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: `MessageAttachment.uploadStage` from Task 3.
- Produces: `fileUpload.preparing` and `fileUpload.serverProcessing` translation keys in all five locales.

- [ ] **Step 1: Write failing card presentation tests**

Render compact editable cards for each upload stage and assert:

```ts
expect(screen.getByText("Preparing image…")).toBeInTheDocument();
expect(screen.getByText("42%")).toBeInTheDocument();
expect(screen.getByText("Processing on server…")).toBeInTheDocument();
expect(screen.queryByText("100%")).not.toBeInTheDocument();
```

Also assert the cancel button remains available in all three stages.

- [ ] **Step 2: Run the component test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/AttachmentCardUploadStage.test.tsx`

Expected: FAIL because the card only renders numeric progress and the translation keys do not exist.

- [ ] **Step 3: Implement stage labels and all locale strings**

Use a small stage-label helper inside `AttachmentCard`: preparing uses `fileUpload.preparing`, processing uses `fileUpload.serverProcessing`, and uploading uses the clamped percentage. Do not change completed or failed attachment labels.

Use these translations:

- English: `Preparing image…`, `Processing on server…`
- Chinese: `正在处理图片…`, `服务器处理中…`
- Japanese: `画像を処理中…`, `サーバーで処理中…`
- Korean: `이미지 처리 중…`, `서버에서 처리 중…`
- Russian: `Обработка изображения…`, `Обработка на сервере…`

- [ ] **Step 4: Run Task 4 tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/AttachmentCardUploadStage.test.tsx`

Expected: all stage presentation tests pass.

---

### Task 5: Focused Regression and Full Frontend Verification

**Files:**
- Modify only files already listed if verification exposes a scoped regression.

**Interfaces:**
- Consumes all Task 1-4 behavior.
- Produces fresh verification evidence; no production API changes.

- [ ] **Step 1: Run the complete focused regression set**

Run:

```bash
cd frontend && pnpm exec vitest run \
  src/utils/__tests__/imageCompression.test.ts \
  src/components/chat/__tests__/clipboardFiles.test.ts \
  src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx \
  src/hooks/__tests__/uploadProgress.test.ts \
  src/hooks/__tests__/useFileUpload.test.tsx \
  src/components/common/__tests__/AttachmentCardUploadStage.test.tsx
```

Expected: all focused tests pass with zero unhandled errors and zero act warnings.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && pnpm test`

Expected: exit code 0 and no failing test files.

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && pnpm run lint`

Expected: exit code 0 with no ESLint errors.

- [ ] **Step 4: Run the production build**

Run: `cd frontend && pnpm run build`

Expected: exit code 0, TypeScript compilation succeeds, and the Vite/PWA performance budget passes.

- [ ] **Step 5: Check workspace integrity**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the approved spec, plan, tests, workers, upload files, attachment card, type, and locale files are modified. Do not stage, commit, push, or clean any path.

- [ ] **Step 6: Report verification boundaries**

State focused/full test counts, lint/build exit status, and whether an actual browser Performance trace was available. Do not claim runtime jank is eliminated without a browser trace; distinguish code-level elimination of main-thread worker-capable paths from measured end-to-end performance.
