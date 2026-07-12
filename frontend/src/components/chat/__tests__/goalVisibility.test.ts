import {
  getGoalForMessage,
  getVisibleActiveGoalForMessages,
  shouldShowGoalDetailsForMessage,
} from "../goalVisibility.ts";
import type { Message } from "../../../types";
import type { ActiveGoalSpec } from "../../../hooks/useAgent/types";

const goal: ActiveGoalSpec = {
  objective: "ship it",
  started_at: "2026-05-30T08:00:00.000Z",
  runId: "run-goal",
};

function message(overrides: Partial<Message>): Message {
  return {
    id: "message",
    role: "assistant",
    content: "",
    timestamp: new Date("2026-05-30T08:01:00.000Z"),
    ...overrides,
  };
}

test("hides the active goal when the current conversation has no messages", () => {
  expect(getVisibleActiveGoalForMessages(goal, [])).toBe(null);
});

test("keeps the active goal visible when a current message belongs to its run", () => {
  expect(
    getVisibleActiveGoalForMessages(goal, [
      message({ id: "user", role: "user", runId: "run-goal" }),
    ]),
  ).toBe(goal);
});

test("hides the active goal when the latest message belongs to another run", () => {
  expect(
    getVisibleActiveGoalForMessages(goal, [
      message({ id: "goal-message", runId: "run-goal" }),
      message({ id: "ordinary", runId: "run-other" }),
    ]),
  ).toBe(null);
});

test("resolves the historical goal for a message by run id", () => {
  expect(
    getGoalForMessage(
      {
        "run-goal": goal,
      },
      message({ id: "goal-message", runId: "run-goal" }),
    ),
  ).toBe(goal);
});

test("does not show goal details on messages from a different run", () => {
  expect(
    shouldShowGoalDetailsForMessage(
      goal,
      message({ id: "ordinary", runId: "run-other" }),
    ),
  ).toBe(false);
});

test("shows goal details on messages from the goal run", () => {
  expect(
    shouldShowGoalDetailsForMessage(
      goal,
      message({ id: "goal-message", runId: "run-goal" }),
    ),
  ).toBe(true);
});
