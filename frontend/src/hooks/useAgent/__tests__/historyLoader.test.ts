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

test("reconstructMessagesFromEvents treats assistant-only run after cancel as retry", () => {
  const cancelledRunId = "run_cancelled";
  const retryRunId = "run_retry";
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: cancelledRunId,
        timestamp: "2026-06-17T12:00:00.000Z",
        data: {
          content: "regenerate this",
          message_id: `${cancelledRunId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-old-chunk",
        event_type: "message:chunk",
        run_id: cancelledRunId,
        timestamp: "2026-06-17T12:00:01.000Z",
        data: { content: "partial" },
      },
      {
        id: "event-cancel",
        event_type: "user:cancel",
        run_id: cancelledRunId,
        timestamp: "2026-06-17T12:00:02.000Z",
        data: { run_id: cancelledRunId },
      },
      {
        id: "event-retry-metadata",
        event_type: "metadata",
        run_id: retryRunId,
        timestamp: "2026-06-17T12:00:03.000Z",
        data: { run_id: retryRunId },
      },
      {
        id: "event-retry-chunk",
        event_type: "message:chunk",
        run_id: retryRunId,
        timestamp: "2026-06-17T12:00:04.000Z",
        data: { content: "fresh answer" },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.map((message) => [message.id, message.role, message.runId])).toEqual([
      [`${cancelledRunId}:user`, "user", cancelledRunId],
      [retryRunId, "assistant", retryRunId],
    ]);
  expect(messages[1]?.content).toBe("fresh answer");
  expect(messages[1]?.cancelled).toBe(undefined);
});

test("reconstructMessagesFromEvents preserves plugin tool result outlet from persisted events", () => {
  const runId = "run_plugin_tool_history";
  const pluginOutlet = {
    plugin_id: "review_center",
    review_id: "review-chat",
    run_id: "run-debug-1",
    version_id: "review-v1",
    status: "failed",
    error: "review_run_not_found",
    interface: {
      entry: {
        type: "tool",
        tool: "review_run",
        argument: "input",
        schema_tool: "review_get_schema",
        schema_field: "input_schema",
      },
      exit: {
        type: "object",
        field: "output",
        schema_tool: "review_get_schema",
        schema_field: "output_schema",
      },
      debug: {
        tool: "review_get_run",
        review_id: "review-chat",
        run_id: "run-debug-1",
        events_field: "events",
      },
    },
    next_action: {
      type: "handle_terminal_error",
      field: "error",
      reason: "review_run_failed",
      tool: "review_get_run",
    },
  };

  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "event-user",
        event_type: "user:message",
        run_id: runId,
        timestamp: "2026-06-28T08:00:00.000Z",
        data: {
          content: "inspect failed plugin run",
          message_id: `${runId}:user`,
          attachments: [],
        },
      },
      {
        id: "event-tool-start",
        event_type: "tool:start",
        run_id: runId,
        timestamp: "2026-06-28T08:00:01.000Z",
        data: {
          tool: "review_get_run",
          tool_call_id: "tool-call-review-debug",
          args: { review_id: "review-chat", run_id: "run-debug-1" },
        },
      },
      {
        id: "event-tool-result",
        event_type: "tool:result",
        run_id: runId,
        timestamp: "2026-06-28T08:00:02.000Z",
        data: {
          tool: "review_get_run",
          tool_call_id: "tool-call-review-debug",
          result: pluginOutlet,
          success: false,
          error: "review_run_not_found",
        },
      },
      {
        id: "event-message",
        event_type: "message:chunk",
        run_id: runId,
        timestamp: "2026-06-28T08:00:03.000Z",
        data: { content: "Plugin debug lookup failed." },
      },
    ] satisfies HistoryEvent[],
    new Set<string>(),
    { activeSubagentStack: [] },
  );

  expect(messages.length).toBe(2);
  const assistant = messages[1];
  expect(assistant?.role).toBe("assistant");
  expect(assistant?.content).toBe("Plugin debug lookup failed.");
  const toolPart = assistant?.parts?.find((part) => part.type === "tool");
  expect(toolPart).toBeTruthy();
  expect(toolPart.type).toBe("tool");
  expect(toolPart.name).toBe("review_get_run");
  expect(toolPart.success).toBe(false);
  expect(toolPart.error).toBe("review_run_not_found");
  expect(toolPart.result).toEqual(pluginOutlet);
  expect(assistant?.toolResults?.[0]?.result).toEqual(pluginOutlet);
  expect((
      assistant?.toolResults?.[0]?.result as {
        interface?: { debug?: { tool?: string } };
      }
    ).interface?.debug?.tool).toBe("review_get_run");
});
