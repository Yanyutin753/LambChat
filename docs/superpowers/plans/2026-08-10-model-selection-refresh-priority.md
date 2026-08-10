# Model Selection Refresh Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make refreshed chats resolve models deterministically as session selection, then user preference, then system initial model, then the first available model.

**Architecture:** Keep selection policy in the existing pure `modelSelection.ts` module, with explicit session, user, and system candidates plus unique-only legacy value matching. Store the session candidate separately from transient rendered state, expose the system default ID from `SettingsContext`, and use the active agent's filtered model list as the availability boundary. Give every history load a monotonic `loadId`; ignore stale restores and combine the active load ID with a user-selection revision so a late restore cannot overwrite a newer explicit choice.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, pnpm

---

## File Map

- Create `frontend/src/components/layout/AppContent/__tests__/modelSelection.test.ts`: focused priority, fallback, ambiguity, and loading tests.
- Create `frontend/src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts`: narrow source-level regression checks for settings/chat wiring.
- Modify `frontend/src/components/layout/AppContent/modelSelection.ts`: canonical selection resolver shared by refresh and new-session flows.
- Modify `frontend/src/contexts/SettingsContext.tsx`: expose `systemDefaultModelId` and distinguish a successful empty model response from unresolved loading/error state.
- Modify `frontend/src/components/layout/AppContent/useSessionSync.ts`: notify the caller immediately before each history load begins.
- Modify `frontend/src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx`: prove load-start notification ordering.
- Modify `frontend/src/components/layout/AppContent/sessionState.ts`: pure revision comparison for late restore protection.
- Modify `frontend/src/components/layout/AppContent/__tests__/sessionState.test.ts`: regression tests for revision behavior.
- Modify `frontend/src/components/layout/AppContent/ChatAppContent.tsx`: wire all priority sources, filtered availability, and restoration revision guard.

### Task 1: Encode the model priority in one pure resolver

**Files:**
- Create: `frontend/src/components/layout/AppContent/__tests__/modelSelection.test.ts`
- Modify: `frontend/src/components/layout/AppContent/modelSelection.ts`

- [ ] **Step 1: Write the failing priority tests**

Create table-driven tests using three available models (`session`, `user`, `system`) and assert:

```ts
expect(
  resolveModelSelection({
    availableModels: models,
    sessionModelId: "session-id",
    sessionModelValue: "provider/session",
    userDefaultId: "user-id",
    userDefaultValue: "provider/user",
    systemDefaultId: "system-id",
    systemDefaultValue: "provider/system",
  }),
).toEqual({ modelId: "session-id", modelValue: "provider/session" });

expect(
  resolveModelSelection({
    availableModels: models,
    userDefaultId: "user-id",
    userDefaultValue: "provider/user",
    systemDefaultId: "system-id",
    systemDefaultValue: "provider/system",
  }),
).toEqual({ modelId: "user-id", modelValue: "provider/user" });
```

Add separate tests proving that the system model wins when user fields are empty and that the first available model is only the final fallback.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/modelSelection.test.ts
```

Expected: FAIL because the resolver does not accept explicit user/system fields and currently chooses the first model instead of the system default.

- [ ] **Step 3: Add invalid-candidate and compatibility tests while still RED**

Cover these independent behaviors:

- invalid session falls through to a valid user candidate;
- invalid user falls through to a valid system candidate;
- a valid ID wins over a mismatched value and returns its canonical current value;
- a missing ID may resolve through a value only when exactly one available model has that value;
- duplicate value matches are unresolved and fall to the next tier;
- `availableModels: null` preserves the highest-priority raw candidate while data is unresolved;
- `availableModels: []` returns `{ modelId: "", modelValue: "" }` because availability is known to be empty.

- [ ] **Step 4: Implement the minimum pure resolver**

Replace ambiguous argument names with explicit source names:

```ts
interface ResolveModelSelectionArgs {
  availableModels?: ModelSelectionOption[] | null;
  sessionModelId?: string;
  sessionModelValue?: string;
  userDefaultId?: string;
  userDefaultValue?: string;
  systemDefaultId?: string;
  systemDefaultValue?: string;
}
```

Add one internal candidate resolver with these rules:

1. trim/ignore empty candidate strings;
2. return a valid ID match immediately with the available model's canonical value;
3. otherwise collect value matches and return only when the match count is exactly one;
4. return `null` for zero or duplicate matches.

For `null`/`undefined` availability, preserve the first raw candidate by priority without selecting the list fallback. For an empty array, return the empty selection. For loaded models, evaluate explicit session, user, system, and finally `availableModels[0]`. Keep temporary compatibility wrappers for the old exports until Task 4 migrates `ChatAppContent`, so each intermediate commit remains typecheckable; remove those wrappers as part of Task 4 so callers cannot pass rendered UI state as persisted session provenance.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the Task 1 command again. Expected: all model-selection tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add frontend/src/components/layout/AppContent/modelSelection.ts frontend/src/components/layout/AppContent/__tests__/modelSelection.test.ts
git commit -m "fix: encode model selection priority"
```

### Task 2: Expose the system model identity and availability state

**Files:**
- Create: `frontend/src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts`
- Modify: `frontend/src/contexts/SettingsContext.tsx`

- [ ] **Step 1: Write failing settings wiring tests**

Read `SettingsContext.tsx` as source and assert that:

- `SettingsContextValue` exposes `systemDefaultModelId: string`;
- the provider value passes `adminDefaultModelId` through as `systemDefaultModelId`;
- a successful response containing no models calls `setDbModels([])` rather than collapsing success into `null`.

The last assertion preserves the resolver's distinction between unresolved model data and a known empty list.

- [ ] **Step 2: Run the source test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts
```

Expected: FAIL because the context does not expose the default ID and successful empty responses currently set `null`.

- [ ] **Step 3: Implement the minimum context changes**

Add `systemDefaultModelId` to the context interface and value. Preserve `null` as loading/error state, but use an empty array for a successful model response with zero models. Keep the existing `defaultModel` value for compatible consumers.

- [ ] **Step 4: Run the source test and verify GREEN**

Run the Task 2 command again. Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add frontend/src/contexts/SettingsContext.tsx frontend/src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts
git commit -m "fix: expose system default model identity"
```

### Task 3: Mark the beginning of every session history load

**Files:**
- Modify: `frontend/src/components/layout/AppContent/useSessionSync.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx`

- [ ] **Step 1: Write a failing behavior test**

Extend the existing harness to accept `onSessionLoadStart(loadId)` and `onConfigRestored(config, loadId)` callbacks and record call order. For both the initial URL load and clicking session B, assert the start callback occurs immediately before the matching `loadHistory` call and that restoration receives the same ID. Use a flat sequence assertion so adjacency, ordering, and correlation are explicit.

Add an overlap case: keep load A pending, start load B, complete A late, and prove A's start/restore IDs remain paired and differ from B's. This supplies the caller enough information to reject stale A.

- [ ] **Step 2: Run the behavior test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx
```

Expected: FAIL because `useSessionSync` has no load-start callback.

- [ ] **Step 3: Implement load-start notification**

Add a monotonic `sessionLoadIdRef`. Change the optional callbacks to:

```ts
onSessionLoadStart?: (loadId: number) => void;
onConfigRestored?: (config: SessionConfig, loadId: number) => void;
```

Create one `beginSessionLoad()` helper that increments the ID and notifies the start callback. Invoke it directly before every history-load path, retain the returned ID in that async operation, and pass the same ID to restoration:

- initial URL mount;
- URL-change/external-navigation load;
- sidebar `handleSelectSession` load.

Do not invoke it for new-session clearing because no history load occurs.

- [ ] **Step 4: Run session-sync tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx src/components/layout/AppContent/__tests__/useSessionSync.test.ts
```

Expected: all session-sync tests PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add frontend/src/components/layout/AppContent/useSessionSync.ts frontend/src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx
git commit -m "fix: expose session history load start"
```

### Task 4: Wire refresh reconciliation and protect newer user choices

**Files:**
- Modify: `frontend/src/components/layout/AppContent/sessionState.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/sessionState.test.ts`
- Modify: `frontend/src/components/layout/AppContent/ChatAppContent.tsx`
- Modify: `frontend/src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts`

- [ ] **Step 1: Write failing revision-policy tests**

Add and test pure helpers for stale-load and revision policy:

```ts
shouldApplyRestoredModelSelection({
  restoredLoadId: 7,
  activeLoadId: 7,
  revisionAtLoadStart: 3,
  currentRevision: 3,
}) // true

shouldApplyRestoredModelSelection({
  restoredLoadId: 6,
  activeLoadId: 7,
  revisionAtLoadStart: 3,
  currentRevision: 3,
}) // false: stale load

shouldApplyRestoredModelSelection({
  restoredLoadId: 7,
  activeLoadId: 7,
  revisionAtLoadStart: 3,
  currentRevision: 4,
}) // false
```

The final case represents a user model change while the active history load is pending. Also test a small `isLatestSessionLoad` helper used to reject all configuration from stale loads, not only model fields.

- [ ] **Step 2: Extend the failing source wiring tests**

Assert `ChatAppContent.tsx`:

- reads `systemDefaultModelId` from settings context;
- keeps an explicit `sessionModelSelection` state rather than using rendered `currentModelId`/`currentModelValue` as resolver provenance;
- passes `filteredModels` and explicit session, user, and system candidates to `resolveModelSelection`;
- passes explicit user and system candidate fields to the resolver;
- supplies `onSessionLoadStart` to `useSessionSync`;
- increments a model-selection revision in `handleSelectModel`;
- gates restored model state updates with `shouldApplyRestoredModelSelection`;
- rejects stale restored configuration using the corresponding `loadId`;
- does not retain the old unconditional `if (isSessionRestoredRef.current) return` reconciliation guard or pass transient current UI state into the resolver.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/sessionState.test.ts src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts
```

Expected: FAIL because the revision helper and new wiring do not exist.

- [ ] **Step 4: Implement the revision helper and chat wiring**

In `sessionState.ts`, add `isLatestSessionLoad` and the pure load-ID-plus-revision helper. In `ChatAppContent.tsx`:

1. destructure `systemDefaultModelId`;
2. add explicit `sessionModelSelection` state, distinct from the rendered current selection;
3. add refs for the active load ID, current user-selection revision, and revision captured for the active load;
4. in `handleSessionLoadStart(loadId)`, replace the active load record with `{ loadId, revisionAtLoadStart }` and clear the prior session candidate for the new target;
5. in `handleConfigRestored(config, loadId)`, ignore the entire result unless `loadId` is still active;
6. apply restored `model_id`/`model` as the session candidate only when the revision helper says no newer user action occurred;
7. whenever `handleSelectModel` makes an explicit choice, increment the revision and replace the session candidate with that choice, making the deliberate in-session action the current session tier;
8. when starting a new chat, invalidate the active load, clear the session candidate, increment the revision, and resolve without a session candidate;
9. derive the rendered current selection by calling `resolveModelSelection` with `filteredModels` plus explicit session, user, and system candidates; do not feed the previous rendered selection back into the resolver.

A valid restored or manually selected session candidate therefore cannot be replaced by defaults. Invalid session candidates fall through via Task 1 policy. An older overlapping load cannot restore any config after a newer load starts, and a user selection made after the active load begins blocks only that load's model fields while allowing its other current configuration to restore.

- [ ] **Step 5: Run all focused model/session tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/components/layout/AppContent/__tests__/modelSelection.test.ts src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts src/components/layout/AppContent/__tests__/sessionState.test.ts src/components/layout/AppContent/__tests__/useSessionSyncBehavior.test.tsx src/components/layout/AppContent/__tests__/useSessionSync.test.ts
```

Expected: all focused tests PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add frontend/src/components/layout/AppContent/ChatAppContent.tsx frontend/src/components/layout/AppContent/sessionState.ts frontend/src/components/layout/AppContent/__tests__/sessionState.test.ts frontend/src/components/layout/AppContent/__tests__/modelSelectionWiringSource.test.ts
git commit -m "fix: preserve model choice across refresh"
```

### Task 5: Full frontend verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Run the complete frontend test suite**

```bash
cd frontend && pnpm test
```

Expected: PASS with no new failures.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && pnpm run lint
```

Expected: PASS with no new errors.

- [ ] **Step 3: Run the production build**

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite build PASS.

- [ ] **Step 4: Inspect final scope**

```bash
git status --short
git diff --check
```

Confirm that only the documented frontend selection/context/session files and tests changed after the design/plan documents, and that there is no whitespace damage.
