import type { Message } from "../../../types";
import { describe, expect, test } from "vitest";

import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import { reconstructMessagesFromEvents } from "../historyLoader.ts";
import type { HistoryEvent, StreamEvent } from "../types.ts";

function createLiveContext(initial: Message[]): {
  ctx: EventHandlerContext;
  messages: () => Message[];
  effects: () => { sandboxCleared: number; sandboxErrorCleared: number };
} {
  let messages = initial;
  let sandboxCleared = 0;
  let sandboxErrorCleared = 0;
  return {
    ctx: {
      sessionIdRef: { current: "session-1" },
      processedEventIdsRef: { current: new Set<string>() },
      lastHistoryTimestampRef: { current: null },
      activeSubagentStackRef: {
        current: [
          { agent_id: "researcher", depth: 1, message_id: "run-1" },
        ],
      },
      streamVersionRef: { current: 0 },
      setSessionId: () => undefined,
      setMessages: (updater: React.SetStateAction<Message[]>) => {
        messages = typeof updater === "function" ? updater(messages) : updater;
      },
      setConnectionStatus: () => undefined,
      setIsInitializingSandbox: () => {
        sandboxCleared += 1;
      },
        setSandboxError: (error: unknown) => {
        if (error === null) sandboxErrorCleared += 1;
      },
      setActiveGoal: () => undefined,
      setGoalsByRunId: () => undefined,
    } as EventHandlerContext,
    messages: () => messages,
    effects: () => ({ sandboxCleared, sandboxErrorCleared }),
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

  test("run:resumed resets stuck subagent stack and sandbox loader", () => {
    const { ctx, effects } = createLiveContext([]);

    handleStreamEvent(
      { event: "run:resumed", data: JSON.stringify({ run_id: "run-1" }) },
      "run-1",
      "evt-resumed-globals",
      undefined,
      ctx,
    );

    // 中断卡住的全局态随恢复一并复位
    expect(ctx.activeSubagentStackRef.current).toEqual([]);
    expect(effects().sandboxCleared).toBe(1);
    expect(effects().sandboxErrorCleared).toBe(1);
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

describe("history folding of unfinished runs", () => {
  const fold = (events: HistoryEvent[]) =>
    reconstructMessagesFromEvents(events, new Set<string>(), {
      activeSubagentStack: [],
    });

  test("run without terminal event leaves no pending tool/thinking spinners", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "原问题" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "tool:start",
        run_id: "run-1",
        data: { tool: "bash", tool_call_id: "t1", args: { cmd: "ls" } },
        timestamp: "2026-09-01T00:00:01Z",
      },
      {
        event_type: "thinking",
        run_id: "run-1",
        data: { content: "半截思考" },
        timestamp: "2026-09-01T00:00:02Z",
      },
      // 无 tool:result / 无 done：中断后未恢复的 run
    ]);
    const assistant = messages.find((m) => m.role === "assistant");

    const tool = assistant?.parts?.find((p) => p.type === "tool");
    expect(tool).toMatchObject({ isPending: false, cancelled: true });
    const thinking = assistant?.parts?.find((p) => p.type === "thinking");
    expect(thinking).toMatchObject({ isStreaming: false });
  });

  test("streaming tool args (tool:args:chunk) partial also stops loading", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "原问题" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "tool:args:chunk",
        run_id: "run-1",
        data: { tool: "bash", tool_call_id: "t9", content: "ls -l" },
        timestamp: "2026-09-01T00:00:01Z",
      },
    ]);
    const assistant = messages.find((m) => m.role === "assistant");
    const tool = assistant?.parts?.find((p) => p.type === "tool");

    expect(tool).toMatchObject({ isPending: false, cancelled: true });
    // 半截参数内容保留
    expect((tool as { args?: Record<string, unknown> })?.args).toMatchObject({
      partial: "ls -l",
    });
  });

  test("subagent with pending nested tool is cleaned recursively", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "原问题" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "agent:call",
        run_id: "run-1",
        data: { agent_id: "researcher", depth: 1 },
        timestamp: "2026-09-01T00:00:01Z",
      },
      {
        event_type: "tool:start",
        run_id: "run-1",
        data: { tool: "bash", tool_call_id: "t2", args: {}, depth: 1 },
        timestamp: "2026-09-01T00:00:02Z",
      },
    ]);
    const assistant = messages.find((m) => m.role === "assistant");
    const subagent = assistant?.parts?.find((p) => p.type === "subagent") as
      | { parts?: Array<Record<string, unknown>>; isPending?: boolean }
      | undefined;

    expect(subagent).toBeDefined();
    expect(subagent?.isPending).toBe(false);
    const nestedTool = subagent?.parts?.find((p) => p.type === "tool");
    expect(nestedTool).toMatchObject({ isPending: false });
  });

  test("unfinished HITL run keeps its ask-human card responsive", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "ask human" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "approval_required",
        run_id: "run-1",
        data: { id: "approval-1", message: "请回答", fields: [] },
        timestamp: "2026-09-01T00:00:01Z",
      },
    ]);
    const assistant = messages.find((m) => m.role === "assistant");
    const askHuman = assistant?.parts?.find((p) => p.type === "tool");

    expect(askHuman).toMatchObject({ name: "ask_human", isPending: true });
  });

  test("partial text content is preserved untouched", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "原问题" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        data: { content: "写到一半的正文" },
        timestamp: "2026-09-01T00:00:01Z",
      },
    ]);
    const assistant = messages.find((m) => m.role === "assistant");

    expect(assistant?.content).toBe("写到一半的正文");
  });

  test("completed run keeps its tool parts untouched", () => {
    const messages = fold([
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "原问题" },
        timestamp: "2026-09-01T00:00:00Z",
      },
      {
        event_type: "tool:start",
        run_id: "run-1",
        data: { tool: "bash", tool_call_id: "t1", args: {} },
        timestamp: "2026-09-01T00:00:01Z",
      },
      {
        event_type: "done",
        run_id: "run-1",
        data: {},
        timestamp: "2026-09-01T00:00:02Z",
      },
    ]);
    const assistant = messages.find((m) => m.role === "assistant");
    const tool = assistant?.parts?.find((p) => p.type === "tool");

    // done 之后的 run 已终态：工具保持原样（是否有结果由事件决定，不做清理判定）
    expect(assistant?.parts?.length).toBeGreaterThan(0);
    expect(tool).toBeDefined();
  });
});
