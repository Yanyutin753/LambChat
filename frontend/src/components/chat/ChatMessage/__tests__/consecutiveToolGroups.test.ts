import { expect, test } from "vitest";
import {
  groupConsecutiveTools,
  type RunPartGroup,
} from "../runStepsCollapseUtils";
const tool = (partIndex: number, overrides = {}): RunPartGroup => ({
  type: "single",
  partIndex,
  part: {
    type: "tool",
    id: `tool-${partIndex}`,
    name: "read_file",
    args: {},
    success: true,
    ...overrides,
  },
});

test("consecutive reads keep their detail entries but count unique files", () => {
  const tools = [
    tool(1, { args: { file_path: "/a.md" } }),
    tool(2, { args: { file_path: "/a.md" } }),
    tool(3, { args: { file_path: "/b.md" } }),
  ];
  expect(groupConsecutiveTools(tools)).toEqual([
    { type: "tools", key: "tool-1", category: "read", count: 2, tools },
  ]);
});
test("reads, searches and commands form separate adjacent groups including single commands", () => {
  const groups = groupConsecutiveTools([
    tool(1),
    tool(2),
    tool(3, { name: "grep" }),
    tool(4, { name: "web_search" }),
    tool(5, { name: "execute" }),
  ]);
  expect(groups).toMatchObject([
    { category: "read", count: 2 },
    { category: "search", count: 2 },
    { category: "execute", count: 1 },
  ]);
});
test("running, failed, cancelled and interactive tools stay individually visible", () => {
  for (const overrides of [
    { isPending: true },
    { success: false },
    { cancelled: true },
    { awaitingConfirmation: true },
    { argsPartial: true },
    { name: "ask_human" },
    { name: "reveal_file" },
    { name: "write_todos" },
  ]) {
    const special = tool(2, overrides);
    const result = groupConsecutiveTools([tool(1), special, tool(3)]);
    expect(result[1]).toBe(special);
    expect(result).toHaveLength(3);
  }
});
test("classification never reorders interleaved categories or crosses prose", () => {
  const text: RunPartGroup = {
    type: "single",
    partIndex: 4,
    part: { type: "text", content: "Next step" },
  };
  const result = groupConsecutiveTools([
    tool(1),
    tool(2, { name: "execute" }),
    tool(3),
    text,
    tool(5),
  ]);
  expect(result).toMatchObject([
    { key: "tool-1" },
    { key: "tool-2" },
    { key: "tool-3" },
    text,
    { key: "tool-5" },
  ]);
});
test("different agents and depths retain separate groups", () => {
  expect(
    groupConsecutiveTools([
      tool(1),
      tool(2, { agent_id: "researcher" }),
      tool(3, { depth: 1 }),
    ]),
  ).toHaveLength(3);
});
test("unknown single tools remain unchanged and appended tools preserve the first key", () => {
  const single = tool(0, { name: "custom_tool" });
  expect(groupConsecutiveTools([single])).toEqual([single]);
  expect(groupConsecutiveTools([tool(1), tool(2)])[0]).toHaveProperty(
    "key",
    "tool-1",
  );
  expect(groupConsecutiveTools([tool(1), tool(2), tool(3)])[0]).toHaveProperty(
    "key",
    "tool-1",
  );
});

test("backend event chunks remain visible until tool completion and then join their category", async () => {
  const { processMessageEvent } = await import(
    "../../../../hooks/useAgent/eventProcessor"
  );
  let parts: import("../../../../types").MessagePart[] = [];
  const dispatch = (
    event: string,
    data: Parameters<typeof processMessageEvent>[1],
  ) => {
    parts = processMessageEvent(
      event,
      data,
      parts,
      "",
      [],
      0,
      [],
      true,
      "stream-test",
    ).parts;
    return groupConsecutiveTools(
      parts.map((part, partIndex) => ({ type: "single", part, partIndex })),
    );
  };
  expect(
    dispatch("tool:args:chunk", {
      tool: "read_file",
      tool_call_id: "read-1",
      content: '{"file_path":',
    })[0],
  ).toMatchObject({ type: "single", part: { argsPartial: true } });
  expect(
    dispatch("tool:start", {
      tool: "read_file",
      tool_call_id: "read-1",
      args: { file_path: "/notes.md" },
    })[0],
  ).toMatchObject({ type: "single", part: { isPending: true } });
  expect(
    dispatch("tool:result", {
      tool: "read_file",
      tool_call_id: "read-1",
      result: "complete output",
      success: true,
    })[0],
  ).toMatchObject({ type: "tools", category: "read", count: 1 });
  dispatch("tool:start", {
    tool: "execute",
    tool_call_id: "cmd-1",
    args: { command: "check" },
  });
  expect(
    dispatch("tool:result", {
      tool: "execute",
      tool_call_id: "cmd-1",
      success: false,
      result: "failed",
      error: "exit 1",
    })[1],
  ).toMatchObject({ type: "single", part: { success: false } });
  dispatch("thinking", { content: "First ", thinking_id: "thought-1" });
  dispatch("thinking", { content: "second", thinking_id: "thought-1" });
  expect(parts.at(-1)).toMatchObject({
    type: "thinking",
    content: "First second",
  });
});
