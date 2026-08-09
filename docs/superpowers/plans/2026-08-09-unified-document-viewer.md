# Unified Document Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give DOCX, PDF, and PPTX previews one fit-relative, continuously scrollable reader with the shared floating `ViewerToolbar` and no preview-level wheel zoom.

**Architecture:** Add a focused `DocumentViewerFrame` that owns fit-relative zoom, viewport measurement, native overflow, loading treatment, and toolbar placement. Keep conversion and page rendering in each format component; use a shared `ScaledDocumentContent` wrapper only for DOM renderers whose natural dimensions must be transformed without losing correct scroll geometry.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library, `docx-preview`, `react-pdf`, `@jvmr/pptx-to-html`.

## Global Constraints

- Only DOCX, PDF, and PPTX use the shared paged-document frame.
- Mouse wheel, trackpad, Ctrl/Command-wheel, one-finger touch, double-click, and drag do not change preview zoom.
- Zoom is controlled only by the shared floating toolbar.
- `100%` is the fitted view; reset returns to this view.
- DOCX and PDF remain continuous pages; PPTX remains a continuous slide sequence.
- DOCX preserves generated page geometry, margins, headers, and footers.
- Existing renderer and text/download fallback behavior remains available.
- Do not modify Excel, Markdown, HTML, code, image, Excalidraw, Mermaid, CAD, audio, or video interaction models.
- Preserve unrelated working-tree changes and do not push.

---

## File Structure

- Create `frontend/src/components/documents/previews/DocumentViewerFrame.tsx`: shared viewport, zoom state, loading overlay, floating toolbar, and transformed-content layout wrapper.
- Create `frontend/src/components/documents/previews/__tests__/documentViewerFrame.test.tsx`: shared fit, toolbar, and native-scroll behavior tests.
- Modify `frontend/src/components/documents/previews/wordPreviewRenderer.ts`: faithful `docx-preview` options and generated-page measurement helper.
- Modify `frontend/src/components/documents/previews/__tests__/wordPreviewRenderer.test.ts`: renderer-option and measurement regression tests.
- Modify `frontend/src/components/documents/previews/WordPreview.tsx`: shared frame for successful DOCX output and reading-card fallback.
- Create `frontend/src/components/documents/previews/__tests__/wordPreviewLayoutSource.test.ts`: DOCX wiring and fixed-card regression checks.
- Modify `frontend/src/components/documents/previews/PdfPreview.tsx`: shared frame and toolbar; remove private wheel, double-click, pinch, and drag gesture handling.
- Modify `frontend/src/components/documents/previews/__tests__/pdfPreviewNative.test.ts`: shared frame and native-scroll expectations.
- Modify `frontend/src/components/documents/previews/PptPreview.tsx`: shared frame, scroll-aware scaled slide sequence, and removal of wheel/drag/pinch behavior.
- Modify `frontend/src/components/documents/previews/__tests__/pptPreviewLocal.test.ts`: shared frame and native-scroll expectations.

### Task 1: Shared Document Viewer Frame

**Files:**
- Create: `frontend/src/components/documents/previews/DocumentViewerFrame.tsx`
- Test: `frontend/src/components/documents/previews/__tests__/documentViewerFrame.test.tsx`

**Interfaces:**
- Produces `DocumentViewerLayout` with `zoom`, `fitScale`, and `displayScale` numbers.
- Produces `DocumentViewerFrame({ naturalWidth, loading, ariaLabel, children })` where `children` is `(layout: DocumentViewerLayout) => ReactNode`.
- Produces `ScaledDocumentContent({ naturalWidth, naturalHeight, displayScale, contentRef, className })` for DOM-based page renderers.
- Produces `calculateDocumentFitScale(viewportWidth: number, naturalWidth: number, horizontalPadding?: number): number`.

- [ ] **Step 1: Write failing shared-frame tests**

Create a jsdom test that mocks `ResizeObserver`, gives the viewport a `clientWidth` of `800`, and asserts:

```tsx
expect(calculateDocumentFitScale(800, 960, 40)).toBeCloseTo(760 / 960);
expect(calculateDocumentFitScale(1200, 960, 40)).toBe(1);

render(
  <DocumentViewerFrame naturalWidth={960} ariaLabel="Document pages">
    {({ displayScale }) => <output>{displayScale.toFixed(3)}</output>}
  </DocumentViewerFrame>,
);
expect(screen.getByLabelText("Document pages")).toHaveClass("overflow-auto");
expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
```

Also render `ScaledDocumentContent` at `naturalWidth={960}`, `naturalHeight={540}`, and `displayScale={0.5}` and assert its outer style is `480px` by `270px` while the inner transform is `scale(0.5)`.

- [ ] **Step 2: Run the shared-frame test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/documents/previews/__tests__/documentViewerFrame.test.tsx
```

Expected: FAIL because `DocumentViewerFrame.tsx` does not exist.

- [ ] **Step 3: Implement the minimal shared frame**

Implement bounded zoom state (`0.5` to `3`, step `0.2`), `ResizeObserver` width measurement, and:

```ts
export function calculateDocumentFitScale(
  viewportWidth: number,
  naturalWidth: number,
  horizontalPadding = 40,
): number {
  if (viewportWidth <= 0 || naturalWidth <= 0) return 1;
  return Math.min(
    1,
    Math.max(0.1, (viewportWidth - horizontalPadding) / naturalWidth),
  );
}
```

Render a relative full-height shell, a separate `overflow-auto` viewport, a centered `min-w-full w-max` content lane with bottom clearance, and `ViewerToolbar` outside the scrolling element. Do not attach wheel, mouse-drag, double-click, or touch gesture handlers. Render the toolbar only when `loading` is false.

Implement `ScaledDocumentContent` with an outer box sized to `naturalWidth * displayScale` and `naturalHeight * displayScale`, plus a top-left-origin inner transform. This makes transformed content contribute the correct horizontal and vertical scroll ranges.

- [ ] **Step 4: Run the shared-frame test and verify GREEN**

Run the Task 1 test command. Expected: PASS with no warnings.

- [ ] **Step 5: Commit the shared frame**

```bash
git add frontend/src/components/documents/previews/DocumentViewerFrame.tsx frontend/src/components/documents/previews/__tests__/documentViewerFrame.test.tsx
git commit -m "feat: add shared document viewer frame"
```

### Task 2: Faithful and Scalable DOCX Preview

**Files:**
- Modify: `frontend/src/components/documents/previews/wordPreviewRenderer.ts`
- Modify: `frontend/src/components/documents/previews/__tests__/wordPreviewRenderer.test.ts`
- Modify: `frontend/src/components/documents/previews/WordPreview.tsx`
- Create: `frontend/src/components/documents/previews/__tests__/wordPreviewLayoutSource.test.ts`

**Interfaces:**
- Consumes `DocumentViewerFrame` and `ScaledDocumentContent` from Task 1.
- Produces `measureDocxPreview(container: HTMLElement): { width: number; height: number } | null`.
- Keeps `renderDocxPreviewHtml` and its `WordPreviewRenderResult` contract unchanged.

- [ ] **Step 1: Write failing DOCX renderer tests**

Extend `wordPreviewRenderer.test.ts` to assert:

```ts
expect(createWordPreviewRendererOptions()).toMatchObject({
  inWrapper: true,
  ignoreWidth: false,
  ignoreHeight: false,
});
```

Build a fake container whose first `section.docx` has `offsetWidth = 816` and whose `.docx-wrapper` has `scrollHeight = 2112`, then assert:

```ts
expect(measureDocxPreview(container)).toEqual({ width: 816, height: 2112 });
```

- [ ] **Step 2: Write a failing DOCX layout source test**

Assert that `WordPreview.tsx` imports `DocumentViewerFrame` and `ScaledDocumentContent`, and that the successful paginated branch no longer contains `max-w-[816px]` or `min-h-[1056px]`. Assert that a separate fallback branch still contains a constrained reading card.

- [ ] **Step 3: Run DOCX tests and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/documents/previews/__tests__/wordPreviewRenderer.test.ts src/components/documents/previews/__tests__/wordPreviewLayoutSource.test.ts
```

Expected: FAIL on wrapper options, missing measurement helper, and missing shared-frame wiring.

- [ ] **Step 4: Implement faithful DOCX rendering and measurement**

Set `inWrapper: true`, `ignoreWidth: false`, and `ignoreHeight: false`. Add `measureDocxPreview` using `querySelector("section.docx")`, `querySelector(".docx-wrapper")`, `offsetWidth`, and `scrollHeight`; return `null` for missing or zero geometry.

In `WordPreview.tsx`, retain the render target while loading, measure successful generated output, and render it through `DocumentViewerFrame` and `ScaledDocumentContent`. Remove generated-page overrides for width, minimum height, and padding. Use higher-specificity styles only to make the generated wrapper transparent, align pages, normalize the gap, and apply the shared paper shadow. Keep generated pages white in both themes.

Render Mammoth, legacy DOC, or extracted-text HTML in a separate responsive `max-w-3xl` reading card without `DocumentViewerFrame` or zoom controls.

- [ ] **Step 5: Run DOCX tests and verify GREEN**

Run the Task 2 test command. Expected: PASS.

- [ ] **Step 6: Commit the DOCX migration**

```bash
git add frontend/src/components/documents/previews/wordPreviewRenderer.ts frontend/src/components/documents/previews/WordPreview.tsx frontend/src/components/documents/previews/__tests__/wordPreviewRenderer.test.ts frontend/src/components/documents/previews/__tests__/wordPreviewLayoutSource.test.ts
git commit -m "feat: migrate DOCX preview to shared reader"
```

### Task 3: Shared PDF Reader Controls

**Files:**
- Modify: `frontend/src/components/documents/previews/PdfPreview.tsx`
- Modify: `frontend/src/components/documents/previews/__tests__/pdfPreviewNative.test.ts`

**Interfaces:**
- Consumes `DocumentViewerFrame` and `DocumentViewerLayout.displayScale` from Task 1.
- Keeps `PdfPreview({ url }: PdfPreviewProps)` unchanged.

- [ ] **Step 1: Replace PDF source expectations with failing shared-reader expectations**

Update the existing tests to assert the `DocumentViewerFrame` import and usage, continuous `Document`/`Page` rendering, and absence of wheel, double-click, touch-zoom, private toolbar, and `touchAction: "none"` code. Keep the worker compatibility and user-facing failure fallback assertions.

- [ ] **Step 2: Run the PDF test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/documents/previews/__tests__/pdfPreviewNative.test.ts
```

Expected: FAIL because PDF still owns its toolbar and gesture handlers.

- [ ] **Step 3: Implement the PDF migration**

Remove format-local zoom state, toolbar markup, wheel handler, double-click handler, pan/pinch state, and touch handlers. Render the existing continuous `<Document>` page list inside `DocumentViewerFrame` with a stable `PDF_NATURAL_PAGE_WIDTH` and pass `Math.round(PDF_NATURAL_PAGE_WIDTH * displayScale)` to each `<Page width={...}>`.

Keep page-count loading, PDF.js worker configuration, and the new-window failure fallback unchanged. Keep page backgrounds white in dark mode so authored colors remain legible.

- [ ] **Step 4: Run the PDF test and verify GREEN**

Run the Task 3 test command. Expected: PASS.

- [ ] **Step 5: Commit the PDF migration**

```bash
git add frontend/src/components/documents/previews/PdfPreview.tsx frontend/src/components/documents/previews/__tests__/pdfPreviewNative.test.ts
git commit -m "feat: migrate PDF preview to shared reader"
```

### Task 4: Scrollable PPTX Slide Reader

**Files:**
- Modify: `frontend/src/components/documents/previews/PptPreview.tsx`
- Modify: `frontend/src/components/documents/previews/__tests__/pptPreviewLocal.test.ts`

**Interfaces:**
- Consumes `DocumentViewerFrame` and `ScaledDocumentContent` from Task 1.
- Keeps `PptPreview({ url, arrayBuffer, fileName, t }: PptPreviewProps)` unchanged.

- [ ] **Step 1: Replace PPTX interaction expectations with failing shared-reader expectations**

Retain local rendering, dependency, normalization, and no-resize-rerender tests. Assert `DocumentViewerFrame` and `ScaledDocumentContent` usage and the absence of captured wheel zoom, `preventDefault`, mouse dragging, touch gesture handlers, and position offsets.

- [ ] **Step 2: Run the PPTX test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/documents/previews/__tests__/pptPreviewLocal.test.ts
```

Expected: FAIL because PPTX still captures wheel events and uses drag positioning.

- [ ] **Step 3: Implement the PPTX migration**

Remove viewport-width, fit-scale, position, dragging, pinch, wheel, and document mouse-listener state/effects. Keep a single natural `960px` render width. After `slidesHtml` is injected, measure `renderRef.current.scrollHeight` and store the natural sequence height.

Render the successful slide sequence with `DocumentViewerFrame naturalWidth={960}` and `ScaledDocumentContent naturalWidth={960} naturalHeight={contentHeight}`. The frame's `displayScale` replaces `fitScale * scale`. Keep the existing local conversion and text/download fallbacks unchanged; fallback slide text does not use the shared toolbar.

- [ ] **Step 4: Run the PPTX test and verify GREEN**

Run the Task 4 test command. Expected: PASS.

- [ ] **Step 5: Commit the PPTX migration**

```bash
git add frontend/src/components/documents/previews/PptPreview.tsx frontend/src/components/documents/previews/__tests__/pptPreviewLocal.test.ts
git commit -m "feat: migrate PPTX preview to shared reader"
```

### Task 5: Cross-format Verification

**Files:**
- Verify only; modify a scoped file only if a verification failure is caused by this feature.

**Interfaces:**
- Consumes all deliverables from Tasks 1-4.
- Produces evidence that shared behavior works without regressing other preview types.

- [ ] **Step 1: Run all focused document preview tests**

```bash
cd frontend && pnpm test -- src/components/documents/previews/__tests__/documentViewerFrame.test.tsx src/components/documents/previews/__tests__/wordPreviewRenderer.test.ts src/components/documents/previews/__tests__/wordPreviewLayoutSource.test.ts src/components/documents/previews/__tests__/pdfPreviewNative.test.ts src/components/documents/previews/__tests__/pptPreviewLocal.test.ts
```

Expected: all focused tests PASS.

- [ ] **Step 2: Run the complete frontend test suite**

```bash
cd frontend && pnpm test
```

Expected: PASS. If an unrelated pre-existing failure appears, reproduce it independently and report it separately.

- [ ] **Step 3: Run lint**

```bash
cd frontend && pnpm run lint
```

Expected: PASS with no new lint errors.

- [ ] **Step 4: Run the production build**

```bash
cd frontend && pnpm run build
```

Expected: PASS and produce the normal Vite build output. Do not commit build artifacts.

- [ ] **Step 5: Inspect the final diff and working tree**

```bash
git diff --check
git status --short
git log --oneline -8
```

Expected: no whitespace errors; only scoped viewer files and tests are committed by this plan, while unrelated user changes remain untouched and uncommitted.
