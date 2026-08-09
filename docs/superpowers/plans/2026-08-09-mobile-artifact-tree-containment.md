# Mobile Artifact Tree Containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep nested artifact-folder rows and their right-side controls inside the mobile “All files” panel.

**Architecture:** Preserve the existing recursive `TreeDirRow` component and establish an explicit horizontal containment chain from the panel scroll region through each recursive directory wrapper. The existing flexible name button will absorb constrained width and truncate the label while the download and chevron buttons remain non-shrinking siblings.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library

## Global Constraints

- Preserve the current tree hierarchy, desktop indentation, download behavior, expansion behavior, and file-preview behavior.
- Long directory names remain single-line and truncated.
- Folder icons, download buttons, and expansion buttons do not shrink.
- The panel must not gain horizontal scrolling.
- Do not change artifact data structures, translations, or persistent-sidebar public interfaces.

---

### Task 1: Bound Recursive Artifact Tree Width

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/RevealArtifactsSummary.tsx:230-312,618-649`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx`

**Interfaces:**
- Consumes: existing `TreeDirRow`, `openAllFilesPanel`, and folder download/expansion controls.
- Produces: a rendered containment chain whose scroll region, directory nodes, rows, and recursive child wrappers can shrink to the panel width without changing component props.

- [ ] **Step 1: Add the failing nested-directory containment test**

Add this focused test after the existing folder placement test:

```tsx
test("keeps long nested folder rows inside the panel width boundary", () => {
  const longFolderName = "3cd5f740-c3d3-4556-b1d7-5bb3b601e20a";
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: `/workspace/${longFolderName}/LambChat/report.pdf`,
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  const folderButton = screen.getByRole("button", { name: longFolderName });
  const folderRow = folderButton.parentElement;
  const folderNode = folderRow?.parentElement;
  const panelScroller = folderRow?.closest(".overflow-y-auto");

  expect(panelScroller).toHaveClass("min-w-0", "max-w-full", "overflow-x-hidden");
  expect(folderNode).toHaveClass("min-w-0", "max-w-full");
  expect(folderRow).toHaveClass("min-w-0", "max-w-full", "overflow-hidden");

  fireEvent.click(folderButton);
  expect(folderRow?.nextElementSibling).toHaveClass("min-w-0", "max-w-full");
  expect(
    screen.getByRole("button", { name: `Export ZIP: ${longFolderName}` }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: `Collapse: ${longFolderName}` }),
  ).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm test src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
```

Expected: FAIL because the panel scroller and recursive folder containers do not yet expose the `min-w-0`, `max-w-full`, and `overflow-x-hidden` containment classes.

- [ ] **Step 3: Implement the minimum containment chain**

In `TreeDirRow`, constrain the node, row, and recursive child wrapper while keeping the current button order:

```tsx
return (
  <div className="min-w-0 max-w-full">
    <div className="group flex min-w-0 max-w-full w-full items-center gap-3 overflow-hidden ...">
      {/* existing folder information, download, and chevron controls */}
    </div>
    {expanded && (
      <div
        className={clsx(
          "min-w-0 max-w-full",
          depth === 0 ? "pl-2" : "pl-4",
        )}
      >
        {/* existing recursive children */}
      </div>
    )}
  </div>
);
```

Constrain the panel scroll region:

```tsx
<div className="min-w-0 max-w-full flex-1 overflow-x-hidden overflow-y-auto p-1.5">
```

Do not alter callbacks, labels, download state, icon sizes, or responsive visibility classes.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
cd frontend && pnpm test src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
```

Expected: all tests in the file pass with no warnings.

- [ ] **Step 5: Run frontend regression verification**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run build
```

Expected: the full Vitest suite and TypeScript/Vite production build pass.

- [ ] **Step 6: Review and commit the implementation**

Run:

```bash
git diff --check
git diff -- frontend/src/components/chat/ChatMessage/RevealArtifactsSummary.tsx frontend/src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
git add frontend/src/components/chat/ChatMessage/RevealArtifactsSummary.tsx frontend/src/components/chat/ChatMessage/__tests__/revealArtifactsDownload.test.tsx
git commit -m "fix(file-panel): contain nested rows on mobile"
```
