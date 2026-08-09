# Tool Sidebar History Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep right-sidebar tool results live when their chat rows scroll out of Virtuoso, and restore every sidebar history node's expansion and scroll state when the user navigates back.

**Architecture:** Decouple tool panel data from rendered `ToolCallItem` lifetimes by synchronizing the message tree into a session-scoped external store. Add a shared DOM snapshot layer to sidebar history; `ToolResultPanel` captures the active panel before navigation and restores expansion controls before nested scroll positions while its existing first-paint mask is active.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library/jsdom, react-virtuoso.

## Global Constraints

- Preserve the current right-panel coordinator, automatic-open policy, and streaming behavior.
- Restore current in-memory sidebar history only; explicit close, session change, and page reload clear it.
- Do not keep inactive document viewers, editors, media, or iframes mounted.
- Apply restored UI state before revealing panel content.
- Preserve unrelated working-tree changes.

---

## File structure

- `frontend/src/components/chat/ChatMessage/toolCallPanelStore.ts`: own durable tool-call records, recursive message synchronization, subscriptions, and lifecycle cleanup.
- `frontend/src/components/chat/ChatMessage/ToolCallItem.tsx`: publish rendered tool data without deleting it on virtual-row unmount; consume durable records in the panel.
- `frontend/src/components/layout/AppContent/ChatView.tsx`: synchronize the complete message tree into the tool panel store and clear it on session changes.
- `frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx`: derive generic tool panel header/footer state from durable tool records.
- `frontend/src/components/chat/ChatMessage/items/sidebarPanelSnapshot.ts`: capture, queue, restore, and clear generic panel UI snapshots.
- `frontend/src/components/chat/ChatMessage/items/sidebarHistoryStore.ts`: attach a view snapshot to each history entry and queue it during back navigation.
- `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx`: register the active panel root and restore pending snapshots during the first-paint mask.
- Focused tests live next to the modules under their existing `__tests__` directories.

### Task 1: Keep generic tool results live outside the virtual render range

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/toolCallPanelStore.ts`
- Modify: `frontend/src/components/chat/ChatMessage/ToolCallItem.tsx`
- Modify: `frontend/src/components/layout/AppContent/ChatView.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx`
- Create: `frontend/src/components/chat/ChatMessage/__tests__/toolCallPanelStore.test.ts`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts`

**Interfaces:**
- Consumes: `Message[]`, recursively nested `MessagePart[]`, and existing `ToolCallPanelData`.
- Produces: `toolCallPanelStore.clear()`, `syncToolCallPanelStore(messages: readonly Message[]): void`, and reactive persistent-panel header/body data keyed by `tool:<toolCallId>`.

- [ ] **Step 1: Write failing durable-store tests**

Add behavioral tests that hand-build one top-level pending tool and one nested subagent tool, call `syncToolCallPanelStore`, and assert literal records. Then synchronize a final result and assert that an existing subscriber observes `status: "success"`, `isPending: false`, and the literal result. Assert `clear()` removes records.

```ts
test("updates an off-screen pending tool with its streamed result", () => {
  syncToolCallPanelStore([assistantMessage(pendingTool)]);
  const notifications: string[] = [];
  toolCallPanelStore.subscribe("tool-1", () => notifications.push("changed"));

  syncToolCallPanelStore([assistantMessage(completedTool)]);

  expect(toolCallPanelStore.get("tool-1")).toMatchObject({
    toolCallId: "tool-1",
    result: "final output",
    isPending: false,
    status: "success",
  });
  expect(notifications).toEqual(["changed"]);
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/toolCallPanelStore.test.ts
```

Expected: FAIL because `syncToolCallPanelStore` and `clear` do not exist.

- [ ] **Step 3: Implement recursive synchronization and session cleanup**

Convert each tool part with an ID into the same display data used by `ToolCallItem`, including partial argument parsing, formatted names, timestamps, cancellation, and status. Traverse nested `subagent.parts`. Make `clear()` emit deletion notifications. In `ChatView`, clear on `sessionId` change and synchronize whenever `messages` changes.

```ts
useEffect(() => {
  toolCallPanelStore.clear();
}, [sessionId]);

useEffect(() => {
  syncToolCallPanelStore(messages);
}, [messages]);
```

Remove the `ToolCallItem` cleanup that deletes a record on unmount. Keep its direct `set` as a harmless immediate publication path for non-`ChatView` consumers.

- [ ] **Step 4: Make persistent tool chrome consume the durable record**

Subscribe unconditionally from `PersistentToolPanelHost` when `panel.panelKey` has the `tool:` prefix. Use the live record's status and timestamps for the header/footer so a hidden source row cannot leave the restored panel stuck in loading state.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/toolCallPanelStore.test.ts src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add frontend/src/components/chat/ChatMessage/toolCallPanelStore.ts frontend/src/components/chat/ChatMessage/ToolCallItem.tsx frontend/src/components/layout/AppContent/ChatView.tsx frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx frontend/src/components/chat/ChatMessage/__tests__/toolCallPanelStore.test.ts frontend/src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts
git commit -m "fix(ui): keep offscreen tool panel results live"
```

### Task 2: Capture and replay generic sidebar view state

**Files:**
- Create: `frontend/src/components/chat/ChatMessage/items/sidebarPanelSnapshot.ts`
- Create: `frontend/src/components/chat/ChatMessage/items/__tests__/sidebarPanelSnapshot.test.ts`

**Interfaces:**
- Produces: `registerActiveSidebarSnapshotTarget(panelKey: string, root: HTMLElement): () => void`, `captureActiveSidebarPanelSnapshot(): SidebarPanelSnapshot | null`, `queueSidebarPanelSnapshot(snapshot: SidebarPanelSnapshot | null): void`, `restorePendingSidebarPanelSnapshot(panelKey: string, root: HTMLElement): Promise<boolean>`, and `clearSidebarPanelSnapshots(): void`.
- Snapshot data contains immutable expansion entries, native-details entries, and scroll entries addressed by explicit `data-sidebar-snapshot-key` values or deterministic element paths.

- [ ] **Step 1: Write failing snapshot capture tests**

Build a real jsdom panel with an `aria-expanded` button, a `details` element, the panel body, and a nested scroller. Set literal `scrollTop`/`scrollLeft` values and assert the captured snapshot contains each state without referencing implementation helpers in the expected value.

- [ ] **Step 2: Run the capture test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/sidebarPanelSnapshot.test.ts
```

Expected: FAIL because the snapshot module does not exist.

- [ ] **Step 3: Implement capture and stable element locators**

Prefer `data-sidebar-snapshot-key`; otherwise record an element-child index path relative to the registered root. Capture all `aria-expanded` controls and `details`, plus the root, `.tool-console-body`, and descendants with a non-zero scroll position or scrollable extent.

- [ ] **Step 4: Write failing replay tests**

Queue the captured snapshot, replace the root with freshly mounted default-state DOM, and assert replay clicks expansion controls before applying the literal nested scroll positions. Add a missing-element case proving that valid sibling state is still restored.

```ts
await restorePendingSidebarPanelSnapshot("panel:a", restoredRoot);

expect(expansionClickOrder).toEqual(["args", "result"]);
expect(restoredBody.scrollTop).toBe(240);
expect(restoredNested.scrollLeft).toBe(36);
```

- [ ] **Step 5: Run replay tests and verify RED**

Run the same focused Vitest command. Expected: FAIL until replay and pending-snapshot behavior exist.

- [ ] **Step 6: Implement replay, bounded layout settling, and cleanup**

Replay expansion through `.click()` and native details through `.open`, wait for React/layout frames, then restore scroll positions over a bounded number of animation frames. Consume a pending snapshot at most once. Cancellation and missing nodes resolve without throwing. `clearSidebarPanelSnapshots` clears the active target and pending work.

- [ ] **Step 7: Run snapshot tests and verify GREEN**

Run the focused snapshot test. Expected: PASS with no warnings.

- [ ] **Step 8: Commit Task 2**

```bash
git add frontend/src/components/chat/ChatMessage/items/sidebarPanelSnapshot.ts frontend/src/components/chat/ChatMessage/items/__tests__/sidebarPanelSnapshot.test.ts
git commit -m "feat(ui): snapshot sidebar panel interactions"
```

### Task 3: Attach snapshots to history and restore them before paint

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/sidebarHistoryStore.ts`
- Modify: `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts`

**Interfaces:**
- Consumes: Task 2 snapshot registry functions.
- Produces: history entries that pair their existing data restore callback with the exact UI snapshot captured at push time.

- [ ] **Step 1: Write failing LIFO history snapshot tests**

Register a real active snapshot target for A, push A, repeat for B, then call `goBackSidebar` twice. Assert B's snapshot is queued for B first and A's immutable snapshot second. Assert `clearSidebarHistory` also clears pending snapshot work.

- [ ] **Step 2: Run history tests and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts src/components/chat/ChatMessage/items/__tests__/sidebarPanelSnapshot.test.ts
```

Expected: FAIL because history does not attach or queue view snapshots.

- [ ] **Step 3: Integrate snapshots into sidebar history**

Capture the active panel UI in `pushCurrentPanelToHistory`. During `goBackSidebar`, queue that entry's snapshot before invoking its restore callback. Clear snapshot state with history. Preserve the existing `isRestoring` guard and registry reset.

- [ ] **Step 4: Write a failing ToolResultPanel restoration test**

Render a panel, register a pending snapshot for its registry key, and assert content remains busy/hidden until replay completes, then becomes visible with restored control and scroll state. Also rerender streamed children under the same registry key and assert it does not reset or replay the panel snapshot.

- [ ] **Step 5: Run the component test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts
```

Expected: FAIL because `ToolResultPanel` neither registers its active root nor awaits snapshot restoration.

- [ ] **Step 6: Register and restore from ToolResultPanel**

When `entry.active` and `registryKey` are present, register `panelRef.current` as the active snapshot target. Replace the fixed two-frame readiness effect with an async first-paint routine that attempts pending restoration and otherwise preserves the existing two-frame delay. Guard cleanup so stale restoration cannot reveal a replaced panel. Do not include `children` in the effect dependencies.

- [ ] **Step 7: Run all sidebar-focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/toolCallPanelStore.test.ts src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts src/components/chat/ChatMessage/items/__tests__/sidebarPanelSnapshot.test.ts src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts src/components/chat/ChatMessage/items/__tests__/toolPanelRegistry.test.ts src/components/common/__tests__/rightPanelCoordinator.test.ts src/components/common/__tests__/rightPanelShell.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Run frontend validation**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: all commands exit 0. If an unrelated pre-existing failure appears, record the exact test and verify the focused suite independently.

- [ ] **Step 9: Commit Task 3**

```bash
git add frontend/src/components/chat/ChatMessage/items/sidebarHistoryStore.ts frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx frontend/src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts
git commit -m "fix(ui): restore sidebar history snapshots"
```

## Plan self-review

- The durable data task covers top-level and nested tools, off-screen streaming completion, reactive header/footer state, and session cleanup.
- The snapshot task covers expansion, native details, body and nested scrolling, missing nodes, ordering, and bounded lazy-layout restoration.
- The integration task covers LIFO history, pre-paint restoration, streamed rerenders, explicit clearing, right-panel regressions, lint, and build.
- Function names and snapshot types are consistent across all tasks; no task relies on an undefined neighboring interface.
