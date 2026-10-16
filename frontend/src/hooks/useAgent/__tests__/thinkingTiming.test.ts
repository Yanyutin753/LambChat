import { expect, test } from "vitest";
import { processMessageEvent } from "../eventProcessor";
import type { MessagePart } from "../../../types";

test.each([true, false])(
  "thinking timing survives live/replay and stops at the answer (%s)",
  (streaming) => {
    let parts: MessagePart[] = [];
    for (const [type, seconds, content] of [
      ["thinking", 0, "First"],
      ["thinking", 3, " second"],
      ["message:chunk", 12, "Answer"],
      ["message:chunk", 20, " more"],
    ] as const) {
      parts = processMessageEvent(
        type,
        {
          content,
          timestamp: new Date(1700000000000 + seconds * 1000).toISOString(),
          thinking_id: "t",
        },
        parts,
        "",
        [],
        0,
        [],
        streaming,
      ).parts;
    }
    expect(parts[0]).toMatchObject({
      startedAt: 1700000000000,
      completedAt: 1700000012000,
      isStreaming: false,
    });
  },
);

test("untimed history never acquires a fabricated duration", () => {
  const parts = processMessageEvent(
    "thinking",
    { content: "Old" },
    [],
    "",
    [],
    0,
    [],
    false,
  ).parts;
  expect(parts[0]).not.toHaveProperty("startedAt", expect.any(Number));
});

test("indexed history preserves the first timestamp and freezes at the answer", async () => {
  const { reconstructMessagesFromEvents } = await import("../historyLoader");
  const messages = reconstructMessagesFromEvents(
    [
      {
        id: "1",
        event_type: "thinking",
        data: { content: "First", thinking_id: "t" },
        timestamp: "2026-10-16T00:00:00Z",
        run_id: "run",
      },
      {
        id: "2",
        event_type: "thinking",
        data: { content: " second", thinking_id: "t" },
        timestamp: "2026-10-16T00:00:03Z",
        run_id: "run",
      },
      {
        id: "3",
        event_type: "message:chunk",
        data: { content: "Answer" },
        timestamp: "2026-10-16T00:00:12Z",
        run_id: "run",
      },
    ],
    new Set(),
    { activeSubagentStack: [] },
  );
  expect(messages[0].parts?.[0]).toMatchObject({
    startedAt: Date.parse("2026-10-16T00:00:00Z"),
    completedAt: Date.parse("2026-10-16T00:00:12Z"),
  });
});

test("a child tool freezes only its own reasoning", () => {
  const start = 1700000000000;
  const parts: MessagePart[] = [
    {
      type: "thinking",
      content: "Parent",
      startedAt: start,
      isStreaming: true,
    },
    {
      type: "subagent",
      agent_id: "child",
      agent_name: "Child",
      input: "",
      depth: 1,
      isPending: true,
      parts: [
        {
          type: "thinking",
          content: "Child",
          agent_id: "child",
          depth: 1,
          startedAt: start,
          isStreaming: true,
        },
      ],
    },
  ];
  const result = processMessageEvent(
    "tool:start",
    {
      tool: "read_file",
      tool_call_id: "tool",
      args: {},
      agent_id: "child",
      timestamp: new Date(start + 3000).toISOString(),
    },
    parts,
    "",
    [],
    1,
    [],
    true,
  );
  expect(result.parts[0]).toEqual(parts[0]);
  expect(result.parts[1]).toMatchObject({
    parts: [
      { completedAt: start + 3000, isStreaming: false },
      expect.anything(),
    ],
  });
});
