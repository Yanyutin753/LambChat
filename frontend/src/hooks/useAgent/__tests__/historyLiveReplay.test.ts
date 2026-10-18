import { expect, test, vi } from "vitest";
import type { Message } from "../../../types";
import type { EventData, HistoryEvent } from "../types";
import * as eventProcessor from "../eventProcessor";
import { handleStreamEvent, type EventHandlerContext } from "../eventHandlers";
import { createSubagentPart } from "../messageParts";
import {
  historyCoverage,
  mergeHistoryTraceViews,
  replayHistoryJournal,
  type HistoryJournalEntry,
} from "../historyLiveReplay";
import {
  reconstructMessagesFromEvents,
  extractGoalsByRunFromEvents,
} from "../historyLoader";

const effects = vi.hoisted(() => ({ markRead: vi.fn(), mutation: vi.fn() }));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { markRead: effects.markRead },
}));
vi.mock(
  "../../../components/chat/ChatMessage/items/toolMutationEvents",
  () => ({ dispatchToolMutationRefresh: effects.mutation }),
);

const time = "2026-10-15T00:00:00Z";
const event = (
  id: string,
  type: string,
  data: EventData,
  trace = "t",
): HistoryEvent => ({
  id,
  event_type: type,
  run_id: "run",
  trace_id: trace,
  timestamp: time,
  data,
});
const user = event("u", "user:message", {
  content: "question",
  _source_id: "user",
});
const entry = (value: HistoryEvent): HistoryJournalEntry => ({
  event: value,
  messageId: "run",
});
const currentAssistant = (streaming = true): Message => ({
  id: "run",
  role: "assistant",
  runId: "run",
  content: "ABCD",
  parts: [],
  timestamp: new Date(time),
  isStreaming: streaming,
});

function replay(
  stored: HistoryEvent[],
  live: HistoryEvent[],
  current = [currentAssistant()],
) {
  return replayHistoryJournal({
    messages: reconstructMessagesFromEvents(stored, new Set(), {
      activeSubagentStack: [],
    }),
    goals: {},
    events: live.map(entry),
    covered: historyCoverage(stored),
    optimisticUsers: new Map(),
    currentMessages: current,
  });
}

test("compacted s1 coverage of s1/s2/s3 removes journal s2/s3 but retains same-timestamp s4 once", () => {
  const compacted = event("stored-first", "message:chunk", {
    content: "ABC",
    _source_id: "s1",
    _source_ids: ["s1", "s2", "s3"],
  });
  const result = replay(
    [user, compacted],
    [
      event("redis-2", "message:chunk", { content: "B", _source_id: "s2" }),
      event("redis-3", "message:chunk", { content: "C", _source_id: "s3" }),
      event("redis-4", "message:chunk", { content: "D", _source_id: "s4" }),
    ],
  );
  expect(
    result.messages.find((message) => message.role === "assistant")?.content,
  ).toBe("ABCD");
});

test("whole trace replacement handles source supersets, changed compaction and legacy missing event ids", () => {
  const old = [
    { ...user, id: undefined, seq: 1 },
    { ...event("", "message:chunk", { content: "A" }), id: undefined, seq: 2 },
  ];
  const updated = [
    { ...user, id: undefined, seq: 1 },
    { ...event("", "message:chunk", { content: "AB" }), id: undefined, seq: 2 },
  ];
  const exactThenCursor = mergeHistoryTraceViews(old, updated);
  expect(exactThenCursor).toEqual(updated);
  expect(
    reconstructMessagesFromEvents(exactThenCursor, new Set(), {
      activeSubagentStack: [],
    }).find((message) => message.role === "assistant")?.content,
  ).toBe("AB");
  const full = event("", "message:chunk", {
    content: "ABC",
    _source_ids: ["a", "b", "c"],
  });
  const split = [
    event("a", "message:chunk", { content: "A", _source_id: "a" }),
    event("bc", "message:chunk", { content: "BC", _source_ids: ["b", "c"] }),
  ];
  expect(mergeHistoryTraceViews([full], split)).toEqual(split);
  expect(
    mergeHistoryTraceViews(
      [full],
      [event("a", "message:chunk", { content: "A", _source_id: "a" })],
    ),
  ).toEqual([full]);
  expect(mergeHistoryTraceViews([user, full], [user], new Set(["t"]))).toEqual([
    user,
    full,
  ]);
});

test("pure live replay stops reasoning at tool dispatch and retains drafts, approval and identity without repeating effects", () => {
  effects.mutation.mockClear();
  effects.markRead.mockClear();
  const timer = vi.spyOn(globalThis, "setTimeout");
  const identity = { seed: "persona", name: "Persona", avatar: "avatar.svg" };
  const live = [
    event("meta", "metadata", { assistant_identity: identity }),
    event("think", "thinking", { content: "working", thinking_id: "reason" }),
    event("args", "tool:args:chunk", {
      tool: "bash",
      tool_call_id: "draft",
      content: '{"cmd":',
    }),
    event("approval", "approval_required", {
      id: "approval",
      message: "confirm",
      fields: [],
    }),
    event("goal", "goal:end", {
      run_id: "run",
      goal: { objective: "task" },
      ended_at: time,
    }),
  ];
  try {
    const result = replay([user], live);
    const assistant = result.messages.find(
      (message) => message.role === "assistant",
    );
    expect(assistant?.isStreaming).toBe(true);
    expect(assistant?.assistantIdentity).toEqual(identity);
    expect(
      assistant?.parts?.find((part) => part.type === "thinking"),
    ).toMatchObject({
      content: "working",
      isStreaming: false,
      completedAt: Date.parse(time),
    });
    expect(
      assistant?.parts?.find(
        (part) => part.type === "tool" && part.id === "draft",
      ),
    ).toMatchObject({ argsPartial: true, isPending: true });
    expect(
      assistant?.parts?.find(
        (part) => part.type === "tool" && part.id === "approval",
      ),
    ).toMatchObject({ name: "ask_human", isPending: true });
    expect(effects.markRead).not.toHaveBeenCalled();
    expect(effects.mutation).not.toHaveBeenCalled();
    expect(timer).not.toHaveBeenCalled();
  } finally {
    timer.mockRestore();
  }
});

test("completed live-only run keeps its optimistic user and attachments after there is no streaming run", () => {
  const optimistic: Message = {
    id: "local-user",
    role: "user",
    content: "question",
    timestamp: new Date(time),
    attachments: [
      {
        id: "file",
        name: "input.txt",
        type: "file",
        key: "k",
        mimeType: "text/plain",
        size: 3,
        url: "/file",
      },
    ],
  };
  const live = [
    event("body", "message:chunk", { content: "answer" }),
    event("done", "done", {}),
  ];
  const result = replayHistoryJournal({
    messages: [],
    goals: {},
    events: live.map(entry),
    covered: new Set(),
    optimisticUsers: new Map([["run", optimistic]]),
    currentMessages: [currentAssistant(false)],
  });
  expect(result.messages.filter((message) => message.role === "user")).toEqual([
    { ...optimistic, runId: "run" },
  ]);
  expect(
    result.messages.find((message) => message.role === "assistant"),
  ).toMatchObject({ content: "answer", isStreaming: false });
  expect(effects.markRead).not.toHaveBeenCalled();
});

test("covered goal start cannot roll a newer stored goal end back to active", () => {
  const start = event("start", "goal:start", {
    _source_id: "gs",
    run_id: "run",
    goal: { objective: "task", rubric: "verified" },
    started_at: time,
  });
  const end = {
    ...event("end", "goal:end", {
      _source_id: "ge",
      run_id: "run",
      goal: { objective: "task", rubric: "verified" },
      ended_at: "2026-10-15T00:00:01Z",
    }),
    timestamp: "2026-10-15T00:00:01Z",
  };
  const stored = [
    user,
    event("body", "message:chunk", { content: "answer" }),
    start,
    end,
  ];
  const goals = extractGoalsByRunFromEvents(stored);
  const result = replayHistoryJournal({
    messages: reconstructMessagesFromEvents(stored, new Set(), {
      activeSubagentStack: [],
    }),
    goals,
    events: [entry(start)],
    covered: historyCoverage(stored),
    optimisticUsers: new Map(),
    currentMessages: [currentAssistant(false)],
  });
  expect(goals.run.ended_at).toBe("2026-10-15T00:00:01Z");
  expect(result.goals.run).toEqual(goals.run);
});

test("covered steer changes the old live message id to the latest persisted turn for new text and tools", () => {
  const at = (second: number) => `2026-10-15T00:00:0${second}Z`;
  const before = {
    ...event("before", "message:chunk", {
      content: "before",
      _source_id: "before",
    }),
    timestamp: at(1),
  };
  const steer = {
    ...event("steer", "steer:message", {
      content: "follow up",
      message_id: "steer-1",
      created_at: at(2),
      _source_id: "steer",
    }),
    timestamp: at(2),
  };
  const after = {
    ...event("after", "message:chunk", {
      content: "after",
      _source_id: "after",
    }),
    timestamp: at(3),
  };
  const stored = [user, before, steer, after];
  const baseline = reconstructMessagesFromEvents(stored, new Set(), {
    activeSubagentStack: [],
  });
  const liveCurrent = baseline.map((message) =>
    message.role !== "assistant"
      ? message
      : {
          ...message,
          id: message.content === "before" ? "run#t1" : "run",
          isStreaming: message.content === "after",
        },
  );
  const tail = {
    ...event("tail", "message:chunk", { content: "+tail", _source_id: "tail" }),
    timestamp: at(4),
  };
  const tool = {
    ...event("tool", "tool:start", {
      tool: "bash",
      tool_call_id: "latest-tool",
      args: { cmd: "pwd" },
      _source_id: "tool",
    }),
    timestamp: at(5),
  };
  const result = replayHistoryJournal({
    messages: baseline,
    goals: {},
    events: [steer, tail, tool].map(entry),
    covered: historyCoverage(stored),
    optimisticUsers: new Map(),
    currentMessages: liveCurrent,
  });
  const assistants = result.messages.filter(
    (message) => message.role === "assistant",
  );
  expect(assistants.map((message) => message.content)).toEqual([
    "before",
    "after+tail",
  ]);
  expect(
    assistants[0].parts?.some(
      (part) => part.type === "tool" && part.id === "latest-tool",
    ),
  ).toBe(false);
  expect(
    assistants[1].parts?.find(
      (part) => part.type === "tool" && part.id === "latest-tool",
    ),
  ).toMatchObject({ args: { cmd: "pwd" }, isPending: true });
});

test("journal replay indexes one thousand baseline messages and tools instead of scanning both per result", () => {
  const count = 1000;
  const stored = [
    user,
    ...Array.from({ length: count }, (_, index) =>
      event(`start-${index}`, "tool:start", {
        tool: "bash",
        tool_call_id: `tool-${index}`,
        args: { cmd: `echo ${index}` },
      }),
    ),
  ];
  const replayed = reconstructMessagesFromEvents(stored, new Set(), {
    activeSubagentStack: [],
  });
  const baseline: Message[] = [
    ...Array.from(
      { length: count },
      (_, index): Message => ({
        id: `old-${index}`,
        role: "user",
        runId: `old-${index}`,
        content: `old ${index}`,
        timestamp: new Date("2026-10-01T00:00:00Z"),
      }),
    ),
    ...replayed,
  ];
  const journal = Array.from({ length: count }, (_, index) =>
    entry(
      event(`result-${index}`, "tool:result", {
        tool: "bash",
        tool_call_id: `tool-${index}`,
        result: `result ${index}`,
        success: true,
      }),
    ),
  );
  // Independent shared-processor oracle, computed before instrumentation.
  let expectedAssistant = structuredClone(baseline[baseline.length - 1]);
  for (const { event: live } of journal) {
    const converted = eventProcessor.processMessageEvent(
      live.event_type,
      {
        ...(live.data as EventData),
        timestamp: (live.data as EventData).timestamp ?? live.timestamp,
      },
      expectedAssistant.parts || [],
      expectedAssistant.content,
      expectedAssistant.toolCalls || [],
      0,
      [],
      true,
      expectedAssistant.id,
    );
    expectedAssistant = {
      ...expectedAssistant,
      parts: converted.parts,
      content: converted.content,
      toolCalls: converted.toolCalls,
      ...(converted.toolResult
        ? {
            toolResults: [
              ...(expectedAssistant.toolResults || []),
              converted.toolResult,
            ],
          }
        : {}),
      ...(converted.tokenUsage ? { tokenUsage: converted.tokenUsage } : {}),
      ...(converted.duration ? { duration: converted.duration } : {}),
      isStreaming: true,
    };
  }
  const reference = {
    messages: [...structuredClone(baseline.slice(0, -1)), expectedAssistant],
    goals: {},
  };
  const untouched = structuredClone(baseline);
  const input = {
    messages: structuredClone(baseline),
    goals: {},
    events: journal,
    covered: new Set<string>(),
    optimisticUsers: new Map<string, Message>(),
    currentMessages: [currentAssistant()],
  };
  const originalMap = Array.prototype.map;
  let messageVisits = 0;
  const mapSpy = vi.spyOn(Array.prototype, "map").mockImplementation(function (
    this: unknown[],
    callback,
    thisArg,
  ) {
    if (this.length >= count && (this[0] as Message | undefined)?.role)
      messageVisits += this.length;
    return originalMap.call(this, callback, thisArg);
  });
  const processorSpy = vi.spyOn(eventProcessor, "processMessageEvent");
  let actual: ReturnType<typeof replayHistoryJournal>;
  let partVisits = 0;
  try {
    actual = replayHistoryJournal(input);
    for (const call of processorSpy.mock.calls) partVisits += call[2].length;
  } finally {
    processorSpy.mockRestore();
    mapSpy.mockRestore();
  }
  expect(actual!).toEqual(reference);
  expect(input.messages).toEqual(untouched);
  expect(messageVisits).toBeLessThan(count * 10);
  expect(partVisits).toBeLessThan(count * 10);
});

test("ordinary live identity projection updates every same-run turn like the shared handler", () => {
  const stored = [
    user,
    {
      ...event("before", "message:chunk", { content: "before" }),
      timestamp: "2026-10-15T00:00:01Z",
    },
    {
      ...event("steer", "steer:message", {
        content: "follow up",
        message_id: "steer-1",
        created_at: "2026-10-15T00:00:02Z",
      }),
      timestamp: "2026-10-15T00:00:02Z",
    },
    {
      ...event("after", "message:chunk", { content: "after" }),
      timestamp: "2026-10-15T00:00:03Z",
    },
  ];
  const baseline = reconstructMessagesFromEvents(stored, new Set(), {
    activeSubagentStack: [],
  });
  baseline[baseline.length - 1] = {
    ...baseline[baseline.length - 1],
    isStreaming: true,
  };
  const targetId = baseline[baseline.length - 1].id;
  const identity = {
    seed: "new-persona",
    name: "New Persona",
    avatar: "avatar.svg",
  };
  const live = event("identity-tail", "message:chunk", {
    run_id: "run",
    content: "+tail",
    assistant_identity: identity,
    _source_id: "identity-tail",
  });
  let reference = structuredClone(baseline);
  const noop = () => {};
  const ctx: EventHandlerContext = {
    replayOnly: true,
    sessionIdRef: { current: "A" },
    processedEventIdsRef: { current: new Set() },
    lastHistoryTimestampRef: { current: null },
    activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 },
    setMessages: (update) => {
      reference = typeof update === "function" ? update(reference) : update;
    },
    setSessionId: noop,
    setConnectionStatus: noop,
    setIsInitializingSandbox: noop,
    setSandboxError: noop,
    setActiveGoal: noop,
    setGoalsByRunId: noop,
  };
  handleStreamEvent(
    { event: "message:chunk", data: JSON.stringify(live.data) },
    targetId,
    "identity-tail",
    live.timestamp,
    ctx,
  );
  const actual = replayHistoryJournal({
    messages: structuredClone(baseline),
    goals: {},
    events: [{ event: live, messageId: targetId }],
    covered: historyCoverage(stored),
    optimisticUsers: new Map(),
    currentMessages: baseline,
  });
  expect(
    actual.messages
      .filter((message) => message.role === "assistant")
      .map((message) => ({
        content: message.content,
        identity: message.assistantIdentity,
      })),
  ).toEqual(
    reference
      .filter((message) => message.role === "assistant")
      .map((message) => ({
        content: message.content,
        identity: message.assistantIdentity,
      })),
  );
  expect(
    actual.messages
      .filter((message) => message.role === "assistant")
      .map((message) => message.assistantIdentity),
  ).toEqual([identity, identity]);
});

test("unrelated shallower stack entries cannot reroute anonymous deeper output away from its existing agent", () => {
  const assistant: Message = {
    id: "run",
    role: "assistant",
    runId: "run",
    timestamp: new Date(time),
    content: "",
    isStreaming: true,
    parts: [createSubagentPart("B", "B", "task", 3, time)],
  };
  const stack = [{ agent_id: "A", depth: 1, message_id: "run" }];
  const data: EventData = { content: "nested", depth: 3, _source_id: "nested" };
  const expected = eventProcessor.processMessageEvent(
    "message:chunk",
    data,
    structuredClone(assistant.parts!),
    "",
    [],
    3,
    structuredClone(stack),
    true,
    "run",
  );
  const actual = replayHistoryJournal({
    messages: [assistant],
    goals: {},
    events: [entry(event("nested", "message:chunk", data))],
    covered: new Set(),
    optimisticUsers: new Map(),
    currentMessages: [assistant],
    activeSubagentStack: stack,
  });
  expect(actual.messages[0].parts).toEqual(expected.parts);
  expect(
    actual.messages[0].parts?.find(
      (part) => part.type === "subagent" && part.agent_id === "B",
    ),
  ).toMatchObject({ parts: [{ type: "text", content: "nested" }] });
});

test("historical usage retains actual settlement identities and amount", () => {
  const actualModels = [
    { model: "fallback", model_id: "b", provider: "openai" },
  ];
  const messages = reconstructMessagesFromEvents(
    [
      event("text", "message:chunk", { content: "Answer" }),
      event("receipt", "token:usage", {
        model: "fallback",
        model_id: "b",
        cost_source: "provider_settlement",
        cost_units: 123_000_000,
        cost_usd: 0.123,
        cost_complete: true,
        actual_models: actualModels,
      }),
    ],
    new Set(),
    { activeSubagentStack: [] },
  );
  expect(
    messages.find((message) => message.role === "assistant")?.tokenUsage,
  ).toMatchObject({
    cost_source: "provider_settlement",
    cost_units: 123_000_000,
    cost_complete: true,
    actual_models: actualModels,
    model: "fallback",
  });
});
