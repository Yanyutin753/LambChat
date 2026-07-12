import { getAgentOptionSyncMode } from "../useAgentOptions";

test("resets agent options when switching to a different agent with identical option schemas", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-b",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
  ).toBe("reset");
});

test("applies restored session options before skip checks", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: true,
    }),
  ).toBe("restore");
});

test("preserves overlapping values only when the same agent schema changes", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"high"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
  ).toBe("preserve");
});
