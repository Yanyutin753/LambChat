# Document Preview Mobile Action Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give document preview header controls a 32 px button box, uniform 16 px icons, and 10 px mobile spacing without horizontal overflow.

**Architecture:** Add component-scoped toolbar and action-group classes to `DocumentPreviewToolbar`, then use direct-child selectors in `components.css` to override the broad mobile `.flex button` reset only for this toolbar. Keep one 16 px icon-size source for every breakpoint and retain the existing flex-shrinking file-information region as the overflow boundary.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, CSS media queries, Vitest, Testing Library, jsdom

## Global Constraints

- Change only the document preview toolbar, its component styles, and its focused test.
- Keep all actions, handlers, labels, titles, ordering, and focus behavior unchanged.
- Keep the filename and metadata truncating inside the viewport.
- Do not change shared `ToolbarIconButton` defaults or global markdown selectors.

---

### Task 1: Lock and implement the responsive action sizing

**Files:**
- Modify: `frontend/src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx`
- Modify: `frontend/src/components/documents/DocumentPreviewToolbar.tsx:112-151`
- Modify: `frontend/src/styles/components.css:3199-3211`

**Interfaces:**
- Consumes: existing `ToolbarIconButton`, file-information flex sizing, and `sm` breakpoint.
- Produces: `.document-preview-toolbar` and `.document-preview-toolbar-actions` styling hooks.

- [ ] **Step 1: Add the failing layout assertions**

Extend the existing rendered-component test with:

```tsx
const toolbar = title.closest(".document-preview-toolbar");

expect(toolbar).toBeInTheDocument();
expect(toolbarIcons).toHaveLength(8);
toolbarIcons.forEach((icon) => {
  expect(icon).toHaveAttribute("width", "16");
  expect(icon).toHaveAttribute("height", "16");
});
expect(actionGroup).toHaveClass(
  "document-preview-toolbar-actions",
  "gap-2.5",
  "sm:gap-1",
);
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx
```

Expected: FAIL because neither the scoped action sizing nor the uniform icon and gap contract exists.

- [ ] **Step 3: Add the scoped component hooks and responsive utilities**

Update the root and action wrappers:

```tsx
<div
  ref={toolbarRef}
  className="document-preview-toolbar flex items-center gap-1.5 sm:gap-2.5 px-2 sm:px-4 py-2 sm:py-3 border-b border-[var(--theme-border)] overflow-hidden"
>
```

```tsx
<div className="document-preview-toolbar-actions ml-auto flex items-center gap-1 relative z-10 shrink-0">
```

- [ ] **Step 4: Override only document preview toolbar button boxes**

Add near the existing tool-console action rule in `components.css`:

```css
.document-preview-toolbar > button,
.document-preview-toolbar-actions > button {
  width: 2rem;
  height: 2rem;
  min-width: 2rem;
  min-height: 2rem;
}
```

This selector wins over `.flex button` without changing shared or global behavior.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx src/components/documents/__tests__/documentPreviewToolbarStyles.test.ts src/components/documents/__tests__/documentPreviewToolbarCompact.test.ts
```

Expected: all focused document toolbar tests PASS.

- [ ] **Step 6: Run frontend regression checks**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run build
```

Expected: the frontend suite and production build PASS.

- [ ] **Step 7: Inspect and commit the focused change**

Run:

```bash
git diff --check
git diff -- frontend/src/components/documents/DocumentPreviewToolbar.tsx frontend/src/styles/components.css frontend/src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx
git add frontend/src/components/documents/DocumentPreviewToolbar.tsx frontend/src/styles/components.css frontend/src/components/documents/__tests__/documentPreviewToolbarLayout.test.tsx
git commit -m "fix(ui): enlarge mobile preview actions"
```
