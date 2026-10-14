import type { MessagePart, SubagentPart } from "../../../types";
import { processMessageEvent } from "../eventProcessor";

test.each([0, 1])("an explicit result ID cannot be consumed by an unrelated legacy tool at depth %s", (depth) => {
  let parts: MessagePart[] = [];
  if (depth) parts = processMessageEvent("agent:call", { agent_id: "child" }, parts, "", [], depth, [], false).parts;
  parts = processMessageEvent("tool:start", { agent_id: "child", tool: "execute", args: { command: "pending" } }, parts, "", [], depth, [], false).parts;
  parts = processMessageEvent("tool:result", { agent_id: "child", tool: "read_file", tool_call_id: "received-id", result: "received" }, parts, "", [], depth, [], false).parts;
  const tools = depth ? (parts[0] as SubagentPart).parts : parts;
  expect(tools).toEqual([
    expect.objectContaining({ name: "execute", isPending: true }),
    expect.objectContaining({ name: "read_file", id: "received-id", result: "received", isPending: false }),
  ]);
});

test.each([true, false])("results render without starts and survive late starts (streaming: %s)", (streaming) => {
  let parts: MessagePart[] = [];
  const emit = (event: string, data: Record<string, unknown> = {}) => {
    parts = processMessageEvent(event, { agent_id: "child", tool: "read_file", tool_call_id: "stable-call", ...data }, parts, "", [], 1, [], streaming).parts;
  };
  emit("agent:call");
  emit("tool:args:chunk", { tool_call_id: "provider-call", content: '{"file_path":"a.py"}' });
  emit("tool:result", { result: "file contents" });
  emit("tool:start", { args: { file_path: "a.py" } });
  emit("tool:args:chunk", { tool_call_id: "provider-call", content: "late delta" });
  const tools = (parts[0] as SubagentPart).parts;
  expect(tools).toHaveLength(1);
  expect(tools?.[0]).toMatchObject({ id: "stable-call", result: "file contents", isPending: false });
});

test.each([true, false])("late results replace interrupted tool state inside completed children (streaming: %s)", (streaming) => {
  let parts: MessagePart[] = [];
  const emit = (event: string, data: Record<string, unknown> = {}) => {
    parts = processMessageEvent(event, { agent_id: "child", tool: "execute", tool_call_id: "call", args: {}, ...data }, parts, "", [], 1, [], streaming).parts;
  };
  emit("agent:call");
  emit("tool:start");
  emit("agent:result", { result: "report", success: true });
  emit("tool:result", { result: "actual output" });
  expect((parts[0] as SubagentPart).parts?.[0]).toMatchObject({ result: "actual output", isPending: false, cancelled: false });
  emit("tool:start", { tool_call_id: "late-start" });
  expect((parts[0] as SubagentPart).parts?.[1]).toMatchObject({ id: "late-start", isPending: false });
  emit("tool:result", { tool_call_id: "late-start", result: "late output" });
  expect((parts[0] as SubagentPart).parts?.[1]).toMatchObject({ result: "late output", isPending: false, cancelled: false });
  expect(parts).toHaveLength(1);
});

test("a result without either agent or tool start remains renderable", () => {
  const result = processMessageEvent("tool:result", { agent_id: "missing-child", tool: "read_file", tool_call_id: "missing-start", result: "received" }, [], "", [], 1, [], false);
  expect(result.parts).toEqual([expect.objectContaining({ type: "tool", id: "missing-start", result: "received", isPending: false })]);
});

test("legacy main-agent results render even without a call ID or start", () => {
  const result = processMessageEvent("tool:result", { tool: "read_file", result: "received" }, [], "", [], 0, [], false);
  expect(result.parts).toEqual([expect.objectContaining({ type: "tool", name: "read_file", result: "received", isPending: false })]);
});

test.each([true, false])("late drafts and starts cannot reopen a completed child (streaming: %s)", (streaming) => {
  let parts: MessagePart[] = [];
  for (const [event, data] of [
    ["agent:call", {}],
    ["agent:result", { result: "report", success: true }],
    ["tool:args:chunk", { tool: "read_file", tool_call_id: "provider-call", content: '{"file_path":"a.py"}' }],
    ["tool:start", { tool: "read_file", tool_call_id: "execution-call", args: { file_path: "a.py" } }],
  ] as const) parts = processMessageEvent(event, { agent_id: "child", ...data }, parts, "", [], 1, [], streaming).parts;
  expect((parts[0] as SubagentPart).parts).toEqual([expect.objectContaining({ id: "execution-call", isPending: false })]);
});

test("a child report renders even when its agent call was missed", () => {
  const result = processMessageEvent("agent:result", { agent_id: "missing-child", result: "completed report", success: true }, [], "", [], 1, [], false);
  expect(result.parts).toEqual([expect.objectContaining({ type: "subagent", result: "completed report", isPending: false, status: "complete" })]);
});

test("parent completion settles children and tools whose result events never arrived", () => {
  let parts: MessagePart[] = [];
  for (const [event, data, depth] of [
    ["agent:call", { agent_id: "child" }, 1],
    ["tool:start", { agent_id: "child", tool: "execute", tool_call_id: "pending", args: {} }, 1],
    ["done", {}, 0],
  ] as const) parts = processMessageEvent(event, data, parts, "", [], depth, [], true).parts;
  expect(parts[0]).toMatchObject({ isPending: false });
  expect((parts[0] as SubagentPart).parts?.[0]).toMatchObject({ isPending: false });
});

test.each([true, false])("parallel subagents keep their own streamed arguments and results (streaming: %s)", (streaming) => {
  let parts: MessagePart[] = [];
  const emit = (event: string, agent: string, data: Record<string, unknown> = {}) => {
    parts = processMessageEvent(event, { agent_id: agent, ...data }, parts, "", [], 1, [], streaming).parts;
  };
  for (const agent of ["child-a", "child-b"]) {
    emit("agent:call", agent, { input: "Review", status: "running" });
    emit("tool:args:chunk", agent, { tool: "read_file", tool_call_id: "provider-shared", content: '{"file_path":"' });
  }
  emit("tool:args:chunk", "child-a", { tool: "read_file", tool_call_id: "provider-shared", content: 'a.py"}' });
  emit("tool:args:chunk", "child-b", { tool: "read_file", tool_call_id: "provider-shared", content: 'b.py"}' });
  expect((parts[0] as SubagentPart).parts?.[0]).toMatchObject({ args: { partial: '{"file_path":"a.py"}' } });
  expect((parts[1] as SubagentPart).parts?.[0]).toMatchObject({ args: { partial: '{"file_path":"b.py"}' } });
  // Execution callbacks have stable IDs, unlike the provider's streamed IDs.
  for (const agent of ["child-b", "child-a"]) {
    emit("tool:start", agent, { tool: "read_file", tool_call_id: `run-${agent}`, args: { file_path: `${agent}.py` } });
    emit("tool:result", agent, { tool: "read_file", tool_call_id: `run-${agent}`, result: `${agent} result`, success: true });
  }
  for (const [index, agent] of ["child-a", "child-b"].entries()) {
    const tools = (parts[index] as SubagentPart).parts;
    expect(tools).toHaveLength(1);
    expect(tools?.[0]).toMatchObject({ id: `run-${agent}`, result: `${agent} result`, isPending: false });
  }
});

test("a child's result cannot settle an unrelated legacy parent tool", () => {
  let parts: MessagePart[] = [{ type: "tool", name: "execute", args: {}, isPending: true }];
  for (const [event, data] of [
    ["agent:call", { agent_id: "child" }],
    ["tool:start", { agent_id: "child", tool: "read_file", tool_call_id: "child-call", args: {} }],
    ["tool:result", { agent_id: "child", tool: "read_file", tool_call_id: "child-call", result: "child result" }],
  ] as const) {
    parts = processMessageEvent(event, data, parts, "", [], 1, [], true).parts;
  }
  expect(parts[0]).toMatchObject({ isPending: true });
  expect((parts[1] as SubagentPart).parts?.[0]).toMatchObject({ result: "child result", isPending: false });
});

test.each([true, false])("confirmation replay cannot take over a sibling's identical tool (streaming: %s)", (streaming) => {
  let parts: MessagePart[] = [];
  const emit = (event: string, agent: string, id?: string) => {
    parts = processMessageEvent(event, { agent_id: agent, tool: "execute", tool_call_id: id, args: { command: "pwd" }, result: "ok" }, parts, "", [], 1, [], streaming).parts;
  };
  for (const agent of ["child-a", "child-b"]) emit("agent:call", agent);
  emit("tool:start", "child-a", "a-first");
  emit("tool:start", "child-b", "b-first");
  emit("tool:start", "child-b", "b-resumed");
  emit("tool:result", "child-b", "b-resumed");
  emit("tool:result", "child-a", "a-first");
  expect((parts[0] as SubagentPart).parts).toEqual([expect.objectContaining({ id: "a-first", isPending: false, result: "ok" })]);
  expect((parts[1] as SubagentPart).parts).toEqual([expect.objectContaining({ id: "b-resumed", isPending: false, result: "ok" })]);
});
