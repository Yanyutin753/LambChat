# Rich Chat Composer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat textarea with a plain-text-first Lexical composer that supports inline file-reference and Skill nodes without disrupting ordinary writing.

**Architecture:** One Lexical editor document owns text order and rich-node order. Pure projection and registry modules derive the submitted message, active attachments, per-run Skills, and undo-aware attachment state; focused plugins integrate slash commands, long-text paste, keyboard behavior, and the normal/expanded layouts.

**Tech Stack:** React 19.2.5, TypeScript 5.6, Lexical 0.49.0, Vitest 4, Testing Library, jsdom, Tailwind CSS

## Global Constraints

- Normal text, line breaks, Markdown, IME composition, paste below the existing threshold, and send shortcuts retain current behavior.
- No WYSIWYG formatting toolbar or general rich-text formatting is introduced.
- A command slash triggers only at document start or after whitespace; embedded slashes and a second slash in the token do not open the popup.
- Only converted long-text paste automatically inserts a file-reference node; ordinary uploads remain card-only.
- File and Skill nodes are atomic, keyboard accessible, localized, and synchronized with their business state and undo/redo.
- The normal and expanded layouts use the same Lexical editor state.
- Legacy string history and `pendingInput` remain compatible.
- No backend attachment-schema change is permitted.

---

### Task 1: Lexical dependencies and pure composer contracts

**Files:**
- Modify: `frontend/package.json`
- Modify: `pnpm-lock.yaml`
- Create: `frontend/src/components/chat/richComposer/composerTypes.ts`
- Create: `frontend/src/components/chat/richComposer/composerProjection.ts`
- Create: `frontend/src/components/chat/richComposer/slashTrigger.ts`
- Create: `frontend/src/components/chat/richComposer/composerHistory.ts`
- Create: `frontend/src/components/chat/richComposer/__tests__/composerProjection.test.ts`
- Create: `frontend/src/components/chat/richComposer/__tests__/slashTrigger.test.ts`
- Create: `frontend/src/components/chat/richComposer/__tests__/composerHistory.test.ts`

**Interfaces:**
- Produces: `ComposerSnapshot`, `ComposerProjection`, `FileReferenceDescriptor`, `SkillReferenceDescriptor`, `projectComposerSnapshot(snapshot)`, `findSlashTrigger(text, caretOffset)`, `decodeComposerHistoryEntry(value)`.
- Consumes: no application UI; these are pure contracts used by every later task.

- [x] **Step 1: Install exact compatible Lexical packages**

Run:

```bash
cd frontend && pnpm add --save-exact lexical@0.49.0 @lexical/react@0.49.0 @lexical/history@0.49.0 @lexical/plain-text@0.49.0 @lexical/utils@0.49.0
```

Expected: `package.json` and `pnpm-lock.yaml` record `0.49.0` for each direct package and preserve React 19.2.5.

- [x] **Step 2: Write failing pure contract tests**

Use literal serialized fixtures. The projection test must prove text order and business projections independently:

```ts
const snapshot = {
  version: 1,
  editorState: {
    root: {
      type: "root",
      version: 1,
      children: [{
        type: "paragraph",
        version: 1,
        children: [
          { type: "text", version: 1, text: "请总结 ", detail: 0, format: 0, mode: "normal", style: "" },
          { type: "file-reference", version: 1, referenceId: "ref-1", fileName: "notes.txt", category: "document", status: "ready" },
          { type: "text", version: 1, text: " 并使用 ", detail: 0, format: 0, mode: "normal", style: "" },
          { type: "skill-reference", version: 1, skillName: "writer", tags: ["writing"] },
          { type: "skill-reference", version: 1, skillName: "writer", tags: ["writing"] },
        ],
      }],
      direction: null,
      format: "",
      indent: 0,
    },
  },
} satisfies ComposerSnapshot;

expect(projectComposerSnapshot(snapshot)).toEqual({
  message: "请总结 [引用文件：notes.txt] 并使用",
  activeReferenceIds: ["ref-1"],
  enabledSkills: ["writer"],
  isEmpty: false,
});
```

Slash tests use a literal table:

```ts
expect(findSlashTrigger("/wri", 4)).toEqual({ from: 0, to: 4, query: "wri" });
expect(findSlashTrigger("请用 /wri", 7)).toEqual({ from: 3, to: 7, query: "wri" });
expect(findSlashTrigger("https://example.com", 8)).toBeNull();
expect(findSlashTrigger("a/b", 3)).toBeNull();
expect(findSlashTrigger("/home/user", 10)).toBeNull();
expect(findSlashTrigger("/skill done", 11)).toBeNull();
```

History tests require versioned JSON, legacy strings, and corrupt JSON fallback:

```ts
expect(decodeComposerHistoryEntry("legacy prompt").plainText).toBe("legacy prompt");
expect(decodeComposerHistoryEntry(JSON.stringify(snapshot))).toEqual(snapshot);
expect(decodeComposerHistoryEntry("{broken").plainText).toBe("{broken");
```

- [x] **Step 3: Run the pure tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer/__tests__/composerProjection.test.ts src/components/chat/richComposer/__tests__/slashTrigger.test.ts src/components/chat/richComposer/__tests__/composerHistory.test.ts
```

Expected: FAIL because the rich composer modules do not exist.

- [x] **Step 4: Implement the minimal contracts**

Define exact public types in `composerTypes.ts`:

```ts
export type FileReferenceStatus = "uploading" | "ready" | "failed";

export interface FileReferenceDescriptor {
  referenceId: string;
  fileName: string;
  category: "document";
  status: FileReferenceStatus;
}

export interface SkillReferenceDescriptor {
  skillName: string;
  tags: string[];
}

export interface ComposerSnapshot {
  version: 1;
  editorState: Record<string, unknown>;
  plainText?: string;
}

export interface ComposerProjection {
  message: string;
  activeReferenceIds: string[];
  enabledSkills: string[];
  isEmpty: boolean;
}
```

`findSlashTrigger` must use the text immediately before the caret, require `^` or whitespace before `/`, reject whitespace or a second slash after the trigger, and return absolute offsets.

`projectComposerSnapshot` recursively walks serialized children, emits readable file markers, emits no message text for Skill nodes, trims the final message, preserves unique reference/Skill order, and reports empty only when text and nodes are absent.

`decodeComposerHistoryEntry` accepts version-1 snapshots, treats ordinary or invalid strings as legacy plain text, and never throws.

- [x] **Step 5: Run tests and verify GREEN**

Run the Step 3 command. Expected: all contract tests pass.

- [x] **Step 6: Commit the contracts**

```bash
git add frontend/package.json pnpm-lock.yaml frontend/src/components/chat/richComposer docs/superpowers/plans/2026-08-09-rich-chat-composer.md
git commit -m "feat(chat): add rich composer contracts"
```

---

### Task 2: Atomic Lexical nodes and the plain-text editor surface

**Files:**
- Create: `frontend/src/components/chat/richComposer/nodes/FileReferenceNode.tsx`
- Create: `frontend/src/components/chat/richComposer/nodes/SkillReferenceNode.tsx`
- Create: `frontend/src/components/chat/richComposer/nodes/referenceCommands.ts`
- Create: `frontend/src/components/chat/richComposer/FileReferenceChip.tsx`
- Create: `frontend/src/components/chat/richComposer/RichChatComposer.tsx`
- Create: `frontend/src/components/chat/richComposer/RichComposerPlugins.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/RichChatComposer.test.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/referenceNodes.test.tsx`
- Modify: `frontend/src/styles/components.css`

**Interfaces:**
- Consumes: Task 1 descriptors and snapshot/projection functions.
- Produces: `RichChatComposerHandle`, `RichChatComposerProps`, `INSERT_FILE_REFERENCE_COMMAND`, `INSERT_SKILL_REFERENCE_COMMAND`, `REMOVE_FILE_REFERENCE_COMMAND`, and `UPDATE_FILE_REFERENCE_COMMAND`.

- [x] **Step 1: Write failing editor behavior tests**

Render the real editor in jsdom. Tests must type ordinary text with
`userEvent.type`, insert nodes through commands exposed by a ref, and assert the
rendered accessible UI plus emitted projection:

```tsx
const handle = createRef<RichChatComposerHandle>();
render(<RichChatComposer ref={handle} ariaLabel="message" onChange={setResult} />);
await userEvent.type(screen.getByRole("textbox", { name: "message" }), "前文 后文");
setContentEditableSelection(screen.getByRole("textbox", { name: "message" }), 3);
act(() => handle.current?.insertSkill({ skillName: "writer", tags: ["writing"] }));
expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
expect(result.projection.enabledSkills).toEqual(["writer"]);
expect(result.projection.message).toBe("前文 后文");
```

Add tests for JSON round-trip, unknown node versions degrading to readable text,
a file node's uploading/ready/failed labels, duplicate Skill insertion focusing
the existing node, arrow navigation around a node, whole-node deletion, and
plain-text clipboard export.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer/__tests__/RichChatComposer.test.tsx src/components/chat/richComposer/__tests__/referenceNodes.test.tsx
```

Expected: FAIL because the editor surface and nodes do not exist.

- [x] **Step 3: Implement node commands and serialized nodes**

`referenceCommands.ts` exports typed Lexical commands:

```ts
export const INSERT_FILE_REFERENCE_COMMAND = createCommand<FileReferenceDescriptor>();
export const INSERT_SKILL_REFERENCE_COMMAND = createCommand<SkillReferenceDescriptor>();
export const REMOVE_FILE_REFERENCE_COMMAND = createCommand<string>();
export const UPDATE_FILE_REFERENCE_COMMAND = createCommand<{
  referenceId: string;
  status: FileReferenceStatus;
  fileName?: string;
}>();
```

Both node classes extend an inline Lexical decorator node, implement versioned
JSON import/export, `isInline(): true`, readable `getTextContent()`, and React
decoration. Node DOM is atomic and uses `contentEditable={false}`.

- [x] **Step 4: Implement `RichChatComposer`**

Expose this ref contract:

```ts
export interface RichChatComposerHandle {
  focus(options?: { atEnd?: boolean }): void;
  setPlainText(text: string): void;
  restoreSnapshot(snapshot: ComposerSnapshot): void;
  getSnapshot(): ComposerSnapshot;
  insertText(text: string): void;
  insertSkill(skill: SkillReferenceDescriptor): void;
  insertFileReference(file: FileReferenceDescriptor): void;
  removeFileReference(referenceId: string): void;
  updateFileReference(update: {
    referenceId: string;
    status: FileReferenceStatus;
    fileName?: string;
  }): void;
}
```

Use `LexicalComposer`, `PlainTextPlugin`, `ContentEditable`, `HistoryPlugin`, and
`OnChangePlugin`. `onChange` emits `{ snapshot, projection }`; it must not expose
Lexical editor objects outside the component. Keep one paragraph-oriented,
plain-text theme and render the placeholder only for an empty document. Use
`LexicalErrorBoundary`; retain the last valid snapshot before reporting an editor
error to the application boundary.

- [x] **Step 5: Add accessible visual treatment**

Use existing theme variables. File references use a blue/theme-primary tinted
background, `FileText`, progress/error icon, visible focus ring, and localized
labels. Skill references reuse `SkillChip`. Do not animate position or modify
ordinary paragraph typography.

- [x] **Step 6: Run tests and verify GREEN**

Run the Step 2 command. Expected: all editor/node tests pass without act or
contentEditable warnings.

- [x] **Step 7: Commit the editor foundation**

```bash
git add frontend/src/components/chat/richComposer frontend/src/styles/components.css
git commit -m "feat(chat): add atomic rich composer nodes"
```

---

### Task 3: Explicit slash popup and inline Skill workflow

**Files:**
- Create: `frontend/src/components/chat/richComposer/SlashCommandPlugin.tsx`
- Create: `frontend/src/components/chat/richComposer/SkillReferencePlugin.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx`
- Modify: `frontend/src/components/chat/SlashDropdownMenu.tsx`
- Modify: `frontend/src/components/chat/__tests__/chatInputSlashCommands.test.ts`

**Interfaces:**
- Consumes: Task 1 `findSlashTrigger`, Task 2 editor commands, existing `SlashDropdownItem` and `SkillResponse`.
- Produces: `SlashCommandContext { range, query, anchorRect }`, `onInsertSkill(skill)`, and document-derived `enabledSkills`.

- [x] **Step 1: Write failing slash/Skill integration tests**

Test the real editor plus dropdown:

```tsx
await userEvent.type(editor, "请使用 /wri");
expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeVisible();
await userEvent.keyboard("{ArrowDown}{Enter}");
expect(editor).toHaveTextContent("请使用");
expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
await userEvent.type(editor, " 继续写");
expect(projection.message).toBe("请使用 继续写");
expect(projection.enabledSkills).toEqual(["writer"]);
```

Also assert no popup for `https://`, `a/b`, and `/home/user`; Escape preserves
text; Tab inserts; toolbar selection uses the last caret; deleting/undoing a
Skill node updates `enabledSkills`; IME Enter never chooses or submits.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx src/components/chat/__tests__/chatInputSlashCommands.test.ts
```

Expected: new workflow tests fail because the plugin is absent.

- [x] **Step 3: Implement the slash context plugin**

On Lexical updates, read the collapsed range selection, derive text from the
current text run before the caret, call `findSlashTrigger`, and emit the popup
context. Register keyboard commands at high priority only while a popup context
exists. Escape closes context without clearing the document.

On selection, remove exactly `range.from..range.to` and dispatch the selected
built-in command or `INSERT_SKILL_REFERENCE_COMMAND`. Position the existing
dropdown from the DOM range rectangle instead of textarea offsets.

- [x] **Step 4: Replace next-run Skill array authority with document nodes**

The rich composer receives available Skills and exposes toolbar insertion through
its imperative handle. Toolbar insertion restores the last saved Lexical
selection before dispatching the insert command. The plugin emits unique
`enabledSkills` directly from document nodes; `ChatInput` consumes that projection
in Task 5.

- [x] **Step 5: Run tests and verify GREEN**

Run the Step 2 command. Expected: all slash boundary, keyboard, and Skill state
tests pass.

- [ ] **Step 6: Commit the Skill workflow**

```bash
git add frontend/src/components/chat/richComposer frontend/src/components/chat/SlashDropdownMenu.tsx frontend/src/components/chat/__tests__/chatInputSlashCommands.test.ts frontend/src/styles/components.css
git commit -m "feat(chat): insert skills as inline composer nodes"
```

---

### Task 4: Undo-aware long-text file references

**Files:**
- Create: `frontend/src/components/chat/richComposer/draftAttachmentRegistry.ts`
- Create: `frontend/src/components/chat/richComposer/useDraftAttachmentRegistry.ts`
- Create: `frontend/src/components/chat/richComposer/LongTextPastePlugin.tsx`
- Create: `frontend/src/components/chat/richComposer/FileReferencePlugin.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/draftAttachmentRegistry.test.ts`
- Create: `frontend/src/components/chat/richComposer/__tests__/longTextFileWorkflow.test.tsx`
- Modify: `frontend/src/hooks/useFileUpload.ts`
- Modify: `frontend/src/components/chat/ChatInputAttachments.tsx`
- Modify: `frontend/src/components/chat/longTextConversion.ts`
- Modify: `frontend/src/types/upload.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: Task 2 file commands, existing upload service, `PASTE_TEXT_THRESHOLD`, Turndown cleanup, and attachment preview.
- Produces: `DraftAttachmentResource`, `DraftAttachmentAction`, `reduceDraftAttachments`, `useDraftAttachmentRegistry`, retry/remove/cleanup commands.

- [ ] **Step 1: Write failing registry reducer tests**

Define literal state transitions:

```ts
const inserted = reduceDraftAttachments(emptyState, {
  type: "insert",
  resource: { referenceId: "ref-1", file, status: "uploading", active: true },
});
const removed = reduceDraftAttachments(inserted, {
  type: "reconcile-active",
  activeReferenceIds: [],
});
expect(removed.resources["ref-1"].active).toBe(false);
expect(selectSubmitAttachments(removed)).toEqual([]);
const restored = reduceDraftAttachments(removed, {
  type: "reconcile-active",
  activeReferenceIds: ["ref-1"],
});
expect(restored.resources["ref-1"].active).toBe(true);
```

Cover ready, failed, retry, final attachment replacement, inactive cleanup, and
ordinary card-only attachments.

- [ ] **Step 2: Write failing long-paste editor tests**

With an editor containing `beforeSELECTEDafter`, select `SELECTED` and paste a
fragment of `PASTE_TEXT_THRESHOLD + 1` characters. Assert:

- the generated `File.text()` equals only the pasted fragment;
- rendered content is `before`, one blue file-reference node, then `after`;
- one attachment card is active;
- Delete hides node and card; undo restores both without a second upload;
- failure renders retry/remove and disables send;
- expanded mode inserts editable text instead of a file node;
- short and ordinary file paste keep existing behavior.

- [ ] **Step 3: Run registry and workflow tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer/__tests__/draftAttachmentRegistry.test.ts src/components/chat/richComposer/__tests__/longTextFileWorkflow.test.tsx
```

Expected: FAIL because the registry and paste plugin do not exist.

- [ ] **Step 4: Implement the pure registry and upload adapter**

Use these stable fields:

```ts
export interface DraftAttachmentResource {
  referenceId: string;
  file: File;
  status: "uploading" | "ready" | "failed";
  active: boolean;
  attachment?: MessageAttachment;
  error?: string;
}
```

Extend client-only attachment metadata with `composerReferenceId?: string` and
strip it before API submit. Add a focused upload adapter that reports progress,
ready, failure, and abort to the registry without removing a failed resource.
Existing ordinary upload behavior stays unchanged.

- [ ] **Step 5: Implement long-text paste and file synchronization**

Intercept paste only when the editor is not expanded and normalized pasted text
exceeds the existing threshold. Validate attachment count before preventing the
fallback. Create the file/reference ID once, replace the Lexical selection with a
file node, start upload, and reconcile node status from registry state.

Card removal dispatches `REMOVE_FILE_REFERENCE_COMMAND`; projection changes call
`reconcile-active`, which provides undo/redo. Retry reuses `resource.file`.
Cleanup deletes only inactive uploaded resources when the draft is sent, cleared,
or discarded.

- [ ] **Step 6: Add localized accessible states**

Add equivalent keys in every locale for `引用文件`, `上传中`, `上传失败`, `重试`,
and removal announcements. The node uses text/icon/status together and exposes
button names that editor tests can query. A polite ARIA live region announces
insertion, upload failure, retry, and removal without moving focus.

- [ ] **Step 7: Run tests and verify GREEN**

Run the Step 3 command plus:

```bash
cd frontend && pnpm exec vitest run src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx src/components/chat/__tests__/longTextConversion.test.ts
```

Update or retire the legacy hook test only after its behavior is covered through
the real Lexical workflow. Expected: all relevant tests pass.

- [ ] **Step 8: Commit long-text references**

```bash
git add frontend/src/components/chat/richComposer frontend/src/components/chat/ChatInputAttachments.tsx frontend/src/components/chat/longTextConversion.ts frontend/src/hooks/useFileUpload.ts frontend/src/types/upload.ts frontend/src/i18n
git commit -m "feat(chat): insert long text as file reference nodes"
```

---

### Task 5: Migrate ChatInput, history, mentions, and expanded layout

**Files:**
- Modify: `frontend/src/components/chat/ChatInput.tsx`
- Modify: `frontend/src/components/chat/ChatInputExpandedComposer.tsx`
- Delete: `frontend/src/components/chat/ChatInputRunSkillsBar.tsx`
- Modify: `frontend/src/components/chat/runSkillSelection.ts`
- Modify: `frontend/src/hooks/useChatInputKeyboard.ts`
- Modify: `frontend/src/hooks/useInputHistory.ts`
- Modify: `frontend/src/hooks/useMentionState.ts`
- Modify: `frontend/src/hooks/useTextareaResize.ts`
- Modify: `frontend/src/components/chat/chatInputTypes.ts`
- Create: `frontend/src/components/chat/richComposer/ComposerLayoutSurface.tsx`
- Create: `frontend/src/components/chat/richComposer/ComposerIntegrationPlugin.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/composerIntegration.test.tsx`
- Create: `frontend/src/components/chat/richComposer/__tests__/composerExpanded.test.tsx`
- Modify: `frontend/src/components/chat/__tests__/chatInputLongTextSource.test.ts`

**Interfaces:**
- Consumes: Tasks 1-4 composer handle, projections, commands, and registry.
- Produces: the complete `ChatInput` feature using one editor state in normal and expanded layouts.

- [ ] **Step 1: Write failing integration tests**

Exercise the real `ChatInput` with minimal real props. Assert:

- ordinary typing and modified-Enter submit the projected message;
- composition Enter neither submits nor selects a popup item;
- `pendingInput` appends/imports plain text and focuses the editor;
- selection-action prompts append plain text;
- Up/Down at document boundaries restores versioned history including nodes;
- persona/team mention selection removes only its query and calls the existing callback;
- expand/collapse preserves text, nodes, selection, undo, and attachment state;
- empty text plus a ready file node can submit; uploading/failed nodes cannot;
- after submit, editor, registry, attachment cards, and Skill nodes reset together.

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer/__tests__/composerIntegration.test.tsx src/components/chat/richComposer/__tests__/composerExpanded.test.tsx
```

Expected: FAIL while `ChatInput` still uses textarea state.

- [ ] **Step 3: Replace textarea state and imperative cursor arithmetic**

Mount one `RichChatComposer` and store only its latest snapshot/projection in
`ChatInput`. Route submit, can-send, history, pending input, selection actions,
mentions, slash commands, and toolbar insertion through the composer handle.
Remove `input`, `cursorPosition`, and direct `selectionStart/selectionEnd` writes
after each behavior has an editor-command equivalent.

`ChatInput` receives `enabledSkills` from the composer projection. Remove the old
toggle-array authority from `runSkillSelection.ts` after the document-node path is
connected.

- [ ] **Step 4: Share one editor between compact and expanded layouts**

Keep `LexicalComposer` above the layout conditional. `ComposerLayoutSurface`
renders the one active `ContentEditable` root inside compact layout or the
expanded portal. Save selection before switching and restore it after the new root
mounts. Preserve current mobile sheet close gestures, Escape, focus trapping,
send/stop buttons, and body scroll lock.

- [ ] **Step 5: Migrate history and resize behavior**

`useInputHistory` stores `ComposerSnapshot` JSON and migrates old strings via
`decodeComposerHistoryEntry`. Content height is measured from the editor root;
retain current min/max heights, scrolling, and expand button threshold.

- [ ] **Step 6: Remove legacy duplicate UI and hooks**

Delete `ChatInputRunSkillsBar`; remove `usePasteHandler` and
`useLongTextConversion` from `ChatInput` only after their conversion/restore
behavior is owned by rich-composer plugins. Keep generic file-drop upload paths.
Delete obsolete source-pattern assertions and replace them with behavior tests.

- [ ] **Step 7: Run integration and existing chat tests**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/chat/richComposer src/components/chat/__tests__/chatInputSlashCommands.test.ts src/components/chat/__tests__/longTextConversion.test.ts src/components/chat/__tests__/teamMentionMode.test.ts src/hooks/__tests__/useMentionState.test.ts
```

Expected: all selected tests pass with no React act, contentEditable, or IME warnings.

- [ ] **Step 8: Commit ChatInput migration**

```bash
git add frontend/src/components/chat frontend/src/hooks frontend/src/styles/components.css
git commit -m "refactor(chat): migrate input to Lexical composer"
```

---

### Task 6: Compatibility, accessibility, and full verification

**Files:**
- Modify: `frontend/src/components/chat/richComposer/**`
- Modify: `frontend/src/components/chat/__tests__/**` only where behavior moved
- Modify: `frontend/src/hooks/__tests__/**` only where behavior moved
- Modify: `docs/superpowers/plans/2026-08-09-rich-chat-composer.md`

**Interfaces:**
- Consumes: the complete rich composer.
- Produces: verified release-ready behavior with no known regression in existing chat input flows.

- [ ] **Step 1: Run the complete frontend test suite**

Run:

```bash
cd frontend && pnpm test
```

Expected: every test passes. Any failure in chat input, upload, message submit,
selection, mobile layout, or i18n is part of this task and must be resolved before
continuing.

- [ ] **Step 2: Run lint and production build**

Run:

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: ESLint has zero errors and the TypeScript/Vite/PWA build exits 0.
Record pre-existing warnings separately; do not introduce new warnings.

- [ ] **Step 3: Run manual browser acceptance checks**

Start the existing source development frontend and verify in Chromium at desktop
and a 375px viewport:

1. Chinese IME composition adjacent to both node types;
2. `/` popup positive and negative trigger cases;
3. keyboard insertion/deletion/undo/redo and continued prose;
4. long plain/HTML paste content, selection replacement, upload retry, preview,
   card synchronization, and removal;
5. toolbar Skill insertion at the saved caret;
6. expanded composer open/close, scrolling, focus, and mobile keyboard;
7. submit payload and rendered user message;
8. legacy history and `pendingInput`.

Expected: no lost text, duplicate node, stuck selection, unintended popup, or
orphaned active attachment.

- [ ] **Step 4: Complete the plan ledger and inspect the final diff**

Mark completed checkboxes, run `git diff --check`, and verify that no unrelated
concurrent files are staged. Confirm the old complete-draft attachment behavior
from commit `e0dc7fde` is no longer reachable.

- [ ] **Step 5: Commit final compatibility fixes**

```bash
git add frontend docs/superpowers/plans/2026-08-09-rich-chat-composer.md
git commit -m "test(chat): verify rich composer compatibility"
```
