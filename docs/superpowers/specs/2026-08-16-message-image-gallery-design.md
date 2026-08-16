# Message Image Gallery Design

**Date:** 2026-08-16
**Scope:** reveal_file images + Markdown inline images in chat messages
**Status:** Approved

## Problem

Images in chat messages currently render at full message width with a fixed 16:10 aspect ratio and `object-cover` cropping. This causes:
- Portrait images (e.g., posters, infographics) to be severely cropped, hiding most content
- Every image stretching to fill the entire message width regardless of natural size
- Multiple images stacking vertically with no spatial efficiency

## Solution

Create a `MessageImageGallery` component with adaptive layout based on image count, and improve single-image rendering in both `FileRevealItem` and `MarkdownContent`.

## Scope

- **In scope:** `FileRevealItem` (reveal_file images), `MarkdownContent` (markdown `![]()` images)
- **Out of scope:** `ImageGenerateItem` (has its own grid), user attachment images, `SessionImageGalleryProvider` lightbox

## Component: MessageImageGallery

**File:** `frontend/src/components/chat/ChatMessage/MessageImageGallery.tsx`

### Props

```tsx
interface ImageGalleryItem {
  id: string;
  src: string;
  alt?: string;
  fileName?: string;
}

interface MessageImageGalleryProps {
  images: ImageGalleryItem[];
  onImageClick: (src: string, fileName?: string) => void;
}
```

### Layout Rules

| Image Count | Layout | Details |
|-------------|--------|---------|
| 1 | Centered, `max-w-md` | Single image, natural aspect ratio |
| 2 | `grid grid-cols-2 gap-2` | Side by side, each preserves natural ratio |
| 3 | `grid grid-cols-2 gap-2`, first `col-span-2` | One large + two small |
| 4+ | CSS `columns-2 gap-2` masonry | Auto-arranged by image height |

### Image Card (within gallery)

- Rounded border + overflow hidden (consistent with existing style)
- **No fixed aspectRatio** — image determines its own height
- `object-contain` — shows full image without cropping
- Hover overlay with preview icon (reuse existing ExternalLink style)
- File name as a small bottom label, visible on hover only (compact)
- Click triggers `sessionImageGallery.openImage()` for full lightbox

## FileRevealItem Changes

### Scene A: Single image reveal_file

- Outer container: `w-full` → `max-w-md` (no longer fills message width)
- Image area: remove fixed `style={{ aspectRatio: "16/10" }}`
- Image: `object-cover` → `object-contain`
- Keep file info bar (single image has room for it)

### Scene B: Multiple consecutive image reveal_files

- `MessagePartRenderer` detects consecutive parts that are image-type `reveal_file`
- Collected images passed to `MessageImageGallery`
- `FileRevealItem` in gallery mode provides only image data (src, alt, fileName) — no standalone card
- Gallery renders all cards uniformly (compact, hover filename overlay)

## MessagePartRenderer Grouping Logic

Algorithm:
1. Iterate over `message.parts`
2. When encountering a `reveal_file` part whose resolved file is an image → add to current image group
3. When encountering a non-image part → flush current group (if any) as `MessageImageGallery`, render the non-image part normally
4. After loop, flush any remaining group

Example:
```
parts: [text, reveal_file(img), reveal_file(img), text, reveal_file(img)]
                    ↑ collected as group of 2          ↑ single → independent render (Scene A)
```

## Markdown Image Changes

In `MarkdownContent.tsx` img override:
- `max-w-full` → `max-w-lg` (limit max width, ~512px)
- Keep `h-auto` (already preserves natural aspect ratio)
- Keep `rounded-lg`, `shadow`, `hover:opacity-90` (existing)
- Markdown images do NOT enter the gallery (they are embedded in text flow; extracting them would break reading experience)

## Edge Cases

- **Image load failure:** Reuse `ImageWithSkeleton` error fallback (shows filename)
- **Very large images:** `max-w-md` constraint + `object-contain`, won't break layout
- **Very small images:** Display at natural size, no minimum dimension constraint
- **Mixed content:** Grouping only triggers on consecutive image parts; text/document parts break the group
- **Streaming:** Streaming reveal_file images also enter gallery; gallery grows naturally as new images arrive

## Tests

- `MessageImageGallery.test.tsx`: Verify layout classes for 1/2/3/4+ images
- `FileRevealItem` regression: single image render, click preview, file info bar
- `MessagePartRenderer` grouping: consecutive images grouped, non-image breaks group, mixed parts

## Not Changed

- `ImageGenerateItem` — has its own established grid layout
- `SessionImageGalleryProvider` — lightbox logic unchanged, gallery images auto-collected
- User attachment images — out of scope
