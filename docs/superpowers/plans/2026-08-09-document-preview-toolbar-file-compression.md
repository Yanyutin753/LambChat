# Document Preview Toolbar File Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compress the document preview toolbar's file-information block so the right-side actions retain clear visual space.

**Architecture:** Extend the shared `FileIcon` with an opt-in compact size, then use it only in `DocumentPreviewToolbar`. Replace the toolbar's unbounded `flex-1` file-information region with a container-relative, capped flex basis and push the non-shrinking action group to the right.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library, jsdom

## Global Constraints

- Change only the shared document preview toolbar and the file icon API needed by that toolbar.
- Do not change preview-panel width, action availability, action order, or click behavior.
- Keep the file-size/type line visible and preserve the filename `title` attribute.
- Keep existing action-button dimensions, labels, tooltips, keyboard behavior, and focus treatment.
- Preserve unrelated working-tree changes.

---

### Task 1: Compress the toolbar file-information region

**Files:**
- Create: `frontend/src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx`
- Modify: `frontend/src/components/common/FileIcon.tsx`
- Modify: `frontend/src/components/documents/DocumentPreviewToolbar.tsx`

**Interfaces:**
- Consumes: existing `FileIconProps` values `icon`, `bg`, and `color`
- Produces: optional `FileIconProps.compact?: boolean`; when true the icon container is `size-8`, otherwise it remains `size-10`

- [ ] **Step 1: Write the failing layout regression test**

Render the real toolbar and assert the compact icon, bounded file-information block, and right-aligned action group:

```tsx
/** @vitest-environment jsdom */

import { createRef, type ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { getFileTypeInfo } from "../utils";

test("document preview toolbar compresses file info before the action group", () => {
  const fileName = "人工智能对大学生的影响（80页）.docx";
  const fileInfo = getFileTypeInfo(fileName);
  const props = {
    t: ((key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key) as ComponentProps<
      typeof DocumentPreviewToolbar
    >["t"],
    data: null,
    copied: false,
    viewSource: false,
    isSidebar: true,
    isFullscreen: false,
    markdownFile: false,
    codeFile: false,
    hasTextContent: false,
    displaySize: 0,
    fileSize: 279347,
    fileName,
    language: "",
    fileInfo,
    Icon: fileInfo.icon,
    s3Key: "documents/file.docx",
    signedUrl: undefined,
    externalImageUrl: undefined,
    resolvedUrl: null,
    unsupportedPreviewFile: false,
    onUserInteraction: undefined,
    onClose: vi.fn(),
    effectiveOnBack: undefined,
    handleCopy: vi.fn(),
    handleDownload: vi.fn(),
    toolbarRef: createRef<HTMLDivElement>(),
    setViewSource: vi.fn(),
    setViewMode: vi.fn(),
    handleFullscreenToggle: vi.fn(),
    exitFullscreen: vi.fn(),
  } satisfies ComponentProps<typeof DocumentPreviewToolbar>;

  render(<DocumentPreviewToolbar {...props} />);

  const title = screen.getByTitle(fileName);
  const fileInfoBlock = title.parentElement;
  const fileIcon = fileInfoBlock?.previousElementSibling;
  const actionGroup = fileInfoBlock?.nextElementSibling;

  expect(fileIcon).toHaveClass("size-8");
  expect(fileInfoBlock).toHaveClass(
    "flex-[0_1_clamp(7rem,28%,12rem)]",
    "min-w-0",
    "overflow-hidden",
  );
  expect(fileInfoBlock).not.toHaveClass("flex-1");
  expect(actionGroup).toHaveClass("ml-auto", "shrink-0");
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx
```

Expected: FAIL because `FileIconProps` has no `compact` option and `DocumentPreviewToolbar` still uses an unbounded `flex-1` middle region.

- [ ] **Step 3: Add the opt-in compact file icon**

Update `FileIconProps` and `FileIcon` in `FileIcon.tsx`:

```tsx
interface FileIconProps {
  icon: LucideIcon;
  bg?: string;
  color?: string;
  compact?: boolean;
}

export function FileIcon({
  icon: Icon,
  bg = "bg-blue-100 dark:bg-blue-900/40",
  color = "text-blue-600 dark:text-blue-400",
  compact = false,
}: FileIconProps) {
  return (
    <div
      className={`flex items-center justify-center ${compact ? "size-8" : "size-10"} rounded-lg shrink-0 ${bg}`}
    >
      <Icon size={18} className={color} />
    </div>
  );
}
```

- [ ] **Step 4: Apply compact, container-relative toolbar sizing**

In `DocumentPreviewToolbar.tsx`, opt into the compact icon, replace the file-information wrapper's `flex-1` sizing, and right-align the action group:

```tsx
<FileIcon
  icon={Icon}
  bg={fileInfo.bg}
  color={fileInfo.color}
  compact
/>
<div className="flex-[0_1_clamp(7rem,28%,12rem)] min-w-0 overflow-hidden">
  {/* existing filename and metadata */}
</div>
<div className="ml-auto flex items-center gap-2 sm:gap-1 relative z-10 shrink-0">
  {/* existing actions unchanged */}
</div>
```

- [ ] **Step 5: Run focused document toolbar tests and verify GREEN**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx src/components/documents/__tests__/documentPreviewToolbarStyles.test.ts src/components/documents/__tests__/documentPreviewToolbarCompact.test.ts
```

Expected: both test files pass.

- [ ] **Step 6: Run frontend build verification**

Run:

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite production build complete successfully.

- [ ] **Step 7: Commit the implementation**

```bash
git add frontend/src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx frontend/src/components/common/FileIcon.tsx frontend/src/components/documents/DocumentPreviewToolbar.tsx
git commit -m "fix(ui): compress preview toolbar file info"
```
