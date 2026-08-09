# Flat Mobile Tool Console Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the tool result panel's view and close controls as independent 32 px icon buttons with 4 px spacing on mobile and desktop.

**Architecture:** Keep the shared `ToolbarIconButton` defaults intact and scope the compact dimensions to direct button children of `ToolResultPanel`'s `.tool-console-actions` wrapper. Use existing utility classes for the wrapper layout and existing button variants for hover, active, and focus feedback.

**Tech Stack:** React 19, TypeScript, Tailwind CSS utilities, project component CSS, Vitest source-structure tests

---

## File Map

- Modify `frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts`: define the compact, flat action-group regression contract.
- Modify `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx`: make both action wrappers use one breakpoint-independent 4 px gap.
- Modify `frontend/src/styles/components.css`: remove capsule styling and scope 32 px dimensions to action-wrapper button children.

### Task 1: Lock the Compact Flat Action Contract

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts:144-175`
- Read: `frontend/src/components/common/ui/ToolbarIconButton.tsx`

- [ ] **Step 1: Replace the obsolete capsule assertion with a focused failing test**

Add a test that reads `ToolResultPanel.tsx`, `components.css`, and `ToolbarIconButton.tsx`, then asserts:

```ts
test("tool result actions stay compact and flat at every breakpoint", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const componentsSource = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  const toolbarButtonSource = readFileSync(
    new URL("../../../../common/ui/ToolbarIconButton.tsx", import.meta.url),
    "utf8",
  );

  expect(
    componentSource.match(
      /className="tool-console-actions flex items-center gap-1 shrink-0"/g,
    ),
  ).toHaveLength(2);
  expect(componentsSource).not.toMatch(/\.tool-console-actions\s*\{/);
  expect(componentsSource).toMatch(
    /\.tool-console-actions\s*>\s*button\s*\{[\s\S]*?width:\s*2rem;[\s\S]*?height:\s*2rem;[\s\S]*?min-width:\s*0;[\s\S]*?min-height:\s*0;/,
  );
  expect(toolbarButtonSource).toMatch(
    /min-h-\[44px\] min-w-\[44px\] sm:size-8 sm:min-h-0 sm:min-w-0/,
  );
});
```

In the existing professional chrome test, remove the assertion requiring `.tool-console-actions` to contain a background declaration because the approved design explicitly removes it.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts
```

Expected: FAIL because the wrappers still use `gap-2 sm:gap-1`, the capsule rule still exists, and the scoped button-size rule does not.

### Task 2: Implement the Scoped Flat Styling

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx:530-587`
- Modify: `frontend/src/styles/components.css:3205-3211`

- [ ] **Step 1: Use the desktop gap at every breakpoint**

Change both action wrappers to:

```tsx
<div className="tool-console-actions flex items-center gap-1 shrink-0">
```

- [ ] **Step 2: Remove the capsule and scope compact dimensions**

Replace the `.tool-console-actions` capsule block with:

```css
.tool-console-actions > button {
  width: 2rem;
  height: 2rem;
  min-width: 0;
  min-height: 0;
}
```

Do not change `ToolbarIconButton.tsx`; its 44 px mobile defaults remain available everywhere else.

- [ ] **Step 3: Run the focused test to verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts
```

Expected: all tests in `ToolResultPanel.test.ts` PASS with no warnings or errors.

- [ ] **Step 4: Commit the focused behavior change**

```bash
git add frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx frontend/src/styles/components.css
git commit -m "fix: flatten tool console actions on mobile"
```

### Task 3: Verify Frontend Regression Safety

**Files:**
- Verify only; no planned file changes.

- [ ] **Step 1: Run the complete frontend test suite**

Run:

```bash
cd frontend && pnpm test
```

Expected: PASS. If an unrelated pre-existing failure occurs, reproduce it independently and report it separately instead of changing unrelated code.

- [ ] **Step 2: Run the production frontend build**

Run:

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff HEAD^ -- frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx frontend/src/styles/components.css
git status --short
```

Expected: only the compact action-group test, wrapper gap, and scoped action-button CSS changed; the user's unrelated untracked design document remains untouched.
