import {
  getNextMessageListSessionKey,
  shouldResetMessageScrollStateForSessionChange,
} from "../useMessageScroll.followState";

test("does not reset scroll state when a new live session receives its first real session id", () => {
  expect(
    shouldResetMessageScrollStateForSessionChange({
      previousSessionId: null,
      sessionId: "session-1",
      messageCount: 2,
    }),
  ).toBe(false);
});

test("does reset scroll state when switching between existing sessions", () => {
  expect(
    shouldResetMessageScrollStateForSessionChange({
      previousSessionId: "session-1",
      sessionId: "session-2",
      messageCount: 2,
    }),
  ).toBe(true);
});

test("keeps the existing message list key during the first null-to-session transition with live messages", () => {
  expect(
    getNextMessageListSessionKey({
      previousSessionId: null,
      sessionId: "session-1",
      messageCount: 2,
      previousKey: "__new_session__",
    }),
  ).toBe("__new_session__");
});

test("switches the message list key when navigating to another stored session", () => {
  expect(
    getNextMessageListSessionKey({
      previousSessionId: "session-1",
      sessionId: "session-2",
      messageCount: 10,
      previousKey: "session-1",
    }),
  ).toBe("session-2");
});
