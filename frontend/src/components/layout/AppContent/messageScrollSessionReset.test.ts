import test from "node:test";
import assert from "node:assert/strict";
import {
  getNextMessageListSessionKey,
  shouldResetMessageScrollStateForSessionChange,
} from "./useMessageScroll.followState";

test("does not reset scroll state when a new live session receives its first real session id", () => {
  assert.equal(
    shouldResetMessageScrollStateForSessionChange({
      previousSessionId: null,
      sessionId: "session-1",
      messageCount: 2,
    }),
    false,
  );
});

test("does reset scroll state when switching between existing sessions", () => {
  assert.equal(
    shouldResetMessageScrollStateForSessionChange({
      previousSessionId: "session-1",
      sessionId: "session-2",
      messageCount: 2,
    }),
    true,
  );
});

test("keeps the existing message list key during the first null-to-session transition with live messages", () => {
  assert.equal(
    getNextMessageListSessionKey({
      previousSessionId: null,
      sessionId: "session-1",
      messageCount: 2,
      previousKey: "__new_session__",
    }),
    "__new_session__",
  );
});

test("switches the message list key when navigating to another stored session", () => {
  assert.equal(
    getNextMessageListSessionKey({
      previousSessionId: "session-1",
      sessionId: "session-2",
      messageCount: 10,
      previousKey: "session-1",
    }),
    "session-2",
  );
});
