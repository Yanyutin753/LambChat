# Rich Composer File Paste Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore file and image paste uploads in the Lexical chat composer while preserving the former file-first clipboard behavior.

**Architecture:** Add a focused `FilePastePlugin` that owns Lexical `PASTE_COMMAND` events containing files and delegates validation/upload to callbacks supplied by `ChatInput`. Keep text-only paste under the existing Lexical and long-text plugin paths, and keep all file processing inside `useFileUpload`.

**Tech Stack:** React 19, TypeScript, Lexical 0.49, Vitest, Testing Library

---

## File structure

- Create `frontend/src/components/chat/richComposer/FilePastePlugin.tsx`: register and handle file-bearing Lexical paste commands only.
- Create `frontend/src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`: behavior-level regression coverage for images, multiple files, mixed clipboard data, rejected counts, and text fallthrough.
- Modify `frontend/src/components/chat/richComposer/RichChatComposer.tsx`: define and expose the file-paste callback contract.
- Modify `frontend/src/components/chat/richComposer/RichComposerPlugins.tsx`: mount `FilePastePlugin` when file-paste options are supplied.
- Modify `frontend/src/components/chat/ChatInput.tsx`: pass the existing `validateCount` and `uploadFiles` functions into the rich composer.
- Modify `frontend/src/components/chat/__tests__/chatInputLongTextSource.test.ts`: verify the application-level callback wiring remains present.

### Task 1: Add failing editor and wiring regression tests

**Files:**
- Create: `frontend/src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`
- Modify: `frontend/src/components/chat/__tests__/chatInputLongTextSource.test.ts`

- [ ] **Step 1: Write the editor behavior tests against the desired `filePaste` API**

Create a jsdom suite that renders `RichChatComposer` with:

```tsx
const validateCount = vi.fn(() => true);
const onFiles = vi.fn();

render(
  <RichChatComposer
    ariaLabel="message"
    filePaste={{ validateCount, onFiles }}
  />,
);
```

Dispatch cancelable paste events carrying `clipboardData.files` and assert:

```ts
expect(event.defaultPrevented).toBe(true);
expect(validateCount).toHaveBeenCalledWith(files.length);
expect(onFiles).toHaveBeenCalledWith(files);
```

Cover these separate behaviors:

- an image plus accompanying plain text uploads the image and does not activate `LongTextPastePlugin`;
- multiple files are forwarded as one collection;
- rejected count validation consumes the paste without calling `onFiles`;
- a text-only long paste falls through and is handled by `LongTextPastePlugin`.

For both the mixed file-and-text case and the rejected-count case, explicitly
assert that no clipboard text is inserted into the editor.

- [ ] **Step 2: Add an application wiring assertion**

Extend `chatInputLongTextSource.test.ts` with a focused assertion that
`ChatInput` supplies both callbacks:

```ts
expect(chatInputSource).toMatch(
  /filePaste=\{\{\s*validateCount,\s*onFiles: uploadFiles,?\s*\}\}/,
);
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx src/components/chat/__tests__/chatInputLongTextSource.test.ts
```

Expected: FAIL because `RichChatComposerProps` has no `filePaste` contract and `ChatInput` does not supply it. Confirm failures are caused by the missing behavior rather than test setup or syntax.

### Task 2: Implement the minimal Lexical file-paste path

**Files:**
- Create: `frontend/src/components/chat/richComposer/FilePastePlugin.tsx`
- Modify: `frontend/src/components/chat/richComposer/RichChatComposer.tsx`
- Modify: `frontend/src/components/chat/richComposer/RichComposerPlugins.tsx`
- Modify: `frontend/src/components/chat/ChatInput.tsx`
- Test: `frontend/src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx`
- Test: `frontend/src/components/chat/__tests__/chatInputLongTextSource.test.ts`

- [ ] **Step 1: Define the composer option contract**

In `RichChatComposer.tsx`, add:

```ts
export interface FilePasteOptions {
  validateCount: (count: number) => boolean;
  onFiles: (files: FileList | File[]) => void;
}
```

Add `filePaste?: FilePasteOptions` to `RichChatComposerProps`, destructure it,
and forward it to `RichComposerPlugins`.

- [ ] **Step 2: Implement the focused plugin**

Create `FilePastePlugin.tsx` with the minimal command handler:

```tsx
export function FilePastePlugin({ options }: { options: FilePasteOptions }) {
  const [editor] = useLexicalComposerContext();

  useEffect(
    () =>
      editor.registerCommand(
        PASTE_COMMAND,
        (event) => {
          if (!("clipboardData" in event) || !event.clipboardData) return false;
          const files = event.clipboardData.files;
          if (files.length === 0) return false;

          event.preventDefault();
          if (options.validateCount(files.length)) options.onFiles(files);
          return true;
        },
        COMMAND_PRIORITY_HIGH,
      ),
    [editor, options],
  );

  return null;
}
```

Do not parse clipboard items, infer categories, compress files, or add upload
state here; those remain responsibilities of the existing upload hook.

- [ ] **Step 3: Register the plugin and wire ChatInput**

In `RichComposerPlugins.tsx`, accept `filePaste?: FilePasteOptions` and render:

```tsx
{filePaste ? <FilePastePlugin options={filePaste} /> : null}
```

In `ChatInput.tsx`, pass:

```tsx
filePaste={{ validateCount, onFiles: uploadFiles }}
```

Keep `LongTextPastePlugin` unchanged: it already returns `false` for file
payloads and continues to own text-only long paste.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx src/components/chat/__tests__/chatInputLongTextSource.test.ts
```

Expected: both files PASS with no warnings or unhandled errors.

- [ ] **Step 5: Run adjacent rich-composer tests**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/longTextFileWorkflow.test.tsx src/components/chat/richComposer/__tests__/RichChatComposer.test.tsx
```

Expected: PASS, proving text paste and the base composer remain unchanged.

- [ ] **Step 6: Commit the tested repair**

```bash
git add frontend/src/components/chat/ChatInput.tsx frontend/src/components/chat/__tests__/chatInputLongTextSource.test.ts frontend/src/components/chat/richComposer/FilePastePlugin.tsx frontend/src/components/chat/richComposer/RichChatComposer.tsx frontend/src/components/chat/richComposer/RichComposerPlugins.tsx frontend/src/components/chat/richComposer/__tests__/filePasteWorkflow.test.tsx
git commit -m "fix(chat): restore file paste uploads"
```

### Task 3: Complete frontend verification

**Files:**
- Verify only; no planned source changes.

- [ ] **Step 1: Run the complete frontend test suite**

Run: `cd frontend && pnpm test`

Expected: all Vitest suites pass.

- [ ] **Step 2: Run frontend lint**

Run: `cd frontend && pnpm run lint`

Expected: ESLint exits successfully with no errors.

- [ ] **Step 3: Run the production build**

Run: `cd frontend && pnpm run build`

Expected: TypeScript and Vite production build exit successfully.

- [ ] **Step 4: Inspect the final diff and repository state**

Run:

```bash
git diff HEAD^ --check
git status --short
git log -3 --oneline
```

Expected: no whitespace errors; only the planned commits and no unrelated
working-tree changes.
