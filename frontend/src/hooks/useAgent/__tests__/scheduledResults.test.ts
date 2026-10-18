import { describe, expect, test } from "vitest";
import {
  mergeScheduledProgress,
  mergeScheduledResult,
} from "../scheduledResults";
import { reconstructMessagesFromEvents } from "../historyLoader";
import { processMessageEvent } from "../eventProcessor";
import type { EventData } from "../types";
import type { Message } from "../../../types";

const result = {
  session_id: "parent",
  run_id: "scheduled-1",
  message_id: "scheduled-result:scheduled-1",
  task_id: "task",
  task_name: "Numbers",
  content: "748196",
  timestamp: "2026-10-16T17:46:50Z",
};

describe("isolated scheduled results", () => {
  test("appends a result without changing the active user's streaming message", () => {
    const active: Message = {
      id: "human-answer",
      role: "assistant",
      content: "answering",
      timestamp: new Date("2026-10-16T17:46:00Z"),
      isStreaming: true,
      runId: "human",
    };
    const messages = mergeScheduledResult([active], result);
    expect(messages[0]).toBe(active);
    expect(messages[0].isStreaming).toBe(true);
    expect(messages[1]).toMatchObject({
      role: "assistant",
      isStreaming: false,
      content: "748196",
      metadata: { scheduledTaskId: "task", scheduledTaskName: "Numbers" },
    });
    expect(mergeScheduledResult(messages, result)).toBe(messages);
  });

  test("replays a result without changing the foreground user turns", () => {
    const messages = reconstructMessagesFromEvents(
      [
        {
          event_type: "user:message",
          run_id: "human",
          data: { content: "my question" },
          timestamp: "2026-10-16T17:46:00Z",
        },
        {
          event_type: "message:chunk",
          run_id: "human",
          data: { content: "before", text_id: "text" },
          timestamp: "2026-10-16T17:46:01Z",
        },
        {
          event_type: "scheduled:result",
          run_id: "scheduled-1",
          data: result,
          timestamp: result.timestamp,
        },
        {
          event_type: "message:chunk",
          run_id: "human",
          data: { content: " after", text_id: "text" },
          timestamp: "2026-10-16T17:46:55Z",
        },
        {
          event_type: "scheduled:result",
          run_id: "scheduled-1",
          data: result,
          timestamp: result.timestamp,
        },
      ],
      new Set(),
      { activeSubagentStack: [] },
    );
    expect(messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(
      messages.find((m) => m.runId === "human" && m.role === "assistant")
        ?.content,
    ).toBe("before after");
    expect(
      messages.filter((m) => m.metadata?.scheduledTaskId === "task"),
    ).toHaveLength(1);
  });
});

test("scheduled progress starts and updates its own bubble while human streaming stays untouched", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const human: Message = {
    id: "human",
    role: "assistant",
    content: "human answer",
    isStreaming: true,
    runId: "human-run",
    timestamp: new Date("2026-10-16T17:46:00Z"),
  };
  const started = mergeScheduledProgress([human], {
    ...result,
    content: "",
    status: "running",
    updated_at: "2026-10-16T17:46:50Z",
  });
  expect(started).toHaveLength(2);
  expect(started[1]).toMatchObject({
    id: result.message_id,
    isStreaming: true,
    content: "",
  });
  const streaming = mergeScheduledProgress(started, {
    ...result,
    content: "748",
    status: "running",
    updated_at: "2026-10-16T17:46:51Z",
  });
  expect(streaming[0]).toBe(human);
  expect(streaming[1].content).toBe("748");
  const finished = mergeScheduledResult(streaming, result);
  expect(finished).toHaveLength(2);
  expect(finished[1]).toMatchObject({
    id: result.message_id,
    content: "748196",
    isStreaming: false,
  });
  expect(finished[0]).toBe(human);
  expect(
    mergeScheduledProgress(finished, {
      ...result,
      content: "old",
      status: "running",
      updated_at: "2026-10-16T17:46:49Z",
    }),
  ).toBe(finished);
});

test("quiet or failed task progress never leaves an unrelated streaming bubble running", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const started = mergeScheduledProgress([], {
    ...result,
    content: "",
    status: "running",
    updated_at: "2026-10-16T17:46:50Z",
  });
  expect(
    mergeScheduledProgress(started, {
      ...result,
      content: "",
      status: "quiet",
      updated_at: "2026-10-16T17:46:51Z",
    }),
  ).toEqual([]);
  const failed = mergeScheduledProgress(started, {
    ...result,
    content: "partial",
    status: "failed",
    updated_at: "2026-10-16T17:46:51Z",
  });
  expect(failed[0].isStreaming).toBe(false);
  expect(failed[0].metadata?.scheduledProgressStatus).toBe("failed");
});

test("scheduled progress replays thinking and tools instead of replacing them with plain text", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const events = [
    {
      event_type: "thinking",
      data: { content: "Checking", thinking_id: "thought" },
    },
    {
      event_type: "tool:start",
      data: {
        tool: "execute",
        tool_call_id: "tool-1",
        args: { command: "date" },
      },
    },
  ];
  const progress = {
    ...result,
    content: "",
    status: "running" as const,
    updated_at: "2026-10-16T17:46:51Z",
    events,
  };
  const started = mergeScheduledProgress([], progress);
  expect(started[0].parts).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ type: "thinking", content: "Checking" }),
      expect.objectContaining({
        type: "tool",
        name: "execute",
        isPending: true,
      }),
    ]),
  );
  const finished = mergeScheduledResult(started, result);
  expect(finished[0].parts).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        type: "tool",
        name: "execute",
        isPending: false,
      }),
      expect.objectContaining({ type: "text", content: result.content }),
    ]),
  );
});

test("two execution events in the same millisecond both reach the task bubble", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const start = {
    ...result,
    content: "",
    status: "running" as const,
    updated_at: result.timestamp,
    events: [
      {
        event_type: "tool:start",
        data: { tool: "execute", tool_call_id: "exec", args: {} },
      },
    ],
  };
  const started = mergeScheduledProgress([], start);
  const completed = mergeScheduledProgress(started, {
    ...start,
    events: [
      ...start.events,
      {
        event_type: "tool:result",
        data: {
          tool: "execute",
          tool_call_id: "exec",
          result: "692",
          success: true,
        },
      },
    ],
  });
  expect(completed[0].parts?.[0]).toMatchObject({
    type: "tool",
    isPending: false,
  });
});

test("subagent output stays inside its execution card", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const messages = mergeScheduledProgress([], {
    ...result,
    content: "",
    status: "running",
    updated_at: result.timestamp,
    events: [
      {
        event_type: "agent:call",
        data: {
          agent_id: "child",
          agent_name: "Research",
          depth: 1,
          input: "Check",
        },
      },
      {
        event_type: "thinking",
        data: { agent_id: "child", depth: 1, content: "Checking" },
      },
      {
        event_type: "tool:start",
        data: {
          agent_id: "child",
          depth: 1,
          tool: "web_search",
          tool_call_id: "search",
          args: {},
        },
      },
    ],
  });
  expect(messages[0].content).toBe("");
  expect(messages[0].parts?.[0]).toMatchObject({
    type: "subagent",
    agent_id: "child",
    parts: [
      expect.objectContaining({ type: "thinking", content: "Checking" }),
      expect.objectContaining({
        type: "tool",
        name: "web_search",
        isPending: true,
      }),
    ],
  });
});

test.each([undefined, []])(
  "omitted or empty progress preserves details until a newer snapshot arrives: %s",
  (events) => {
    const progress = {
      ...result,
      content: "",
      status: "running" as const,
      updated_at: result.timestamp,
      events: [
        {
          event_type: "thinking",
          data: { content: "Checking", thinking_id: "thought" },
        },
        {
          event_type: "tool:start",
          data: { tool: "execute", tool_call_id: "exec", args: {} },
        },
      ],
    };
    const started = mergeScheduledProgress([], progress);
    const updatedAt = "2026-10-16T17:46:51Z";
    const omitted = mergeScheduledProgress(started, {
      ...progress,
      content: "Latest text",
      updated_at: updatedAt,
      events_omitted: true,
      events,
    });
    expect(omitted[0].parts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "thinking", content: "Checking" }),
        expect.objectContaining({
          type: "tool",
          name: "execute",
          isPending: true,
        }),
        expect.objectContaining({ type: "text", content: "Latest text" }),
      ]),
    );
    expect(omitted[0].metadata?.scheduledEventCount).toBe(2);
    const recovered = mergeScheduledProgress(omitted, {
      ...progress,
      updated_at: updatedAt,
      events: [
        ...progress.events,
        {
          event_type: "tool:result",
          data: {
            tool: "execute",
            tool_call_id: "exec",
            result: "692",
            success: true,
          },
        },
      ],
    });
    expect(recovered[0].parts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: "tool",
          name: "execute",
          isPending: false,
        }),
      ]),
    );
    expect(mergeScheduledProgress(recovered, progress)).toBe(recovered);
  },
);

test("scheduled replay resolves the same assistant identity as ordinary conversation history", async () => {
  const { mergeScheduledProgress } = await import("../scheduledResults");
  const messages = mergeScheduledProgress([], {
    ...result,
    content: "",
    status: "waiting_human",
    updated_at: result.timestamp,
    events: [
      {
        event_type: "metadata",
        data: { agent_id: "search", agent_name: "Search Agent" },
      },
      {
        event_type: "thinking",
        data: { content: "Check the previous numbers", thinking_id: "thought" },
      },
      {
        event_type: "tool:args:chunk",
        data: {
          tool: "execute",
          tool_call_id: "exec",
          content: '{"command":"echo 123"}',
        },
      },
      { event_type: "hitl:suspended", data: {} },
    ],
  });
  expect(messages[0].assistantIdentity?.seed).toBe("search");
  expect(messages[0].parts).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        type: "thinking",
        content: "Check the previous numbers",
      }),
      expect.objectContaining({ type: "tool", name: "execute" }),
    ]),
  );
});

test.each(["live", "history"])(
  "approval resumes one command and keeps the actual execution result: %s",
  (mode) => {
    const events = [
      {
        event_type: "tool:args:chunk",
        data: {
          tool: "execute",
          tool_call_id: "draft",
          content: '{"command":"echo 123"}',
        },
      },
      { event_type: "hitl:suspended", data: {} },
      {
        event_type: "approval_resolved",
        data: {
          id: "approval",
          tool_call_ids: ["draft"],
          success: true,
          result: { message: "Approved" },
        },
      },
      { event_type: "human_resume_started", data: {} },
      {
        event_type: "tool:start",
        data: {
          tool: "execute",
          tool_call_id: "actual",
          args: { command: "echo 123" },
        },
      },
      {
        event_type: "tool:result",
        data: {
          tool: "execute",
          tool_call_id: "actual",
          result: "123",
          success: true,
        },
      },
    ];
    const messages = mergeScheduledProgress([], {
      ...result,
      content: "",
      status: "running",
      updated_at: result.timestamp,
      events,
    });
    const parts =
      mode === "live"
        ? events.reduce(
            (parts, event) =>
              processMessageEvent(
                event.event_type,
                event.data as EventData,
                parts,
                "",
                [],
                0,
                [],
                true,
              ).parts,
            [] as NonNullable<Message["parts"]>,
          )
        : messages[0].parts;
    const tools = parts?.filter((part) => part.type === "tool");
    expect(tools).toHaveLength(1);
    expect(tools?.[0]).toMatchObject({
      name: "execute",
      result: "123",
      isPending: false,
    });
  },
);
