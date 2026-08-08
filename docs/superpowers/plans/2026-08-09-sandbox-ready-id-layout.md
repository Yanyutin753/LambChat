# Sandbox Ready ID Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the sandbox ID directly after the ready label while retaining the same ID and elapsed time in the expanded details.

**Architecture:** Keep `CollapsiblePill.label` responsible for the localized ready text and use its existing `suffix` slot for the localized sandbox ID. Leave the expanded-detail rendering unchanged so the ID remains available in both places without changing events, translations, or shared component APIs.

**Tech Stack:** React 19, TypeScript, react-i18next, Tailwind CSS, Vitest, Testing Library

## Global Constraints

- Only change `SandboxItem` rendering and its focused regression test.
- Do not modify sandbox events, translation keys, or the `CollapsiblePill` public interface.
- Preserve the existing expanded sandbox ID and elapsed-time details.
- Preserve the current starting, error, cancelled, and missing-ID behavior.
- Render the ID in a truncating monospace suffix so long IDs do not expand the message area beyond its available width.

---

### Task 1: Show the sandbox ID in the ready pill

**Files:**
- Create: `frontend/src/components/chat/ChatMessage/__tests__/SandboxItem.test.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/SandboxItem.tsx`

**Interfaces:**
- Consumes: `CollapsiblePillProps.suffix?: React.ReactNode` and the existing `chat.sandboxId` translation key.
- Produces: `SandboxItem` ready-state output containing the sandbox ID in the collapsed pill and the unchanged expanded details.

- [x] **Step 1: Write the failing component test**

Create `frontend/src/components/chat/ChatMessage/__tests__/SandboxItem.test.tsx`:

```tsx
/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, string>) => {
        if (key === "chat.sandbox.ready") return "Sandbox ready";
        if (key === "chat.sandboxId") return `ID: ${values?.id}`;
        if (key === "chat.sandbox.elapsed") {
          return `Elapsed ${values?.duration}`;
        }
        return key;
      },
    }),
  };
});

import { SandboxItem } from "../SandboxItem";

test("ready sandbox shows its ID in the pill and keeps it in expanded details", () => {
  render(
    <SandboxItem
      status="ready"
      sandboxId="SBX-AbC123"
      startedAt="2026-08-09T00:00:00.000Z"
      completedAt="2026-08-09T00:00:01.000Z"
    />,
  );

  expect(screen.getByText("ID: SBX-AbC123")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /sandbox ready/i }));

  expect(screen.getAllByText("ID: SBX-AbC123")).toHaveLength(2);
  expect(screen.getByText("Elapsed 1s")).toBeInTheDocument();
});
```

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/ChatMessage/__tests__/SandboxItem.test.tsx
```

Expected: FAIL before the click because `ID: SBX-AbC123` is not rendered in the collapsed ready pill.

- [x] **Step 3: Add the ID suffix with the existing translation**

Add this prop to the existing `CollapsiblePill` in `SandboxItem.tsx`, after `label` and before `expandable`:

```tsx
suffix={
  status === "ready" && sandboxId ? (
    <span className="text-xs font-mono font-medium min-w-0 truncate overflow-hidden leading-none">
      {t("chat.sandboxId", { id: sandboxId })}
    </span>
  ) : undefined
}
```

Do not remove or alter the existing expanded-detail block that renders `chat.sandboxId` and `chat.sandbox.elapsed`.

- [x] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/ChatMessage/__tests__/SandboxItem.test.tsx
```

Expected: PASS with one ID visible before expansion, two identical IDs after expansion, and `Elapsed 1s` visible after expansion.

- [x] **Step 5: Run frontend regression checks**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: all Vitest tests pass, ESLint exits successfully, and the TypeScript/Vite build completes successfully.

- [x] **Step 6: Commit the focused implementation**

```bash
git add frontend/src/components/chat/ChatMessage/SandboxItem.tsx frontend/src/components/chat/ChatMessage/__tests__/SandboxItem.test.tsx docs/superpowers/plans/2026-08-09-sandbox-ready-id-layout.md
git commit -m "feat: show sandbox id in ready pill"
```
