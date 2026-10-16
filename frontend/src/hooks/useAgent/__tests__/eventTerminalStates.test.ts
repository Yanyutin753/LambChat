import { expect, test } from "vitest";
import type { MessagePart } from "../../../types";
import { processMessageEvent } from "../eventProcessor";
import { clearAllLoadingStates } from "../messageParts";

const pending: MessagePart[] = [
  { type: "thinking", content: "Earlier reasoning", isStreaming: true },
  {
    type: "tool",
    id: "done",
    name: "read_file",
    args: {},
    success: true,
    isPending: false,
    result: "ok",
  },
  { type: "thinking", content: "Still reasoning", isStreaming: true },
];

test.each([true, false])(
  "failure settles only the current thought during live/replay (%s)",
  (streaming) => {
    const result = processMessageEvent(
      "error",
      { error: "Provider offline", type: "task_error" },
      pending,
      "",
      [],
      0,
      [],
      streaming,
    );
    expect(result.parts[0]).not.toHaveProperty("status");
    expect(result.parts[1]).toEqual(pending[1]);
    expect(result.parts[2]).toMatchObject({
      isStreaming: false,
      status: "error",
    });
  },
);

test("cancellation retains the unfinished thought and its cancelled status", () => {
  const result = processMessageEvent(
    "error",
    { type: "task_cancelled" },
    pending,
    "",
    [],
    0,
    [],
    true,
  );
  expect(result.parts[2]).toMatchObject({
    content: "Still reasoning",
    status: "cancelled",
    isStreaming: false,
  });
});

test("run failure settles pending tools, sandbox and children as failures rather than user cancellations", () => {
  const parts: MessagePart[] = [
    { type: "tool", id: "read", name: "read_file", args: {}, isPending: true },
    { type: "sandbox", status: "starting" },
    {
      type: "subagent",
      agent_id: "child",
      agent_name: "Reviewer",
      input: "review",
      depth: 1,
      status: "running",
      isPending: true,
      parts: [{ type: "thinking", content: "Checking", isStreaming: true }],
    },
  ];
  const result = processMessageEvent(
    "error",
    { error: "Provider offline", type: "task_error" },
    parts,
    "",
    [],
    0,
    [],
    true,
  );
  expect(result.parts[0]).toMatchObject({
    isPending: false,
    success: false,
    cancelled: false,
    result: expect.stringContaining("Provider offline"),
  });
  expect(result.parts[1]).toMatchObject({ status: "error" });
  expect(result.parts[2]).toMatchObject({
    status: "error",
    cancelled: false,
    parts: [{ status: "error" }],
  });
});

test("ordinary completion keeps thoughts successful", () => {
  const result = clearAllLoadingStates(pending, { discardToolDrafts: true });
  expect(result[2]).toMatchObject({ isStreaming: false });
  expect(result[2]).not.toHaveProperty("status");
});

test.each(["error", "cancelled", "timed_out"])(
  "child %s settles its own unfinished reasoning without changing parent reasoning",
  (status) => {
    const child: MessagePart = {
      type: "subagent",
      agent_id: "child",
      agent_name: "Reviewer",
      input: "review",
      depth: 1,
      status: "running",
      isPending: true,
      parts: [{ type: "thinking", content: "Checking", isStreaming: true }],
    };
    const result = processMessageEvent(
      "agent:result",
      {
        agent_id: "child",
        depth: 1,
        success: false,
        result: "",
        error: status === "cancelled" ? "Cancelled" : "Provider offline",
        status,
      },
      [pending[0], child],
      "",
      [],
      1,
      [],
      true,
    );
    expect(result.parts[0]).toEqual(pending[0]);
    expect(result.parts[1]).toMatchObject({
      status,
      parts: [
        {
          status: status === "cancelled" ? "cancelled" : "error",
          isStreaming: false,
        },
      ],
    });
  },
);

test("a later parent failure does not relabel a previously cancelled child", () => {
  const part: MessagePart = {
    type: "subagent",
    agent_id: "stopped",
    agent_name: "Reviewer",
    input: "review",
    depth: 1,
    status: "cancelled",
    cancelled: true,
    isPending: false,
  };
  const result = processMessageEvent(
    "error",
    { error: "Provider offline", type: "task_error" },
    [part],
    "",
    [],
    0,
    [],
    true,
  );
  expect(result.parts[0]).toMatchObject({
    status: "cancelled",
    cancelled: true,
  });
});

test("reasoning before sandbox initialization stays completed when initialization is interrupted", () => {
  const parts: MessagePart[] = [
    { type: "thinking", content: "Ready to execute", isStreaming: true },
    { type: "sandbox", status: "starting" },
  ];
  const result = processMessageEvent(
    "error",
    { type: "task_cancelled" },
    parts,
    "",
    [],
    0,
    [],
    true,
  );
  expect(result.parts[0]).not.toHaveProperty("status");
  expect(result.parts[1]).toMatchObject({ status: "cancelled" });
});

test.each([0, 1])(
  "resumed reasoning clears its previous terminal status at depth %s",
  (depth) => {
    const thinking: MessagePart = {
      type: "thinking",
      content: "Before",
      thinking_id: "resume",
      isStreaming: false,
      status: "cancelled",
    };
    const parts: MessagePart[] = depth
      ? [
          {
            type: "subagent",
            agent_id: "child",
            agent_name: "Reviewer",
            input: "review",
            depth: 1,
            status: "running",
            isPending: true,
            parts: [thinking],
          },
        ]
      : [thinking];
    const result = processMessageEvent(
      "thinking",
      {
        content: " After",
        thinking_id: "resume",
        depth,
        agent_id: depth ? "child" : undefined,
      },
      parts,
      "",
      [],
      depth,
      [],
      true,
    );
    const part =
      depth && result.parts[0].type === "subagent"
        ? result.parts[0].parts?.[0]
        : result.parts[0];
    expect(part).toMatchObject({ content: "Before After", isStreaming: true });
    expect(part).toHaveProperty("status", undefined);
  },
);
