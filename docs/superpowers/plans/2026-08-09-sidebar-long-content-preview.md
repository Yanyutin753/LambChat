# Sidebar Long-Content Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the performance-safe sidebar text preview the same readable spacing and typography as normal Markdown in both thinking and subagent panels.

**Architecture:** Keep `SidebarMarkdownContent` as the single owner of the lightweight preview state. Style its plain-text surface with Tailwind utilities; `ThinkingBlock` and `SubagentPanelContent` inherit the change through their existing use of the shared component.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library

## Global Constraints

- Preserve plain-text rendering while streaming or over the preview limit.
- Preserve preview thresholds, truncation, bounded scrolling, the bottom fade, and expand behavior.
- Do not modify normal Markdown rendering, chat-stream cards, or panel structure.
- Preserve all existing uncommitted work in unrelated files.

---

### Task 1: Style the shared lightweight preview surface

**Files:**
- Create: `frontend/src/components/chat/ChatMessage/__tests__/sidebarMarkdownContent.test.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/SidebarMarkdownContent.tsx:31-37`

**Interfaces:**
- Consumes: `SidebarMarkdownContent({ content, isStreaming, expandable })`
- Produces: The existing component API with a padded, Markdown-aligned lightweight preview DOM surface.

- [ ] **Step 1: Write the failing regression test**

```tsx
/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback: string) => fallback,
    }),
  };
});

import { SidebarMarkdownContent } from "../SidebarMarkdownContent";

test("lightweight sidebar preview keeps normal reading-area spacing and typography", () => {
  render(
    <SidebarMarkdownContent
      content={"First preview line\nSecond preview line"}
      isStreaming
    />,
  );

  const preview = screen.getByText(/First preview line/);
  expect(preview).toHaveClass(
    "px-3",
    "py-2",
    "sm:px-4",
    "text-[0.9375rem]",
    "leading-[1.75]",
  );
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/sidebarMarkdownContent.test.tsx
```

Expected: FAIL because the lightweight preview still has `px-0.5 text-sm leading-7` and lacks the intended reading-area classes.

- [ ] **Step 3: Implement the shared preview styling**

Replace the lightweight preview surface classes in `SidebarMarkdownContent.tsx` with:

```tsx
<div className="max-h-[min(58vh,680px)] w-full overflow-auto whitespace-pre-wrap break-words px-3 py-2 text-[0.9375rem] leading-[1.75] text-theme-text-secondary sm:px-4">
  {previewContent}
</div>
```

Keep the surrounding bounded surface, bottom fade, and expand button unchanged. This single shared change covers thinking previews and subagent process previews.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/sidebarMarkdownContent.test.tsx src/components/chat/ChatMessage/__tests__/sidebarLongTextPerformanceSource.test.ts
```

Expected: both test files pass.

- [ ] **Step 5: Run frontend validation**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run build
```

Expected: the frontend test suite and production build pass. If an unrelated failure comes from pre-existing uncommitted files, record it separately with the failing file and error.

- [ ] **Step 6: Review the final diff**

Run:

```bash
git diff --check
git diff -- frontend/src/components/chat/ChatMessage/SidebarMarkdownContent.tsx frontend/src/components/chat/ChatMessage/__tests__/sidebarMarkdownContent.test.tsx
```

Expected: no whitespace errors; the production change is limited to the shared lightweight preview classes, and the regression test exercises the real rendered component.
