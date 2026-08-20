import {
  prepareMessagesForRunningRun,
  reconstructMessagesFromEvents,
} from "../historyLoader.ts";
import type { Message } from "../../../types";
import type { HistoryEvent } from "../types.ts";

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
  expect(users.map((m) => m.content)).toEqual(["搜索今日新闻", "给我多一点中国的"]);
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
        data: { content: "hello", message_id: `${runId}:user`, attachments: [] },
      } satisfies HistoryEvent,
      {
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-08-20T10:00:01.000Z",
        data: { content: "hello", message_id: `${runId}:user`, attachments: [] },
      } satisfies HistoryEvent,
    ],
    new Set<string>(),
    { activeSubagentStack: [] },
  );
  expect(messages.filter((m) => m.role === "user")).toHaveLength(1);
});
