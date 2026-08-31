import type { Message } from "../../../types";
import { describe, expect, test } from "vitest";

import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import { reconstructMessagesFromEvents } from "../historyLoader.ts";
import type { HistoryEvent, StreamEvent } from "../types.ts";

function createLiveContext(initial: Message[]): {
  ctx: EventHandlerContext;
  messages: () => Message[];
} {
  let messages = initial;
  return {
    ctx: {
      sessionIdRef: { current: "session-1" },
      processedEventIdsRef: { current: new Set<string>() },
      lastHistoryTimestampRef: { current: null },
      activeSubagentStackRef: { current: [] },
      streamVersionRef: { current: 0 },
      setSessionId: () => undefined,
      setMessages: (updater: React.SetStateAction<Message[]>) => {
        messages = typeof updater === "function" ? updater(messages) : updater;
      },
      setConnectionStatus: () => undefined,
      setIsInitializingSandbox: () => undefined,
      setSandboxError: () => undefined,
      setActiveGoal: () => undefined,
      setGoalsByRunId: () => undefined,
    } as EventHandlerContext,
    messages: () => messages,
  };
}

describe("live run:resumed event", () => {
  test("resets interrupted bubble content and returns to streaming", () => {
    const { ctx, messages } = createLiveContext([
      {
        id: "run-1",
        role: "assistant",
        content: "错误：连接中断",
        timestamp: new Date(),
        isStreaming: false,
        cancelled: true,
        runId: "run-1",
        parts: [{ type: "cancelled" }],
        toolCalls: [{ id: "t1", name: "bash", args: {} }],
      },
    ]);

    const event: StreamEvent = {
      event: "run:resumed",
      data: JSON.stringify({ run_id: "run-1" }),
    };
    handleStreamEvent(event, "run-1", "evt-resumed-1", undefined, ctx);

    const message = messages().find((m) => m.id === "run-1");
    expect(message).toBeDefined();
    expect(message?.parts).toEqual([]);
    expect(message?.content).toBe("");
    expect(message?.toolCalls).toEqual([]);
    expect(message?.cancelled).toBe(false);
    expect(message?.isStreaming).toBe(true);
  });

  test("creates a streaming placeholder when bubble does not exist yet", () => {
    const { ctx, messages } = createLiveContext([]);

    handleStreamEvent(
      {
        event: "run:resumed",
        data: JSON.stringify({ run_id: "run-1" }),
      },
      "run-1",
      "evt-resumed-2",
      undefined,
      ctx,
    );

    const message = messages().find((m) => m.id === "run-1");
    expect(message?.role).toBe("assistant");
    expect(message?.isStreaming).toBe(true);
    expect(message?.parts).toEqual([]);
  });

  test("post-resume chunks rebuild content from scratch", () => {
    const { ctx, messages } = createLiveContext([
      {
        id: "run-1",
        role: "assistant",
        content: "半截输出",
        timestamp: new Date(),
        isStreaming: true,
        runId: "run-1",
        parts: [],
      },
    ]);

    handleStreamEvent(
      { event: "run:resumed", data: JSON.stringify({ run_id: "run-1" }) },
      "run-1",
      "evt-resumed-3",
      undefined,
      ctx,
    );
    handleStreamEvent(
      {
        event: "message:chunk",
        data: JSON.stringify({ content: "重新生成的完整回答" }),
      },
      "run-1",
      "evt-chunk-1",
      undefined,
      ctx,
    );

    expect(messages().find((m) => m.id === "run-1")?.content).toBe(
      "重新生成的完整回答",
    );
  });
});

describe("history rebuild with run:resumed", () => {
  const events: HistoryEvent[] = [
    {
      event_type: "user:message",
      run_id: "run-1",
      data: { content: "原问题" },
      timestamp: "2026-09-01T00:00:00Z",
    },
    {
      event_type: "message:chunk",
      run_id: "run-1",
      data: { content: "中断前的半截" },
      timestamp: "2026-09-01T00:00:01Z",
    },
    {
      event_type: "run:resumed",
      run_id: "run-1",
      data: { run_id: "run-1" },
      timestamp: "2026-09-01T00:00:10Z",
    },
    {
      event_type: "message:chunk",
      run_id: "run-1",
      data: { content: "恢复后的完整回答" },
      timestamp: "2026-09-01T00:00:11Z",
    },
  ];

  test("keeps only post-resume content in the assistant bubble", () => {
    const messages = reconstructMessagesFromEvents(
      events,
      new Set<string>(),
      { activeSubagentStack: [] },
    );
    const assistant = messages.find((m) => m.role === "assistant");

    expect(assistant?.content).toBe("恢复后的完整回答");
    expect(assistant?.id).toBe("run-1");
  });

  test("a run interrupted without resume still keeps partial content", () => {
    const messages = reconstructMessagesFromEvents(
      events.slice(0, 2),
      new Set<string>(),
      { activeSubagentStack: [] },
    );
    const assistant = messages.find((m) => m.role === "assistant");

    expect(assistant?.content).toBe("中断前的半截");
  });
});
