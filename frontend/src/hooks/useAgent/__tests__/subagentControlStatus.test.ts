import { describe, expect, test } from "vitest";
import { processMessageEvent } from "../eventProcessor";
import type { MessagePart } from "../../../types";
import { addPartToDepth, createSubagentPart, updateSubagentResult } from "../messageParts";

describe("persistent subagent status survives event replay", () => {
  test("starting a queued child updates its existing block", () => {
    const queued = createSubagentPart("agent-1", "Reviewer", "work", 1, undefined, undefined, "queued");
    const running = createSubagentPart("agent-1", "Reviewer", "work", 1);
    const result = addPartToDepth([queued], running, 1, [], "agent-1");
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({status: "running"});
  });
  test.each(["cancelled", "timed_out", "waiting_human"] as const)("retains %s instead of mapping to failed", (status) => {
    const part = createSubagentPart("agent-1", "Reviewer", "work", 1);
    const result = updateSubagentResult([part], "agent-1", "", false, 1, "", undefined, status);
    expect(result[0]).toMatchObject({ status, isPending: status === "waiting_human" });
  });
  test("queued child is visible without claiming it is running", () => {
    const part = createSubagentPart("agent-1", "Reviewer", "work", 1, undefined, undefined, "queued");
    expect(part.status).toBe("queued");
  });
});


test.each([true, false])("approval resume keeps one child card through reducer (streaming: %s)", (isStreaming) => {
  let parts: MessagePart[] = [];
  const events = [
    { type: "agent:call", status: "queued" },
    { type: "agent:call", status: "running" },
    { type: "agent:result", status: "waiting_human" },
    { type: "agent:call", status: "queued" },
    { type: "agent:call", status: "running" },
    { type: "agent:result", status: "complete" },
  ];
  for (const event of events) {
    parts = processMessageEvent(event.type, {
      agent_id: "agent-1", agent_name: "Reviewer", input: "work",
      status: event.status, success: event.status === "complete",
      result: event.status === "complete" ? "approved-once" : "",
      timestamp: "2026-10-13T00:00:00Z",
    }, parts, "", [], 1, [], isStreaming).parts;
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({ status: event.status, isPending: event.status !== "complete" });
    if (event.status !== "complete") expect(parts[0]).not.toHaveProperty("completedAt", expect.any(Number));
  }
  expect(parts[0]).toMatchObject({ result: "approved-once", success: true });
});


test.each([true, false])("waiting approval stays resumable after done (streaming: %s)", (isStreaming) => {
  let parts: MessagePart[] = [createSubagentPart("agent-1", "Reviewer", "work", 1)];
  parts = processMessageEvent("agent:result", { agent_id: "agent-1", status: "waiting_human", success: false }, parts, "", [], 1, [], isStreaming).parts;
  parts = processMessageEvent("done", {}, parts, "", [], 0, [], isStreaming).parts;
  expect(parts[0]).toMatchObject({ status: "waiting_human", isPending: true });
  parts = processMessageEvent("agent:call", { agent_id: "agent-1", status: "running" }, parts, "", [], 1, [], isStreaming).parts;
  expect(parts).toHaveLength(1);
  expect(parts[0]).toMatchObject({ status: "running", isPending: true });
});


test.each([true, false])("timeout remains a timeout after parent completion (streaming: %s)", (isStreaming) => {
  let parts: MessagePart[] = [createSubagentPart("agent-1", "Reviewer", "work", 1)];
  parts = processMessageEvent("agent:result", {
    agent_id: "agent-1", status: "timed_out", success: false,
    error: "Subagent execution deadline exceeded.",
  }, parts, "", [], 1, [], isStreaming).parts;
  parts = processMessageEvent("done", {}, parts, "", [], 0, [], isStreaming).parts;
  expect(parts[0]).toMatchObject({ status: "timed_out", isPending: false, cancelled: false });
});


test.each(["complete", "timed_out"] as const)("%s child closes unfinished tools before parent completes", (status) => {
  const child = createSubagentPart("agent-1", "Reviewer", "work", 1);
  child.parts = [
    { type: "tool", id: "executed", name: "web_fetch", args: { url: "https://example.com" }, isPending: true },
    { type: "tool", id: "draft", name: "read_file", args: { partial: '{"file_path":' }, argsPartial: true, isPending: true },
    { type: "tool", id: "done", name: "web_search", args: {}, result: "found", success: true, isPending: false },
  ];
  const parts = processMessageEvent("agent:result", {
    agent_id: "agent-1", status, success: status === "complete",
  }, [child], "", [], 1, [], true).parts;
  expect(parts[0]).toMatchObject({ status, isPending: false, parts: [
    { id: "executed", isPending: false, cancelled: true },
    { id: "done", result: "found", success: true },
  ] });
});


test("recovered terminal result gets a child block in a fresh parent turn", () => {
  let parts: MessagePart[] = [];
  for (const type of ["agent:call", "agent:result", "done"]) {
    parts = processMessageEvent(type, {
      agent_id: "saved-child", agent_name: "Reviewer", input: "Original assignment",
      status: "timed_out", result: "Partial result: saved tool contents",
      success: false, error: "deadline",
    }, parts, "", [], type === "done" ? 0 : 1, [], true).parts;
  }
  expect(parts).toHaveLength(1);
  expect(parts[0]).toMatchObject({status: "timed_out", isPending: false, cancelled: false, result: "Partial result: saved tool contents"});
});
