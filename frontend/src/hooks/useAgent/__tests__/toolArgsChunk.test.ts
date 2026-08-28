import type { MessagePart, ToolPart } from "../../../types";
import { processMessageEvent } from "../eventProcessor.ts";

function toolArgsChunk(
  content: string,
  extras: Record<string, unknown> = {},
): Parameters<typeof processMessageEvent>[1] {
  return {
    tool: "write_file",
    tool_call_id: "call_1",
    content,
    ...extras,
  };
}

test("tool:args:chunk creates a generating tool part with partial args", () => {
  const result = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"con'),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(result.parts).toHaveLength(1);
  expect(result.parts[0]).toMatchObject({
    type: "tool",
    id: "call_1",
    name: "write_file",
    args: { partial: '{"con' },
    argsPartial: true,
    isPending: true,
  });
});

test("consecutive tool:args:chunks append into the same partial args", () => {
  const first = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"con'),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );
  const second = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('tent":"hello"}'),
    first.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(second.parts).toHaveLength(1);
  expect((second.parts[0] as ToolPart).args).toEqual({
    partial: '{"content":"hello"}',
  });
});

test("tool:start upgrades the generating part in place with final args", () => {
  const generating = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"content":"hel'),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  const started = processMessageEvent(
    "tool:start",
    {
      tool: "write_file",
      tool_call_id: "run-level-id",
      args: { content: "hello world" },
    },
    generating.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(started.parts).toHaveLength(1);
  expect(started.parts[0]).toMatchObject({
    type: "tool",
    id: "run-level-id",
    name: "write_file",
    args: { content: "hello world" },
    isPending: true,
  });
  expect((started.parts[0] as ToolPart).argsPartial).toBeUndefined();
  expect(started.toolCalls).toEqual([
    { id: "run-level-id", name: "write_file", args: { content: "hello world" } },
  ]);
});

test("parallel tool calls upgrade in generation order", () => {
  let parts: MessagePart[] = [];

  parts = processMessageEvent(
    "tool:args:chunk",
    {
      tool: "grep",
      tool_call_id: "call_a",
      content: '{"q',
    },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;
  parts = processMessageEvent(
    "tool:args:chunk",
    {
      tool: "read_file",
      tool_call_id: "call_b",
      content: '{"file_path',
    },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  expect(parts).toHaveLength(2);

  // First tool:start must upgrade the FIRST generating part (grep), not read_file.
  const upgraded = processMessageEvent(
    "tool:start",
    {
      tool: "grep",
      tool_call_id: "run-grep",
      args: { q: "pattern" },
    },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(upgraded.parts).toHaveLength(2);
  expect(upgraded.parts[0]).toMatchObject({
    id: "run-grep",
    args: { q: "pattern" },
  });
  expect(upgraded.parts[1]).toMatchObject({
    id: "call_b",
    args: { partial: '{"file_path' },
    argsPartial: true,
  });
});

test("tool:args:chunk without id appends to the last generating part", () => {
  const first = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"a"'),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );
  const cleared = processMessageEvent(
    "tool:args:chunk",
    {
      tool: "write_file",
      content: ',"b":1}',
    },
    first.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(cleared.parts).toHaveLength(1);
  expect((cleared.parts[0] as ToolPart).args).toEqual({
    partial: '{"a","b":1}',
  });
});

test("tool:start without a generating part keeps the existing append behavior", () => {
  const started = processMessageEvent(
    "tool:start",
    {
      tool: "ls",
      tool_call_id: "run-ls",
      args: { path: "/tmp" },
    },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(started.parts).toHaveLength(1);
  expect(started.parts[0]).toMatchObject({
    type: "tool",
    id: "run-ls",
    args: { path: "/tmp" },
  });
});

test("tool:args:chunk lands inside the matching subagent container", () => {
  const called = processMessageEvent(
    "agent:call",
    {
      agent_id: "sub-agent-1",
      agent_name: "Researcher",
      input: "research",
      depth: 1,
    },
    [],
    "",
    [],
    1,
    [{ agent_id: "sub-agent-1", depth: 1, message_id: "message-1" }],
    true,
    "message-1",
  );

  const chunked = processMessageEvent(
    "tool:args:chunk",
    {
      tool: "read_file",
      tool_call_id: "call_sub",
      content: '{"file_path',
      depth: 1,
      agent_id: "sub-agent-1",
    },
    called.parts,
    "",
    [],
    1,
    [{ agent_id: "sub-agent-1", depth: 1, message_id: "message-1" }],
    true,
    "message-1",
  );

  const subagent = chunked.parts[0] as unknown as {
    type: string;
    parts: ToolPart[];
  };
  expect(subagent.type).toBe("subagent");
  expect(subagent.parts).toHaveLength(1);
  expect(subagent.parts[0]).toMatchObject({
    type: "tool",
    id: "call_sub",
    argsPartial: true,
    args: { partial: '{"file_path' },
  });
});

test("subagent tool:start upgrades the generating part inside the container", () => {
  const stack = [{ agent_id: "sub-agent-1", depth: 1, message_id: "message-1" }];
  let parts: MessagePart[] = processMessageEvent(
    "agent:call",
    {
      agent_id: "sub-agent-1",
      agent_name: "Researcher",
      input: "research",
      depth: 1,
    },
    [],
    "",
    [],
    1,
    stack,
    true,
    "message-1",
  ).parts;
  parts = processMessageEvent(
    "tool:args:chunk",
    {
      tool: "read_file",
      tool_call_id: "call_sub",
      content: '{"file_path',
      depth: 1,
      agent_id: "sub-agent-1",
    },
    parts,
    "",
    [],
    1,
    stack,
    true,
    "message-1",
  ).parts;

  const started = processMessageEvent(
    "tool:start",
    {
      tool: "read_file",
      tool_call_id: "run-sub",
      args: { file_path: "/a" },
      depth: 1,
      agent_id: "sub-agent-1",
    },
    parts,
    "",
    [],
    1,
    stack,
    true,
    "message-1",
  );

  const subagent = started.parts[0] as unknown as {
    parts: ToolPart[];
  };
  expect(subagent.parts).toHaveLength(1);
  expect(subagent.parts[0]).toMatchObject({
    id: "run-sub",
    args: { file_path: "/a" },
  });
  expect(subagent.parts[0].argsPartial).toBeUndefined();
});
