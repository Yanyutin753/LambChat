/** status(memory) 事件——后台记忆注入的进度反馈（提交与召回解耦后）。 */
import type { Message } from "../../../types";
import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import type { StreamEvent } from "../types.ts";

const toastCalls: Array<{ op: string; id?: string }> = [];

vi.mock("react-hot-toast", () => ({
  default: {
    loading: (_msg: string, opts?: { id?: string }) =>
      toastCalls.push({ op: "loading", id: opts?.id }),
    dismiss: (id?: string) => toastCalls.push({ op: "dismiss", id }),
    success: () => undefined,
    error: () => undefined,
  },
}));

function createContext(): EventHandlerContext {
  return {
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
    setSandboxError: () => undefined,
    setActiveGoal: (() => undefined) as unknown as React.Dispatch<
      React.SetStateAction<import("../types").ActiveGoalSpec | null>
    >,
    setGoalsByRunId: (() => undefined) as unknown as React.Dispatch<
      React.SetStateAction<Record<string, import("../types").ActiveGoalSpec>>
    >,
  };
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
  beforeEach(() => {
    toastCalls.length = 0;
  });

  it("shows loading toast on status stage=memory", async () => {
    handleStreamEvent(
      event("status", { stage: "memory" }, "e1"),
      "m1",
      "e1",
      undefined,
      createContext(),
    );
    await vi.waitFor(() => {
      expect(
        toastCalls.some((c) => c.op === "loading" && c.id === "chat-memory-recall"),
      ).toBe(true);
    });
  });

  it("dismisses recall toast when metadata arrives", async () => {
    const ctx = createContext();
    handleStreamEvent(event("status", { stage: "memory" }, "e1"), "m1", "e1", undefined, ctx);
    handleStreamEvent(event("metadata", {}, "e2"), "m1", "e2", undefined, ctx);
    await vi.waitFor(() => {
      expect(
        toastCalls.some((c) => c.op === "dismiss" && c.id === "chat-memory-recall"),
      ).toBe(true);
    });
  });

  it("ignores other status stages", async () => {
    handleStreamEvent(
      event("status", { stage: "other" }, "e3"),
      "m1",
      "e3",
      undefined,
      createContext(),
    );
    await new Promise((r) => setTimeout(r, 30));
    expect(toastCalls).toHaveLength(0);
  });
});
