import test from "node:test";
import assert from "node:assert/strict";

import { findMentionMatch, getMentionState } from "../useMentionState.ts";

test("detects a standalone at sign as an empty mention query", () => {
  assert.deepEqual(findMentionMatch("@", 1), {
    atIndex: 0,
    query: "",
  });
});

test("activates mention search without requiring preloaded results", () => {
  assert.deepEqual(
    getMentionState({
      input: "@",
      cursorPosition: 1,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: null,
    }),
    {
      isActive: true,
      query: "",
      atIndex: 0,
      highlightedIndex: 0,
    },
  );
});

test("suppresses only the currently dismissed mention token", () => {
  assert.equal(
    getMentionState({
      input: "@",
      cursorPosition: 1,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: { input: "@", atIndex: 0 },
    }).isActive,
    false,
  );

  assert.equal(
    getMentionState({
      input: " @",
      cursorPosition: 2,
      enabled: true,
      highlightedIndex: 0,
      dismissedMention: { input: "@", atIndex: 0 },
    }).isActive,
    true,
  );
});
