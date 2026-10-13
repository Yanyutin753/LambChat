import {
  createSubagentPanelStore,
  type SubagentPanelData,
} from "../subagentPanelStore.ts";

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

  expect(calls).toEqual(["a"]);
});

test("notifies listeners when an agent entry is deleted", () => {
  const store = createSubagentPanelStore();
  const calls: string[] = [];

  store.set(createData("agent-a"));
  store.subscribe("agent-a", () => calls.push("a"));

  store.delete("agent-a");

  expect(calls).toEqual(["a"]);
  expect(store.get("agent-a")).toBe(undefined);
});

test("tracks current store size for lightweight observability", () => {
  const store = createSubagentPanelStore();

  store.set(createData("agent-a"));
  store.set(createData("agent-b"));
  store.delete("agent-a");

  expect(store.size()).toBe(1);
});

test("same-length streaming parts refresh an open conversation", () => {
  const store = createSubagentPanelStore();
  store.set({
    ...createData("agent-a"),
    parts: [{ type: "text", content: "Partial" }],
  });
  let notifications = 0;
  store.subscribe("agent-a", () => notifications++);
  store.set({
    ...createData("agent-a"),
    parts: [{ type: "text", content: "Partial reply grew" }],
  });
  expect(notifications).toBe(1);
});
