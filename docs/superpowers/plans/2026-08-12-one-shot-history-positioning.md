# One-Shot History Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open reconstructed conversation history at the final message with one non-animated Virtuoso command and no visible recovery, overlay, or history-specific retry loop.

**Architecture:** Expose the existing history request sequence as a generation token, key pending positioning to that generation, and replace history finalization with one direct `virtuosoRef.current.scrollToIndex({ index: "LAST", align: "end", behavior: "auto" })`. Remove the competing mount-time history alignment and settling UI; retain the generic multi-attempt helper only for explicit bottom actions, streaming, viewport recovery, and external-navigation behavior.

**Tech Stack:** React 19, TypeScript, react-virtuoso, Vitest, Testing Library, Tailwind CSS.

---

## File Structure

- Modify `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`: issue and consume the guarded one-shot history alignment without generic scrolling side effects.
- Modify `frontend/src/components/layout/AppContent/useMessageScroll.ts`: remove obsolete settling exports.
- Modify `frontend/src/components/layout/AppContent/ChatView.tsx`: render history immediately, remove settling state/overlay, and stop providing the competing initial bottom location.
- Modify `frontend/src/components/layout/AppContent/ChatViewProps.tsx`: carry the history generation into the view.
- Modify `frontend/src/components/layout/AppContent/ChatAppContent.tsx`: pass the current accepted history generation.
- Modify `frontend/src/hooks/useAgent.ts` and `frontend/src/hooks/useAgent/types.ts`: expose the monotonically increasing history request generation.
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
- Create: `frontend/src/components/layout/AppContent/__tests__/useMessageScrollOneShot.test.tsx`
- Modify: `frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`
- Create: `frontend/src/components/layout/AppContent/__tests__/historyGenerationPropsSource.test.ts`

- [ ] **Step 1: Replace the history settling source assertions**

Require the history-finalization layout effect to call the Virtuoso handle directly:

```typescript
expect(hookSource).toMatch(
  /const virtuoso = virtuosoRef\.current;[\s\S]*virtuoso\.scrollToIndex\(\{\s*index: "LAST",\s*align: "end",\s*behavior: "auto",?\s*\}\)/,
);
expect(historyFinalizeBlock).not.toMatch(/requestScrollToBottom|requestAnimationFrame|setTimeout|ResizeObserver/);
```

Require `ChatView` to omit `initialTopMostItemIndex`, `isHistoryScrollSettling`, `chat-history-scroll-settling`, and `chat-history-settling-overlay`, while rendering the input whenever messages exist.

- [ ] **Step 2: Preserve guards and unrelated scroll paths in tests**

Keep or add assertions that:

- external-navigation history does not consume another generation's pending
  bottom action;
- empty, loading, stale/replaced, missing-ref, and rerender states cannot
  schedule retries or a second call;
- first outgoing messages, streaming follow/detach, viewport recovery,
  explicit bottom action, unexpected-top recovery, and external-navigation
  targeting retain behavioral coverage.

Add a jsdom `renderHook` test that supplies a mutable mocked Virtuoso handle and
rerenders the real hook across loading/generation transitions. Assert one exact
call for an accepted non-external generation, no second call after rerenders or
flushed timers/RAF, zero calls when a missing ref is attached later, and zero
calls for empty/loading/replaced/external-navigation cases. Also cover a batched
transition that changes directly from the old idle/session signature to a new
completed message list and generation without rendering
`isLoadingHistory=true`; `shouldInferBatchedHistoryLoadReady` must arm that
current generation and still produce exactly one call.

Extend `useAgentLoadHistoryRace.test.ts` to prove each `loadHistory` start
publishes its incremented request ID and stale completion cannot restore an old
generation. Add a source-chain test requiring `ChatAppContent` to destructure
and pass `historyLoadGeneration`, `ChatViewProps` to declare it, and `ChatView`
to forward it to `useMessageScroll` instead of a literal value.

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
  src/components/layout/AppContent/__tests__/useMessageScrollOneShot.test.tsx \
  src/components/layout/AppContent/__tests__/historyGenerationPropsSource.test.ts \
  src/hooks/__tests__/useAgentLoadHistoryRace.test.ts \
  --reporter=dot
```

Expected: FAIL because production still uses the history settling overlay, mount-time alignment, RAF retries, and the generic history-finalize loop.

### Task 2: Implement one direct bottom alignment

**Files:**
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.ts`
- Modify: `frontend/src/components/layout/AppContent/ChatView.tsx`
- Modify: `frontend/src/components/layout/AppContent/ChatViewProps.tsx`
- Modify: `frontend/src/components/layout/AppContent/ChatAppContent.tsx`
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/hooks/useAgent/types.ts`
- Modify: `frontend/src/components/layout/AppContent/messageScrollUtils.ts`
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.followState.ts`
- Delete: `frontend/src/components/layout/AppContent/useMessageScroll.historySettling.ts`
- Modify: `frontend/src/styles/chat.css`

- [ ] **Step 1: Replace history finalization with the minimal command**

At `loadHistory` start, publish its existing incremented request ID as
`historyLoadGeneration`. In the scroll hook, replace the unkeyed boolean with a
pending generation. Arm/re-arm it when `isLoadingHistory` is true and the
generation changes. When `shouldInferBatchedHistoryLoadReady` detects a direct
idle-to-complete transition, arm the current generation in the same layout
effect. After the load/message-count guards accept a non-external current
generation:

```typescript
const virtuoso = virtuosoRef.current;
const pendingGeneration = pendingHistoryScrollRef.current;
pendingHistoryScrollRef.current = null;
if (
  pendingGeneration !== historyLoadGeneration ||
  externalNavigationToken
) return;
if (!virtuoso) return;
virtuoso.scrollToIndex({
  index: "LAST",
  align: "end",
  behavior: "auto",
});
```

Do not call `requestScrollToBottom`, touch physical scroller/footer refs, mutate follow state, or create deferred retries. Consume the pending generation before mismatch, external-navigation, and missing-ref returns so rerenders cannot retry it. Upstream request IDs still prevent stale history data from committing; the same ID now prevents pending scroll intent from crossing a replacement load.

- [ ] **Step 2: Remove competing history UI and mount positioning**

Remove the settling hook/state from the return contract, the overlay and invisible classes from `ChatView`, the `initialTopMostItemIndex` prop, the settling CSS rules, and now-unused settling/initial-location helpers. Keep the ordinary loading skeleton shown while `messages.length === 0 && isLoading`.

- [ ] **Step 3: Run focused tests and verify GREEN**

Run Task 1 Step 3 and expect all selected tests to pass without warnings.

- [ ] **Step 4: Commit the production change and tests**

Stage only the files listed in Tasks 1-2, including
`frontend/src/components/layout/AppContent/useMessageScroll.ts`,
`frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`, and
`frontend/src/components/layout/AppContent/__tests__/historyGenerationPropsSource.test.ts`,
and commit:

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

- [ ] **Step 3: Run the repository check**

```bash
make check-all
```

Expected: exit 0. If an unrelated dirty file is reformatted or fails, restore
only the tool-created change and report the independently run typecheck, test,
and build results without modifying user-owned work.

- [ ] **Step 4: Check repository ownership and runtime boundary**

Confirm only task files are committed and preserve unrelated dirty files. The local dev server may prove compilation and endpoint availability, but the authenticated browser session must confirm the final visual criterion: history appears at the final message without a visible downward animation or repeated refresh.
