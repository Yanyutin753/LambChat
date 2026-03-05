# Feedback Panel Optimization Design

## Overview

Optimize the FeedbackPanel component to maintain consistency with other panels (UsersPanel, SettingsPanel) and improve mobile responsiveness.

## Goals

1. **Visual Consistency**: Align styling with other panels using shared CSS classes
2. **Mobile Responsiveness**: Implement mobile-optimized card layout
3. **Component Reuse**: Use shared components (Pagination, modal patterns)
4. **Maintainability**: Reduce custom styles in favor of design system

## Current State Analysis

### FeedbackPanel Issues

1. **Header**: Uses custom `px-6 py-4` instead of `panel-header` class
2. **Mobile Layout**: No separate mobile view - same layout on all screen sizes
3. **Delete Modal**: Uses fixed centered modal instead of mobile-friendly bottom sheet
4. **Buttons**: Custom button styles instead of `btn-*` classes
5. **Pagination**: Custom implementation instead of shared `Pagination` component

### Reference Patterns (UsersPanel)

- `panel-header` class for consistent header styling
- Mobile card view (`sm:hidden`) vs desktop view (`hidden sm:block`)
- Bottom sheet modals (`modal-bottom-sheet`) for mobile
- `btn-primary`, `btn-secondary`, `btn-icon` classes
- `panel-card` class for mobile cards
- `tag` classes for status badges
- Shared `Pagination` component

## Design Specification

### 1. Layout Structure

```
┌─────────────────────────────────────────────────┐
│ Header (panel-header)                           │
│ - Title and subtitle                            │
│ - Filter dropdown (integrated)                  │
├─────────────────────────────────────────────────┤
│ Stats Section (grid-cols-2 md:grid-cols-4)      │
│ - Total, Positive, Negative, Rate cards         │
├─────────────────────────────────────────────────┤
│ Feedback List                                   │
│ - Desktop: Card list with horizontal layout     │
│ - Mobile: Stacked cards with compact layout     │
├─────────────────────────────────────────────────┤
│ Pagination (shared component)                   │
└─────────────────────────────────────────────────┘
```

### 2. Component Changes

#### Header Section

```tsx
<div className="panel-header">
  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <div className="flex items-center gap-3">
      <div>
        <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100">
          {t("feedback.title")}
        </h1>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
          {t("feedback.subtitle")}
        </p>
      </div>
    </div>
    {/* Filter dropdown */}
    <div className="relative">
      <select className="panel-search w-full sm:w-48">
        ...
      </select>
    </div>
  </div>
</div>
```

#### Stats Section (keep existing, adjust padding)

```tsx
<div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 sm:p-4 sm:gap-4 bg-gray-50 dark:bg-stone-800/50">
  {/* Stat cards - reduce padding on mobile */}
</div>
```

#### Desktop Feedback Card

```tsx
<div className="hidden sm:block space-y-4">
  {feedbackList.map((feedback) => (
    <div className="panel-card flex items-start justify-between gap-4">
      {/* User info, rating, comment, delete button */}
    </div>
  ))}
</div>
```

#### Mobile Feedback Card

```tsx
<div className="sm:hidden space-y-3">
  {feedbackList.map((feedback) => (
    <div className="panel-card">
      {/* Compact layout: user + rating in header, comment below */}
    </div>
  ))}
</div>
```

#### Delete Modal (Bottom Sheet)

```tsx
function DeleteConfirmModal({ ... }) {
  return (
    <>
      <div className="fixed inset-0" onClick={onCancel} />
      <div className="modal-bottom-sheet sm:modal-centered-wrapper">
        <div className="modal-bottom-sheet-content sm:modal-centered-content">
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Modal content */}
        </div>
      </div>
    </>
  );
}
```

#### Pagination

```tsx
import { Pagination } from "../common/Pagination";

<Pagination
  page={currentPage}
  pageSize={limit}
  total={total}
  onChange={setPage}
/>
```

### 3. CSS Class Mappings

| Current | New |
|---------|-----|
| Custom header div | `panel-header` |
| Custom card styles | `panel-card` |
| Custom button styles | `btn-primary`, `btn-secondary`, `btn-icon` |
| Custom select styles | `panel-search` |
| Custom status badge | `tag tag-success`, `tag tag-error` |
| Fixed modal | `modal-bottom-sheet` |

### 4. Mobile Responsiveness Breakpoints

- `sm:hidden` - Mobile-only elements
- `hidden sm:block` - Desktop-only elements
- `p-3 sm:p-4` - Responsive padding
- `gap-3 sm:gap-4` - Responsive gaps
- `text-sm sm:text-base` - Responsive text (if needed)

## Implementation Checklist

1. [ ] Update header to use `panel-header` class
2. [ ] Move filter into header section
3. [ ] Adjust stats section padding for mobile
4. [ ] Create separate mobile card layout
5. [ ] Create separate desktop card layout
6. [ ] Update delete modal to use bottom sheet pattern
7. [ ] Replace custom pagination with shared component
8. [ ] Update button styles to use `btn-*` classes
9. [ ] Update rating badge to use `tag` classes
10. [ ] Test on mobile and desktop viewports

## Files to Modify

- `frontend/src/components/panels/FeedbackPanel.tsx` - Main component

## Dependencies

- No new dependencies required
- Uses existing shared components and CSS classes
