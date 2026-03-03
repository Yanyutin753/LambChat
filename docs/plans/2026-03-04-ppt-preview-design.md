# PPT Preview Design

## Overview

Improve PPT preview by using local rendering for `.pptx` files while keeping Office Online for legacy `.ppt` files.

## Goals

- Remove dependency on external services for `.pptx` files
- Provide better interactivity (zoom, pan, touch gestures) like Mermaid preview
- Support mobile devices with touch gestures
- Maintain backward compatibility for `.ppt` files

## Design

### File Type Handling

| Format | Preview Method | Reason |
|--------|----------------|--------|
| `.ppt` | Office Online (iframe) | No pure frontend library supports old format |
| `.pptx` | `pptx-preview` local rendering | Full-featured, supports interaction |

### PptPreview Component Features (for .pptx)

1. **Slide Navigation**
   - Thumbnail sidebar on the left
   - Click thumbnail to switch slides
   - Previous/Next buttons

2. **Zoom & Pan**
   - Mouse wheel zoom
   - Two-finger pinch zoom (mobile)
   - Mouse drag to pan
   - Touch drag to pan

3. **Mobile Support**
   - Responsive layout
   - Touch gestures
   - Collapsible thumbnail sidebar

4. **Toolbar**
   - Slide counter (e.g., "3 / 10")
   - Zoom controls (+ / - / percentage)
   - Fit to screen button
   - Fullscreen toggle

### Data Flow

```typescript
interface PptPreviewProps {
  url: string;           // For .ppt (Office Online)
  arrayBuffer?: ArrayBuffer;  // For .pptx (pptx-preview)
  fileName: string;      // To determine file type
}
```

### Component Structure

```
PptPreview.tsx
├── .ppt path
│   └── iframe (Office Online)
└── .pptx path
    ├── ThumbnailSidebar
    ├── SlideViewer
    │   └── pptx-preview canvas
    └── Toolbar
        ├── Navigation
        ├── Zoom controls
        └── Fullscreen
```

### Dependencies

- `pptx-preview` - For .pptx rendering

## Implementation Notes

1. Lazy load `pptx-preview` library (~size TBD)
2. Reuse zoom/pan logic from MermaidDiagram component
3. Update `utils.ts` to distinguish `.ppt` vs `.pptx`
4. Update `DocumentPreview.tsx` to pass `arrayBuffer` for pptx files
