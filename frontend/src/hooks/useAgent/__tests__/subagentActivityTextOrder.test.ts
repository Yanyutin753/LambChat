import { expect, test } from "vitest";
import type { MessagePart, SubagentPart } from "../../../types";
import type { EventData, HistoryEvent } from "../types";
import { processMessageEvent } from "../eventProcessor";
import { reconstructMessagesFromEvents } from "../historyLoader";

function replay(mode: string, frames: [string, EventData][]): SubagentPart[] {
  let parts: MessagePart[] = [];
  if (mode === "live") {
    for (const [event, data] of frames) {
      parts = processMessageEvent(
        event,
        data,
        parts,
        "",
        [],
        data.depth ?? 0,
        [],
        true,
      ).parts;
    }
  } else {
    const events: HistoryEvent[] = [
      { event_type: "user:message", data: { content: "Review" } },
      ...frames.map(([event_type, data]) => ({ event_type, data })),
    ].map((event, index) => ({
      ...event,
      run_id: "parent",
      timestamp: new Date(1700000000000 + index).toISOString(),
    }));
    const messages = reconstructMessagesFromEvents(events, new Set(), {
      activeSubagentStack: [],
    });
    parts =
      messages.find((message) => message.role === "assistant")?.parts ?? [];
  }
  return parts.filter((part): part is SubagentPart => part.type === "subagent");
}

test.each(["live", "history"])(
  "%s places a late-confirmed child text prefix before its pending tool",
  (mode) => {
    const frames: [string, EventData][] = [
      ["agent:call", { agent_id: "child", agent_name: "Reviewer", depth: 1 }],
      [
        "message:chunk",
        { agent_id: "child", depth: 1, content: "Review ", text_id: "model" },
      ],
      [
        "tool:args:chunk",
        {
          agent_id: "child",
          depth: 1,
          tool: "execute",
          tool_call_id: "call",
          content: "{}",
        },
      ],
      [
        "message:chunk",
        { agent_id: "child", depth: 1, content: "[Act", text_id: "model" },
      ],
    ];
    const child = replay(mode, frames)[0];
    expect(child?.parts).toEqual([
      expect.objectContaining({ type: "text", content: "Review [Act" }),
      expect.objectContaining({ type: "tool", id: "call", argsPartial: true }),
    ]);
  },
);

test.each(["live", "history"])(
  "%s keeps late text inside its parallel child and after already-started tools",
  (mode) => {
    const frames: [string, EventData][] = [];
    for (const child of ["a", "b"]) {
      frames.push(
        ["agent:call", { agent_id: child, depth: 1 }],
        ["message:chunk", { agent_id: child, depth: 1, content: `${child} ` }],
        [
          "tool:args:chunk",
          {
            agent_id: child,
            depth: 1,
            tool: "execute",
            tool_call_id: "shared-provider-id",
            content: "{}",
          },
        ],
      );
    }
    for (const child of ["b", "a"]) {
      frames.push(
        ["message:chunk", { agent_id: child, depth: 1, content: "[Act" }],
        [
          "tool:start",
          {
            agent_id: child,
            depth: 1,
            tool: "execute",
            tool_call_id: `real-${child}`,
            args: {},
          },
        ],
        [
          "message:chunk",
          { agent_id: child, depth: 1, content: `${child} after tool` },
        ],
      );
    }
    const children = replay(mode, frames);
    expect(children).toHaveLength(2);
    for (const child of children) {
      expect(child.parts).toEqual([
        expect.objectContaining({
          type: "text",
          content: `${child.agent_id} [Act`,
        }),
        expect.objectContaining({ type: "tool", id: `real-${child.agent_id}` }),
        expect.objectContaining({
          type: "text",
          content: `${child.agent_id} after tool`,
        }),
      ]);
    }
  },
);

test.each(["live", "history"])(
  "%s places the first late-confirmed reasoning before its pending tool",
  (mode) => {
    const child = replay(mode, [
      ["agent:call", { agent_id: "child", depth: 1 }],
      [
        "tool:args:chunk",
        {
          agent_id: "child",
          depth: 1,
          tool: "execute",
          tool_call_id: "call",
          content: "{}",
        },
      ],
      [
        "thinking",
        { agent_id: "child", depth: 1, content: "[Act", thinking_id: "model" },
      ],
    ])[0];
    expect(child.parts).toEqual([
      expect.objectContaining({ type: "thinking", content: "[Act" }),
      expect.objectContaining({ type: "tool", id: "call", argsPartial: true }),
    ]);
  },
);

test.each(["live", "history"])(
  "%s places root reasoning before argument drafts consistently with children",
  (mode) => {
    const frames: [string, EventData][] = [
      [
        "tool:args:chunk",
        { tool: "execute", tool_call_id: "call", content: "{}" },
      ],
      ["thinking", { content: "[Act", thinking_id: "model" }],
    ];
    let parts: MessagePart[] = [];
    if (mode === "live") {
      for (const [event, data] of frames) {
        parts = processMessageEvent(
          event,
          data,
          parts,
          "",
          [],
          0,
          [],
          true,
        ).parts;
      }
    } else {
      const events = [
        { event_type: "user:message", data: { content: "Review" } },
        ...frames.map(([event_type, data]) => ({ event_type, data })),
      ].map((event, index) => ({
        ...event,
        run_id: "parent",
        timestamp: new Date(1700000000000 + index).toISOString(),
      }));
      parts =
        reconstructMessagesFromEvents(events, new Set(), {
          activeSubagentStack: [],
        }).find((message) => message.role === "assistant")?.parts ?? [];
    }
    expect(parts).toEqual([
      expect.objectContaining({ type: "thinking", content: "[Act" }),
      expect.objectContaining({ type: "tool", id: "call", argsPartial: true }),
    ]);
  },
);

test("history retains hundreds of consecutive late reasoning parts and the pending tool", () => {
  const contents = Array.from(
    { length: 256 },
    (_, index) => `thought-${index}`,
  );
  const events = [
    { event_type: "user:message", data: { content: "Review" } },
    {
      event_type: "tool:args:chunk",
      data: { tool: "execute", tool_call_id: "call", content: "{}" },
    },
    ...contents.map((content) => ({
      event_type: "thinking",
      data: { content, thinking_id: content },
    })),
  ].map((event, index) => ({
    ...event,
    run_id: "parent",
    timestamp: new Date(1700000000000 + index).toISOString(),
  }));
  const parts =
    reconstructMessagesFromEvents(events, new Set(), {
      activeSubagentStack: [],
    }).find((message) => message.role === "assistant")?.parts ?? [];
  expect(
    parts
      .filter((part) => part.type === "thinking")
      .map((part) => part.content),
  ).toEqual(contents);
  expect(parts).toHaveLength(257);
  expect(parts[256]).toMatchObject({
    type: "tool",
    id: "call",
    argsPartial: true,
  });
});
