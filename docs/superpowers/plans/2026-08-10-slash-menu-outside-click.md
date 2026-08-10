# Slash Menu Outside-Click Dismissal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the rich composer slash menu on every outside mouse press while preserving the typed slash token and the outside target's normal interaction.

**Architecture:** `SlashDropdownMenu` detects whether a document-level `mousedown` occurred outside its portaled root and reports dismissal through a callback. `SlashCommandPlugin` owns dismissal state and suppresses the complete unchanged slash word with a caret-independent identity so selection movement cannot reopen it.

**Tech Stack:** React 19, TypeScript, Lexical, Vitest, Testing Library, jsdom.

---

## File map

- Modify `frontend/src/components/chat/richComposer/slashTrigger.ts`: derive a stable slash-token identity from the complete slash word.
- Modify `frontend/src/components/chat/richComposer/__tests__/slashTrigger.test.ts`: prove identity is independent of caret position and changes with token text.
- Modify `frontend/src/components/chat/SlashDropdownMenu.tsx`: add `onDismiss` and the scoped document listener.
- Create `frontend/src/components/chat/__tests__/SlashDropdownMenu.test.tsx`: isolate outside, inside, closed, cleanup, and latest-callback behavior.
- Modify `frontend/src/components/chat/richComposer/SlashCommandPlugin.tsx`: connect menu dismissal to stable token suppression and share it with Escape.
- Modify `frontend/src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx`: verify text preservation, persistent dismissal, outside control activation, and retained item selection.

### Task 1: Stable slash-token identity

**Files:**
- Modify: `frontend/src/components/chat/richComposer/slashTrigger.ts`
- Test: `frontend/src/components/chat/richComposer/__tests__/slashTrigger.test.ts`

- [ ] **Step 1: Write the failing identity tests**

Import `getSlashTokenId` and assert that node key, slash start, and the complete
slash word produce a stable value such as `node-1:0:/wri`, while changing the
word to `/write` changes the value. The integration test in Task 3 varies the
caret position; this pure helper deliberately takes only stable inputs.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/slashTrigger.test.ts
```

Expected: FAIL because `getSlashTokenId` is not exported.

- [ ] **Step 3: Implement the minimal identity helper**

```ts
export function getSlashTokenId(
  nodeKey: string,
  text: string,
  from: number,
): string {
  const slashWord = /^\/[^/\s]*/.exec(text.slice(from))?.[0] ?? "";
  return `${nodeKey}:${from}:${slashWord}`;
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same Vitest command. Expected: PASS with no warnings.

- [ ] **Step 5: Commit the stable identity**

```bash
git add frontend/src/components/chat/richComposer/slashTrigger.ts frontend/src/components/chat/richComposer/__tests__/slashTrigger.test.ts
git commit -m "test(chat): define stable slash token identity"
```

### Task 2: Portaled menu outside-click detection

**Files:**
- Modify: `frontend/src/components/chat/SlashDropdownMenu.tsx`
- Create: `frontend/src/components/chat/__tests__/SlashDropdownMenu.test.tsx`

- [ ] **Step 1: Write the failing menu tests**

Render `SlashDropdownMenu` with one command item and assert:

```ts
fireEvent.mouseDown(screen.getByTestId("outside"));
expect(onDismiss).toHaveBeenCalledOnce();

fireEvent.mouseDown(screen.getByRole("listbox", { name: "Slash commands" }));
expect(onDismiss).not.toHaveBeenCalled();
```

Also rerender with `open={false}` and unmount an open menu, then dispatch a
document `mousedown`; neither case may call `onDismiss`. Include a rerender with
a new callback while still open and assert only the latest callback runs.

- [ ] **Step 2: Run the component test and verify RED**

```bash
cd frontend && pnpm test -- src/components/chat/__tests__/SlashDropdownMenu.test.tsx
```

Expected: FAIL because `SlashDropdownMenuProps` has no `onDismiss` and no
outside listener exists.

- [ ] **Step 3: Implement the minimal listener**

Add optional `onDismiss?: () => void` to the props and destructuring so this
task leaves the existing caller type-correct before Task 3 wires real state.
Place the effect with the other hooks, before the component's `if (!open)
return null`, then add:

```ts
useEffect(() => {
  if (!open) return;
  const handleMouseDown = (event: MouseEvent) => {
    const target = event.target;
    if (target instanceof Node && popupRef.current?.contains(target)) return;
    onDismiss?.();
  };
  document.addEventListener("mousedown", handleMouseDown);
  return () => document.removeEventListener("mousedown", handleMouseDown);
}, [onDismiss, open]);
```

- [ ] **Step 4: Run the component test and verify GREEN**

Run the same Vitest command. Expected: PASS with no warnings.

- [ ] **Step 5: Commit the menu behavior**

```bash
git add frontend/src/components/chat/SlashDropdownMenu.tsx frontend/src/components/chat/__tests__/SlashDropdownMenu.test.tsx
git commit -m "feat(chat): dismiss slash menu on outside press"
```

### Task 3: Plugin dismissal and user-flow regression coverage

**Files:**
- Modify: `frontend/src/components/chat/richComposer/SlashCommandPlugin.tsx`
- Modify: `frontend/src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx`

- [ ] **Step 1: Write the failing integration tests**

Add a test that types `/wri`, fires `mousedown` on the editor, verifies the
menu closes and exact text remains, then deterministically moves the DOM caret
inside the same text node: create a collapsed `Range`, set it to an inner text
offset, then inside `act` call `window.getSelection()?.removeAllRanges()`, add
the range with `window.getSelection()?.addRange(range)`, and dispatch
`new Event("selectionchange")` on `document`. This exercises Lexical's
selection update listener; assert the menu stays closed.

Parameterize that stable-suppression assertion over both outside `mousedown`
and Escape dismissal. After dismissal, also verify two reset paths through the
real composer:

- insert another character so `/wri` becomes `/writ`, then assert the menu
  reopens because token text changed;
- move the DOM selection to a non-trigger position, dispatch `selectionchange`,
  return it to the unchanged slash word, and assert the menu may reopen because
  the editor stopped having a valid trigger between the two selections.

Add another test that wraps the composer with a real button, presses and clicks
it, then asserts the menu is closed and the button handler ran once.

Retain `renders above the app in a portal and supports pointer selection`
unchanged as the inside-click regression.

- [ ] **Step 2: Run the workflow test and verify RED**

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx
```

Expected: FAIL because the plugin does not pass `onDismiss`, outside presses do
not clear its slash context, the token identity is caret-dependent, and
dismissal reset behavior is incomplete.

- [ ] **Step 3: Implement plugin dismissal**

Import `getSlashTokenId`, build `tokenId` from the full text node rather than
the caret-limited slice, and clear stale dismissal state when no valid trigger
exists:

```ts
if (!trigger) {
  dismissedTokenRef.current = null;
  return null;
}
```

Then add:

```ts
const dismissMenu = useCallback(() => {
  if (!context) return;
  dismissedTokenRef.current = context.tokenId;
  setContext(null);
}, [context]);
```

Pass `onDismiss={dismissMenu}` to `SlashDropdownMenu` and call `dismissMenu()`
from the Escape command instead of duplicating the state transition. Add
`dismissMenu` to the keyboard-registration effect dependency array so the
command always sees the latest context and satisfies exhaustive-deps lint.

- [ ] **Step 4: Run the workflow test and verify GREEN**

Run the same Vitest command. Expected: all slash workflow tests PASS.

- [ ] **Step 5: Run focused regression tests**

```bash
cd frontend && pnpm test -- src/components/chat/richComposer/__tests__/slashTrigger.test.ts src/components/chat/__tests__/SlashDropdownMenu.test.tsx src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx
```

Expected: all focused tests PASS with no warnings.

- [ ] **Step 6: Commit the integration**

```bash
git add frontend/src/components/chat/richComposer/SlashCommandPlugin.tsx frontend/src/components/chat/richComposer/__tests__/slashSkillWorkflow.test.tsx
git commit -m "fix(chat): keep dismissed slash menu closed"
```

### Task 4: Final verification

**Files:**
- Verify all files listed above; no new production files.

- [ ] **Step 1: Run the rich composer test group**

```bash
cd frontend && pnpm test -- src/components/chat/richComposer
```

Expected: all rich composer tests PASS.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && pnpm run lint
```

Expected: ESLint exits 0.

- [ ] **Step 3: Build the frontend**

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite build exit 0.

- [ ] **Step 4: Inspect the final diff**

```bash
git status --short
git diff --check
```

Expected: only the scoped implementation and test files are changed, and
`git diff --check` reports no whitespace errors.
