import { expect, test } from "vitest";

import type { Message } from "../../../../types";
import { syncSubagentPanelStore } from "../subagentPanelState";
import { subagentPanelStore } from "../subagentPanelStore";

function assistantMessage(parts: Message["parts"]): Message {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "",
    timestamp: new Date("2026-08-29T10:00:00.000Z"),
    parts,
  };
}

const runningSubagent = {
  type: "subagent" as const,
  agent_id: "researcher",
  agent_name: "Researcher",
  input: "find it",
  depth: 1,
  isPending: true,
  status: "running" as const,
  parts: [
    {
      type: "tool" as const,
      id: "nested-tool",
      name: "search",
      args: { q: "x" },
      isPending: true,
    },
  ],
  startedAt: 1_750_000_000_000,
};

test("syncSubagentPanelStore feeds the store from the full message list", () => {
  syncSubagentPanelStore([
    assistantMessage([
      runningSubagent,
      {
        type: "subagent" as const,
        agent_id: "writer",
        agent_name: "Writer",
        input: "write it",
        depth: 1,
        isPending: false,
        success: true,
        status: "complete" as const,
        result: "done",
        parts: [],
        startedAt: 1_750_000_001_000,
        completedAt: 1_750_000_002_000,
      },
    ]),
  ]);

  expect(subagentPanelStore.get("researcher")).toMatchObject({
    agentId: "researcher",
    agentName: "Researcher",
    isPending: true,
    status: "running",
    parts: [{ type: "tool", id: "nested-tool" }],
  });
  expect(subagentPanelStore.get("writer")).toMatchObject({
    agentId: "writer",
    status: "complete",
    success: true,
  });

  subagentPanelStore.delete("researcher");
  subagentPanelStore.delete("writer");
});

test("syncSubagentPanelStore keeps an open panel live across streaming updates", () => {
  syncSubagentPanelStore([assistantMessage([runningSubagent])]);

  const notifications: string[] = [];
  const unsubscribe = subagentPanelStore.subscribe("researcher", () =>
    notifications.push("changed"),
  );

  syncSubagentPanelStore([
    assistantMessage([
      {
        ...runningSubagent,
        isPending: false,
        success: true,
        status: "complete",
        result: "all done",
      },
    ]),
  ]);

  expect(subagentPanelStore.get("researcher")).toMatchObject({
    status: "complete",
    result: "all done",
  });
  expect(notifications).toEqual(["changed"]);
  unsubscribe();

  subagentPanelStore.delete("researcher");
});

test("syncSubagentPanelStore syncs nested subagents recursively", () => {
  syncSubagentPanelStore([
    assistantMessage([
      {
        ...runningSubagent,
        parts: [
          {
            type: "subagent" as const,
            agent_id: "nested-agent",
            agent_name: "Nested",
            input: "inner",
            depth: 2,
            isPending: true,
            status: "running" as const,
            parts: [],
            startedAt: 1_750_000_000_500,
          },
        ],
      },
    ]),
  ]);

  expect(subagentPanelStore.get("nested-agent")).toMatchObject({
    agentId: "nested-agent",
    isPending: true,
  });

  subagentPanelStore.delete("researcher");
  subagentPanelStore.delete("nested-agent");
});

test("subagentPanelStore clear() drops all entries and notifies subscribers", () => {
  syncSubagentPanelStore([assistantMessage([runningSubagent])]);

  const notifications: string[] = [];
  const unsubscribe = subagentPanelStore.subscribe("researcher", () =>
    notifications.push("cleared"),
  );

  subagentPanelStore.clear();

  expect(subagentPanelStore.get("researcher")).toBeUndefined();
  expect(notifications).toEqual(["cleared"]);
  unsubscribe();
});
