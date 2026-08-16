# Message Image Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-width cropped image rendering with natural-ratio, width-constrained images and waterfall gallery for multiple images in chat messages.

**Architecture:** A new `MessageImageGallery` component handles multi-image layout. A utility function detects image-type `reveal_file` parts. The `ChatMessage/index.tsx` parts loop groups consecutive image parts before rendering. `FileRevealItem` is updated for single-image display with `max-w-md` + `object-contain`. Markdown images get a `max-w-lg` constraint.

**Tech Stack:** React 19, TypeScript, TailwindCSS, Vitest

## Global Constraints

- Frontend monorepo at `frontend/`, components in `frontend/src/components/chat/ChatMessage/`
- Tests in `frontend/src/components/chat/ChatMessage/__tests__/`
- Run tests: `cd frontend && pnpm test`
- Existing tests use source-assertion pattern (read .tsx, regex match) and some component rendering
- `ImageWithSkeleton` is the shared image primitive (inline mode for thumbnails, block mode for standalone)
- `useSessionImageGallery()` hook provides `openImage(src, alt, options?)` for lightbox
- `isImageFile(ext)` from `components/documents/utils` checks file extension
- Out of scope: `ImageGenerateItem`, user attachments, `SessionImageGalleryProvider`

---

### Task 1: Create `isRevealFileImagePart` utility

**Files:**
- Create: `frontend/src/components/chat/ChatMessage/revealFileImageUtils.ts`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/revealFileImageUtils.test.ts`

**Interfaces:**
- Consumes: `MessagePart` from `types`, `isImageFile` from `documents/utils`
- Produces: `RevealFileImageInfo | null`

```typescript
// revealFileImageUtils.ts

import type { MessagePart } from "../../../types";
import { isImageFile } from "../../documents/utils";
import { getFullUrl } from "../../../services/api/config";

export interface RevealFileImageInfo {
  id: string;
  src: string;
  fileName: string;
}

/**
 * Detects whether a MessagePart is a reveal_file containing an image.
 * Returns image metadata if it is an image, null otherwise.
 *
 * Handles both new format (result: { key, url, name, type }) and
 * old format (result: { file: { path, s3_url } }).
 */
export function isRevealFileImagePart(
  part: MessagePart,
): RevealFileImageInfo | null {
  if (part.type !== "tool" || part.name !== "reveal_file") return null;
  if (!part.result || !part.success) return null;

  try {
    let result: Record<string, unknown>;
    if (typeof part.result === "object") {
      result = part.result as Record<string, unknown>;
    } else {
      let jsonStr: string = part.result;
      const m = part.result.match(/content='(.+?)'(\s|$)/);
      if (m) jsonStr = m[1].replace(/\\'/g, "'");
      result = JSON.parse(jsonStr);
    }

    // New format: { key, url, name, type: "image" }
    if ("key" in result && "url" in result && "type" in result) {
      const r = result as { url: string; name: string; type: string };
      if (r.type === "image" && r.url) {
        return {
          id: part.id || `reveal-${result.key}`,
          src: getFullUrl(r.url),
          fileName: r.name || "image",
        };
      }
      return null;
    }

    // Old format: { type: "file_reveal", file: { path, s3_url } }
    if ("type" in result && result.type === "file_reveal") {
      const file = result.file as Record<string, unknown> | undefined;
      if (!file) return null;
      const path = (file.path as string) || "";
      const s3Url = (file.s3_url as string) || "";
      const ext = path.split(".").pop()?.toLowerCase() || "";
      if (!isImageFile(ext) || !s3Url) return null;
      return {
        id: part.id || `reveal-${file.path}`,
        src: getFullUrl(s3Url),
        fileName: path.split("/").pop() || "image",
      };
    }

    return null;
  } catch {
    return null;
  }
}
```

- [ ] **Step 1: Write the failing test**

```typescript
// __tests__/revealFileImageUtils.test.ts

import { describe, expect, it } from "vitest";

// Source-assertion test pattern (matches existing test conventions)
import { readFileSync } from "node:fs";

describe("isRevealFileImagePart", () => {
  it("exports a function that accepts a MessagePart", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain(
      "export function isRevealFileImagePart(",
    );
    expect(source).toContain("RevealFileImageInfo | null");
  });

  it("checks for tool type and reveal_file name", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain('part.name !== "reveal_file"');
    expect(source).toContain('part.type !== "tool"');
  });

  it("handles both new format (type: image) and old format (file_reveal)", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain('r.type === "image"');
    expect(source).toContain('result.type === "file_reveal"');
  });

  it("uses isImageFile for old format extension check", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain("isImageFile(ext)");
  });

  it("returns null for non-image reveal_file (e.g. pdf, document)", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    // For old format, should return null if !isImageFile(ext)
    expect(source).toMatch(/if \(!isImageFile\(ext\)/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/revealFileImageUtils.test.ts`
Expected: FAIL — file not found

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/chat/ChatMessage/revealFileImageUtils.ts` with the code above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/revealFileImageUtils.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatMessage/revealFileImageUtils.ts \
        frontend/src/components/chat/ChatMessage/__tests__/revealFileImageUtils.test.ts
git commit -m "feat(chat): add isRevealFileImagePart utility for image detection"
```

---

### Task 2: Create `MessageImageGallery` component

**Files:**
- Create: `frontend/src/components/chat/ChatMessage/MessageImageGallery.tsx`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/MessageImageGallery.test.tsx`

**Interfaces:**
- Consumes: `RevealFileImageInfo` from `revealFileImageUtils.ts`, `useSessionImageGallery` from `sessionImageGallery.ts`
- Produces: `<MessageImageGallery images={RevealFileImageInfo[]} />`

```tsx
// MessageImageGallery.tsx

import { useMemo } from "react";
import { ExternalLink } from "lucide-react";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { useSessionImageGallery } from "./sessionImageGallery";
import type { RevealFileImageInfo } from "./revealFileImageUtils";

interface MessageImageGalleryProps {
  images: RevealFileImageInfo[];
}

export function MessageImageGallery({ images }: MessageImageGalleryProps) {
  const sessionImageGallery = useSessionImageGallery();

  const handleImageClick = (image: RevealFileImageInfo) => {
    sessionImageGallery?.openImage(image.src, image.fileName, {
      group: "reveal-file",
    });
  };

  const layoutClass = useMemo(() => {
    const count = images.length;
    if (count === 1) return "flex justify-center";
    if (count <= 3) return "grid grid-cols-2 gap-2";
    return "columns-2 gap-2";
  }, [images.length]);

  return (
    <div className={layoutClass}>
      {images.map((image, index) => {
        const isFirstOfThree = images.length === 3 && index === 0;
        return (
          <div
            key={image.id}
            className={
              isFirstOfThree
                ? "col-span-2"
                : images.length === 1
                  ? "w-full max-w-md"
                  : "break-inside-avoid"
            }
          >
            <div
              className="group relative cursor-pointer rounded-xl border overflow-hidden transition-shadow hover:shadow-lg border-theme-border bg-white dark:bg-theme-bg"
              onClick={() => handleImageClick(image)}
            >
              <ImageWithSkeleton
                src={image.src}
                alt={image.fileName}
                skipUrlResolve
                inline
                className="w-full h-auto object-contain"
                loading="lazy"
              />
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center pointer-events-none">
                <div className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-full bg-white/90 dark:bg-theme-bg-card/90 shadow-lg pointer-events-auto cursor-pointer">
                  <ExternalLink
                    size={16}
                    className="text-theme-text-secondary"
                  />
                </div>
              </div>
              {/* File name label on hover */}
              <div className="absolute bottom-0 left-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="px-2 py-1 bg-gradient-to-t from-black/60 to-transparent">
                  <span className="text-[11px] text-white/90 truncate block">
                    {image.fileName}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 1: Write the failing test**

```tsx
// __tests__/MessageImageGallery.test.tsx

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("MessageImageGallery", () => {
  const source = readFileSync(
    new URL("../MessageImageGallery.tsx", import.meta.url),
    "utf8",
  );

  it("exports a MessageImageGallery component", () => {
    expect(source).toContain(
      "export function MessageImageGallery",
    );
  });

  it("accepts images prop of type RevealFileImageInfo[]", () => {
    expect(source).toContain("images: RevealFileImageInfo[]");
  });

  it("uses flex justify-center layout for single image", () => {
    expect(source).toContain("images.length === 1");
    expect(source).toContain("flex justify-center");
  });

  it("uses grid grid-cols-2 for 2-3 images", () => {
    expect(source).toContain("images.length === 3");
    expect(source).toContain("grid grid-cols-2");
  });

  it("uses columns-2 masonry for 4+ images", () => {
    expect(source).toContain("columns-2");
  });

  it("applies col-span-2 to first image when there are 3 images", () => {
    expect(source).toContain("col-span-2");
  });

  it("constrains single image width with max-w-md", () => {
    expect(source).toContain("max-w-md");
  });

  it("uses object-contain instead of object-cover for full image visibility", () => {
    expect(source).toContain("object-contain");
    expect(source).not.toContain("object-cover");
  });

  it("uses ImageWithSkeleton with inline mode", () => {
    expect(source).toContain("ImageWithSkeleton");
    expect(source).toContain("skipUrlResolve");
  });

  it("opens session image gallery on click", () => {
    expect(source).toContain("sessionImageGallery?.openImage");
    expect(source).toContain('"reveal-file"');
  });

  it("shows hover overlay with ExternalLink icon", () => {
    expect(source).toContain("ExternalLink");
    expect(source).toContain("group-hover:opacity-100");
  });

  it("shows file name on hover at bottom", () => {
    expect(source).toContain("image.fileName");
    expect(source).toContain("truncate block");
  });

  it("uses break-inside-avoid for masonry items", () => {
    expect(source).toContain("break-inside-avoid");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/MessageImageGallery.test.tsx`
Expected: FAIL — file not found

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/chat/ChatMessage/MessageImageGallery.tsx` with the code above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/MessageImageGallery.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatMessage/MessageImageGallery.tsx \
        frontend/src/components/chat/ChatMessage/__tests__/MessageImageGallery.test.tsx
git commit -m "feat(chat): add MessageImageGallery with adaptive layout"
```

---

### Task 3: Integrate gallery grouping in ChatMessage parts loop

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/index.tsx:535-561` (the `hasParts` rendering block)
- Modify: `frontend/src/components/chat/ChatMessage/index.tsx:1-20` (imports)

**Interfaces:**
- Consumes: `isRevealFileImagePart` from `revealFileImageUtils.ts`, `MessageImageGallery` from `MessageImageGallery.tsx`, `MessagePart` from `types`
- Produces: Grouped parts rendering — consecutive image reveal_files become `<MessageImageGallery />`, all other parts render via `<MessagePartRenderer />`

**Changes to `index.tsx`:**

1. Add imports at top — add `isRevealFileImagePart` and `MessageImageGallery` imports alongside existing ones:
```typescript
// Add after line 18 (MessagePartRenderer import):
import { isRevealFileImagePart } from "./revealFileImageUtils";
import { MessageImageGallery } from "./MessageImageGallery";
```

2. Add a grouping helper function **before** the `ChatMessage` component (after imports, around line 40):

```typescript
/** Groups consecutive image reveal_file parts for gallery rendering. */
function groupPartsForGallery(
  parts: MessagePart[],
): Array<
  | { type: "gallery"; images: ReturnType<typeof isRevealFileImagePart>[]; startPartIndex: number }
  | { type: "single"; part: MessagePart; partIndex: number }
> {
  const groups: Array<
    | { type: "gallery"; images: ReturnType<typeof isRevealFileImagePart>[]; startPartIndex: number }
    | { type: "single"; part: MessagePart; partIndex: number }
  > = [];
  let imageBuffer: Array<ReturnType<typeof isRevealFileImagePart>> | null = null;
  let bufferStartIndex = 0;

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];

    // Check if this part is an image reveal_file
    if (part.type === "tool") {
      const imageInfo = isRevealFileImagePart(part);
      if (imageInfo) {
        if (!imageBuffer) {
          imageBuffer = [];
          bufferStartIndex = i;
        }
        imageBuffer.push(imageInfo);
        continue;
      }
    }

    // Non-image part: flush buffer if any
    if (imageBuffer) {
      groups.push({ type: "gallery", images: imageBuffer, startPartIndex: bufferStartIndex });
      imageBuffer = null;
    }

    if (part.type !== "recommend_questions") {
      groups.push({ type: "single", part, partIndex: i });
    }
  }

  // Flush remaining buffer
  if (imageBuffer) {
    groups.push({ type: "gallery", images: imageBuffer, startPartIndex: bufferStartIndex });
  }

  return groups;
}
```

3. Replace the parts rendering loop at lines 535-561. **Before:**

```tsx
{hasParts ? (
  <div className="space-y-3 my-2">
    {message.parts!.map((part: MessagePart, index: number) =>
      part.type === "recommend_questions" ? null : (
        <MessagePartRenderer
          key={index}
          part={part}
          messageId={message.id}
          partIndex={index}
          isStreaming={message.isStreaming}
          isLast={index === message.parts!.length - 1}
          activePreview={activePreview}
          onOpenPreview={onOpenPreview}
          onRecommendQuestionClick={onRecommendQuestionClick}
          onRetryCancelled={
            part.type === "cancelled" && onRetryCancelledMessage
              ? () => void onRetryCancelledMessage(message.id)
              : undefined
          }
          allowAutoPreview={shouldAllowAutoPreviewForPart({
            messageId: message.id,
            partIndex: index,
            latestAutoPreview: latestAutoPreview ?? null,
          })}
        />
      ),
    )}
```

**After:**

```tsx
{hasParts ? (
  <div className="space-y-3 my-2">
    {groupPartsForGallery(message.parts!).map((group, groupIdx) =>
      group.type === "gallery" ? (
        <MessageImageGallery key={`gallery-${group.startPartIndex}`} images={group.images} />
      ) : (
        <MessagePartRenderer
          key={group.partIndex}
          part={group.part}
          messageId={message.id}
          partIndex={group.partIndex}
          isStreaming={message.isStreaming}
          isLast={group.partIndex === message.parts!.length - 1}
          activePreview={activePreview}
          onOpenPreview={onOpenPreview}
          onRecommendQuestionClick={onRecommendQuestionClick}
          onRetryCancelled={
            group.part.type === "cancelled" && onRetryCancelledMessage
              ? () => void onRetryCancelledMessage(message.id)
              : undefined
          }
          allowAutoPreview={shouldAllowAutoPreviewForPart({
            messageId: message.id,
            partIndex: group.partIndex,
            latestAutoPreview: latestAutoPreview ?? null,
          })}
        />
      ),
    )}
```

- [ ] **Step 1: Write the failing test**

```typescript
// Add to existing test file or create new:
// __tests__/messageImageGrouping.test.ts

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("ChatMessage image grouping", () => {
  const source = readFileSync(
    new URL("../index.tsx", import.meta.url),
    "utf8",
  );

  it("imports isRevealFileImagePart utility", () => {
    expect(source).toContain("isRevealFileImagePart");
  });

  it("imports MessageImageGallery component", () => {
    expect(source).toContain("MessageImageGallery");
  });

  it("does not import ToolPart separately (uses MessagePart)", () => {
    // ToolPart should not be imported since isRevealFileImagePart accepts MessagePart
    const importSection = source.substring(0, source.indexOf("function ChatMessage"));
    expect(importSection).not.toContain("ToolPart");
  });

  it("defines a groupPartsForGallery function", () => {
    expect(source).toContain("function groupPartsForGallery(");
  });

  it("renders MessageImageGallery for gallery groups", () => {
    expect(source).toContain('<MessageImageGallery key={`gallery-${group.startPartIndex}`}');
  });

  it("uses groupPartsForGallery in the parts rendering loop", () => {
    expect(source).toContain("groupPartsForGallery(message.parts!)");
  });

  it("handles both gallery and single group types", () => {
    expect(source).toContain('group.type === "gallery"');
  });

  it("skips recommend_questions parts", () => {
    expect(source).toContain('part.type !== "recommend_questions"');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/messageImageGrouping.test.ts`
Expected: FAIL — imports not found

- [ ] **Step 3: Apply the changes to `index.tsx`**

Add imports, add `groupPartsForGallery` function, replace the parts loop as shown above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/messageImageGrouping.test.ts`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd frontend && pnpm test`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ChatMessage/index.tsx \
        frontend/src/components/chat/ChatMessage/__tests__/messageImageGrouping.test.ts
git commit -m "feat(chat): integrate image gallery grouping in message parts loop"
```

---

### Task 4: Improve FileRevealItem single-image rendering

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/FileRevealItem.tsx:330-398` (image preview container)
- Modify: `frontend/src/components/chat/ChatMessage/items/FileRevealItem.tsx:362-371` (ImageWithSkeleton usage)

**Changes:**

1. **Line 331-336** — Outer container: add `max-w-md mx-auto` for single images (images not in gallery still render via FileRevealItem):

**Before (line 331-336):**
```tsx
        <div
          className={clsx(
            "w-full rounded-xl border overflow-hidden transition-colors transition-shadow",
            "border-theme-border bg-white dark:bg-theme-bg",
            "hover:shadow-lg hover:border-theme-border-hover",
          )}
        >
```

**After:**
```tsx
        <div
          className={clsx(
            "rounded-xl border overflow-hidden transition-colors transition-shadow",
            "border-theme-border bg-white dark:bg-theme-bg",
            "hover:shadow-lg hover:border-theme-border-hover",
            isImage && "max-w-md mx-auto",
          )}
        >
```

2. **Line 348-350** — Remove fixed aspectRatio for images:

**Before (line 348-350):**
```tsx
            <div
              className="relative group cursor-pointer"
              style={{ aspectRatio: isImage ? "16/10" : "16/9" }}
```

**After:**
```tsx
            <div
              className="relative group cursor-pointer"
              style={isImage ? undefined : { aspectRatio: "16/9" }}
```

3. **Line 368** — Change object-cover to object-contain, remove absolute positioning:

**Before (line 363-371):**
```tsx
                <ImageWithSkeleton
                  src={parsed.s3Url}
                  alt={fileName}
                  skipUrlResolve
                  inline
                  className="absolute inset-0 w-full h-full object-cover z-[1] rounded-lg"
                  onLoad={() => setMediaLoaded(true)}
                  onError={() => setMediaLoaded(true)}
                />
```

**After:**
```tsx
                <ImageWithSkeleton
                  src={parsed.s3Url}
                  alt={fileName}
                  skipUrlResolve
                  inline
                  className="w-full h-auto object-contain z-[1] rounded-lg"
                  onLoad={() => setMediaLoaded(true)}
                  onError={() => setMediaLoaded(true)}
                />
```

Note: Removing `absolute inset-0` is important — with `object-contain` and natural aspect ratio, the image should flow normally (not be absolutely positioned). The parent div also loses its fixed height since we removed the aspectRatio style.

- [ ] **Step 1: Write the failing test**

```typescript
// __tests__/fileRevealItemSizing.test.ts

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("FileRevealItem image sizing", () => {
  const source = readFileSync(
    new URL("../items/FileRevealItem.tsx", import.meta.url),
    "utf8",
  );

  it("adds max-w-md mx-auto for image container", () => {
    expect(source).toContain("isImage && \"max-w-md mx-auto\"");
  });

  it("does not set fixed aspectRatio for images", () => {
    // Should only set aspectRatio for non-images (video)
    expect(source).toContain("isImage ? undefined : { aspectRatio");
    // Should NOT have the old fixed ratio for images
    expect(source).not.toContain('isImage ? "16/10"');
  });

  it("uses object-contain instead of object-cover for images", () => {
    expect(source).toContain("object-contain");
  });

  it("uses w-full h-auto for natural image sizing", () => {
    expect(source).toContain("w-full h-auto object-contain");
  });

  it("does not use absolute positioning for image", () => {
    // The ImageWithSkeleton for images should NOT have absolute inset-0
    // Find the ImageWithSkeleton that has object-contain
    const lines = source.split("\n");
    const objectContainLineIdx = lines.findIndex((l) =>
      l.includes("object-contain"),
    );
    expect(objectContainLineIdx).toBeGreaterThanOrEqual(0);
    // The className with object-contain should NOT contain "absolute inset-0"
    expect(lines[objectContainLineIdx]).not.toContain("absolute inset-0");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/fileRevealItemSizing.test.ts`
Expected: FAIL — assertions don't match current code

- [ ] **Step 3: Apply the 3 changes to FileRevealItem.tsx**

Edit lines 331-336, 348-350, and 363-371 as shown above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/fileRevealItemSizing.test.ts`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd frontend && pnpm test`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ChatMessage/items/FileRevealItem.tsx \
        frontend/src/components/chat/ChatMessage/__tests__/fileRevealItemSizing.test.ts
git commit -m "feat(chat): improve FileRevealItem image sizing - max-w-md, object-contain, natural ratio"
```

---

### Task 5: Improve Markdown image max-width

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/MarkdownContent.tsx:576` (img className)

**Change:**

**Before (line 576):**
```tsx
                className="max-w-full h-auto rounded-lg shadow hover:opacity-90 transition-opacity"
```

**After:**
```tsx
                className="max-w-lg h-auto rounded-lg shadow hover:opacity-90 transition-opacity cursor-zoom-in"
```

Also add `cursor-zoom-in` for consistent affordance (images are clickable).

- [ ] **Step 1: Write the failing test**

```typescript
// __tests__/markdownImageSizing.test.ts

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("MarkdownContent image sizing", () => {
  const source = readFileSync(
    new URL("../MarkdownContent.tsx", import.meta.url),
    "utf8",
  );

  it("limits markdown images to max-w-lg instead of max-w-full", () => {
    // Find the ImageWithSkeleton in the img override — it should have max-w-lg
    // The className on ImageWithSkeleton inside the img renderer
    const imgOverrideSection = source.substring(
      source.indexOf("img: ({ src, alt })"),
      source.indexOf("},\n          // Images"),
    );
    expect(imgOverrideSection).toContain("max-w-lg");
    expect(imgOverrideSection).not.toContain("max-w-full");
  });

  it("preserves h-auto for natural aspect ratio", () => {
    const imgOverrideSection = source.substring(
      source.indexOf("img: ({ src, alt })"),
      source.indexOf("},\n          // Images"),
    );
    expect(imgOverrideSection).toContain("h-auto");
  });

  it("adds cursor-zoom-in for click affordance", () => {
    const imgOverrideSection = source.substring(
      source.indexOf("img: ({ src, alt })"),
      source.indexOf("},\n          // Images"),
    );
    expect(imgOverrideSection).toContain("cursor-zoom-in");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/markdownImageSizing.test.ts`
Expected: FAIL — `max-w-full` found, `max-w-lg` not found

- [ ] **Step 3: Apply the change**

Edit line 576 in `MarkdownContent.tsx` as shown above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/markdownImageSizing.test.ts`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd frontend && pnpm test`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ChatMessage/MarkdownContent.tsx \
        frontend/src/components/chat/ChatMessage/__tests__/markdownImageSizing.test.ts
git commit -m "feat(chat): limit markdown images to max-w-lg with zoom cursor"
```

---

### Task 6: Build verification

- [ ] **Step 1: Run lint**

Run: `cd frontend && pnpm run lint`
Expected: No errors

- [ ] **Step 2: Run build**

Run: `cd frontend && pnpm run build`
Expected: Build succeeds within performance budget

- [ ] **Step 3: Run full test suite**

Run: `cd frontend && pnpm test`
Expected: All pass

- [ ] **Step 4: Visual verification**

Run: `cd frontend && pnpm run dev` then open `http://localhost:3001/chat/4f6da2ac-b4d6-4c1b-81aa-f73cbf227573` and verify:
- Single images are centered, not full-width, fully visible
- Multiple consecutive image reveal_files render in gallery layout
- Markdown images are constrained to max-w-lg
- Click on any image opens the lightbox

- [ ] **Step 5: Final commit if any adjustments needed**
