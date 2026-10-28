import type { MessagePart } from "../../../types";
import type { EventData, HistoryEvent } from "../types";
import { processMessageEvent } from "../eventProcessor";
import { reconstructMessagesFromEvents } from "../historyLoader";

const events: Array<[string, EventData]> = [
  [
    "tool:args:chunk",
    {
      tool: "task",
      tool_call_id: "first",
      agent_id: "search",
      content: '{"description":"Review',
    },
  ],
  [
    "tool:args:chunk",
    {
      tool: "task",
      tool_call_id: "second",
      agent_id: "search",
      content: '{"description":"Research',
    },
  ],
  [
    "agent:call",
    {
      agent_id: "child-2",
      agent_call_id: "second",
      agent_name: "Researcher",
      input: "Research",
      depth: 1,
      status: "queued",
    },
  ],
  [
    "agent:call",
    {
      agent_id: "child-1",
      agent_call_id: "first",
      agent_name: "Reviewer",
      input: "Review",
      depth: 1,
      status: "queued",
    },
  ],
  [
    "agent:call",
    {
      agent_id: "child-1",
      agent_call_id: "first",
      agent_name: "Reviewer",
      input: "Review",
      depth: 1,
      status: "running",
    },
  ],
];

test.each(["live", "history"])(
  "%s creation replaces only its own draft and keeps assignment order",
  (mode) => {
    let parts: MessagePart[] = [];
    if (mode === "live") {
      for (const [type, data] of events)
        parts = processMessageEvent(
          type,
          data,
          parts,
          "",
          [],
          data.depth || 0,
          [],
          true,
        ).parts;
    } else {
      const history = [
        ["user:message", { content: "Delegate" }],
        ...events,
      ].map(([type, data], i) => ({
        event_type: type,
        data,
        run_id: "run",
        timestamp: new Date(1700000000000 + i * 1000).toISOString(),
      })) as HistoryEvent[];
      parts = reconstructMessagesFromEvents(history, new Set(), {
        activeSubagentStack: [],
      }).find((message) => message.role === "assistant")!.parts!;
    }
    expect(parts).toHaveLength(2);
    expect(parts).toMatchObject([
      {
        type: "subagent",
        agent_id: "child-1",
        agent_call_id: "first",
        status: mode === "live" ? "running" : "cancelled",
      },
      {
        type: "subagent",
        agent_id: "child-2",
        agent_call_id: "second",
        status: mode === "live" ? "queued" : "cancelled",
      },
    ]);
  },
);
