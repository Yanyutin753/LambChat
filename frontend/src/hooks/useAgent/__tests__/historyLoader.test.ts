import {
  normalizeEventRunIds,
  extractGoalFromEvents,
  extractGoalsByRunFromEvents,
  prepareMessagesForRunningRun,
  reconstructMessagesFromEvents,
  resolveLegacyScheduledTaskApproval,
} from "../historyLoader.ts";
import { vi } from "vitest";
import * as historyFetch from "../../../services/api/fetch";
import * as historyProcessor from "../eventProcessor";
import { clearAllLoadingStates } from "../messageParts";
import * as sharedParts from "../messageParts";
import * as suspendedParts from "../suspendedToolParts";
import type { Message } from "../../../types";
import type { EventData, HistoryEvent, SubagentStackItem } from "../types.ts";

test("history replay keeps one pending execution and one stack entry for repeated agent calls", () => {
  const activeSubagentStack: SubagentStackItem[] = [];
  const events: HistoryEvent[] = [
    { event_type: "user:message", run_id: "run-1", data: { content: "task" } },
    {
      event_type: "agent:call",
      run_id: "run-1",
      data: {
        agent_id: "stable-agent",
        agent_name: "Researcher",
        input: "task",
        depth: 1,
      },
    },
    {
      event_type: "message:chunk",
      run_id: "run-1",
      data: { agent_id: "stable-agent", content: "before approval", depth: 1 },
    },
    {
      event_type: "agent:call",
      run_id: "run-1",
      data: {
        agent_id: "stable-agent",
        agent_name: "Researcher",
        input: "resume",
        depth: 1,
      },
    },
  ];
  const messages = reconstructMessagesFromEvents(events, new Set<string>(), {
    activeSubagentStack,
  });
  const execution = messages[1].parts?.[0];
  expect(messages[1].parts).toHaveLength(1);
  expect(execution).toMatchObject({
    type: "subagent",
    parts: [{ type: "text", content: "before approval" }],
  });
  expect(activeSubagentStack).toHaveLength(1);

  const completedStack: SubagentStackItem[] = [];
  const completed = reconstructMessagesFromEvents(
    [
      ...events,
      {
        event_type: "agent:result",
        run_id: "run-1",
        data: { agent_id: "stable-agent", result: "done", depth: 1 },
      },
    ],
    new Set<string>(),
    { activeSubagentStack: completedStack },
  );
  expect(completedStack).toEqual([]);
  expect(completed[1].parts?.[0]).toMatchObject({ isPending: false, result: "done" });
});

test("reconstructMessagesFromEvents preserves backend user message ids", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-05-08T00:00:00.000Z",
        data: {
          content: "fork from here",
          message_id: "user-message-1",
          attachments: [],
        },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(1);
  expect(messages[0]?.id).toBe("user-message-1");
  expect(messages[0]?.runId).toBe("run-1");
});

test("attaches runless recommendation events to the preceding assistant turn", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "hello", message_id: "run-1:user" },
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: { content: "answer" },
      },
      {
        event_type: "done",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:02.000Z",
        data: { status: "completed" },
      },
      {
        event_type: "recommend:questions",
        timestamp: "2026-08-21T00:00:03.000Z",
        data: { questions: ["next?"] },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages).toHaveLength(2);
  expect(messages[1]?.role).toBe("assistant");
  expect(messages[1]?.runId).toBe("run-1");
  expect(messages[1]?.parts).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        type: "recommend_questions",
        questions: [{ content: "next?" }],
      }),
    ]),
  );
});

test("drops an assistant turn that only carries recommend questions", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "hello", message_id: "run-1:user" },
      },
      {
        event_type: "recommend:questions",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: { questions: ["next?"] },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  // 活跃 run 历史快照可能只带 user:message + 合成推荐事件（零正文）；
  // 只有推荐 part 的助手轮次要整体丢弃，不能留一个空壳气泡。
  expect(messages).toHaveLength(1);
  expect(messages[0]?.role).toBe("user");
  expect(messages[0]?.id).toBe("run-1:user");
});

test("reconstructs one resolved ask-human item from same-run history", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "start", message_id: "run-1:user" },
      },
      {
        event_type: "tool:start",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: {
          tool: "ask_human",
          tool_call_id: "call-1",
          args: { message: "confirm" },
        },
      },
      {
        event_type: "approval_resolved",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:02.000Z",
        data: {
          id: "approval-1",
          tool_call_id: "call-1",
          success: true,
          result: {
            status: "success",
            message: "用户已响应",
            values: { choice: "a" },
          },
        },
      },
      {
        event_type: "tool:start",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:03.000Z",
        data: {
          tool: "ask_human",
          tool_call_id: "call-1",
          args: { message: "confirm" },
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const assistant = messages.find((message) => message.role === "assistant");
  const tools = assistant?.parts?.filter((part) => part.type === "tool") ?? [];
  expect(tools).toHaveLength(1);
  expect(tools[0]).toMatchObject({
    id: "call-1",
    isPending: false,
    success: true,
  });
});

test("resolves an approval_required history item by tool_call_id", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "ask", message_id: "run-1:user" },
      },
      {
        event_type: "approval_required",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: {
          id: "approval-1",
          tool_call_id: "call-1",
          message: "回答问题",
          type: "form",
          fields: [],
        },
      },
      {
        event_type: "approval_resolved",
        run_id: "run-1",
        timestamp: "2026-08-21T00:00:02.000Z",
        data: {
          id: "approval-1",
          tool_call_id: "call-1",
          success: true,
          result: { status: "success", values: { answer: "ok" } },
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const askHuman = messages[1]?.parts?.find(
    (part) => part.type === "tool" && part.name === "ask_human",
  );
  expect(askHuman).toEqual(
    expect.objectContaining({
      id: "call-1",
      isPending: false,
      success: true,
    }),
  );
});

test("keeps resolved ask-human attached before a delivered steer in the same run", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-hitl-steer",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "开始", message_id: "run-hitl-steer:user" },
      },
      {
        event_type: "tool:start",
        run_id: "run-hitl-steer",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: {
          tool: "ask_human",
          tool_call_id: "call-confirm",
          args: { message: "确认" },
        },
      },
      {
        event_type: "approval_resolved",
        run_id: "run-hitl-steer",
        timestamp: "2026-08-21T00:00:02.000Z",
        data: {
          id: "approval-1",
          tool_call_id: "call-confirm",
          success: true,
          result: { status: "success", values: { choice: "yes" } },
        },
      },
      {
        event_type: "steer:message",
        run_id: "run-hitl-steer",
        timestamp: "2026-08-21T00:00:03.000Z",
        data: { content: "继续时换个方向", message_id: "steer-after-hitl" },
      },
      {
        event_type: "message:chunk",
        run_id: "run-hitl-steer",
        timestamp: "2026-08-21T00:00:04.000Z",
        data: { content: "已按新方向继续" },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const steerIndex = messages.findIndex(
    (message) => message.id === "steer-after-hitl",
  );
  const beforeSteer = messages[steerIndex - 1];
  const askHuman = beforeSteer.parts?.find(
    (part) => part.type === "tool" && part.id === "call-confirm",
  );
  expect(askHuman).toMatchObject({ isPending: false, success: true });
  expect(messages[steerIndex]).toMatchObject({
    role: "user",
    metadata: { steer: true },
  });
  expect(messages[steerIndex + 1]).toMatchObject({
    role: "assistant",
    content: "已按新方向继续",
  });
});

test("reconstructs an ask-human tool card from approval_required history", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-history-hitl",
        timestamp: "2026-08-21T00:00:00.000Z",
        data: { content: "ask human", message_id: "run-history-hitl:user" },
      },
      {
        event_type: "approval_required",
        run_id: "run-history-hitl",
        timestamp: "2026-08-21T00:00:01.000Z",
        data: {
          id: "approval-history-1",
          message: "请回答",
          fields: [],
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        runId: "run-history-hitl",
        parts: [
          expect.objectContaining({
            type: "tool",
            name: "ask_human",
            id: "approval-history-1",
            isPending: true,
          }),
        ],
      }),
    ]),
  );
});

test("reconstructs the same message from raw and compacted text chunks", () => {
  const rawChunks = Array.from({ length: 15_000 }, (_, index) => ({
    event_type: "message:chunk" as const,
    run_id: "run-large",
    trace_id: "trace-large",
    seq: index + 1,
    timestamp: "2026-08-12T00:00:00.000Z",
    data: {
      content: "x",
      agent_id: "main",
      depth: 0,
    },
  }));
  const compacted = [
    {
      ...rawChunks[rawChunks.length - 1],
      data: {
        ...rawChunks[rawChunks.length - 1].data,
        content: "x".repeat(rawChunks.length),
      },
    },
  ];

  const rawMessages = reconstructMessagesFromEvents(
    rawChunks,
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  const compactMessages = reconstructMessagesFromEvents(
    compacted,
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(compactMessages).toEqual(rawMessages);
});

test("does not render an empty assistant placeholder between persisted turns", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-20T00:00:00.000Z",
        data: { content: "asd", message_id: "user-1" },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-1",
        timestamp: "2026-08-20T00:00:01.000Z",
        data: { content: "ok" },
      } satisfies HistoryEvent,
      {
        event_type: "user:message",
        run_id: "run-2",
        timestamp: "2026-08-20T00:00:02.000Z",
        data: { content: "asd", message_id: "user-2" },
      } satisfies HistoryEvent,
      {
        event_type: "agent:start",
        run_id: "run-2",
        timestamp: "2026-08-20T00:00:03.000Z",
        data: {},
      } satisfies HistoryEvent,
      {
        event_type: "user:message",
        run_id: "run-3",
        timestamp: "2026-08-20T00:00:04.000Z",
        data: { content: "asd", message_id: "user-3" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(
    messages.filter((message) => message.role === "assistant"),
  ).toHaveLength(1);
  expect(
    messages.some(
      (message) =>
        message.role === "assistant" &&
        !message.content &&
        !message.parts?.length,
    ),
  ).toBe(false);
});

test("prepareMessagesForRunningRun preserves the optimistic user message when running history has not persisted it yet", () => {
  const optimisticUser: Message = {
    id: "optimistic-user-latest",
    role: "user",
    content: "latest question",
    timestamp: new Date("2026-04-19T01:01:00.000Z"),
  };

  const historyMessages: Message[] = [
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
    },
  ];

  const result = prepareMessagesForRunningRun(
    historyMessages,
    "run-latest",
    () => "assistant-latest",
    [
      optimisticUser,
      {
        id: "run-latest",
        role: "assistant",
        content: "",
        timestamp: new Date("2026-04-19T01:01:00.000Z"),
        isStreaming: true,
        runId: "run-latest",
      },
    ],
  );

  expect(
    result.messages.map((message) => [message.id, message.role, message.runId]),
  ).toEqual([
    ["user-previous", "user", "run-previous"],
    ["assistant-previous", "assistant", "run-previous"],
    ["optimistic-user-latest", "user", "run-latest"],
    ["assistant-latest", "assistant", "run-latest"],
  ]);
});

test("prepareMessagesForRunningRun does not duplicate the optimistic user message after history persists it", () => {
  const historyMessages: Message[] = [
    {
      id: "persisted-user-latest",
      role: "user",
      content: "latest question",
      timestamp: new Date("2026-04-19T01:01:00.000Z"),
      runId: "run-latest",
    },
  ];

  const result = prepareMessagesForRunningRun(
    historyMessages,
    "run-latest",
    () => "assistant-latest",
    [
      {
        id: "optimistic-user-latest",
        role: "user",
        content: "latest question",
        timestamp: new Date("2026-04-19T01:01:00.000Z"),
      },
      {
        id: "run-latest",
        role: "assistant",
        content: "",
        timestamp: new Date("2026-04-19T01:01:00.000Z"),
        isStreaming: true,
        runId: "run-latest",
      },
    ],
  );

  expect(
    result.messages.map((message) => [message.id, message.role, message.runId]),
  ).toEqual([
    ["persisted-user-latest", "user", "run-latest"],
    ["assistant-latest", "assistant", "run-latest"],
  ]);
});

test("prepareMessagesForRunningRun does not reveal a running assistant before its user message", () => {
  const result = prepareMessagesForRunningRun(
    [],
    "run-active",
    () => "assistant-active",
  );

  expect(result.streamingMessageId).toBe("assistant-active");
  expect(result.messages).toEqual([]);
});

test("prepareMessagesForRunningRun removes an existing same-run assistant when its user is absent", () => {
  const result = prepareMessagesForRunningRun(
    [
      {
        id: "assistant-active",
        role: "assistant",
        content: "partial",
        timestamp: new Date("2026-08-09T00:00:00.000Z"),
        runId: "run-active",
      },
    ],
    "run-active",
  );

  expect(result.streamingMessageId).toBe("assistant-active");
  expect(result.messages).toEqual([]);
});

test("reconstructMessagesFromEvents ignores goal update events as message content", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-05-08T00:00:00.000Z",
        data: {
          content: "/goal hi",
          message_id: "run-1:user",
          attachments: [],
        },
      },
      {
        id: "event-goal",
        event_type: "goal:updated",
        run_id: "run-1",
        timestamp: "2026-05-08T00:00:01.000Z",
        data: {
          action: "set",
          goal: { objective: "hi", rubric: "- greet" },
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(1);
  expect(messages[0]?.role).toBe("user");
});

test("reconstructMessagesFromEvents restores artifact result parts", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-artifact",
        event_type: "artifact:result",
        run_id: "run-1",
        timestamp: "2026-05-08T00:00:01.000Z",
        data: {
          success: true,
          artifact: {
            kind: "file",
            id: "file:revealed/puppy.svg",
            name: "puppy.svg",
            path: "/workspace/puppy.svg",
            preview: {
              kind: "file",
              previewKey: "revealed/puppy.svg",
              filePath: "/workspace/puppy.svg",
              s3Key: "revealed/puppy.svg",
              signedUrl: "/api/upload/file/revealed/puppy.svg",
            },
          },
        },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(1);
  expect(messages[0]?.role).toBe("assistant");
  expect(messages[0]?.parts?.[0]?.type).toBe("artifact");
});

test("reconstructMessagesFromEvents does not create duplicate assistant ids for goal lifecycle events", () => {
  const runId = "run_20260530120841_cf52eb51";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:41.000Z",
        data: {
          content: "start",
          message_id: `${runId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-thinking",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:42.000Z",
        data: {
          content: "working",
        },
      },
      {
        id: "event-goal-start",
        event_type: "goal:start",
        run_id: runId,
        timestamp: "2026-05-30T12:08:43.000Z",
        data: {
          started_at: "2026-05-30T12:08:43.000Z",
          goal: { objective: "finish the task" },
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.map((message) => message.id)).toEqual([
    `${runId}:user`,
    runId,
  ]);
});

test("reconstructMessagesFromEvents ignores duplicate persisted user messages for the same run", () => {
  const runId = "run_20260530120841_cf52eb51";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user-1",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:41.000Z",
        data: {
          content: "hello",
          message_id: `${runId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-thinking-1",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:42.000Z",
        data: {
          content: "working",
        },
      },
      {
        id: "event-user-2",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:43.000Z",
        data: {
          content: "hello",
          message_id: `${runId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-thinking-2",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:44.000Z",
        data: {
          content: " more",
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.map((message) => message.id)).toEqual([
    `${runId}:user`,
    runId,
  ]);
});

test("reconstructMessagesFromEvents ignores duplicate user messages with different ids for the same run", () => {
  const runId = "run_20260530120841_cf52eb51";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user-1",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:41.000Z",
        data: {
          content: "hello",
          message_id: "user-message-a",
          attachments: [],
        },
      },
      {
        id: "event-thinking-1",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:42.000Z",
        data: {
          content: "working",
        },
      },
      {
        id: "event-user-2",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:43.000Z",
        data: {
          content: "hello",
          message_id: "user-message-b",
          attachments: [],
        },
      },
      {
        id: "event-thinking-2",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:44.000Z",
        data: {
          content: " more",
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.map((message) => [message.id, message.role])).toEqual([
    ["user-message-a", "user"],
    [runId, "assistant"],
  ]);
});

test("reconstructMessagesFromEvents treats timezone-less backend timestamps as UTC", () => {
  const originalTimezone = process.env.TZ;
  process.env.TZ = "Asia/Shanghai";
  try {
    const messages = reconstructMessagesFromEvents(
      [
        {
          event_type: "user:message",
          run_id: "run-1",
          timestamp: "2026-05-07T16:30:00.000",
          data: {
            content: "hello",
            message_id: "user-message-1",
            attachments: [],
          },
        } satisfies HistoryEvent,
      ],
      new Set<string>(),
      { activeSubagentStack: [] },
    );

    expect(messages[0]?.timestamp.toISOString()).toBe(
      "2026-05-07T16:30:00.000Z",
    );
  } finally {
    process.env.TZ = originalTimezone;
  }
});

test("reconstructMessagesFromEvents keeps token usage after cancel on the cancelled assistant", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:17.793Z",
        data: {
          content: "创建一个 Python Hello World 脚本",
          message_id: "run_20260516152217_bd0ba9a2:user",
          run_id: "run_20260516152217_bd0ba9a2",
          attachments: [],
        },
      },
      {
        id: "event-sandbox-starting",
        event_type: "sandbox:starting",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:18.961Z",
        data: {
          timestamp: "2026-05-16T15:22:18.961711+00:00",
          agent_id: "search",
        },
      },
      {
        id: "event-thinking",
        event_type: "thinking",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:40.515Z",
        data: {
          content:
            "用户要求创建一个 Python Hello World 脚本。这是一个简单的任务。",
          thinking_id: "lc_run--019e3161-c59c-7ab2-a91d-7249e2216feb",
          agent_id: "search",
        },
      },
      {
        id: "event-token-empty",
        event_type: "token:usage",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:43.422Z",
        data: {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          duration: 0,
        },
      },
      {
        id: "event-cancel",
        event_type: "user:cancel",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:43.445Z",
        data: {
          run_id: "run_20260516152217_bd0ba9a2",
        },
      },
      {
        id: "event-token-final",
        event_type: "token:usage",
        run_id: "run_20260516152217_bd0ba9a2",
        timestamp: "2026-05-16T15:22:43.732Z",
        data: {
          input_tokens: 15581,
          output_tokens: 68,
          total_tokens: 15649,
          duration: 24.927353858947754,
          model: "MiniMax-M2.7",
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(2);
  expect(messages[0]?.role).toBe("user");
  expect(messages[1]?.role).toBe("assistant");
  expect(messages[1]?.cancelled).toBe(true);
  expect(messages[1]?.tokenUsage?.total_tokens).toBe(15649);
  expect(messages[1]?.duration).toBe(24927.353858947754);
});

test("user:cancel with reason=steer marks cancelled without the cancelled pill part", () => {
  const runId = "run_20260905_steer_interrupt";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-09-05T10:00:00.000Z",
        data: { content: "任务", message_id: `${runId}:user`, attachments: [] },
      },
      {
        id: "event-chunk",
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-09-05T10:00:01.000Z",
        data: { content: "半截输出", depth: 0 },
      },
      {
        id: "event-approval-required",
        event_type: "approval_required",
        run_id: runId,
        timestamp: "2026-09-05T10:00:05.000Z",
        data: { id: "appr-1", message: "要继续吗？", fields: [] },
      },
      {
        id: "event-steer-cancel",
        event_type: "user:cancel",
        run_id: runId,
        timestamp: "2026-09-05T10:00:20.000Z",
        data: { run_id: runId, reason: "steer" },
      },
      {
        id: "event-done",
        event_type: "done",
        run_id: runId,
        timestamp: "2026-09-05T10:00:20.100Z",
        data: { status: "cancelled" },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(2);
  const assistant = messages[1];
  expect(assistant?.role).toBe("assistant");
  // 已停止走状态行文字切换：cancelled 标志置位，但不出现 cancelled part 胶囊
  expect(assistant?.cancelled).toBe(true);
  expect(assistant?.parts?.some((part) => part.type === "cancelled")).toBe(
    false,
  );
});

test("reconstructMessagesFromEvents keeps late run events after cancel on the cancelled assistant", () => {
  const runId = "run_20260530120841_cf52eb51";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-05-30T12:08:41.000Z",
        data: {
          content: "hello",
          message_id: `${runId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-sandbox-ready",
        event_type: "sandbox:ready",
        run_id: runId,
        timestamp: "2026-05-30T12:08:42.000Z",
        data: {
          sandbox_id: "sandbox-1",
          work_dir: "/tmp/work",
        },
      },
      {
        id: "event-cancel",
        event_type: "user:cancel",
        run_id: runId,
        timestamp: "2026-05-30T12:08:43.000Z",
        data: {
          run_id: runId,
        },
      },
      {
        id: "event-thinking-late",
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-05-30T12:08:44.000Z",
        data: {
          content: "late thought",
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.map((message) => message.id)).toEqual([
    `${runId}:user`,
    runId,
  ]);
  expect(messages[1]?.cancelled).toBe(true);
  expect(messages[1]?.parts?.map((part) => part.type)).toEqual([
    "sandbox",
    "cancelled",
    "thinking",
  ]);
});

test("keeps steer user messages sharing the run with the initial user message", () => {
  const runId = "run-1";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-20T10:34:41.000Z",
        data: {
          content: "搜索今日新闻",
          message_id: `${runId}:user`,
          attachments: [],
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-20T10:34:45.000Z",
        data: { content: "第一轮回复" },
      } satisfies HistoryEvent,
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-20T10:34:55.000Z",
        data: {
          content: "给我多一点中国的",
          message_id: "steer-d8f46d22bcf5",
          attachments: [],
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-20T10:35:02.000Z",
        data: { content: "针对插话的回复" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const users = messages.filter((m) => m.role === "user");
  expect(users.map((m) => m.content)).toEqual([
    "搜索今日新闻",
    "给我多一点中国的",
  ]);
  // 顺序：首轮回复在插话前，插话后的回复在其后
  const steerIndex = messages.findIndex((m) => m.id === "steer-d8f46d22bcf5");
  const assistants = messages.filter((m) => m.role === "assistant");
  expect(assistants.length).toBe(2);
  expect(messages[steerIndex - 1].role).toBe("assistant");
  expect(messages[steerIndex + 1].role).toBe("assistant");
});

test("still deduplicates replayed canonical user messages within one run", () => {
  const runId = "run-2";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-20T10:00:00.000Z",
        data: {
          content: "hello",
          message_id: `${runId}:user`,
          attachments: [],
        },
      } satisfies HistoryEvent,
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-20T10:00:01.000Z",
        data: {
          content: "hello",
          message_id: `${runId}:user`,
          attachments: [],
        },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  expect(messages.filter((m) => m.role === "user")).toHaveLength(1);
});

test("reconstructs steer:message events as standalone steer items between turns", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-s",
        timestamp: "2026-08-20T10:00:00.000Z",
        data: { content: "任务", message_id: "run-s:user", attachments: [] },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-s",
        timestamp: "2026-08-20T10:00:05.000Z",
        data: { content: "第一轮" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: "run-s",
        timestamp: "2026-08-20T10:00:30.000Z",
        data: {
          content: "插话",
          message_id: "steer-abc",
          created_at: "2026-08-20T10:00:20.000Z",
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-s",
        timestamp: "2026-08-20T10:01:00.000Z",
        data: { content: "回复插话" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const steer = messages.find((m) => m.id === "steer-abc");
  expect(steer?.role).toBe("user");
  expect(steer?.content).toBe("插话");
  expect(steer?.metadata).toEqual({ steer: true });
  const steerIndex = messages.findIndex((m) => m.id === "steer-abc");
  expect(messages[steerIndex - 1].role).toBe("assistant");
  expect(messages[steerIndex + 1].role).toBe("assistant");
  expect(messages.map((message) => message.id)).toEqual([
    "run-s:user",
    "run-s",
    "steer-abc",
    "run-s#t1",
  ]);
});

test("uses the steer created_at send time as the message timestamp", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-ts",
        timestamp: "2026-08-22T15:14:35.000Z",
        data: { content: "任务", message_id: "run-ts:user", attachments: [] },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-ts",
        timestamp: "2026-08-22T15:14:50.000Z",
        data: { content: "第一轮" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: "run-ts",
        // 事件信封时间是注入时刻，created_at 才是用户真正发送的时刻
        timestamp: "2026-08-22T15:14:56.100Z",
        data: {
          content: "插话",
          message_id: "steer-ts",
          created_at: "2026-08-22T15:14:55.000Z",
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-ts",
        timestamp: "2026-08-22T15:14:57.000Z",
        data: { content: "回复插话" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const steer = messages.find((m) => m.id === "steer-ts");
  expect(steer?.timestamp?.toISOString()).toBe("2026-08-22T15:14:55.000Z");
});

test("renders a retried steer:message only once by message_id", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-retry",
        timestamp: "2026-08-22T15:00:00.000Z",
        data: {
          content: "任务",
          message_id: "run-retry:user",
          attachments: [],
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-retry",
        timestamp: "2026-08-22T15:00:05.000Z",
        data: { content: "第一轮" },
      } satisfies HistoryEvent,
      {
        // 首次注入写出的事件（该次模型调用失败，消息回队）
        event_type: "steer:message",
        run_id: "run-retry",
        timestamp: "2026-08-22T15:00:10.000Z",
        data: {
          content: "插话",
          message_id: "steer-retry",
          created_at: "2026-08-22T15:00:08.000Z",
        },
      } satisfies HistoryEvent,
      {
        // 重试送达时再次写出同 message_id 事件
        event_type: "steer:message",
        run_id: "run-retry",
        timestamp: "2026-08-22T15:00:20.000Z",
        data: {
          content: "插话",
          message_id: "steer-retry",
          created_at: "2026-08-22T15:00:08.000Z",
        },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: "run-retry",
        timestamp: "2026-08-22T15:00:25.000Z",
        data: { content: "回复插话" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const steerMessages = messages.filter((m) => m.id === "steer-retry");
  expect(steerMessages).toHaveLength(1);
  expect(steerMessages[0]?.timestamp?.toISOString()).toBe(
    "2026-08-22T15:00:08.000Z",
  );
});

test("places a legacy tail steer:message before the reply turn it answers", () => {
  // 旧版后端在模型调用成功后才写出 steer:message，事件落在 run 尾部
  // 且不带 created_at；重建时应移回其回答文本轮次之前
  const runId = "run-legacy";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-22T15:14:35.186Z",
        data: {
          content: "搜索 今日新闻",
          message_id: `${runId}:user`,
          attachments: [],
        },
      } satisfies HistoryEvent,
      {
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-08-22T15:14:41.375Z",
        data: { content: "User wants today's news." },
      } satisfies HistoryEvent,
      {
        event_type: "tool:start",
        run_id: runId,
        timestamp: "2026-08-22T15:14:41.476Z",
        data: {
          tool: "web-search",
          args: { query: "今日新闻" },
          tool_call_id: "t1",
        },
      } satisfies HistoryEvent,
      {
        event_type: "tool:result",
        run_id: runId,
        timestamp: "2026-08-22T15:14:42.100Z",
        data: {
          tool: "web-search",
          result: "结果",
          tool_call_id: "t1",
          success: true,
        },
      } satisfies HistoryEvent,
      {
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-08-22T15:14:56.228Z",
        data: { content: "User asks what else I can do." },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-22T15:14:56.500Z",
        data: { content: "我主要还能做这些" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: runId,
        timestamp: "2026-08-22T15:15:03.800Z",
        data: { content: "你还能干啥", message_id: "steer-legacy" },
      } satisfies HistoryEvent,
      {
        event_type: "token:usage",
        run_id: runId,
        timestamp: "2026-08-22T15:15:03.846Z",
        data: { input_tokens: 1 },
      } satisfies HistoryEvent,
      {
        event_type: "done",
        run_id: runId,
        timestamp: "2026-08-22T15:15:03.864Z",
        data: { status: "completed" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const steerIndex = messages.findIndex((m) => m.id === "steer-legacy");
  expect(steerIndex).toBeGreaterThan(-1);
  // 插话位于第一轮（搜索）之后、针对插话的回答轮次之前
  const firstTurnIndex = messages.findIndex((m) => m.id === runId);
  const replyIndex = messages.findIndex((m) => m.id === `${runId}#t1`);
  expect(firstTurnIndex).toBeGreaterThan(-1);
  expect(replyIndex).toBeGreaterThan(-1);
  expect(steerIndex).toBeGreaterThan(firstTurnIndex);
  expect(steerIndex).toBeLessThan(replyIndex);
  // 回答轮次的内容是"针对插话的回答"而不是搜索结果
  const reply = messages[replyIndex];
  expect(reply?.content).toContain("我主要还能做这些");
});

test("keeps legacy adjacent steer groups in order when repositioning", () => {
  const runId = "run-legacy-group";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-22T15:00:00.000Z",
        data: { content: "任务", message_id: `${runId}:user`, attachments: [] },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-22T15:00:05.000Z",
        data: { content: "回答前半" },
      } satisfies HistoryEvent,
      {
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-08-22T15:00:20.000Z",
        data: { content: "回复两条插话" },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-22T15:00:21.000Z",
        data: { content: "回答后半" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: runId,
        timestamp: "2026-08-22T15:00:30.000Z",
        data: { content: "插话一", message_id: "steer-g1" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: runId,
        timestamp: "2026-08-22T15:00:30.100Z",
        data: { content: "插话二", message_id: "steer-g2" },
      } satisfies HistoryEvent,
      {
        event_type: "done",
        run_id: runId,
        timestamp: "2026-08-22T15:00:31.000Z",
        data: { status: "completed" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const ids = messages.map((m) => m.id);
  // 两条插话一起移到回答（thinking + 回答后半）之前，且保持先后顺序
  expect(ids.indexOf("steer-g1")).toBeGreaterThan(-1);
  expect(ids.indexOf("steer-g2")).toBeGreaterThan(ids.indexOf("steer-g1"));
  // 回答前半属于插话之前的轮次
  const firstTurnIndex = ids.indexOf(runId);
  expect(ids.indexOf("steer-g1")).toBeGreaterThan(firstTurnIndex);
  const replyIndex = ids.indexOf(`${runId}#t1`);
  expect(ids.indexOf("steer-g2")).toBeLessThan(replyIndex);
});

test("normalizeEventRunIds backfills missing run_id preferring previous neighbor", () => {
  const events = [
    {
      event_type: "message",
      run_id: "run-a",
      timestamp: "2026-08-26T00:00:01.000Z",
      data: { content: "answer" },
    },
    {
      event_type: "recommend:questions",
      timestamp: "2026-08-26T00:00:02.000Z",
      data: { questions: ["next?"] },
    },
    {
      event_type: "recommend:questions",
      timestamp: "2026-08-26T00:00:03.000Z",
      data: { questions: ["more?"] },
    },
    {
      event_type: "message",
      run_id: "run-b",
      timestamp: "2026-08-26T00:00:04.000Z",
      data: { content: "answer b" },
    },
  ] satisfies HistoryEvent[];

  const normalized = normalizeEventRunIds(events);

  expect(normalized[1]?.run_id).toBe("run-a");
  expect(normalized[2]?.run_id).toBe("run-a");
  expect(normalized[3]?.run_id).toBe("run-b");
});

test("normalizeEventRunIds falls back to next neighbor when no previous run exists", () => {
  const events = [
    {
      event_type: "recommend:questions",
      timestamp: "2026-08-26T00:00:00.000Z",
      data: { questions: ["hi?"] },
    },
    {
      event_type: "message",
      run_id: "run-a",
      timestamp: "2026-08-26T00:00:01.000Z",
      data: { content: "answer" },
    },
  ] satisfies HistoryEvent[];

  const normalized = normalizeEventRunIds(events);

  expect(normalized[0]?.run_id).toBe("run-a");
});

test("normalizeEventRunIds keeps events without any neighboring run_id untouched", () => {
  const events = [
    {
      event_type: "recommend:questions",
      timestamp: "2026-08-26T00:00:00.000Z",
      data: { questions: ["hi?"] },
    },
  ] satisfies HistoryEvent[];

  const normalized = normalizeEventRunIds(events);

  expect(normalized[0]?.run_id).toBeUndefined();
});

test("normalizeEventRunIds stays linear on large runless inputs", () => {
  const events = Array.from({ length: 20000 }, (_, index) => ({
    event_type: "recommend:questions",
    timestamp: new Date(index * 1000).toISOString(),
    data: { questions: ["next?"] },
  })) as HistoryEvent[];

  const start = performance.now();
  const normalized = normalizeEventRunIds(events);
  const elapsed = performance.now() - start;

  expect(normalized).toHaveLength(20000);
  // 旧的逐事件 slice+reverse+find 实现在 2 万条无 run_id 事件上远超 1s
  expect(elapsed).toBeLessThan(1000);
});

test("multi-turn run ids keep incrementing suffixes per completed assistant turn", () => {
  const runId = "run-mt";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-26T10:00:00.000Z",
        data: { content: "q1", message_id: `${runId}:u1` },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-26T10:00:01.000Z",
        data: { content: "a1" },
      } satisfies HistoryEvent,
      {
        event_type: "done",
        run_id: runId,
        timestamp: "2026-08-26T10:00:02.000Z",
        data: { status: "completed" },
      } satisfies HistoryEvent,
      {
        event_type: "steer:message",
        run_id: runId,
        timestamp: "2026-08-26T10:00:03.000Z",
        data: { content: "插话", message_id: "steer-mt1" },
      } satisfies HistoryEvent,
      {
        event_type: "thinking",
        run_id: runId,
        timestamp: "2026-08-26T10:00:04.000Z",
        data: { content: "thinking after steer" },
      } satisfies HistoryEvent,
      {
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-08-26T10:00:05.000Z",
        data: { content: "a2" },
      } satisfies HistoryEvent,
      {
        event_type: "done",
        run_id: runId,
        timestamp: "2026-08-26T10:00:06.000Z",
        data: { status: "completed" },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const ids = messages.map((m) => m.id);
  expect(ids).toContain(runId);
  expect(ids).toContain(`${runId}#t1`);
});

test("normalizeEventRunIds treats empty-string run_id as missing", () => {
  const events = [
    {
      event_type: "message",
      run_id: "run-a",
      timestamp: "2026-08-26T00:00:01.000Z",
      data: { content: "a" },
    },
    {
      event_type: "thinking",
      run_id: "",
      timestamp: "2026-08-26T00:00:02.000Z",
      data: { content: "legacy empty" },
    },
    {
      event_type: "recommend:questions",
      timestamp: "2026-08-26T00:00:03.000Z",
      data: { questions: ["next?"] },
    },
    {
      event_type: "message",
      run_id: "run-b",
      timestamp: "2026-08-26T00:00:04.000Z",
      data: { content: "b" },
    },
  ] satisfies HistoryEvent[];

  const normalized = normalizeEventRunIds(events);

  // 空字符串 run_id 视为缺失：自身被回填，也不会作为邻居传播
  expect(normalized[1]?.run_id).toBe("run-a");
  expect(normalized[2]?.run_id).toBe("run-a");
  expect(normalized[3]?.run_id).toBe("run-b");
});

test("restores run modes on user messages from history events", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-08-30T00:00:00.000Z",
        data: {
          content: "ok",
          message_id: "run-1:user",
          run_modes: ["auto", "goal"],
        },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(1);
  expect(messages[0]?.runModes).toEqual(["auto", "goal"]);
});

test("resolves a scheduled-task approval pill from an approval_resolved event without tool_call_id", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-st-confirm",
        timestamp: "2026-09-01T00:00:00.000Z",
        data: { content: "创建定时任务", message_id: "run-st-confirm:user" },
      },
      {
        event_type: "approval_required",
        run_id: "run-st-confirm",
        timestamp: "2026-09-01T00:00:01.000Z",
        data: {
          id: "approval-st-1",
          message: "Please confirm creation of this scheduled task.",
          type: "confirm",
          fields: [],
          timeout: 300,
        },
      },
      {
        event_type: "approval_resolved",
        run_id: "run-st-confirm",
        timestamp: "2026-09-01T00:00:02.000Z",
        data: {
          id: "approval-st-1",
          approval_id: "approval-st-1",
          status: "approved",
          success: true,
          result: { status: "success", message: "ok", values: {} },
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const askHuman = messages[1]?.parts?.find(
    (part) => part.type === "tool" && part.name === "ask_human",
  );
  expect(askHuman).toMatchObject({ isPending: false, success: true });
});

test("reports fetched scheduled-task approvals via onApprovalLookup", async () => {
  const onApprovalLookup = vi.fn();
  vi.stubGlobal("localStorage", {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "approval-legacy-1",
          status: "approved",
          message: "Please confirm creation of this scheduled task.",
          type: "confirm",
          fields: [],
          metadata: { approval_type: "scheduled_task_create" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );

  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "approval_required",
        run_id: "run-legacy",
        timestamp: "2026-09-01T00:00:00.000Z",
        data: {
          id: "approval-legacy-1",
          message: "Please confirm creation of this scheduled task.",
          type: "confirm",
          fields: [],
          timeout: 300,
        },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [], onApprovalLookup },
  );

  // 事件本身不带 metadata（旧版后端），先按 pending 重建 pill
  expect(messages[0]?.parts?.[0]).toMatchObject({
    type: "tool",
    name: "ask_human",
    id: "approval-legacy-1",
    isPending: true,
  });

  await vi.waitFor(() => expect(onApprovalLookup).toHaveBeenCalled());
  const approval = onApprovalLookup.mock.calls[0]?.[0] as {
    id: string;
    status: string;
    metadata?: Record<string, unknown>;
  };

  const resolved = resolveLegacyScheduledTaskApproval(messages, approval);
  expect(resolved[0]?.parts?.[0]).toMatchObject({
    isPending: false,
    success: true,
  });
  vi.unstubAllGlobals();
});

test("resolveLegacyScheduledTaskApproval only touches terminal scheduled-task approvals", () => {
  const buildMessages = () => [
    {
      id: "m1",
      role: "assistant" as const,
      content: "",
      timestamp: new Date(),
      parts: [
        {
          type: "tool" as const,
          name: "ask_human",
          id: "approval-x",
          args: { message: "confirm?", fields: [] },
          isPending: true,
          depth: 0,
        },
      ],
    },
  ];

  // pending 审批不动（卡片还要继续交互）
  expect(
    resolveLegacyScheduledTaskApproval(buildMessages(), {
      id: "approval-x",
      status: "pending",
      metadata: { approval_type: "scheduled_task_create" },
    })[0]?.parts?.[0],
  ).toMatchObject({ isPending: true });

  // 非 scheduled-task 审批不动（真实 ask_human 走 interrupt 恢复路径）
  const untouched = buildMessages();
  const result = resolveLegacyScheduledTaskApproval(untouched, {
    id: "approval-x",
    status: "approved",
    metadata: { mode: "interrupt" },
  });
  expect(result[0]?.parts?.[0]).toMatchObject({ isPending: true });

  // scheduled-task 已决审批：补收尾，避免幽灵 pill 永远转圈
  const resolved = resolveLegacyScheduledTaskApproval(buildMessages(), {
    id: "approval-x",
    status: "rejected",
    metadata: { approval_type: "scheduled_task_create" },
  });
  expect(resolved[0]?.parts?.[0]).toMatchObject({
    isPending: false,
    success: false,
  });
});

test("steer delivered marks the pre-steer assistant turn as cancelled", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:00.000Z",
        data: { content: "任务", message_id: "run-1:user" },
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:01.000Z",
        data: { content: "第一轮部分输出" },
      },
      {
        event_type: "steer:message",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:02.000Z",
        data: {
          content: "加点中国的",
          message_id: "steer-1",
          created_at: "2026-09-05T00:00:01.500Z",
        },
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:03.000Z",
        data: { content: "插话后的回答" },
      },
      {
        event_type: "done",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:04.000Z",
        data: { status: "completed" },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  // [user, assistant(已停止), steer-user, assistant(final)]
  expect(messages).toHaveLength(4);
  const sealed = messages[1];
  expect(sealed.role).toBe("assistant");
  expect(sealed.cancelled).toBe(true);
  // 已停止是状态行文字切换，不追加 cancelled part 胶囊
  expect(sealed.parts?.some((part) => part.type === "cancelled")).toBe(false);
  const final = messages[3];
  expect(final.cancelled).toBeUndefined();
  expect(final.parts?.some((part) => part.type === "cancelled")).toBe(false);
});

test("steer with no prior assistant output adds no cancelled marker", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:00.000Z",
        data: { content: "任务", message_id: "run-1:user" },
      },
      {
        event_type: "steer:message",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:02.000Z",
        data: {
          content: "快点",
          message_id: "steer-1",
          created_at: "2026-09-05T00:00:01.500Z",
        },
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:03.000Z",
        data: { content: "插话后的回答" },
      },
      {
        event_type: "done",
        run_id: "run-1",
        timestamp: "2026-09-05T00:00:04.000Z",
        data: { status: "completed" },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  // [user, steer-user, assistant(final)] —— 没有封存的空气泡
  expect(messages).toHaveLength(3);
  expect(messages.some((message) => message.cancelled)).toBe(false);
});

test("sandbox confirm approval does not synthesize an extra tool card", () => {
  // 沙箱确认门（origin=sandbox_confirm）：执行卡（等待确认→结果）+ 审批面板
  // 已完整表达，历史回放不得再合成 ask_human 卡——否则一次执行渲染两张卡。
  const stableId = "tools:e5648a60-7bef-ec09-bc93-884797cec567|5fc527e7b116";
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:09.000Z",
        data: { content: "看看磁盘", message_id: "run-sbx:user" },
      },
      {
        event_type: "metadata",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:10.000Z",
        data: { session_id: "s1", agent_id: "search" },
      },
      {
        event_type: "tool:start",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:15.000Z",
        data: {
          tool: "execute",
          tool_call_id: stableId,
          args: { command: "df -h" },
        },
      },
      {
        event_type: "approval_required",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:16.000Z",
        data: {
          id: "approval-sbx-1",
          message: "确认在本机执行命令：\ndf -h",
          type: "form",
          fields: [],
          origin: "sandbox_confirm",
        },
      },
      {
        event_type: "hitl:suspended",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:16.500Z",
        data: { session_id: "s1", run_id: "run-sbx", status: "waiting_human" },
      },
      {
        event_type: "approval_resolved",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:59.000Z",
        data: {
          id: "approval-sbx-1",
          tool_call_id: null,
          interrupt_id: "intr-1",
          status: "approved",
          success: true,
        },
      },
      {
        event_type: "human_resume_started",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:51:59.500Z",
        data: { approval_id: "approval-sbx-1" },
      },
      {
        event_type: "tool:start",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:52:00.000Z",
        data: {
          tool: "execute",
          tool_call_id: stableId,
          args: { command: "df -h" },
        },
      },
      {
        event_type: "tool:result",
        run_id: "run-sbx",
        timestamp: "2026-09-05T15:52:01.000Z",
        data: {
          tool: "execute",
          tool_call_id: stableId,
          result: "文件系统 468G",
          success: true,
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  const toolParts = messages
    .filter((m) => m.role === "assistant")
    .flatMap((m) => (m.parts || []).filter((p) => p.type === "tool"));
  expect(toolParts).toHaveLength(1);
  expect(toolParts[0]).toMatchObject({ id: stableId, name: "execute" });
  expect(toolParts[0].result).toBe("文件系统 468G");
});

test("legacy sandbox confirm approval (no origin) is recognized by message prefix", () => {
  const messages = reconstructMessagesFromEvents(
    [
      {
        event_type: "user:message",
        run_id: "run-sbx-old",
        timestamp: "2026-09-05T15:25:46.000Z",
        data: { content: "磁盘", message_id: "run-sbx-old:user" },
      },
      {
        event_type: "approval_required",
        run_id: "run-sbx-old",
        timestamp: "2026-09-05T15:25:56.000Z",
        data: {
          id: "approval-old",
          message: "确认在本机执行命令：\ndf -h",
          type: "form",
          fields: [],
        },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  const toolParts = messages
    .filter((m) => m.role === "assistant")
    .flatMap((m) => (m.parts || []).filter((p) => p.type === "tool"));
  expect(toolParts).toHaveLength(0);
});

test("completed history drops unexecuted tool drafts and preserves actual results", () => {
  const event = (
    event_type: string,
    data: Record<string, unknown>,
    seq: number,
  ): HistoryEvent => ({
    event_type,
    data,
    run_id: "run-tools",
    timestamp: `2026-10-11T04:00:${String(seq).padStart(2, "0")}.000Z`,
  });
  const messages = reconstructMessagesFromEvents(
    [
      event(
        "tool:args:chunk",
        {
          tool: "edit_file",
          tool_call_id: "orphan",
          content: '{"file_path":"file.txt"',
        },
        1,
      ),
      event(
        "tool:args:chunk",
        {
          tool: "edit_file",
          tool_call_id: "actual",
          content: '{"file_path":"file.txt"}',
        },
        2,
      ),
      event(
        "tool:start",
        {
          tool: "edit_file",
          tool_call_id: "actual",
          args: { file_path: "file.txt" },
        },
        3,
      ),
      event(
        "tool:result",
        {
          tool: "edit_file",
          tool_call_id: "actual",
          success: true,
          result: "Updated file",
        },
        4,
      ),
      event("done", { status: "completed" }, 5),
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  expect(messages).toHaveLength(1);
  expect(messages[0].parts).toHaveLength(1);
  expect(messages[0].parts?.[0]).toMatchObject({
    type: "tool",
    id: "actual",
    result: "Updated file",
    success: true,
  });
});

test("completed runs discard tool drafts in turns sealed by steer messages", () => {
  const messages = reconstructMessagesFromEvents(
    [
      { event_type: "message:chunk", data: { content: "第一轮" } },
      {
        event_type: "tool:args:chunk",
        data: {
          tool: "edit_file",
          tool_call_id: "orphan",
          content: '{"file_path":',
        },
      },
      {
        event_type: "steer:message",
        data: { content: "继续", message_id: "steer-1" },
      },
      { event_type: "message:chunk", data: { content: "已完成" } },
      { event_type: "done", data: { status: "completed" } },
    ].map((event, index) => ({
      ...event,
      run_id: "run-sealed",
      timestamp: `2026-10-11T04:00:0${index}.000Z`,
    })),
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  const assistants = messages.filter((message) => message.role === "assistant");
  expect(assistants).toHaveLength(2);
  expect(
    assistants
      .flatMap((message) => message.parts || [])
      .filter((part) => part.type === "tool"),
  ).toHaveLength(0);
  expect(assistants.map((message) => message.content)).toEqual([
    "第一轮",
    "已完成",
  ]);
});


test("history preserves persistent projection ID without leaking it into ordinary runs", () => {
  const events: HistoryEvent[] = [{ event_type: "goal:start", run_id: "r1", data: { goal: { objective: "docs", rubric: "verified", _persistent_id: "g1" } } }];
  expect(extractGoalFromEvents(events)).toMatchObject({ _persistent_id: "g1" });
  expect(extractGoalsByRunFromEvents(events).r1).toMatchObject({ _persistent_id: "g1" });
  events.push({ event_type: "goal:start", run_id: "r2", data: { goal: { objective: "docs", rubric: "verified" } } });
  expect(extractGoalFromEvents(events)?._persistent_id).toBeUndefined();
  expect(extractGoalsByRunFromEvents(events).r2._persistent_id).toBeUndefined();
});


test.each([100, 1000])("legacy steer replay reads event kinds linearly while keeping all %i turns", (count) => {
  let eventKindReads = 0;
  const events: HistoryEvent[] = [
    { event_type: "user:message", run_id: "legacy-scale", data: { content: "task" } },
    { event_type: "thinking", run_id: "legacy-scale", data: { content: "reply" } },
  ];
  for (let index = 0; index < count; index++) {
    events.push(
      { event_type: "message:chunk", run_id: "legacy-scale", data: { content: `${index},` } },
      { event_type: "steer:message", run_id: "legacy-scale", data: { content: `steer ${index}`, message_id: `steer-${index}` } },
    );
  }
  for (const event of events) {
    const kind = event.event_type;
    Object.defineProperty(event, "event_type", {
      get() { eventKindReads++; return kind; },
    });
  }

  const messages = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] });

  expect(messages.filter(message => message.metadata?.steer).map(message => message.content))
    .toEqual(Array.from({ length: count }, (_, index) => `steer ${index}`));
  expect(messages.at(-1)?.content).toBe(Array.from({ length: count }, (_, index) => `${index},`).join(""));
  expect(eventKindReads).toBeLessThan(events.length * 20);
});

test("durably resolved history approvals keep their complete tool results without status requests", () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue(null);
  try {
    const events: HistoryEvent[] = [];
    for (let index = 0; index < 100; index++) {
      events.push(
        { event_type: "user:message", run_id: `run-${index}`, data: { content: `ask ${index}` } },
        { event_type: "approval_required", run_id: `run-${index}`, data: { id: `approval-${index}`, tool_call_id: `call-${index}`, message: `confirm ${index}` } },
        { event_type: "approval_resolved", run_id: `run-${index}`, data: { id: `approval-${index}`, tool_call_id: `call-${index}`, success: true, result: { status: "success", values: { answer: index } } } },
      );
    }
    const messages = reconstructMessagesFromEvents(events, new Set(), {
      activeSubagentStack: [], onApprovalLookup: vi.fn(),
    });
    const assistants = messages.filter(message => message.role === "assistant");
    expect(assistants).toHaveLength(100);
    for (let index = 0; index < assistants.length; index++) {
      expect(assistants[index].parts?.[0]).toMatchObject({
        id: `call-${index}`, isPending: false, success: true,
        result: { status: "success", values: { answer: index } },
      });
    }
    expect(lookup).not.toHaveBeenCalled();
  } finally {
    lookup.mockRestore();
  }
});

test("repeated unresolved history approval checks status once and keeps pending interaction", async () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue({
    id: "approval-repeat", status: "pending", message: "confirm", type: "form", fields: [],
  });
  const onApprovalRequired = vi.fn();
  const onApprovalLookup = vi.fn();
  try {
    const events: HistoryEvent[] = Array.from({ length: 100 }, () => ({
      event_type: "approval_required", run_id: "approval-run",
      data: { id: "approval-repeat", tool_call_id: "call-repeat", message: "confirm" },
    }));
    const messages = reconstructMessagesFromEvents(events, new Set(), {
      activeSubagentStack: [], options: { onApprovalRequired }, onApprovalLookup,
    });
    await vi.waitFor(() => expect(onApprovalRequired).toHaveBeenCalledOnce());
    expect(lookup).toHaveBeenCalledOnce();
    expect(onApprovalLookup).toHaveBeenCalledOnce();
    expect(messages[0].parts).toHaveLength(1);
    expect(messages[0].parts?.[0]).toMatchObject({ id: "call-repeat", isPending: true });
  } finally {
    lookup.mockRestore();
  }
});


test("anonymous steer ids keep original sorted positions without repeated full-array searches", () => {
  const events: HistoryEvent[] = Array.from({ length: 1000 }, (_, index) => ({
    event_type: "steer:message", run_id: "anonymous-steers",
    data: { content: `steer ${index}`, created_at: "2026-10-15T00:00:00Z" },
  }));
  const originalIndexOf = Array.prototype.indexOf;
  let eventSearchWork = 0;
  const search = vi.spyOn(Array.prototype, "indexOf").mockImplementation(function(this: unknown[], value: unknown, fromIndex?: number) {
    if (value && typeof value === "object" && "event_type" in value) eventSearchWork += this.length;
    return originalIndexOf.call(this, value, fromIndex);
  });
  try {
    const messages = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] });
    expect(messages.map(message => message.id)).toEqual(events.map((_, index) => `steer-h-${index}`));
    expect(eventSearchWork).toBeLessThanOrEqual(events.length * 2);
  } finally {
    search.mockRestore();
  }
});


test("prefetched legacy approvals preserve pending fields and repair completed scheduled task cards without requests", async () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue(null);
  const onApprovalRequired = vi.fn();
  const onApprovalLookup = vi.fn();
  try {
    const messages = reconstructMessagesFromEvents([
      { event_type: "approval_required", run_id: "completed", data: { id: "legacy-completed", message: "confirm" } },
      { event_type: "user:message", run_id: "pending", data: { content: "ask" } },
      { event_type: "approval_required", run_id: "pending", data: { id: "legacy-pending", message: "question" } },
    ], new Set(), {
      activeSubagentStack: [], options: { onApprovalRequired }, onApprovalLookup,
      approvalStatuses: {
        "legacy-completed": { id: "legacy-completed", status: "approved", metadata: { approval_type: "scheduled_task_create" } },
        "legacy-pending": { id: "legacy-pending", status: "pending", message: "full question", type: "form", fields: [{ name: "answer", type: "text", label: "Answer" }], metadata: { run_id: "pending", detail: "retained" } },
      },
    });
    expect(messages[0].parts?.[0]).toMatchObject({ isPending: false, success: true });
    await vi.waitFor(() => expect(onApprovalRequired).toHaveBeenCalledOnce());
    expect(onApprovalRequired).toHaveBeenCalledWith({ id: "legacy-pending", message: "full question", type: "form", fields: [{ name: "answer", type: "text", label: "Answer" }], metadata: { run_id: "pending", detail: "retained" } });
    expect(onApprovalLookup).toHaveBeenCalledTimes(2);
    expect(lookup).not.toHaveBeenCalled();
  } finally { lookup.mockRestore(); }
});

test("missing prefetched approval status falls back to the existing lookup", async () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue({ id: "fallback", status: "not_found" });
  const onApprovalLookup = vi.fn();
  try {
    reconstructMessagesFromEvents([{ event_type: "approval_required", run_id: "run", data: { id: "fallback" } }], new Set(), { activeSubagentStack: [], approvalStatuses: {}, onApprovalLookup });
    await vi.waitFor(() => expect(onApprovalLookup).toHaveBeenCalledOnce());
    expect(lookup).toHaveBeenCalledOnce();
  } finally { lookup.mockRestore(); }
});


test("prefetched approval callbacks do not update a session after its history becomes stale", async () => {
  let current = true;
  const onApprovalLookup = vi.fn();
  const onApprovalRequired = vi.fn();
  reconstructMessagesFromEvents([{ event_type: "approval_required", run_id: "old", data: { id: "old-approval" } }], new Set(), {
    activeSubagentStack: [], onApprovalLookup, options: { onApprovalRequired },
    approvalStatuses: { "old-approval": { id: "old-approval", status: "pending", message: "old question" } },
    isCurrent: () => current,
  });
  current = false;
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  expect(onApprovalLookup).not.toHaveBeenCalled();
  expect(onApprovalRequired).not.toHaveBeenCalled();
});


function plainToolHistory(count: number): HistoryEvent[] {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < count; index++) {
    events.push(
      { event_type: "tool:start", run_id: "tool-run", data: { tool: "read_file", tool_call_id: `tool-${index}`, args: { path: `/file-${index}` }, timestamp: "2026-10-15T00:00:00Z" } },
      { event_type: "tool:result", run_id: "tool-run", data: { tool: "read_file", tool_call_id: `tool-${index}`, result: { content: `file ${index}`, attachments: [{ key: `asset-${index}` }] }, success: index % 2 === 0, error: index % 2 ? "fixture failure" : undefined, timestamp: "2026-10-15T00:00:01Z" } },
    );
  }
  return events;
}

test.each([1, 1000])("ordinary history keeps the shared processor output for all %i tools without repeated full scans", (count) => {
  const events = plainToolHistory(count);
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "tool-run",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const messages = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] });
    expect(messages).toHaveLength(1);
    expect(messages[0].parts).toEqual(expected.parts);
    expect(messages[0].toolCalls).toEqual(expected.toolCalls);
    expect(messages[0].content).toBe(expected.content);
    expect(messages[0].toolResults).toBeUndefined();
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});

test("history tool replay keeps duplicate starts and repeated results identical to the shared processor", () => {
  const events = [...plainToolHistory(1), ...plainToolHistory(1)];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "tool-run",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
  expect(message.parts).toEqual(expected.parts);
  expect(message.toolCalls).toEqual(expected.toolCalls);
});

test("history tool replay preserves streamed aliases and interrupted pending takeover", () => {
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const events: HistoryEvent[] = [
      { event_type: "tool:args:chunk", run_id: "args-run", data: { tool: "shell", tool_call_id: "draft", content: '{"command":' } },
      { event_type: "tool:start", run_id: "args-run", data: { tool: "shell", tool_call_id: "call", args: { command: "ls" } } },
      { event_type: "hitl:suspended", run_id: "args-run", data: {} },
      { event_type: "tool:start", run_id: "args-run", data: { tool: "shell", tool_call_id: "resumed", args: { command: "ls" } } },
      { event_type: "tool:result", run_id: "args-run", data: { tool: "shell", tool_call_id: "resumed", result: "all files", success: true } },
    ];
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toHaveLength(1);
    expect(message.parts?.[0]).toMatchObject({ id: "resumed", args: { command: "ls" }, result: "all files", isPending: false });
    expect(message.toolCalls?.map(tool => tool.id)).toEqual(["call", "resumed"]);
    expect(processor).not.toHaveBeenCalled();
  } finally { processor.mockRestore(); }
});

test("history tool replay keeps nested results and legacy ask-human interrupt semantics", () => {
  const events: HistoryEvent[] = [
    { event_type: "agent:call", run_id: "complex", data: { agent_id: "child", agent_name: "Child", depth: 1 } },
    { event_type: "tool:start", run_id: "complex", data: { agent_id: "child", depth: 1, tool: "read_file", tool_call_id: "child-call", args: { path: "nested" } } },
    { event_type: "tool:result", run_id: "complex", data: { agent_id: "child", depth: 1, tool: "read_file", tool_call_id: "child-call", result: "nested content" } },
    { event_type: "agent:result", run_id: "complex", data: { agent_id: "child", depth: 1, result: "child done" } },
    { event_type: "tool:start", run_id: "complex", data: { tool: "ask_human", tool_call_id: "human", args: { message: "confirm" } } },
    { event_type: "tool:result", run_id: "complex", data: { tool: "ask_human", tool_call_id: "human", result: "GraphInterrupt", success: false } },
  ];
  const parts = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0].parts;
  expect(parts?.[0]).toMatchObject({ type: "subagent", result: "child done", parts: [{ id: "child-call", result: "nested content", isPending: false }] });
  expect(parts?.[1]).toMatchObject({ id: "human", name: "ask_human", isPending: true });
});


test("parallel history keeps all 1000 distinct tool calls and results with linear signature work", () => {
  const interleaved = plainToolHistory(1000);
  const events = [
    ...interleaved.filter(event => event.event_type === "tool:start"),
    ...interleaved.filter(event => event.event_type === "tool:result"),
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "tool-run",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  const serialization = vi.spyOn(JSON, "stringify");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.parts).toHaveLength(1000);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(message.toolResults).toBeUndefined();
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
    expect(serialization.mock.calls.length).toBeLessThanOrEqual(events.length * 3);
  } finally { serialization.mockRestore(); processor.mockRestore(); }
});

test("same-name same-args parallel starts retain indexed dangling takeover", () => {
  const events: HistoryEvent[] = [
    { event_type: "tool:start", run_id: "takeover", data: { tool: "read_file", tool_call_id: "first", args: { path: "same" } } },
    { event_type: "tool:start", run_id: "takeover", data: { tool: "read_file", tool_call_id: "second", args: { path: "same" } } },
    { event_type: "tool:result", run_id: "takeover", data: { tool: "read_file", tool_call_id: "second", result: "complete file" } },
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "takeover",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.parts).toHaveLength(1);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor).not.toHaveBeenCalled();
  } finally { processor.mockRestore(); }
});


test("pending tool signatures preserve args property order and are removed by completed results", () => {
  const events: HistoryEvent[] = [
    { event_type: "tool:start", run_id: "ordered", data: { tool: "read_file", tool_call_id: "first", args: { a: 1, b: 2 } } },
    { event_type: "tool:start", run_id: "ordered", data: { tool: "read_file", tool_call_id: "different-order", args: { b: 2, a: 1 } } },
    { event_type: "tool:result", run_id: "ordered", data: { tool: "read_file", tool_call_id: "first", result: "first complete" } },
    { event_type: "tool:start", run_id: "ordered", data: { tool: "read_file", tool_call_id: "after-completion", args: { a: 1, b: 2 } } },
    { event_type: "tool:result", run_id: "ordered", data: { tool: "read_file", tool_call_id: "different-order", result: "second complete" } },
    { event_type: "tool:result", run_id: "ordered", data: { tool: "read_file", tool_call_id: "after-completion", result: "third complete" } },
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "ordered",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.parts).toHaveLength(3);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor).not.toHaveBeenCalled();
  } finally { processor.mockRestore(); }
});


test("ordinary tools alternating with text and thinking keep golden output with linear replay work", () => {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const pair = plainToolHistory(1).map(event => ({ ...event, data: { ...(event.data as EventData), tool_call_id: `alternating-${index}` } }));
    events.push(...pair,
      { event_type: "message:chunk", run_id: "tool-run", data: { content: `text-${index};` } },
      { event_type: "thinking", run_id: "tool-run", data: { thinking_id: `thinking-${index % 3}`, content: `thought-${index};` } },
    );
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "tool-run",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  const serialization = vi.spyOn(JSON, "stringify");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.content).toBe(expected.content);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
    expect(serialization.mock.calls.length).toBeLessThanOrEqual(events.length * 3);
  } finally { serialization.mockRestore(); processor.mockRestore(); }
});


test("one nested execution replays 1000 tools and interleaved text with linear processor work", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const events: HistoryEvent[] = [{ event_type: "agent:call", run_id: "nested", data: {
    agent_id: "worker", depth: 1, input: "all files", timestamp: stamp,
  } }];
  for (let index = 0; index < 1000; index++) {
    events.push(...plainToolHistory(1).map(event => ({ ...event, run_id: "nested", data: {
      ...(event.data as EventData), agent_id: "worker", depth: 1, tool_call_id: `nested-${index}`,
    } })),
    { event_type: "message:chunk", run_id: "nested", data: { agent_id: "worker", depth: 1, content: `${index};` } },
    { event_type: "thinking", run_id: "nested", data: { agent_id: "worker", depth: 1, thinking_id: "thought", content: `${index};` } });
  }
  events.push({ event_type: "agent:result", run_id: "nested", data: { agent_id: "worker", depth: 1, result: "all files", timestamp: stamp } });
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "nested",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    // History also settles runs without a run-level terminal event after the shared reducer.
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, {
      preserveAskHuman: true, discardToolDrafts: false,
    }));
    expect(message.content).toEqual(expected.content);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(3);
  } finally { processor.mockRestore(); }
});


test("1000 uniquely routed short child executions preserve settlement with linear processor work", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const agent_id = `child-${index}`;
    events.push({ event_type: "agent:call", run_id: "children", data: { agent_id, depth: 1, input: `${index}`, timestamp: stamp } },
      ...plainToolHistory(1).map(event => ({ ...event, run_id: "children", data: {
        ...(event.data as EventData), agent_id, depth: 1, tool_call_id: `child-tool-${index}`,
      } })),
      { event_type: "agent:result", run_id: "children", data: { agent_id, depth: 1, result: `${index}`, timestamp: stamp,
        success: index % 2 === 0, error: index % 2 ? "failed" : undefined } });
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "children",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  const stack: SubagentStackItem[] = [];
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: stack })[0];
    // History also settles runs without a run-level terminal event after the shared reducer.
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, {
      preserveAskHuman: true, discardToolDrafts: false,
    }));
    expect(message.parts).toHaveLength(1000);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(stack).toEqual([]);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});


test("1000 parallel explicitly routed child lifecycles avoid stack scans and retain every result", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const calls: HistoryEvent[] = [];
  const tools: HistoryEvent[] = [];
  const results: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const agent_id = `parallel-child-${index}`;
    calls.push({ event_type: "agent:call", run_id: "parallel-children", data: { agent_id, depth: 1, input: `${index}`, timestamp: stamp } });
    tools.push(...plainToolHistory(1).map(event => ({ ...event, run_id: "parallel-children", data: {
      ...(event.data as EventData), agent_id, depth: 1, tool_call_id: `parallel-child-tool-${index}`, args: { path: `${index}` },
    } })));
    results.push({ event_type: "agent:result", run_id: "parallel-children", data: { agent_id, depth: 1, result: `${index}`, timestamp: stamp } });
  }
  const events = [...calls, ...tools, ...results];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "parallel-children",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const stack: SubagentStackItem[] = [];
  const scan = vi.spyOn(stack, "findIndex");
  const some = vi.spyOn(stack, "some");
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: stack })[0];
    // History also settles runs without a run-level terminal event after the shared reducer.
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, {
      preserveAskHuman: true, discardToolDrafts: false,
    }));
    expect(message.parts).toHaveLength(1000);
    expect(stack).toEqual([]);
    expect(scan).not.toHaveBeenCalled();
    expect(some).not.toHaveBeenCalled();
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); scan.mockRestore(); some.mockRestore(); }
});


test("1000 explicit-ID args streams upgrade without growing history scans or ghost parts", () => {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const id = `args-${index}`;
    events.push({ event_type: "tool:args:chunk", run_id: "args", data: { tool: "read_file", tool_call_id: id, content: '{"path":' } },
      { event_type: "tool:args:chunk", run_id: "args", data: { tool: "read_file", tool_call_id: id, content: `"${index}"}` } },
      { event_type: "tool:start", run_id: "args", data: { tool: "read_file", tool_call_id: id, args: { path: `${index}` }, timestamp: "2026-10-15T00:00:00Z" } },
      { event_type: "tool:args:chunk", run_id: "args", data: { tool: "read_file", tool_call_id: id, content: "late ignored" } },
      { event_type: "tool:result", run_id: "args", data: { tool: "read_file", tool_call_id: id, result: `${index}` } });
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "args",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.parts).toHaveLength(1000);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});

test("1000 indexed dangling replacements retain shared last-signature takeover semantics", () => {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    events.push({ event_type: "tool:start", run_id: "takeover-scale", data: {
      tool: "read_file", tool_call_id: `dangling-${index}`, args: { path: "same" }, timestamp: "2026-10-15T00:00:00Z",
    } });
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "takeover-scale",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts?.[0]).toMatchObject({ id: "dangling-999", args: { path: "same" } });
    expect(message.parts).toHaveLength(1);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});


test("mixed root tools and depth-1/depth-2 child tools preserve full output without repeated scans", () => {
  const events: HistoryEvent[] = [];
  const stamp = "2026-10-15T00:00:00Z";
  for (let index = 0; index < 1000; index++) {
    events.push(...plainToolHistory(1).map(event => ({ ...event, data: {
      ...(event.data as EventData), tool_call_id: `root-mixed-${index}`,
    } })));
    const depth = index % 2 + 1;
    const agent_id = `mixed-${index}`;
    events.push({ event_type: "agent:call", run_id: "tool-run", data: { agent_id, depth, input: `${index}`, timestamp: stamp } },
      { event_type: "message:chunk", run_id: "tool-run", data: { agent_id, depth, content: `${index};` } },
      ...plainToolHistory(1).map(event => ({ ...event, data: {
        ...(event.data as EventData), agent_id, depth, tool_call_id: `nested-mixed-${index}`,
      } })),
      { event_type: "agent:result", run_id: "tool-run", data: { agent_id, depth, result: `${index}`, timestamp: stamp } });
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "tool-run",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    // History also settles runs without a run-level terminal event after the shared reducer.
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, {
      preserveAskHuman: true, discardToolDrafts: false,
    }));
    expect(message.content).toEqual(expected.content);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});

test.each(["renamed-draft", "draft-text", "late-child", "depth2-draft", "waiting-human"])("complex %s boundary keeps shared output", (scenario) => {
  const stamp = "2026-10-15T00:00:00Z";
  const data = (value: EventData): EventData => ({ timestamp: stamp, ...value });
  const records: Array<[string, EventData]> = scenario === "renamed-draft" ? [
    ["tool:args:chunk", data({ tool: "read_file", tool_call_id: "draft", content: "{" })],
    ["tool:start", data({ tool: "read_file", tool_call_id: "final", args: { path: "file" } })],
    ["tool:args:chunk", data({ tool: "read_file", tool_call_id: "draft", content: "late ignored" })],
    ["tool:start", data({ tool: "read_file", tool_call_id: "resumed", args: { path: "file" } })],
    ["tool:args:chunk", data({ tool: "read_file", tool_call_id: "draft", content: "new draft after takeover dropped alias" })],
    ["tool:result", data({ tool: "read_file", tool_call_id: "resumed", result: "file" })],
  ] : scenario === "draft-text" ? [
    ["tool:args:chunk", data({ tool: "read_file", tool_call_id: "draft", content: "{" })],
    ["message:chunk", data({ content: "before draft" })],
    ["tool:start", data({ tool: "read_file", tool_call_id: "draft", args: { path: "file" } })],
    ["tool:result", data({ tool: "read_file", tool_call_id: "draft", result: "file" })],
  ] : scenario === "depth2-draft" ? [
    ["agent:call", data({ agent_id: "worker", depth: 2 })],
    ["tool:args:chunk", data({ agent_id: "worker", depth: 2, tool: "read_file", tool_call_id: "draft", content: "{" })],
    ["tool:start", data({ agent_id: "worker", depth: 2, tool: "read_file", tool_call_id: "draft", args: { path: "file" } })],
    ["tool:result", data({ agent_id: "worker", depth: 2, tool: "read_file", tool_call_id: "draft", result: "file" })],
    ["agent:result", data({ agent_id: "worker", depth: 2, result: "done" })],
  ] : [
    ["agent:call", data({ agent_id: "worker", depth: 1, status: "queued" })],
    ["agent:call", data({ agent_id: "worker", depth: 1, status: "running" })],
    ["tool:start", data({ agent_id: "worker", depth: 1, tool: "read_file", tool_call_id: "first", args: { path: "file" } })],
    ["agent:result", data({ agent_id: "worker", depth: 1, result: "waiting", status: scenario === "waiting-human" ? "waiting_human" : "complete" })],
    ["tool:result", data({ agent_id: "worker", depth: 1, tool: "read_file", tool_call_id: "first", result: "late file" })],
    ["message:chunk", data({ agent_id: "worker", depth: 1, content: "late body" })],
    ["agent:result", data({ agent_id: "worker", depth: 1, result: "done" })],
  ];
  const events: HistoryEvent[] = records.map(([event_type, value]) => ({ event_type, run_id: "boundary", data: value }));
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "boundary",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
  expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
  expect(message.content).toEqual(expected.content);
  expect(message.toolCalls).toEqual(expected.toolCalls);
});


test.each([false, true])("1000 single-tail drafts keep late text and thinking with linear work (renamed=%s)", (renamed) => {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const draft = `text-draft-${index}`;
    const final = renamed ? `text-final-${index}` : draft;
    events.push(
      { event_type: "thinking", run_id: "draft-text-scale", data: { thinking_id: `thought-${index % 3}`, content: `before-${index};` } },
      { event_type: "tool:args:chunk", run_id: "draft-text-scale", data: { tool: "read_file", tool_call_id: draft, content: '{"path":' } },
      { event_type: "message:chunk", run_id: "draft-text-scale", data: { content: `first-${index};` } },
      { event_type: "message:chunk", run_id: "draft-text-scale", data: { content: `second-${index};` } },
      { event_type: "tool:args:chunk", run_id: "draft-text-scale", data: { tool: "read_file", tool_call_id: draft, content: `"${index}"}` } },
      { event_type: "thinking", run_id: "draft-text-scale", data: { thinking_id: `thought-${index % 3}`, content: `after-${index};` } },
      { event_type: "tool:start", run_id: "draft-text-scale", data: { tool: "read_file", tool_call_id: final, args: { path: `${index}` }, timestamp: "2026-10-15T00:00:00Z" } },
      { event_type: "tool:args:chunk", run_id: "draft-text-scale", data: { tool: "read_file", tool_call_id: draft, content: "ignored after upgrade" } },
      { event_type: "tool:result", run_id: "draft-text-scale", data: { tool: "read_file", tool_call_id: final, result: { content: `${index}`, attachments: [{ key: `file-${index}` }] } } },
    );
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "draft-text-scale",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
    expect(message.content).toEqual(expected.content);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(2);
  } finally { processor.mockRestore(); }
});


test.each(["todo_write", "write_todos"])("%s with an existing tool ID retains checklist dispatch precedence", (tool) => {
  const events: HistoryEvent[] = [
    { event_type: "tool:start", run_id: "todo-collision", data: { tool: "read_file", tool_call_id: "same", args: { path: "file" }, timestamp: "2026-10-15T00:00:00Z" } },
    { event_type: "tool:result", run_id: "todo-collision", data: { tool: "read_file", tool_call_id: "same", result: "file" } },
    { event_type: "tool:start", run_id: "todo-collision", data: { tool, tool_call_id: "same", args: { todos: [{ content: "preserve this checklist", status: "completed" }] } } },
    { event_type: "tool:result", run_id: "todo-collision", data: { tool, tool_call_id: "same", result: "ignored checklist result" } },
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "todo-collision",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
  expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
  expect(message.toolCalls).toEqual(expected.toolCalls);
  expect(message.parts?.some(part => part.type === "todo")).toBe(true);
});


test.each(["todo_write", "write_todos"])("1000 %s updates alternate with tools without growing reducer work", (tool) => {
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const id = `todo-alternating-${index}`;
    events.push(...plainToolHistory(1).map(event => ({ ...event, run_id: "todo-scale", data: {
      ...(event.data as EventData), tool_call_id: id,
    } })),
    { event_type: "tool:start", run_id: "todo-scale", data: { tool, tool_call_id: id, args: { todos: [
      { id: `done-${index}`, content: `complete-${index}`, status: "completed", activeForm: `completed-${index}`, metadata: { step: index } },
      { id: `cancelled-${index}`, content: `cancel-${index}`, status: "cancelled", activeForm: `cancelled-${index}` },
      { id: `pending-${index}`, content: `pending-${index}`, status: "in_progress", activeForm: `working-${index}` },
    ] } } },
    { event_type: "tool:args:chunk", run_id: "todo-scale", data: { tool, tool_call_id: id, content: "ignored todo draft" } },
    { event_type: "tool:result", run_id: "todo-scale", data: { tool, tool_call_id: id, result: "ignored todo result" } });
  }
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "todo-scale",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(message.parts?.filter(part => part.type === "todo")).toHaveLength(1);
    // Reuse the authoritative todo conversion on an empty parts array; no growing-history scans.
    expect(processor.mock.calls.reduce((work, call) => work + call[2].length, 0)).toBeLessThanOrEqual(2);
    expect(processor.mock.calls.length).toBeLessThanOrEqual(1002);
  } finally { processor.mockRestore(); }
});

test("nested todo updates and empty updates retain complete shared metadata and routing", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const events: HistoryEvent[] = [
    { event_type: "agent:call", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, timestamp: stamp } },
    { event_type: "todo:updated", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, todos: [{ content: "first", status: "pending", activeForm: "doing first" }] } },
    { event_type: "tool:start", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, tool: "read_file", tool_call_id: "same", args: {}, timestamp: stamp } },
    { event_type: "tool:start", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, tool: "write_todos", tool_call_id: "same", args: { todos: [{ id: "stable", content: "replacement", status: "cancelled", activeForm: "cancelled form", metadata: { stable: true } }] } } },
    { event_type: "todo:updated", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, todos: [] } },
    { event_type: "tool:result", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, tool: "read_file", tool_call_id: "same", result: "file" } },
    { event_type: "agent:result", run_id: "nested-todo", data: { agent_id: "worker", depth: 1, result: "done", timestamp: stamp } },
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "nested-todo",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
  expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
  expect(message.toolCalls).toEqual(expected.toolCalls);
});


test("1000 tool approvals alternate without growing parts scans and keep sandbox receipts", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const events: HistoryEvent[] = [];
  for (let index = 0; index < 1000; index++) {
    const id = `approved-tool-${index}`;
    events.push(
      { event_type: "tool:start", run_id: "approval-scale", data: { tool: "read_file", tool_call_id: id, args: { path: `${index}` }, timestamp: stamp } },
      { event_type: "hitl:suspended", run_id: "approval-scale", data: {} },
      { event_type: "approval_required", run_id: "approval-scale", data: { id: `approval-${index}`, tool_call_id: id, origin: "sandbox_confirm", message: `${index}` } },
      { event_type: "human_resume_started", run_id: "approval-scale", data: {} },
      { event_type: "approval_resolved", run_id: "approval-scale", data: { id: `approval-${index}`, tool_call_id: id, result: { status: "success", metadata: { sequence: index } }, timestamp: stamp } },
      { event_type: "tool:result", run_id: "approval-scale", data: { tool: "read_file", tool_call_id: id, result: { content: `${index}`, attachments: [{ key: `approved-file-${index}` }] }, success: index % 2 === 0, error: index % 2 ? "failure" : undefined, timestamp: stamp } },
    );
  }
  const expected = events.filter(event => event.event_type !== "approval_required").reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "approval-scale",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  const awaiting = vi.spyOn(suspendedParts, "markPendingToolsAwaiting");
  const results = vi.spyOn(sharedParts, "updateToolResultInDepth");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.reduce((work, call) => work + call[2].length, 0)).toBeLessThanOrEqual(2);
    expect(awaiting.mock.calls.reduce((work, call) => work + call[0].length, 0)).toBeLessThanOrEqual(2000);
    expect(results.mock.calls.reduce((work, call) => work + call[0].length, 0)).toBeLessThanOrEqual(2000);
  } finally { processor.mockRestore(); awaiting.mockRestore(); results.mockRestore(); }
});

test("one 1000-ID approval batch keeps complete receipts with linear addressed-slot work", () => {
  const events: HistoryEvent[] = [];
  const ids: string[] = [];
  for (let index = 0; index < 1000; index++) {
    const id = `batch-tool-${index}`;
    ids.push(id);
    events.push({ event_type: "tool:start", run_id: "batch-approval", data: { tool: "read_file", tool_call_id: id, args: { path: `${index}` }, timestamp: "2026-10-15T00:00:00Z" } });
  }
  events.push(
    { event_type: "hitl:suspended", run_id: "batch-approval", data: {} },
    { event_type: "approval_resolved", run_id: "batch-approval", data: { tool_call_ids: ids, result: { status: "rejected", detail: { all: true } }, success: false, error: "user rejected", timestamp: "2026-10-15T00:00:01Z" } },
  );
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls, 0, [], false, "batch-approval",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const processor = vi.spyOn(historyProcessor, "processMessageEvent");
  const results = vi.spyOn(sharedParts, "updateToolResultInDepth");
  try {
    const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
    expect(message.parts).toEqual(expected.parts);
    expect(message.parts).toHaveLength(1000);
    expect(message.toolCalls).toEqual(expected.toolCalls);
    expect(processor.mock.calls.reduce((work, call) => work + call[2].length, 0)).toBeLessThanOrEqual(2);
    expect(results.mock.calls.reduce((work, call) => work + call[0].length, 0)).toBeLessThanOrEqual(1000);
  } finally { processor.mockRestore(); results.mockRestore(); }
});

test("approval broadcast reaches parallel pending children and receipts clear draft/cancel flags", () => {
  const stamp = "2026-10-15T00:00:00Z";
  const events: HistoryEvent[] = [
    { event_type: "agent:call", run_id: "child-approval", data: { agent_id: "first", depth: 1, status: "queued", timestamp: stamp } },
    { event_type: "agent:call", run_id: "child-approval", data: { agent_id: "second", depth: 2, timestamp: stamp } },
    { event_type: "tool:args:chunk", run_id: "child-approval", data: { agent_id: "first", depth: 1, tool: "read_file", tool_call_id: "draft", content: "{" } },
    { event_type: "tool:start", run_id: "child-approval", data: { agent_id: "second", depth: 2, tool: "read_file", tool_call_id: "cancelled", args: {}, timestamp: stamp } },
    { event_type: "hitl:suspended", run_id: "child-approval", data: {} },
    { event_type: "human_resume_started", run_id: "child-approval", data: {} },
    { event_type: "agent:result", run_id: "child-approval", data: { agent_id: "second", depth: 2, result: "cancelled", status: "cancelled", timestamp: stamp } },
    { event_type: "approval_resolved", run_id: "child-approval", data: { tool_call_ids: ["draft", "cancelled"], result: { status: "success", full: { nested: true } }, timestamp: stamp } },
    { event_type: "agent:result", run_id: "child-approval", data: { agent_id: "first", depth: 1, result: "done", timestamp: stamp } },
  ];
  const expected = events.reduce((state, event) => historyProcessor.processMessageEvent(
    event.event_type, event.data as EventData, state.parts, state.content, state.toolCalls,
    (event.data as EventData).depth || 0, [], false, "child-approval",
  ), { parts: [] as NonNullable<Message["parts"]>, content: "", toolCalls: [] as NonNullable<Message["toolCalls"]> });
  const message = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] })[0];
  expect(message.parts).toEqual(clearAllLoadingStates(expected.parts, { preserveAskHuman: true, discardToolDrafts: false }));
  expect(message.toolCalls).toEqual(expected.toolCalls);
});

test("late tool start cannot revive a canceled partial history draft", () => {
  const events: HistoryEvent[] = [
    { event_type: "tool:args:chunk", run_id: "cancelled-run", data: { tool: "read_file", tool_call_id: "draft", content: "{" } },
    { event_type: "user:cancel", run_id: "cancelled-run", data: {} },
    { event_type: "tool:start", run_id: "cancelled-run", data: { tool: "read_file", tool_call_id: "draft", args: {} } },
  ];
  const messages = reconstructMessagesFromEvents(events, new Set(), { activeSubagentStack: [] });
  const tool = messages.flatMap(message => message.parts ?? []).find(part => part.type === "tool" && part.id === "draft");
  expect(tool?.type).toBe("tool");
  if (tool?.type !== "tool") throw new Error("History tool missing");
  expect(tool.result).toBeTruthy();
  expect(tool.cancelled).toBe(true);
  expect(tool.isPending).toBe(false);
});
