import assert from "node:assert/strict";
import test from "node:test";

import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
} from "./sessionState.ts";

test("treats loading or visible streaming messages as an active session", () => {
  assert.equal(isSessionRunning([], true), true);
  assert.equal(
    isSessionRunning([{ isStreaming: false }, { isStreaming: true }], false),
    true,
  );
  assert.equal(isSessionRunning([{ isStreaming: false }], false), false);
});

test("shows the footer skeleton only when reconnecting after a stream disappears", () => {
  assert.equal(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "reconnecting",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
    true,
  );

  assert.equal(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "connected",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
    false,
  );

  assert.equal(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "disconnected",
      sessionRunning: true,
      messageCount: 2,
      hasVisibleStreamingMessage: true,
    }),
    false,
  );

  assert.equal(
    shouldShowStreamingFooterSkeleton({
      connectionStatus: "disconnected",
      sessionRunning: false,
      messageCount: 2,
      hasVisibleStreamingMessage: false,
    }),
    false,
  );
});
