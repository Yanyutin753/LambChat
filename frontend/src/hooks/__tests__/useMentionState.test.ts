import { findMentionMatch, getMentionState } from "../useMentionState.ts";

test("detects a standalone at sign as an empty mention query", () => {
  expect(findMentionMatch("@", 1)).toEqual({
    atIndex: 0,
    query: "",
  });
});

test("activates mention search without requiring preloaded results", () => {
  expect(
    getMentionState({
      input: "@",
      cursorPosition: 1,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: null,
    }),
  ).toEqual({
    isActive: true,
    query: "",
    atIndex: 0,
    highlightedIndex: 0,
  });
});

test("suppresses only the currently dismissed mention token", () => {
  expect(
    getMentionState({
      input: "@",
      cursorPosition: 1,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: { input: "@", atIndex: 0 },
    }).isActive,
  ).toBe(false);

  expect(
    getMentionState({
      input: " @",
      cursorPosition: 2,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: { input: "@", atIndex: 0 },
    }).isActive,
  ).toBe(true);
});
