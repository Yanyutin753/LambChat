# PPT Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement local PPT preview using pptx-preview library for .pptx files, while keeping Office Online for legacy .ppt files.

**Architecture:** Update PptPreview component to handle both file types - .pptx uses pptx-preview library for local rendering with zoom/pan/touch support, .ppt falls back to Office Online iframe. Reuse zoom/pan patterns from MermaidDiagram component.

**Tech Stack:** React, TypeScript, pptx-preview library

---

### Task 1: Install pptx-preview dependency

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install the package**

```bash
cd frontend && npm install pptx-preview
```

**Step 2: Verify installation**

Run: `cd frontend && npm list pptx-preview`
Expected: `pptx-preview@x.x.x`

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add pptx-preview dependency for local pptx rendering"
```

---

### Task 2: Update utils.ts to distinguish ppt vs pptx

**Files:**
- Modify: `frontend/src/components/documents/utils.ts`

**Step 1: Add helper functions**

Find the `isPptFile` function and update it:

```typescript
// Replace existing isPptFile function
export function isPptFile(ext: string): boolean {
  return ext === "ppt" || ext === "pptx";
}

export function isPptxFile(ext: string): boolean {
  return ext === "pptx";
}

export function isLegacyPptFile(ext: string): boolean {
  return ext === "ppt";
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/documents/utils.ts
git commit -m "feat(utils): add helpers to distinguish ppt vs pptx files"
```

---

### Task 3: Update DocumentPreview to pass arrayBuffer for pptx

**Files:**
- Modify: `frontend/src/components/documents/DocumentPreview.tsx`

**Step 1: Update imports**

Add new imports at the top (around line 26-34):

```typescript
import {
  // ... existing imports ...
  isPptxFile,
  isLegacyPptFile,
} from "./utils";
```

**Step 2: Update state and file type detection**

Add new state variable after `pptUrl` state (around line 104):

```typescript
const [pptxBuffer, setPptxBuffer] = useState<ArrayBuffer | null>(null);
```

Update file type detection (around line 119):

```typescript
const pptxFile = isPptxFile(ext);
const legacyPptFile = isLegacyPptFile(ext);
// Keep pptFile for backward compatibility
const pptFile = isPptFile(ext);
```

**Step 3: Update loadContent to fetch arrayBuffer for pptx**

In the `loadContent` function, update the PPT handling section (around line 221-227):

```typescript
// PPT 文件处理
if (pptFile) {
  if (pptxFile) {
    // .pptx 文件获取 ArrayBuffer 用于本地预览
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch file: ${response.status}`);
      }
      const buffer = await response.arrayBuffer();
      setPptxBuffer(buffer);
      setData({ content: "", path });
    } catch (e) {
      console.error("Failed to fetch pptx:", e);
      setError(t("documents.failedToLoadFromS3", "从存储加载文件失败"));
    }
  } else {
    // .ppt 文件使用 Office Online viewer
    setPptUrl(url);
    setData({ content: "", path });
  }
  setLoading(false);
  return;
}
```

**Step 4: Update reset state in useEffect**

Add `setPptxBuffer(null)` to the reset section (around line 167):

```typescript
setPptxBuffer(null);
```

**Step 5: Update PptPreview props**

Update the PptPreview rendering section (around line 565-568):

```typescript
) : pptFile && (pptUrl || pptxBuffer) ? (
  <div className="h-full min-h-[400px]">
    <PptPreview
      url={pptUrl || ""}
      arrayBuffer={pptxBuffer}
      fileName={fileName}
    />
  </div>
```

**Step 6: Update hasTextContent memo**

Update the memoization (around line 130-148):

```typescript
const hasTextContent = useMemo(() => {
  return !!(
    data?.content &&
    !binaryFile &&
    !wordFile &&
    !excelFile &&
    !pptFile &&
    !htmlFile &&
    !excalidrawFile
  );
}, [
  data?.content,
  binaryFile,
  wordFile,
  excelFile,
  pptFile,
  htmlFile,
  excalidrawFile,
]);
```

**Step 7: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 8: Commit**

```bash
git add frontend/src/components/documents/DocumentPreview.tsx
git commit -m "feat(document-preview): pass arrayBuffer for pptx files"
```

---

### Task 4: Rewrite PptPreview component

**Files:**
- Modify: `frontend/src/components/documents/previews/PptPreview.tsx`

**Step 1: Implement the new PptPreview component**

Replace the entire file content:

```typescript
import { memo, useEffect, useRef, useState, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
} from "lucide-react";

interface PptPreviewProps {
  url: string;
  arrayBuffer?: ArrayBuffer | null;
  fileName: string;
}

const PptPreview = memo(function PptPreview({
  url,
  arrayBuffer,
  fileName,
}: PptPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

  // Touch zoom state
  const [touchStart, setTouchStart] = useState<{
    x: number;
    y: number;
    distance: number;
  } | null>(null);

  // Determine file type
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  const isPptx = ext === "pptx";

  // For pptx-preview
  const [slides, setSlides] = useState<Array<{ index: number; src: string }>>(
    [],
  );
  const [currentSlide, setCurrentSlide] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pptxPreviewerRef = useRef<ReturnType<typeof initPptxPreview> | null>(
    null,
  );

  // Dynamic import for pptx-preview
  const initPptxPreview = async () => {
    const { init } = await import("pptx-preview");
    return init;
  };

  // Initialize pptx-preview for .pptx files
  useEffect(() => {
    if (!isPptx || !arrayBuffer || !containerRef.current) return;

    const initPreview = async () => {
      try {
        setLoading(true);
        const init = await initPptxPreview();
        const previewer = init(containerRef.current!, {
          width: containerRef.current!.clientWidth || 800,
        });
        pptxPreviewerRef.current = previewer;

        await previewer.preview(arrayBuffer);

        // Get slide count from the previewer
        const slideCount = previewer.slideCount || 1;
        const slideList = Array.from({ length: slideCount }, (_, i) => ({
          index: i,
          src: "", // pptx-preview renders directly to DOM
        }));
        setSlides(slideList);
        setError(null);
      } catch (err) {
        console.error("Failed to init pptx-preview:", err);
        setError(
          err instanceof Error ? err.message : "Failed to load presentation",
        );
      } finally {
        setLoading(false);
      }
    };

    initPreview();
  }, [isPptx, arrayBuffer]);

  // Handle wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 3));
  }, []);

  // Handle touch zoom
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      setTouchStart({
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
        distance: Math.sqrt(dx * dx + dy * dy),
      });
    }
  }, []);

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2 && touchStart) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const delta = (distance - touchStart.distance) / 200;
        setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 3));
        setTouchStart({ ...touchStart, distance });
      }
    },
    [touchStart],
  );

  const handleTouchEnd = useCallback(() => {
    setTouchStart(null);
  }, []);

  // Handle mouse drag to pan
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      setIsDragging(true);
      setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
    },
    [translate],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging) return;
      setTranslate({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    },
    [isDragging, dragStart],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Navigation
  const goToSlide = useCallback((index: number) => {
    if (index >= 0 && index < slides.length) {
      setCurrentSlide(index);
      pptxPreviewerRef.current?.gotoSlide(index + 1); // pptx-preview uses 1-based index
    }
  }, [slides.length]);

  const nextSlide = useCallback(() => {
    goToSlide(currentSlide + 1);
  }, [currentSlide, goToSlide]);

  const prevSlide = useCallback(() => {
    goToSlide(currentSlide - 1);
  }, [currentSlide, goToSlide]);

  // Zoom controls
  const zoomIn = useCallback(() => {
    setScale((prev) => Math.min(prev + 0.2, 3));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((prev) => Math.max(prev - 0.2, 0.5));
  }, []);

  const fitToScreen = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  // For .ppt files, use Office Online
  if (!isPptx) {
    const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(
      url,
    )}`;
    return (
      <div className="h-full w-full flex flex-col">
        <iframe
          src={officeUrl}
          className="flex-1 w-full min-h-[400px] border-0"
          title="PowerPoint Preview"
        />
      </div>
    );
  }

  // Loading state for .pptx
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-stone-500 dark:text-stone-400">Loading...</div>
      </div>
    );
  }

  // Error state for .pptx
  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-4">
        <div className="text-center">
          <p className="text-red-500 dark:text-red-400 mb-2">
            Failed to load presentation
          </p>
          <p className="text-sm text-stone-400">{error}</p>
        </div>
      </div>
    );
  }

  // .pptx preview with zoom/pan
  return (
    <div className="h-full flex flex-col bg-stone-100 dark:bg-stone-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700">
        {/* Navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={prevSlide}
            disabled={currentSlide === 0}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="text-sm text-stone-600 dark:text-stone-300 min-w-[60px] text-center">
            {currentSlide + 1} / {slides.length}
          </span>
          <button
            onClick={nextSlide}
            disabled={currentSlide === slides.length - 1}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight size={18} />
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={zoomOut}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
          >
            <ZoomOut size={18} />
          </button>
          <span className="text-sm text-stone-600 dark:text-stone-300 min-w-[50px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={zoomIn}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
          >
            <ZoomIn size={18} />
          </button>
          <button
            onClick={fitToScreen}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 text-xs"
          >
            Fit
          </button>
          <div className="w-px h-4 bg-stone-200 dark:bg-stone-700 mx-1" />
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
          >
            {isFullscreen ? (
              <Minimize2 size={18} />
            ) : (
              <Maximize2 size={18} />
            )}
          </button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Slide thumbnails sidebar */}
        <div className="w-24 md:w-32 bg-stone-50 dark:bg-stone-850 border-r border-stone-200 dark:border-stone-700 overflow-y-auto p-2 space-y-2">
          {slides.map((slide) => (
            <button
              key={slide.index}
              onClick={() => goToSlide(slide.index)}
              className={`w-full aspect-[16/9] rounded border-2 transition-all ${
                currentSlide === slide.index
                  ? "border-amber-500 ring-2 ring-amber-500/50"
                  : "border-stone-200 dark:border-stone-600 hover:border-stone-400"
              } bg-white dark:bg-stone-800 flex items-center justify-center text-xs text-stone-400`}
            >
              {slide.index + 1}
            </button>
          ))}
        </div>

        {/* Slide viewer */}
        <div
          className={`flex-1 overflow-hidden ${
            isFullscreen ? "fixed inset-0 z-50 bg-stone-900" : ""
          }`}
          onWheel={handleWheel}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <div
            ref={containerRef}
            className={`w-full h-full flex items-center justify-center cursor-${
              isDragging ? "grabbing" : "grab"
            }`}
            style={{
              transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.2s ease-out",
            }}
          />
        </div>
      </div>
    </div>
  );
});

export default PptPreview;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/documents/previews/PptPreview.tsx
git commit -m "feat(ppt-preview): implement local pptx rendering with zoom/pan support"
```

---

### Task 5: Export new utilities and test

**Files:**
- Modify: `frontend/src/components/documents/index.ts`
- Modify: `frontend/src/components/documents/DocumentPreview.tsx`

**Step 1: Update exports in index.ts**

Add new exports to `frontend/src/components/documents/index.ts`:

```typescript
export { isPptxFile, isLegacyPptFile } from "./utils";
```

**Step 2: Test the implementation**

Run: `cd frontend && npm run dev`

Manual test steps:
1. Open a .pptx file in the document preview
2. Verify local rendering works (not iframe)
3. Test zoom with mouse wheel
4. Test slide navigation
5. Test with a .ppt file to verify Office Online fallback

**Step 3: Commit**

```bash
git add frontend/src/components/documents/index.ts
git commit -m "feat: export ppt utility functions"
```

---

### Task 6: Update i18n translations

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`

**Step 1: Add translations**

Add any new translation keys if needed (for error messages, etc.):

In `en.json`:
```json
"documents": {
  "failedToLoadPresentation": "Failed to load presentation",
  "loadingPresentation": "Loading presentation..."
}
```

In `zh.json`:
```json
"documents": {
  "failedToLoadPresentation": "加载演示文稿失败",
  "loadingPresentation": "加载演示文稿中..."
}
```

**Step 2: Commit**

```bash
git add frontend/src/i18n/locales/*.json
git commit -m "feat(i18n): add ppt preview translations"
```

---

### Task 7: Final verification and cleanup

**Step 1: Run full type check**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors

**Step 3: Build production bundle**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Final commit (if any changes)**

```bash
git status
# If any changes, commit them
git add -A
git commit -m "chore: final cleanup for ppt preview feature"
```

---

## Summary

This plan implements local PPT preview for `.pptx` files using the `pptx-preview` library with features matching the Mermaid preview:
- Zoom (wheel + pinch)
- Pan (drag + touch)
- Slide navigation with thumbnails
- Mobile-friendly

Legacy `.ppt` files continue to use Office Online iframe.
