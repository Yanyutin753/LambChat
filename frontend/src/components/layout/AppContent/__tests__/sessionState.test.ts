import {
  applyLatestSessionLoadResult,
  isLatestSessionLoad,
  isSessionRunning,
  shouldApplyRestoredModelSelection,
  shouldShowStreamingFooterSkeleton,
  withoutModelSelection,
} from "../sessionState.ts";

test("treats loading or visible streaming messages as an active session", () => {
  expect(isSessionRunning([], true)).toBe(true);
  expect(
    isSessionRunning([{ isStreaming: false }, { isStreaming: true }], false),
  ).toBe(true);
  expect(isSessionRunning([{ isStreaming: false }], false)).toBe(false);
});

test("shows the footer skeleton only when reconnecting after a stream disappears", () => {
  expect(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "reconnecting",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
  ).toBe(true);

  expect(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "connected",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
  ).toBe(false);

  expect(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "disconnected",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: true,
    }),
  ).toBe(false);

  expect(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "disconnected",
      sessionRunning: false,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
  ).toBe(false);
});

test("accepts configuration only from the latest session load", () => {
  expect(isLatestSessionLoad({ restoredLoadId: 7, activeLoadId: 7 })).toBe(
    true,
  );
  expect(isLatestSessionLoad({ restoredLoadId: 6, activeLoadId: 7 })).toBe(
    false,
  );
  expect(isLatestSessionLoad({ restoredLoadId: 7, activeLoadId: null })).toBe(
    false,
  );
});

test("applies a restored model only when its load is current and no newer choice exists", () => {
  expect(
    shouldApplyRestoredModelSelection({
      restoredLoadId: 7,
      activeLoadId: 7,
      revisionAtLoadStart: 3,
      currentRevision: 3,
    }),
  ).toBe(true);

  expect(
    shouldApplyRestoredModelSelection({
      restoredLoadId: 6,
      activeLoadId: 7,
      revisionAtLoadStart: 3,
      currentRevision: 3,
    }),
  ).toBe(false);

  expect(
    shouldApplyRestoredModelSelection({
      restoredLoadId: 7,
      activeLoadId: 7,
      revisionAtLoadStart: 3,
      currentRevision: 4,
    }),
  ).toBe(false);
});

test("removes model identity from generic agent options", () => {
  expect(
    withoutModelSelection({
      model_id: "stale-id",
      model: "provider/stale",
      enable_thinking: "high",
    }),
  ).toEqual({ enable_thinking: "high" });
});

test("does not apply an async result after a newer session load starts", async () => {
  let activeLoadId = 1;
  let resolveFirst: ((value: string) => void) | undefined;
  const firstResult = new Promise<string>((resolve) => {
    resolveFirst = resolve;
  });
  const applied: string[] = [];

  const firstTask = applyLatestSessionLoadResult({
    load: firstResult,
    restoredLoadId: 1,
    getActiveLoadId: () => activeLoadId,
    apply: (value) => applied.push(value),
  });

  activeLoadId = 2;
  const secondApplied = await applyLatestSessionLoadResult({
    load: Promise.resolve("session-b"),
    restoredLoadId: 2,
    getActiveLoadId: () => activeLoadId,
    apply: (value) => applied.push(value),
  });

  resolveFirst?.("session-a");
  const firstApplied = await firstTask;

  expect(secondApplied).toBe(true);
  expect(firstApplied).toBe(false);
  expect(applied).toEqual(["session-b"]);
});
