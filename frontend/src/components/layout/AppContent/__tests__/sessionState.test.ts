import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
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
