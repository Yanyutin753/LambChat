import { processMessageEvent } from "../eventProcessor";

test("handoff remains a single milestone when replayed", () => {
  const data = {
    stage: "agent_handoff",
    target_agent_id: "search",
    timestamp: "2026-10-17T10:00:00Z",
  };
  const first = processMessageEvent("status", data, [], "", [], 0, [], true);
  expect(first.parts).toEqual([
    { type: "agentHandoff", agentId: "search", timestamp: data.timestamp },
  ]);
  const replay = processMessageEvent(
    "status",
    data,
    first.parts,
    "",
    [],
    0,
    [],
    false,
  );
  expect(replay.parts).toEqual(first.parts);
  expect(replay.content).toBe("");
});

test("handoff does not remove earlier text or tool results", () => {
  const first = processMessageEvent(
    "status",
    { stage: "agent_handoff", target_agent_id: "search" },
    [{ type: "text", content: "已有上下文" }],
    "已有上下文",
    [],
    0,
    [],
    true,
  );
  expect(first.parts).toHaveLength(2);
  expect(first.parts[0]).toEqual({ type: "text", content: "已有上下文" });
  expect(first.content).toBe("已有上下文");
});
