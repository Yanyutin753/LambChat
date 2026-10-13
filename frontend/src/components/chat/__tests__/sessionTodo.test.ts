import { expect, test } from "vitest";
import type { Message, TodoPart } from "../../../types";
import { getSessionTodo } from "../sessionTodo";

const todo: TodoPart = { type: "todo", items: [{ content: "Verify", status: "in_progress" }] };
const message = (overrides: Partial<Message>): Message => ({
  id: "m", role: "assistant", content: "", timestamp: new Date(), ...overrides,
});

test("selects the latest checklist in the current run without merging older tasks", () => {
  const updated: TodoPart = { type: "todo", items: [{ content: "Ship", status: "pending" }] };
  expect(getSessionTodo([
    message({ runId: "old", parts: [todo] }),
    message({ runId: "current", parts: [todo, updated] }),
    message({ runId: "current", parts: [{ type: "text", content: "Still working" }] }),
  ], "current")).toBe(updated);
});

test("does not show the previous run's checklist while a new run starts", () => {
  expect(getSessionTodo([message({ runId: "old", parts: [todo] })], "new")).toBeNull();
});

test("a stale current run id cannot expose a previous turn's checklist", () => {
  expect(getSessionTodo([
    message({ runId: "old", parts: [todo] }),
    message({ runId: "new", parts: [{ type: "text", content: "New response" }] }),
  ], "old")).toBeNull();
});

test("keeps a completed checklist available after the run ends", () => {
  const done: TodoPart = { type: "todo", items: [{ content: "Verify", status: "completed" }] };
  expect(getSessionTodo([message({ parts: [done] })])).toBe(done);
});

test("stops at a new user turn when restored messages have no run ids", () => {
  expect(getSessionTodo([
    message({ parts: [todo] }), message({ role: "user" }), message({}),
  ])).toBeNull();
});

test("does not expose a nested subagent checklist as the main task", () => {
  expect(getSessionTodo([message({ parts: [{ type: "subagent", agent_id: "child", agent_name: "Research", input: "", depth: 1, parts: [todo] }] })])).toBeNull();
});

test("an empty latest checklist clears the previous summary", () => {
  expect(getSessionTodo([message({ parts: [todo, { type: "todo", items: [] }] })])).toBeNull();
});
