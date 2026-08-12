# One-Shot History Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open reconstructed conversation history at the final message with one non-animated Virtuoso command and no visible recovery, overlay, or history-specific retry loop.

**Architecture:** Keep the existing pending-history and stale/external-navigation guards, but replace history finalization with one direct `virtuosoRef.current.scrollToIndex({ index: "LAST", align: "end", behavior: "auto" })`. Remove the competing mount-time history alignment and settling UI; retain the generic multi-attempt helper only for explicit bottom actions, streaming, viewport recovery, and external-navigation behavior.

**Tech Stack:** React 19, TypeScript, react-virtuoso, Vitest, Testing Library, Tailwind CSS.

---

## File Structure

- Modify `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`: issue and consume the guarded one-shot history alignment without generic scrolling side effects.
- Modify `frontend/src/components/layout/AppContent/ChatView.tsx`: render history immediately, remove settling state/overlay, and stop providing the competing initial bottom location.
- Modify `frontend/src/components/layout/AppContent/messageScrollUtils.ts`: remove the unused initial-history location helper while retaining generic scrolling primitives.
- Modify `frontend/src/components/layout/AppContent/useMessageScroll.followState.ts`: remove settling-only predicate code if it has no remaining callers.
- Delete `frontend/src/components/layout/AppContent/useMessageScroll.historySettling.ts`: remove the obsolete overlay timeout state.
- Modify `frontend/src/styles/chat.css`: remove obsolete history-settling selectors.
- Modify the colocated AppContent tests to encode one-shot behavior and preserved non-history scrolling.

### Task 1: Lock the one-shot contract with failing tests

**Files:**
- Modify: `frontend/src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/chatViewMessageListKey.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/messageScrollSessionReset.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/useMessageScroll.test.ts`

- [ ] **Step 1: Replace the history settling source assertions**

Require the history-finalization layout effect to call the Virtuoso handle directly:

```typescript
expect(hookSource).toMatch(
  /virtuosoRef\.current\.scrollToIndex\(\{\s*index: "LAST",\s*align: "end",\s*behavior: "auto",?\s*\}\)/,
);
expect(historyFinalizeBlock).not.toMatch(/requestScrollToBottom|requestAnimationFrame|setTimeout|ResizeObserver/);
```

Require `ChatView` to omit `initialTopMostItemIndex`, `isHistoryScrollSettling`, `chat-history-scroll-settling`, and `chat-history-settling-overlay`, while rendering the input whenever messages exist.

- [ ] **Step 2: Preserve guards and unrelated scroll paths in tests**

Keep or add assertions that:

- external-navigation history does not arm the pending bottom action;
- empty, loading, stale/replaced, missing-ref, and rerender states cannot schedule retries or a second call;
- the generic `requestScrollToBottom("default")` paths for first outgoing messages, streaming follow, viewport recovery, and explicit user action remain present;
- removing the initial location helper does not change session-key remounting or external-navigation targeting.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run \
  src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts \
  src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts \
  src/components/layout/AppContent/__tests__/chatViewMessageListKey.test.ts \
  src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts \
  src/components/layout/AppContent/__tests__/messageScrollSessionReset.test.ts \
  src/components/layout/AppContent/__tests__/useMessageScroll.test.ts \
  --reporter=dot
```

Expected: FAIL because production still uses the history settling overlay, mount-time alignment, RAF retries, and the generic history-finalize loop.

### Task 2: Implement one direct bottom alignment

**Files:**
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`
- Modify: `frontend/src/components/layout/AppContent/ChatView.tsx`
- Modify: `frontend/src/components/layout/AppContent/messageScrollUtils.ts`
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.followState.ts`
- Delete: `frontend/src/components/layout/AppContent/useMessageScroll.historySettling.ts`
- Modify: `frontend/src/styles/chat.css`

- [ ] **Step 1: Replace history finalization with the minimal command**

After the existing pending/load/message-count guards accept a non-external history generation:

```typescript
const virtuoso = virtuosoRef.current;
pendingHistoryScrollRef.current = false;
if (!virtuoso) return;
virtuoso.scrollToIndex({
  index: "LAST",
  align: "end",
  behavior: "auto",
});
```

Do not call `requestScrollToBottom`, touch physical scroller/footer refs, mutate follow state, or create deferred retries. Consume the pending generation before the missing-ref return so rerenders cannot retry it.

- [ ] **Step 2: Remove competing history UI and mount positioning**

Remove the settling hook/state from the return contract, the overlay and invisible classes from `ChatView`, the `initialTopMostItemIndex` prop, the settling CSS rules, and now-unused settling/initial-location helpers. Keep the ordinary loading skeleton shown while `messages.length === 0 && isLoading`.

- [ ] **Step 3: Run focused tests and verify GREEN**

Run Task 1 Step 3 and expect all selected tests to pass without warnings.

- [ ] **Step 4: Commit the production change and tests**

Stage only the files listed in Tasks 1-2 and commit:

```bash
git commit -m "fix: position loaded history once"
```

### Task 3: Verify the frontend behavior

- [ ] **Step 1: Run all AppContent scroll tests**

```bash
cd frontend && pnpm exec vitest run src/components/layout/AppContent/__tests__ --reporter=dot
```

Expected: PASS.

- [ ] **Step 2: Run frontend lint and production build**

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: both exit 0. Existing Vite chunk-size warnings are non-blocking.

- [ ] **Step 3: Check repository ownership and runtime boundary**

Confirm only task files are committed and preserve unrelated dirty files. The local dev server may prove compilation and endpoint availability, but the authenticated browser session must confirm the final visual criterion: history appears at the final message without a visible downward animation or repeated refresh.
