import assert from "node:assert/strict";
import test from "node:test";
import {
  createSubagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore.ts";

function createData(agentId: string): SubagentPanelData {
  return {
    agentId,
    agentName: `agent-${agentId}`,
    input: `input-${agentId}`,
    status: "running",
  };
}

test("notifies only listeners subscribed to the updated agent id", () => {
  const store = createSubagentPanelStore();
  const calls: string[] = [];

  store.subscribe("agent-a", () => calls.push("a"));
  store.subscribe("agent-b", () => calls.push("b"));

  store.set(createData("agent-a"));

  assert.deepEqual(calls, ["a"]);
});

test("notifies listeners when an agent entry is deleted", () => {
  const store = createSubagentPanelStore();
  const calls: string[] = [];

  store.set(createData("agent-a"));
  store.subscribe("agent-a", () => calls.push("a"));

  store.delete("agent-a");

  assert.deepEqual(calls, ["a"]);
  assert.equal(store.get("agent-a"), undefined);
});

test("tracks current store size for lightweight observability", () => {
  const store = createSubagentPanelStore();

  store.set(createData("agent-a"));
  store.set(createData("agent-b"));
  store.delete("agent-a");

  assert.equal(store.size(), 1);
});
