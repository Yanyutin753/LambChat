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
test.each(["read_file", "grep", "web_search", "execute"])(
  "a single %s call stays directly visible",
  (name) => {
    const single = tool(1, { name });
    expect(groupConsecutiveTools([single])).toEqual([single]);
  },
);

test("local file searches can group across grep and glob", () => {
  const tools = [tool(1, { name: "grep" }), tool(2, { name: "glob" })];
  expect(groupConsecutiveTools(tools)).toEqual([
    { type: "tools", key: "tool-1", category: "search", count: 2, tools },
  ]);
});

test.each([
  "web_search",
  "search_tools",
  "search_skills",
  "search_persona_presets",
  "search_conversation_history",
  "memory_recall",
])("consecutive %s calls form a search group", (name) => {
  const tools = [tool(1, { name }), tool(2, { name })];
  expect(groupConsecutiveTools(tools)).toEqual([
    { type: "tools", key: "tool-1", category: "search", count: 2, tools },
  ]);
});

test("different search purposes retain separate adjacent groups", () => {
  const names = [
    "grep",
    "web_search",
    "search_tools",
    "search_skills",
    "search_persona_presets",
    "search_conversation_history",
    "memory_recall",
  ];
  const tools = names.flatMap((name, index) => [
    tool(index * 2, { name }),
    tool(index * 2 + 1, { name }),
  ]);
  expect(groupConsecutiveTools(tools)).toMatchObject(
    names.map((_, index) => ({
      type: "tools",
      key: `tool-${index * 2}`,
      category: "search",
      count: 2,
      tools: tools.slice(index * 2, index * 2 + 2),
    })),
  );
});

test.each([
  "execute",
  "write_file",
  "edit_file",
  "image_generate",
  "web_fetch",
  "memory_store",
  "custom_tool",
])("consecutive %s results stay directly visible", (name) => {
  const tools = [tool(1, { name }), tool(2, { name })];
  expect(groupConsecutiveTools(tools)).toEqual(tools);
});
test("running, failed, cancelled and interactive tools stay individually visible", () => {
  for (const overrides of [
    { isPending: true },
    { success: false },
    { success: undefined },
    { error: "Could not read file" },
    { cancelled: true },
    { awaitingConfirmation: true },
    { argsPartial: true },
    { name: "ask_human" },
    { name: "reveal_file" },
    { name: "write_todos" },
    { name: "todo_write" },
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
  const groups: RunPartGroup[] = [
    tool(1),
    tool(2, { name: "execute" }),
    tool(3),
    text,
    tool(5),
  ];
  expect(groupConsecutiveTools(groups)).toEqual(groups);
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

test.each<RunPartGroup>([
  { type: "single", partIndex: 3, part: { type: "text", content: "Next" } },
  {
    type: "single",
    partIndex: 3,
    part: { type: "thinking", content: "Check" },
  },
  { type: "gallery", startPartIndex: 3, images: [] },
])("non-tool content separates completed lookup batches: $type", (boundary) => {
  expect(
    groupConsecutiveTools([tool(1), tool(2), boundary, tool(4), tool(5)]),
  ).toMatchObject([
    { type: "tools", key: "tool-1", category: "read", count: 2 },
    boundary,
    { type: "tools", key: "tool-4", category: "read", count: 2 },
  ]);
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

test("streamed reads only group after a second adjacent call completes", async () => {
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
  ).toMatchObject({ type: "single", part: { id: "read-1", success: true } });
  expect(
    dispatch("tool:start", {
      tool: "read_file",
      tool_call_id: "read-2",
      args: { file_path: "/other.md" },
    }),
  ).toMatchObject([
    { type: "single", part: { id: "read-1", success: true } },
    { type: "single", part: { id: "read-2", isPending: true } },
  ]);
  expect(
    dispatch("tool:result", {
      tool: "read_file",
      tool_call_id: "read-2",
      result: "second output",
      success: true,
    }),
  ).toMatchObject([
    { type: "tools", key: "read-1", category: "read", count: 2 },
  ]);
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
