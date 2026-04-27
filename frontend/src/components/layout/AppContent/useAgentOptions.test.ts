import test from "node:test";
import assert from "node:assert/strict";
import { getAgentOptionSyncMode } from "./useAgentOptions";

test("resets agent options when switching to a different agent with identical option schemas", () => {
  assert.equal(
    getAgentOptionSyncMode({
      currentAgentId: "agent-b",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
    "reset",
  );
});

test("applies restored session options before skip checks", () => {
  assert.equal(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: true,
    }),
    "restore",
  );
});

test("preserves overlapping values only when the same agent schema changes", () => {
  assert.equal(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"high"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
    "preserve",
  );
});
