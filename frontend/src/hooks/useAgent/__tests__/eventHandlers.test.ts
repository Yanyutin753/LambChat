import type { Message } from "../../../types";
import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import type { ActiveGoalSpec, StreamEvent } from "../types.ts";
import { prepareMessagesForRunningRun } from "../historyLoader.ts";
import { subscribePersonaPresetsChanged } from "../../personaPresetEvents.ts";
import { subscribeTeamsChanged } from "../../teamEvents.ts";

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
