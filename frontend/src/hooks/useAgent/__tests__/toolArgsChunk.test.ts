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
    {
      id: "run-level-id",
      name: "write_file",
      args: { content: "hello world" },
    },
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
  const stack = [
    { agent_id: "sub-agent-1", depth: 1, message_id: "message-1" },
  ];
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

test("late text chunk merges into the text part before a generating tool", () => {
  // 复现真实乱序：正文首段先到，参数增量插入，正文余段晚到。
  let parts: MessagePart[] = processMessageEvent(
    "message:chunk",
    { content: "我先" },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;
  parts = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"path":'),
    parts,
    "我先",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  const healed = processMessageEvent(
    "message:chunk",
    { content: "确认工作区路径，然后写入文件。" },
    parts,
    "我先",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(healed.parts).toHaveLength(2);
  expect(healed.parts[0]).toMatchObject({
    type: "text",
    content: "我先确认工作区路径，然后写入文件。",
  });
  expect(healed.parts[1]).toMatchObject({ type: "tool", argsPartial: true });
  expect(healed.content).toBe("我先确认工作区路径，然后写入文件。");
});

test("late text chunk inserted before the tool even without an earlier text part", () => {
  const parts: MessagePart[] = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"path":'),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  const healed = processMessageEvent(
    "message:chunk",
    { content: "我先确认工作区路径。" },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(healed.parts).toHaveLength(2);
  expect(healed.parts[0]).toMatchObject({
    type: "text",
    content: "我先确认工作区路径。",
  });
  expect(healed.parts[1]).toMatchObject({ type: "tool", argsPartial: true });
});

test("text chunk after a started tool still appends after the tool", () => {
  const started: MessagePart[] = processMessageEvent(
    "tool:start",
    {
      tool: "write_file",
      tool_call_id: "run-1",
      args: { content: "hello" },
    },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  const result = processMessageEvent(
    "message:chunk",
    { content: "工作区为空，我将新建文件。" },
    started,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(result.parts).toHaveLength(2);
  expect(result.parts[0]).toMatchObject({ type: "tool", id: "run-1" });
  expect(result.parts[1]).toMatchObject({
    type: "text",
    content: "工作区为空，我将新建文件。",
  });
});

test("late text chunk merges before a trailing run of parallel generating tools", () => {
  // 并行工具：两个参数生成中的工具都在尾部，晚到的正文属于两者之前
  let parts: MessagePart[] = processMessageEvent(
    "message:chunk",
    { content: "我先" },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;
  parts = processMessageEvent(
    "tool:args:chunk",
    { tool: "grep", tool_call_id: "call_a", content: '{"q":"x"' },
    parts,
    "我先",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;
  parts = processMessageEvent(
    "tool:args:chunk",
    { tool: "read_file", tool_call_id: "call_b", content: '{"file_path":"/a"' },
    parts,
    "我先",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  const healed = processMessageEvent(
    "message:chunk",
    { content: "搜索一下。" },
    parts,
    "我先",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(healed.parts).toHaveLength(3);
  expect(healed.parts[0]).toMatchObject({
    type: "text",
    content: "我先搜索一下。",
  });
  expect(healed.parts[1]).toMatchObject({ type: "tool", id: "call_a" });
  expect(healed.parts[2]).toMatchObject({ type: "tool", id: "call_b" });
});

test("tool:start upgrade keeps the streaming id as alias for live panels", () => {
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

  const upgraded = started.parts[0] as ToolPart;
  expect(upgraded.id).toBe("run-level-id");
  // 参数流式期间以 LLM call id 打开的面板，升级后要靠 alias 继续收更新
  expect(upgraded.alias_id).toBe("call_1");
});

test("tool:start upgrade keeps existing alias when the generating part has none", () => {
  const generating = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"content":"hel', { tool_call_id: undefined }),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );
  expect((generating.parts[0] as ToolPart).id).toBeUndefined();

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

  expect((started.parts[0] as ToolPart).alias_id).toBeUndefined();
});

test("tool:start upgrades the LATEST generating part, not a stale leftover", () => {
  // 上一轮流式中断残留的 stale 生成中 part 排在前面；新一轮工具的
  // 生成中 part 在最后。tool:start 必须升级后者，否则新 pill 永远
  // 停在"参数生成中"不被替换（用户实测的卡死现象）
  const stale = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"q":"old"', { tool: "grep" }),
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );
  const fresh = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"q":"new"', { tool: "grep", tool_call_id: "call_new" }),
    stale.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );
  expect(fresh.parts).toHaveLength(2);

  const started = processMessageEvent(
    "tool:start",
    { tool: "grep", tool_call_id: "run-9", args: { q: "new" } },
    fresh.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  const parts = started.parts as ToolPart[];
  expect(parts).toHaveLength(2);
  // 升级命中的是最后一个（本轮正在流式的）part
  expect(parts[1]).toMatchObject({ id: "run-9", args: { q: "new" } });
  expect(parts[1].argsPartial).toBeUndefined();
  // stale part 保持原样（由中断清理流程标记 cancelled，不被误吃）
  expect(parts[0]).toMatchObject({
    argsPartial: true,
    args: { partial: '{"q":"old"' },
  });
});

test("parallel tools upgrade by tool name even in reverse execution order", () => {
  let parts: MessagePart[] = [];
  parts = processMessageEvent(
    "tool:args:chunk",
    { tool: "grep", tool_call_id: "call_a", content: '{"q' },
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
    { tool: "read_file", tool_call_id: "call_b", content: '{"file_path' },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts;

  // 执行顺序与生成顺序相反：read_file 先执行
  const startedB = processMessageEvent(
    "tool:start",
    { tool: "read_file", tool_call_id: "run-b", args: { file_path: "/a" } },
    parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts as ToolPart[];
  expect(startedB[0]).toMatchObject({ name: "grep", argsPartial: true });
  expect(startedB[1]).toMatchObject({ id: "run-b", args: { file_path: "/a" } });
  expect(startedB[1].argsPartial).toBeUndefined();

  const startedA = processMessageEvent(
    "tool:start",
    { tool: "grep", tool_call_id: "run-a", args: { q: "x" } },
    startedB,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  ).parts as ToolPart[];
  expect(startedA[0]).toMatchObject({ id: "run-a", args: { q: "x" } });
  expect(startedA[0].argsPartial).toBeUndefined();
});

test("late args chunk after upgrade does not create a ghost generating part", () => {
  const generating = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('{"q":"x"'),
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
    { tool: "grep", tool_call_id: "run-1", args: { q: "x" } },
    generating.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  // 迟到的参数增量（极端时序下可能残留）：不得再生成新的 argsPartial part
  const late = processMessageEvent(
    "tool:args:chunk",
    toolArgsChunk('y"}', { tool_call_id: "call_1" }),
    started.parts,
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(late.parts).toHaveLength(1);
  expect((late.parts[0] as ToolPart).argsPartial).toBeUndefined();
  expect((late.parts[0] as ToolPart).args).toEqual({ q: "x" });
});
