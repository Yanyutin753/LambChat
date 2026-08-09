# CJK Markdown Rendering Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every frontend Markdown renderer correctly parse CJK-adjacent bold, italic, and GFM strikethrough syntax without requiring whitespace.

**Architecture:** Add the two CJK parser extensions as direct frontend dependencies and centralize their required order in one shared remark plugin list. Keep the three existing `ReactMarkdown` entry points and their renderer-specific plugins/components intact, then enforce shared configuration with behavioral and source-completeness regression tests.

**Tech Stack:** React 19, TypeScript, react-markdown, remark-gfm, remark-cjk-friendly, remark-cjk-friendly-gfm-strikethrough, Vitest, React DOM server rendering, pnpm.

---

## File Structure

- Create `frontend/src/components/common/markdownRemarkPlugins.ts`: own the ordered GFM/CJK parser extension list.
- Create `frontend/src/components/common/__tests__/markdownRendererSources.test.ts`: ensure every direct `ReactMarkdown` entry point uses the shared list.
- Modify `frontend/src/components/layout/AppContent/__tests__/TaskToastMarkdown.test.tsx`: behavior regressions for all supported CJK delimiter variants.
- Modify `frontend/src/components/layout/AppContent/TaskToastMarkdown.tsx`: use the shared base plugins.
- Modify `frontend/src/components/chat/ChatMessage/MarkdownContent.tsx`: use the shared base plus its existing breaks/math plugins.
- Modify `frontend/src/components/panels/ApprovalPanel.tsx`: use the shared base plus its existing breaks plugin.
- Modify `frontend/package.json` and `frontend/pnpm-lock.yaml`: declare and lock both CJK parser extensions directly.

### Task 1: Prove and Fix CJK Inline Markdown Behavior

**Files:**
- Modify: `frontend/src/components/layout/AppContent/__tests__/TaskToastMarkdown.test.tsx`
- Create: `frontend/src/components/common/markdownRemarkPlugins.ts`
- Modify: `frontend/src/components/layout/AppContent/TaskToastMarkdown.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`

- [ ] **Step 1: Add the failing CJK behavior matrix**

Extend `TaskToastMarkdown.test.tsx` with a `test.each` matrix that server-renders no-space Markdown and expects semantic output:

```tsx
test.each([
  ["中文星号粗体", "提出到**锻炼人数达40%**左右", "strong", "锻炼人数达40%"],
  ["中文标点边界粗体", "这是**（重要）**内容", "strong", "（重要）"],
  ["日文星号斜体", "これは*（重要）*です", "em", "（重要）"],
  ["韩文标点边界斜体", "이것은*강조.*입니다", "em", "강조."],
  ["中文删除线", "提出到~~锻炼人数达40%~~左右", "del", "锻炼人数达40%"],
])("renders CJK-adjacent %s", (_name, markdown, tag, text) => {
  const html = renderToStaticMarkup(<TaskToastMarkdown content={markdown} />);
  expect(html).toContain(`<${tag}>${text}</${tag}>`);
});
```

If a specific example is already valid under plain CommonMark, replace only that fixture with an equivalent CJK punctuation-boundary case that fails for the intended missing extension; do not weaken the semantic assertion.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/TaskToastMarkdown.test.tsx
```

Expected: the new CJK cases fail because the HTML still contains literal delimiter text instead of the expected semantic elements.

- [ ] **Step 3: Add direct dependencies**

Run:

```bash
cd frontend && pnpm add remark-cjk-friendly@^2.3.1 remark-cjk-friendly-gfm-strikethrough@^2.3.1
```

Confirm `frontend/package.json` and `frontend/pnpm-lock.yaml` are updated and no unrelated package versions are changed.

- [ ] **Step 4: Add the shared ordered plugin list**

Create `markdownRemarkPlugins.ts`:

```ts
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import remarkCjkFriendlyGfmStrikethrough from "remark-cjk-friendly-gfm-strikethrough/parseOnly";
import remarkGfm from "remark-gfm";

export const cjkGfmRemarkPlugins = [
  remarkGfm,
  remarkCjkFriendly,
  remarkCjkFriendlyGfmStrikethrough,
] as const;
```

Keep the strikethrough parser after `remarkGfm`; this ordering is required by the package.

- [ ] **Step 5: Use the shared plugins in task toasts**

Replace the direct `remarkGfm` import in `TaskToastMarkdown.tsx` with `cjkGfmRemarkPlugins`, and pass a mutable spread to `ReactMarkdown`:

```tsx
remarkPlugins={[...cjkGfmRemarkPlugins]}
```

- [ ] **Step 6: Run the focused test and verify GREEN**

Run the TaskToast test again. Expected: all existing tests and the new CJK matrix pass without warnings.

- [ ] **Step 7: Commit the behavior fix**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml \
  frontend/src/components/common/markdownRemarkPlugins.ts \
  frontend/src/components/layout/AppContent/TaskToastMarkdown.tsx \
  frontend/src/components/layout/AppContent/__tests__/TaskToastMarkdown.test.tsx
git commit -m "fix: support CJK markdown delimiters"
```

### Task 2: Apply and Enforce the Shared Configuration Everywhere

**Files:**
- Create: `frontend/src/components/common/__tests__/markdownRendererSources.test.ts`
- Modify: `frontend/src/components/chat/ChatMessage/MarkdownContent.tsx`
- Modify: `frontend/src/components/panels/ApprovalPanel.tsx`

- [ ] **Step 1: Add the failing renderer-completeness test**

Create this source test so the guard scans every TSX file under `frontend/src`, including future renderers outside `components/`:

```ts
import { readdirSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function listTsxFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return listTsxFiles(path);
    return entry.isFile() && entry.name.endsWith(".tsx") ? [path] : [];
  });
}

const sourceRoot = fileURLToPath(new URL("../../../", import.meta.url));
const directRenderers = listTsxFiles(sourceRoot)
  .map((path) => ({
    path: relative(sourceRoot, path),
    source: readFileSync(path, "utf8"),
  }))
  .filter(({ source }) => source.includes("<ReactMarkdown"));

test("tracks every direct ReactMarkdown renderer", () => {
  expect(directRenderers.map(({ path }) => path).sort()).toEqual([
    "components/chat/ChatMessage/MarkdownContent.tsx",
    "components/layout/AppContent/TaskToastMarkdown.tsx",
    "components/panels/ApprovalPanel.tsx",
  ]);
});

test.each(directRenderers)(
  "$path uses the shared CJK remark configuration",
  ({ path, source }) => {
    expect(source, path).toContain("...cjkGfmRemarkPlugins");
  },
);
```

This makes a newly added direct entry point fail until its CJK configuration is intentional.

- [ ] **Step 2: Run the completeness test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/common/__tests__/markdownRendererSources.test.ts
```

Expected: failures identify `MarkdownContent.tsx` and `ApprovalPanel.tsx` as missing the shared plugin list.

- [ ] **Step 3: Update the rich chat/document renderer**

Remove its direct `remarkGfm` import, import `cjkGfmRemarkPlugins`, and preserve the existing additional plugin order:

```tsx
remarkPlugins={[
  ...cjkGfmRemarkPlugins,
  remarkBreaks,
  remarkMath,
]}
```

Do not change code-fence normalization, rehype plugins, component mappings, or styling.

- [ ] **Step 4: Update approval messages**

Remove the direct `remarkGfm` import, import `cjkGfmRemarkPlugins`, and retain line-break behavior:

```tsx
remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks]}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- \
  src/components/common/__tests__/markdownRendererSources.test.ts \
  src/components/layout/AppContent/__tests__/TaskToastMarkdown.test.tsx \
  src/components/chat/ChatMessage/__tests__/sidebarMarkdownContent.test.tsx
```

Expected: all focused tests pass without warnings.

- [ ] **Step 6: Commit the full renderer coverage**

```bash
git add frontend/src/components/common/__tests__/markdownRendererSources.test.ts \
  frontend/src/components/chat/ChatMessage/MarkdownContent.tsx \
  frontend/src/components/panels/ApprovalPanel.tsx
git commit -m "fix: apply CJK markdown parsing everywhere"
```

### Task 3: Full Frontend Verification

**Files:**
- Verify only; modify implementation files only if a verification failure is directly caused by this change.

- [ ] **Step 1: Run all frontend tests**

```bash
cd frontend && pnpm test
```

Expected: Vitest exits zero with all tests passing.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && pnpm run lint
```

Expected: ESLint exits zero.

- [ ] **Step 3: Run the production build**

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite build exit zero. Existing non-fatal chunk-size notices may be reported separately but must not be presented as failures.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff 3d034ee5..HEAD --check
git diff 3d034ee5..HEAD --stat
git status --short
```

Confirm only the approved dependencies, shared plugin module, three direct renderers, regression tests, and design/plan documentation changed.

- [ ] **Step 5: Record verification evidence**

Report exact test counts and command results. Do not claim completion if any focused regression, full test, lint, or build command fails.
