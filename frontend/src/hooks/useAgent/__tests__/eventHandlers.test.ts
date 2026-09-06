import type { Message } from "../../../types";
import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import type { ActiveGoalSpec, StreamEvent } from "../types.ts";
import { prepareMessagesForRunningRun } from "../historyLoader.ts";
import { subscribePersonaPresetsChanged } from "../../personaPresetEvents.ts";
import { subscribeTeamsChanged } from "../../teamEvents.ts";
import { vi } from "vitest";

function createContext(
  messages: Message[],
  lastHistoryTimestamp: Date | null,
): EventHandlerContext & {
  connectionStatuses: string[];
  messages: () => Message[];
  activeGoal: () => ActiveGoalSpec | null;
  setMessagesCalls: () => number;
} {
  let setMessagesCalls = 0;
  let activeGoal: ActiveGoalSpec | null = null;
  const connectionStatuses: string[] = [];

  return {
    sessionIdRef: { current: "session-1" },
    processedEventIdsRef: { current: new Set<string>() },
    lastHistoryTimestampRef: { current: lastHistoryTimestamp },
    activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 },
    setSessionId: () => undefined,
    setMessages: (updater: React.SetStateAction<Message[]>) => {
      setMessagesCalls += 1;
      if (typeof updater === "function") {
        messages = updater(messages);
      } else {
        messages = updater;
      }
    },
    setConnectionStatus: (status: string) => {
      connectionStatuses.push(status);
    },
    setIsInitializingSandbox: () => undefined,
    setSandboxError: () => undefined,
    setActiveGoal: (updater: React.SetStateAction<ActiveGoalSpec | null>) => {
      activeGoal =
        typeof updater === "function" ? updater(activeGoal) : updater;
    },
    setGoalsByRunId: () => undefined,
    connectionStatuses,
    messages: () => messages,
    activeGoal: () => activeGoal,
    setMessagesCalls: () => setMessagesCalls,
  } as EventHandlerContext & {
    connectionStatuses: string[];
    messages: () => Message[];
    activeGoal: () => ActiveGoalSpec | null;
    setMessagesCalls: () => number;
  };
}

test("skips SSE events older than loaded history", () => {
  const historyTimestamp = "2026-04-19T01:02:03.456Z";
  const eventTimestamp = "2026-04-19T01:02:03.455Z";
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date(historyTimestamp),
        parts: [],
        isStreaming: true,
      },
    ],
    new Date(historyTimestamp),
  );

  const event: StreamEvent = {
    event: "message:chunk",
    data: JSON.stringify({ content: "older", _timestamp: eventTimestamp }),
  };

  handleStreamEvent(event, "assistant-1", "redis-event-1", eventTimestamp, ctx);

  expect(ctx.setMessagesCalls()).toBe(0);
});

test("renders approval_required from the SSE payload when approval lookup is unavailable", async () => {
  const onApprovalRequired = vi.fn();
  const ctx = createContext([], null);
  ctx.options = { onApprovalRequired };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "approval-1", status: "not_found" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  handleStreamEvent(
    {
      event: "approval_required",
      data: JSON.stringify({
        id: "approval-1",
        message: "请回答几个问题",
        type: "form",
        fields: [
          {
            name: "topic",
            label: "主题",
            type: "select",
            required: true,
            options: ["兴趣爱好"],
          },
        ],
      }),
    },
    "assistant-1",
    "approval-event-1",
    undefined,
    ctx,
  );

  await vi.waitFor(() => expect(onApprovalRequired).toHaveBeenCalled());
  expect(onApprovalRequired).toHaveBeenCalledWith(
    expect.objectContaining({
      id: "approval-1",
      message: "请回答几个问题",
      fields: expect.arrayContaining([
        expect.objectContaining({ name: "topic" }),
      ]),
    }),
  );
  expect(ctx.messages()).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: "assistant-1",
        parts: expect.arrayContaining([
          expect.objectContaining({
            type: "tool",
            name: "ask_human",
            isPending: true,
          }),
        ]),
      }),
    ]),
  );
  vi.unstubAllGlobals();
});

test("renders a delivered steer event and removes its optimistic duplicate", () => {
  const timestamp = "2026-04-19T01:02:03.456Z";
  const marked: string[] = [];
  const ctx = createContext(
    [
      {
        id: "optimistic-steer",
        role: "user",
        content: "继续做这个",
        timestamp: new Date(timestamp),
        metadata: { steer: true, queued: true },
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: "前面的回答",
        timestamp: new Date(timestamp),
        parts: [],
        isStreaming: true,
      },
    ],
    null,
  );
  ctx.markSteerDelivered = (content) => marked.push(content);

  handleStreamEvent(
    {
      event: "steer:message",
      data: JSON.stringify({ content: "继续做这个", message_id: "steer-1" }),
    },
    "assistant-1",
    "steer-event-1",
    timestamp,
    ctx,
  );

  const messages = ctx.messages();
  expect(
    messages.filter((message) => message.content === "继续做这个"),
  ).toHaveLength(1);
  expect(
    messages.find((message) => message.id === "steer-1")?.metadata,
  ).toEqual({
    steer: true,
    queued: false,
  });
  expect(messages.map((message) => message.id)).toEqual([
    "assistant-1#t1",
    "steer-1",
    "assistant-1",
  ]);
  expect(marked).toEqual(["继续做这个"]);
});

test("uses the steer created_at send time for the delivered message timestamp", () => {
  const ctx = createContext([], null);

  handleStreamEvent(
    {
      event: "steer:message",
      data: JSON.stringify({
        content: "中途插话",
        message_id: "steer-ts",
        created_at: "2026-08-22T15:14:55.000Z",
      }),
    },
    "assistant-1",
    "steer-ts-event",
    "2026-08-22T15:14:56.100Z",
    ctx,
  );

  const delivered = ctx.messages().find((message) => message.id === "steer-ts");
  expect(delivered?.timestamp?.toISOString()).toBe("2026-08-22T15:14:55.000Z");
});

test("keeps distinct steer events with the same content when IDs differ", () => {
  const ctx = createContext([], null);
  const first = {
    event: "steer:message",
    data: JSON.stringify({ content: "同一句", message_id: "steer-a" }),
  } as StreamEvent;
  const second = {
    event: "steer:message",
    data: JSON.stringify({ content: "同一句", message_id: "steer-b" }),
  } as StreamEvent;
  handleStreamEvent(first, "assistant-1", "steer-a-event", undefined, ctx);
  handleStreamEvent(second, "assistant-1", "steer-b-event", undefined, ctx);
  expect(
    ctx
      .messages()
      .filter((message) => message.metadata?.steer)
      .map((m) => m.id),
  ).toEqual(["steer-a", "steer-b"]);
});

test("ignores a delivered steer from a stale run", () => {
  const ctx = createContext([], null);
  ctx.currentRunIdRef = { current: "run-current" };
  handleStreamEvent(
    {
      event: "steer:message",
      data: JSON.stringify({
        content: "旧消息",
        message_id: "old",
        run_id: "run-old",
      }),
    },
    "assistant-1",
    "old-event",
    undefined,
    ctx,
  );
  expect(ctx.messages()).toEqual([]);
});

test("clears approvals only for the session whose stream failed", () => {
  const cleared: Array<string | null | undefined> = [];
  const ctx = createContext([], null);
  ctx.options = {
    onClearApprovals: (sessionId) => cleared.push(sessionId),
  };

  handleStreamEvent(
    {
      event: "error",
      data: JSON.stringify({ error: "failed" }),
    },
    "assistant-1",
    "error-event",
    undefined,
    ctx,
  );

  expect(cleared).toEqual(["session-1"]);
});

test("keeps post-steer tool and assistant output after the steer message", () => {
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "第一轮回复",
        timestamp: new Date("2026-08-20T12:45:43.970Z"),
        parts: [{ type: "text", content: "第一轮回复" }],
        isStreaming: true,
      },
    ],
    null,
  );
  const events: Array<[StreamEvent, string]> = [
    [
      {
        event: "steer:message",
        data: JSON.stringify({ content: "1500字的", message_id: "steer-1" }),
      },
      "steer-event",
    ],
    [
      {
        event: "tool:start",
        data: JSON.stringify({
          tool: "write_file",
          tool_call_id: "tool-1",
          args: {},
        }),
      },
      "tool-start",
    ],
    [
      {
        event: "message:chunk",
        data: JSON.stringify({ content: "第二轮回复" }),
      },
      "message-chunk",
    ],
    [{ event: "done", data: JSON.stringify({ status: "completed" }) }, "done"],
  ];
  for (const [event, eventId] of events) {
    handleStreamEvent(
      event,
      "assistant-1",
      eventId,
      "2026-08-20T12:46:03.142Z",
      ctx,
    );
  }

  const messages = ctx.messages();
  expect(messages.map((message) => message.id)).toEqual([
    "assistant-1#t1",
    "steer-1",
    "assistant-1",
  ]);
  expect(messages[2]?.content).toContain("第二轮回复");
  expect(messages[2]?.toolCalls).toHaveLength(1);
  expect(messages[2]?.isStreaming).toBe(false);
});

test("keeps distinct SSE events that share the same timestamp", () => {
  const timestamp = "2026-04-19T01:02:03.456Z";
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date(timestamp),
        parts: [],
        isStreaming: true,
      },
    ],
    null,
  );

  handleStreamEvent(
    {
      event: "message:chunk",
      data: JSON.stringify({ content: "hello ", _timestamp: timestamp }),
    },
    "assistant-1",
    "redis-event-1",
    timestamp,
    ctx,
  );
  handleStreamEvent(
    {
      event: "message:chunk",
      data: JSON.stringify({ content: "world", _timestamp: timestamp }),
    },
    "assistant-1",
    "redis-event-2",
    timestamp,
    ctx,
  );

  expect(ctx.setMessagesCalls()).toBe(2);
  expect(ctx.messages()[0]?.content).toBe("hello world");
});

test("creates a new streaming assistant for a running run after the latest user message", () => {
  const messages: Message[] = [
    {
      id: "user-previous",
      role: "user",
      content: "previous question",
      timestamp: new Date("2026-04-19T01:00:00.000Z"),
      runId: "run-previous",
    },
    {
      id: "assistant-previous",
      role: "assistant",
      content: "previous answer",
      timestamp: new Date("2026-04-19T01:00:01.000Z"),
      runId: "run-previous",
      isStreaming: false,
    },
    {
      id: "user-latest",
      role: "user",
      content: "latest question",
      timestamp: new Date("2026-04-19T01:01:00.000Z"),
      runId: "run-latest",
    },
  ];

  const result = prepareMessagesForRunningRun(
    messages,
    "run-latest",
    () => "assistant-latest",
  );

  expect(result.streamingMessageId).toBe("assistant-latest");
  expect(
    result.messages.map((message) => [
      message.id,
      message.role,
      message.runId,
      message.isStreaming ?? false,
    ]),
  ).toEqual([
    ["user-previous", "user", "run-previous", false],
    ["assistant-previous", "assistant", "run-previous", false],
    ["user-latest", "user", "run-latest", false],
    ["assistant-latest", "assistant", "run-latest", true],
  ]);
});

test("atomically inserts an SSE user before its streaming assistant without duplicates", () => {
  const ctx = createContext([], null);
  const event: StreamEvent = {
    event: "user:message",
    data: JSON.stringify({
      content: "active question",
      run_id: "run-active",
    }),
  };

  handleStreamEvent(
    event,
    "assistant-active",
    "redis-user-1",
    "2026-08-09T00:00:00.000Z",
    ctx,
  );

  expect(ctx.setMessagesCalls()).toBe(1);
  expect(
    ctx.messages().map((message) => [message.id, message.role, message.runId]),
  ).toEqual([
    ["run-active:user", "user", "run-active"],
    ["assistant-active", "assistant", "run-active"],
  ]);

  handleStreamEvent(
    event,
    "assistant-active",
    "redis-user-2",
    "2026-08-09T00:00:00.000Z",
    ctx,
  );

  expect(
    ctx.messages().map((message) => [message.id, message.role, message.runId]),
  ).toEqual([
    ["run-active:user", "user", "run-active"],
    ["assistant-active", "assistant", "run-active"],
  ]);
});

test("user cancel marks message cancelled without closing the SSE connection", () => {
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date("2026-04-19T01:02:03.456Z"),
        parts: [{ type: "text", content: "partial" }],
        isStreaming: true,
      },
    ],
    null,
  );

  handleStreamEvent(
    {
      event: "user:cancel",
      data: JSON.stringify({ run_id: "run-1" }),
    },
    "assistant-1",
    "redis-event-cancel",
    "2026-04-19T01:02:04.000Z",
    ctx,
  );

  expect(ctx.messages()[0]?.cancelled).toBe(true);
  expect(ctx.messages()[0]?.isStreaming).toBe(false);
  expect(ctx.messages()[0]?.parts?.map((part) => part.type)).toEqual([
    "text",
    "cancelled",
  ]);
  expect(ctx.connectionStatuses).toEqual([]);
});

test("steer interrupt (user:cancel reason=steer) seals the message without the cancelled pill", () => {
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date("2026-04-19T01:02:03.456Z"),
        parts: [{ type: "text", content: "partial" }],
        isStreaming: true,
      },
    ],
    null,
  );

  handleStreamEvent(
    {
      event: "user:cancel",
      data: JSON.stringify({ run_id: "run-1", reason: "steer" }),
    },
    "assistant-1",
    "redis-event-steer-interrupt",
    "2026-04-19T01:02:04.000Z",
    ctx,
  );

  // 已停止是状态行文字切换（RunStepsCollapse 读 cancelled 标志），
  // 不追加 cancelled part 胶囊组件
  expect(ctx.messages()[0]?.cancelled).toBe(true);
  expect(ctx.messages()[0]?.isStreaming).toBe(false);
  expect(ctx.messages()[0]?.parts?.map((part) => part.type)).toEqual(["text"]);
  expect(ctx.connectionStatuses).toEqual([]);
});

test("adds recommended questions from SSE events to the streaming assistant", () => {
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "回答内容",
        timestamp: new Date("2026-04-19T01:02:03.456Z"),
        parts: [{ type: "text", content: "回答内容" }],
        isStreaming: true,
      },
    ],
    null,
  );

  handleStreamEvent(
    {
      event: "recommend:questions",
      data: JSON.stringify({
        questions: ["如何预防胫骨内侧压力综合征？", "赛前减量期具体怎么做？"],
      }),
    },
    "assistant-1",
    "redis-event-recommend",
    "2026-04-19T01:02:04.000Z",
    ctx,
  );

  const parts = ctx.messages()[0]?.parts ?? [];
  const recommendations = parts[1];
  expect(recommendations?.type).toBe("recommend_questions");
  expect(
    recommendations.type === "recommend_questions"
      ? recommendations.questions.map((question) => question.content)
      : [],
  ).toEqual(["如何预防胫骨内侧压力综合征？", "赛前减量期具体怎么做？"]);
});

test("updates active goal runtime from lifecycle SSE events", () => {
  const ctx = createContext([], null);

  handleStreamEvent(
    {
      event: "goal:start",
      data: JSON.stringify({
        goal: { objective: "finish docs", rubric: "- docs done" },
        started_at: "2026-05-30T08:00:00.000Z",
      }),
    } as StreamEvent,
    "assistant-1",
    "redis-event-goal-start",
    "2026-05-30T08:00:00.000Z",
    ctx,
  );

  expect(ctx.activeGoal()).toEqual({
    objective: "finish docs",
    rubric: "- docs done",
    started_at: "2026-05-30T08:00:00.000Z",
  });

  // goal:end immediately sets ended_at on the goal
  handleStreamEvent(
    {
      event: "goal:end",
      data: JSON.stringify({
        goal: { objective: "finish docs", rubric: "- docs done" },
        started_at: "2026-05-30T08:00:00.000Z",
        ended_at: "2026-05-30T08:02:03.000Z",
      }),
    } as StreamEvent,
    "assistant-1",
    "redis-event-goal-end",
    "2026-05-30T08:02:03.000Z",
    ctx,
  );

  expect(ctx.activeGoal()).toEqual({
    objective: "finish docs",
    rubric: "- docs done",
    started_at: "2026-05-30T08:00:00.000Z",
    ended_at: "2026-05-30T08:02:03.000Z",
  });
});

test("dispatches refresh events for persona and team tool mutation results", () => {
  const previousWindow = globalThis.window;
  const target = new EventTarget();
  globalThis.window = target as Window & typeof globalThis;

  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date("2026-04-19T01:02:03.456Z"),
        parts: [],
        isStreaming: true,
      },
    ],
    null,
  );
  const personaEvents: unknown[] = [];
  const teamEvents: unknown[] = [];
  const unsubscribePersonas = subscribePersonaPresetsChanged(
    (detail) => personaEvents.push(detail),
    target,
  );
  const unsubscribeTeams = subscribeTeamsChanged(
    (detail) => teamEvents.push(detail),
    target,
  );

  try {
    handleStreamEvent(
      {
        event: "tool:result",
        data: JSON.stringify({
          tool: "save_persona_preset",
          tool_call_id: "tool-1",
          success: true,
          result: {
            success: true,
            entity_type: "persona_preset",
            action: "created",
            preset: { id: "preset-1", name: "Planner" },
          },
        }),
      },
      "assistant-1",
      "redis-event-persona",
      "2026-04-19T01:02:04.000Z",
      ctx,
    );
    handleStreamEvent(
      {
        event: "tool:result",
        data: JSON.stringify({
          tool: "create_agent_team",
          tool_call_id: "tool-2",
          success: true,
          result: {
            success: true,
            entity_type: "team",
            action: "updated",
            team_id: "team-1",
            team: { id: "team-1", name: "Research Team" },
          },
        }),
      },
      "assistant-1",
      "redis-event-team",
      "2026-04-19T01:02:05.000Z",
      ctx,
    );
  } finally {
    unsubscribePersonas();
    unsubscribeTeams();
    globalThis.window = previousWindow;
  }

  expect(personaEvents).toEqual([
    { action: "created", presetId: "preset-1", presetName: "Planner" },
  ]);
  expect(teamEvents).toEqual([
    { action: "updated", teamId: "team-1", teamName: "Research Team" },
  ]);
});

test("goal:end auto-clears the active goal after a short delay", () => {
  // Use real timers so setTimeout fires
  const ctx = createContext([], null);

  handleStreamEvent(
    {
      event: "goal:start",
      data: JSON.stringify({
        goal: { objective: "draw something", rubric: "- it looks good" },
        started_at: "2026-05-30T08:00:00.000Z",
      }),
    } as StreamEvent,
    "assistant-1",
    "redis-event-goal-start",
    "2026-05-30T08:00:00.000Z",
    ctx,
  );

  expect(ctx.activeGoal() != null).toBeTruthy();

  handleStreamEvent(
    {
      event: "goal:end",
      data: JSON.stringify({
        goal: { objective: "draw something" },
        started_at: "2026-05-30T08:00:00.000Z",
        ended_at: "2026-05-30T08:00:05.000Z",
      }),
    } as StreamEvent,
    "assistant-1",
    "redis-event-goal-end",
    "2026-05-30T08:00:05.000Z",
    ctx,
  );

  // Immediately after goal:end, the goal still has ended_at set
  expect(ctx.activeGoal()?.ended_at).toBe("2026-05-30T08:00:05.000Z");
});
