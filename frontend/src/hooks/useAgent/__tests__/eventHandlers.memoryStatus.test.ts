/** status(memory) 事件——后台记忆注入的界面内加载状态（提交与召回解耦后）。 */
import type { Message } from "../../../types";
import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import type { StreamEvent } from "../types.ts";

function createContext() {
  const recallStates: boolean[] = [];
  const ctx: EventHandlerContext = {
    sessionIdRef: { current: "session-1" },
    processedEventIdsRef: { current: new Set<string>() },
    lastHistoryTimestampRef: { current: null },
    activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 },
    setSessionId: () => undefined,
    setMessages: (() => undefined) as unknown as React.Dispatch<
      React.SetStateAction<Message[]>
    >,
    setConnectionStatus: () => undefined,
    setIsInitializingSandbox: () => undefined,
    setIsRecallingMemory: (loading: boolean) => recallStates.push(loading),
    setSandboxError: () => undefined,
    setActiveGoal: (() => undefined) as unknown as React.Dispatch<
      React.SetStateAction<import("../types").ActiveGoalSpec | null>
    >,
    setGoalsByRunId: (() => undefined) as unknown as React.Dispatch<
      React.SetStateAction<Record<string, import("../types").ActiveGoalSpec>>
    >,
  };
  return { ctx, recallStates };
}

function event(name: string, payload: unknown, id: string): StreamEvent {
  return {
    event: name,
    data: JSON.stringify(payload),
    id,
    timestamp: undefined,
  } as unknown as StreamEvent;
}

describe("memory recall status event", () => {
  it("sets recall state on status stage=memory and clears on metadata", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "memory" }, "e1"), "m1", "e1", undefined, ctx);
    handleStreamEvent(event("metadata", {}, "e2"), "m1", "e2", undefined, ctx);
    expect(recallStates).toEqual([true, false]);
  });

  it("ignores other status stages", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "other" }, "e3"), "m1", "e3", undefined, ctx);
    expect(recallStates).toEqual([]);
  });
});
