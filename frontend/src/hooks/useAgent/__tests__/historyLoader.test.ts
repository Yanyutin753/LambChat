import {
  normalizeEventRunIds,
  prepareMessagesForRunningRun,
  reconstructMessagesFromEvents,
  resolveLegacyScheduledTaskApproval,
} from "../historyLoader.ts";
import { vi } from "vitest";
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

test("inherits the run id for a synthesized recommendation event", () => {
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
        timestamp: "2026-08-21T00:00:01.000Z",
        data: { questions: ["next?"] },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.at(-1)?.runId).toBe("run-1");
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
        data: { content: "任务", message_id: "run-retry:user", attachments: [] },
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
        data: { content: "搜索 今日新闻", message_id: `${runId}:user`, attachments: [] },
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
        data: { tool: "web-search", args: { query: "今日新闻" }, tool_call_id: "t1" },
      } satisfies HistoryEvent,
      {
        event_type: "tool:result",
        run_id: runId,
        timestamp: "2026-08-22T15:14:42.100Z",
        data: { tool: "web-search", result: "结果", tool_call_id: "t1", success: true },
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
