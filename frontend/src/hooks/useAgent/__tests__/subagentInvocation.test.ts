import { expect, test } from "vitest";
import type { Message } from "../../../types";
import { processMessageEvent } from "../eventProcessor";
import { HistoryPartReplay, HistoryReplayStack } from "../historyReplayParts";
import type { SubagentStackItem } from "../types";

test.each([false, true])(
  "same-agent parallel results pair by invocation (history: %s)",
  (history) => {
    const message: Message = {
      id: "m",
      role: "assistant",
      content: "",
      timestamp: new Date(0),
      parts: [],
    };
    const replay = new HistoryPartReplay();
    const events = [
      ["agent:call", "first", "work one"],
      ["agent:call", "second", "work two"],
      ["agent:result", "first", "answer one"],
      ["agent:result", "second", "answer two"],
      ["agent:call", "first", "duplicate replay"],
      ["agent:result", "first", "answer one replay"],
      ["agent:result", "unknown", "orphan answer"],
    ];
    for (const [type, agent_call_id, value] of events) {
      const data = {
        agent_id: "worker",
        agent_call_id,
        depth: 1,
        input: value,
        result: value,
      };
      if (history) expect(replay.replay(message, type, data)).toBe(true);
      else
        message.parts = processMessageEvent(
          type,
          data,
          message.parts || [],
          "",
          [],
          1,
          [],
          true,
        ).parts;
    }
    replay.flush(message);
    expect(message.parts).toMatchObject([
      {
        agent_call_id: "first",
        input: "work one",
        result: "answer one replay",
        isPending: false,
      },
      {
        agent_call_id: "second",
        input: "work two",
        result: "answer two",
        isPending: false,
      },
      { agent_call_id: "unknown", result: "orphan answer", isPending: false },
    ]);
  },
);

test("history stack removes the exact invocation without removing its parallel sibling", () => {
  const output: SubagentStackItem[] = [];
  const stack = new HistoryReplayStack(output);
  for (const agent_call_id of ["first", "second", "second"])
    stack.add({ agent_id: "worker", agent_call_id, depth: 1, message_id: "m" });
  stack.remove("worker", "m", "second");
  stack.flush();
  expect(output).toEqual([
    { agent_id: "worker", agent_call_id: "first", depth: 1, message_id: "m" },
  ]);
});

test.each([false, true])(
  "a newer confirmed restart revives a cancelled child without replaying old calls (history: %s)",
  (history) => {
    const message: Message = {
      id: "m",
      role: "assistant",
      content: "",
      timestamp: new Date(0),
      parts: [],
    };
    const replay = new HistoryPartReplay();
    const emit = (type: string, data: Record<string, unknown>) => {
      const event = {
        agent_id: "worker",
        agent_call_id: "same-call",
        depth: 1,
        ...data,
      };
      if (history) {
        replay.replay(message, type, event);
        replay.flush(message);
      } else
        message.parts = processMessageEvent(
          type,
          event,
          message.parts || [],
          "",
          [],
          1,
          [],
          true,
        ).parts;
    };
    emit("agent:call", {
      status: "running",
      timestamp: "2026-11-07T00:00:00Z",
      input: "Original assignment",
    });
    emit("agent:result", {
      status: "cancelled",
      success: false,
      error: "Cancelled",
      timestamp: "2026-11-07T00:01:00Z",
    });
    emit("agent:call", {
      status: "running",
      timestamp: "2026-11-07T00:00:00Z",
    });
    expect(message.parts?.[0]).toMatchObject({
      status: "cancelled",
      isPending: false,
    });
    emit("agent:call", { status: "running" });
    expect(message.parts?.[0]).toMatchObject({
      status: "cancelled",
      isPending: false,
    });
    emit("agent:call", {
      status: "running",
      timestamp: "2026-11-07T00:02:00Z",
    });
    expect(message.parts).toHaveLength(1);
    expect(message.parts?.[0]).toMatchObject({
      status: "running",
      isPending: true,
      input: "Original assignment",
      error: undefined,
      completedAt: undefined,
    });
  },
);
