import { vi } from "vitest";
import { handleStreamEvent, type EventHandlerContext } from "../eventHandlers";
import { extractPersistentGoalFromEvents } from "../historyLoader";

const goal = { id: "g1", session_id: "s1", objective: "docs", status: "active", revision: 2 };

test("goal updated event uses dedicated state and run end never completes it", () => {
  const setPersistentGoal = vi.fn();
  const ctx = {
    sessionIdRef: { current: "s1" }, processedEventIdsRef: { current: new Set() },
    lastHistoryTimestampRef: { current: null }, activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 }, setPersistentGoal,
    setActiveGoal: vi.fn(), setGoalsByRunId: vi.fn(), setMessages: vi.fn(),
  } as unknown as EventHandlerContext;
  handleStreamEvent({ event: "goal:updated", data: JSON.stringify({ goal }) }, "m1", "e1", undefined, ctx);
  expect(setPersistentGoal).toHaveBeenCalledOnce();
  expect(ctx.setActiveGoal).not.toHaveBeenCalled();
  handleStreamEvent({ event: "goal:updated", data: JSON.stringify({ goal: { ...goal, session_id: "foreign" } }) }, "m1", "e2", undefined, ctx);
  expect(setPersistentGoal).toHaveBeenCalledOnce();
});

test("history persistent goal comes only from goal updated with matching scope", () => {
  expect(extractPersistentGoalFromEvents([
    { event_type: "goal:updated", data: { goal } },
    { event_type: "goal:end", data: { goal: { objective: "run ended" } } },
  ], "s1")).toEqual(goal);
  expect(extractPersistentGoalFromEvents([{ event_type: "goal:updated", data: { goal } }], "other")).toBeNull();
});
