/** status(memory/memory_done) 事件——首轮记忆装配的开始/完成事件。

对齐沙箱初始化（starting/ready）的两段式生命周期：开始亮行、完成收起，
且带最短展示保护——SSE 重放时 start/done 可能同批毫秒级到达，React 合并
渲染会吞掉行，固定延迟收起保证用户总能看见。
*/
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows row on start and collapses on memory_done after min display", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "memory" }, "e1"), "m1", "e1", undefined, ctx);
    expect(recallStates).toEqual([true]);
    handleStreamEvent(event("status", { stage: "memory_done" }, "e2"), "m1", "e2", undefined, ctx);
    // 召回刚完成：未到最短展示时长，不立即收起（防 SSE 重放同批吞行）
    expect(recallStates).toEqual([true]);
    vi.advanceTimersByTime(600);
    expect(recallStates).toEqual([true, false]);
  });

  it("collapses promptly on memory_done when recall was slow", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "memory" }, "e3"), "m1", "e3", undefined, ctx);
    vi.advanceTimersByTime(2000); // 召回耗时 2s，早已满足最短展示
    handleStreamEvent(event("status", { stage: "memory_done" }, "e4"), "m1", "e4", undefined, ctx);
    expect(recallStates).toEqual([true]); // 收起仍走异步任务
    vi.advanceTimersByTime(0);
    expect(recallStates).toEqual([true, false]);
  });

  it("metadata also collapses the row (fallback, min display applies)", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "memory" }, "e5"), "m1", "e5", undefined, ctx);
    handleStreamEvent(event("metadata", {}, "e6"), "m1", "e6", undefined, ctx);
    expect(recallStates).toEqual([true]);
    vi.advanceTimersByTime(600);
    expect(recallStates).toEqual([true, false]);
  });

  it("ignores other status stages", () => {
    const { ctx, recallStates } = createContext();
    handleStreamEvent(event("status", { stage: "other" }, "e7"), "m1", "e7", undefined, ctx);
    expect(recallStates).toEqual([]);
  });
});
