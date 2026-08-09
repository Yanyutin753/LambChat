# Folder Download Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place each folder ZIP download button immediately before its expand/collapse chevron without changing download or expansion behavior.

**Architecture:** Keep `TreeDirRow` responsible for its local expanded and downloading state. Render the folder-information toggle, ZIP download action, and chevron toggle as three sibling buttons in one flex row so their DOM order matches their visual order and no buttons are nested.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library

## Global Constraints

- Update only the revealed-artifacts folder row, its focused regression test, and this plan.
- Keep ZIP loading, disabled, error, hover, responsive, and dark-mode behavior unchanged.
- Clicking download must not toggle the folder; clicking the folder information or chevron must toggle the same expanded state.
- Reuse existing `common.expand` and `common.collapse` translations for the chevron's accessible label.

---

### Task 1: Reorder Folder Download and Chevron Controls

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/RevealArtifactsSummary.tsx:215-305`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx`

**Interfaces:**
- Consumes: `TreeDirRow` local `expanded` state, existing `project.exportZip`, `common.expand`, and `common.collapse` translations.
- Produces: Three sibling buttons ordered as folder information, ZIP download, then expand/collapse chevron.

- [ ] **Step 1: Write the failing rendered-layout test**

Add the common translation labels to the existing test mock and add this test after the existing folder-download test:

```tsx
test("folder download appears immediately before the expansion chevron", () => {
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/folder/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  const folderButton = screen.getByRole("button", { name: "folder" });
  const folderDownload = screen.getByRole("button", {
    name: "Export ZIP: folder",
  });
  const folderChevron = screen.getByRole("button", {
    name: "Expand: folder",
  });

  expect(folderButton.nextElementSibling).toBe(folderDownload);
  expect(folderDownload.nextElementSibling).toBe(folderChevron);
});
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
```

Expected: FAIL because there is no separately labelled chevron button and the download follows the combined folder/chevron button.

- [ ] **Step 3: Implement the sibling controls**

Create a shared local toggle callback:

```tsx
const toggleExpanded = () => setExpanded((value) => !value);
```

Remove `ChevronRight` from the folder-information button, use `toggleExpanded` for that button, retain the ZIP button unchanged, then append:

```tsx
<button
  type="button"
  aria-expanded={expanded}
  aria-label={`${t(expanded ? "common.collapse" : "common.expand")}: ${node.name}`}
  onClick={toggleExpanded}
  className="shrink-0 rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-700 dark:hover:text-stone-300"
>
  <ChevronRight
    size={18}
    className={clsx(
      "transition-transform duration-200",
      expanded && "rotate-90",
    )}
  />
</button>
```

- [ ] **Step 4: Run the focused test to verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
```

Expected: all tests in the file PASS.

- [ ] **Step 5: Run proportional verification**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx src/components/chat/ChatMessage/__tests__/revealArtifactsSummary.test.ts
cd frontend && pnpm run build
git diff --check
```

Expected: both Vitest files pass, the frontend build succeeds, and `git diff --check` produces no output.

- [ ] **Step 6: Commit the implementation**

```bash
git add frontend/src/components/chat/ChatMessage/RevealArtifactsSummary.tsx frontend/src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx docs/superpowers/plans/2026-08-09-folder-download-placement.md
git commit -m "fix(file-panel): place folder download before chevron"
```
