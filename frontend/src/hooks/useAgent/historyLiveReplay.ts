/** Stored trace views and accepted stream events have distinct identities. */
import type { Message, MessagePart } from "../../types";
import type {
  ActiveGoalSpec,
  EventData,
  HistoryEvent,
  SubagentStackItem,
} from "./types";
import { handleStreamEvent, type EventHandlerContext } from "./eventHandlers";
import { settleAssistantMessage } from "./settleStream";
import { HistoryPartReplay } from "./historyReplayParts";

export interface HistoryJournalEntry {
  event: HistoryEvent;
  messageId: string;
}

export function historySourceIds(event: HistoryEvent): string[] {
  const data = event.data as EventData | null;
  if (!data) return [];
  return [
    ...new Set([
      ...(Array.isArray(data._source_ids) ? data._source_ids : []),
      ...(data._source_id ? [data._source_id] : []),
    ]),
  ];
}

export function historyCoverage(events: HistoryEvent[]): Set<string> {
  const covered = new Set<string>();
  for (const event of events)
    for (const source of historySourceIds(event)) covered.add(source);
  return covered;
}

/** A cursor response contains whole traces; never union overlapping compact chunks. */
export function mergeHistoryTraceViews(
  current: HistoryEvent[],
  incoming: HistoryEvent[],
  partialTraceIds: ReadonlySet<string> = new Set(),
): HistoryEvent[] {
  const previous = new Map<string, HistoryEvent[]>();
  const next = new Map<string, HistoryEvent[]>();
  for (const event of current)
    if (event.trace_id) {
      const group = previous.get(event.trace_id) || [];
      group.push(event);
      previous.set(event.trace_id, group);
    }
  for (const event of incoming)
    if (event.trace_id) {
      const group = next.get(event.trace_id) || [];
      group.push(event);
      next.set(event.trace_id, group);
    }
  const selected = new Map(previous);
  for (const [trace, events] of next) {
    const old = previous.get(trace);
    if (!old) {
      selected.set(trace, events);
      continue;
    }
    if (
      partialTraceIds.has(trace) &&
      old.some((event) => event.event_type !== "user:message")
    )
      continue;
    const oldSources = historyCoverage(old),
      newSources = historyCoverage(events);
    if (
      oldSources.size &&
      [...newSources].every((source) => oldSources.has(source)) &&
      oldSources.size > newSources.size
    )
      continue;
    selected.set(trace, events);
  }
  const result: HistoryEvent[] = [],
    emitted = new Set<string>();
  const currentIds = new Set(
    current
      .filter((event) => !event.trace_id)
      .map((event) => event.id)
      .filter((id) => id != null),
  );
  const incomingEvents = new Set(incoming);
  for (const event of [...incoming, ...current]) {
    if (event.trace_id) {
      if (!emitted.has(event.trace_id)) {
        result.push(...(selected.get(event.trace_id) || []));
        emitted.add(event.trace_id);
      }
    } else if (
      !incomingEvents.has(event) ||
      event.id == null ||
      !currentIds.has(event.id)
    )
      result.push(event);
  }
  return result;
}

/** Replay uses the same transformations with a local context and effects disabled. */
export function replayHistoryJournal(input: {
  messages: Message[];
  goals: Record<string, ActiveGoalSpec>;
  events: HistoryJournalEntry[];
  covered: ReadonlySet<string>;
  optimisticUsers: ReadonlyMap<string, Message>;
  currentMessages: Message[];
  activeSubagentStack?: SubagentStackItem[];
}): { messages: Message[]; goals: Record<string, ActiveGoalSpec> } {
  const cloneParts = (parts: MessagePart[]): MessagePart[] =>
    parts.map((part) =>
      part.type === "subagent" && part.parts
        ? { ...part, parts: cloneParts(part.parts) }
        : { ...part },
    );
  let messages = input.messages.map((message) => ({
    ...message,
    ...(message.parts ? { parts: cloneParts(message.parts) } : {}),
    ...(message.toolCalls ? { toolCalls: [...message.toolCalls] } : {}),
    ...(message.toolResults ? { toolResults: [...message.toolResults] } : {}),
  }));
  let goals = input.goals;
  const byId = new Map<string, number>();
  const latestByRun = new Map<string, number>();
  const assistantIndexesByRun = new Map<string, number[]>();
  const userRuns = new Set<string>();
  const reindex = () => {
    byId.clear();
    latestByRun.clear();
    assistantIndexesByRun.clear();
    userRuns.clear();
    messages.forEach((message, index) => {
      if (!byId.has(message.id)) byId.set(message.id, index);
      if (message.runId && message.role === "assistant") {
        latestByRun.set(message.runId, index);
        const indexes = assistantIndexesByRun.get(message.runId) || [];
        indexes.push(index);
        assistantIndexesByRun.set(message.runId, indexes);
      }
      if (message.runId && message.role === "user") userRuns.add(message.runId);
    });
  };
  reindex();
  const liveById = new Map<string, Message>();
  const liveByRun = new Map<string, Message>();
  for (const message of input.currentMessages)
    if (message.role === "assistant") {
      liveById.set(message.id, message);
      if (message.runId) liveByRun.set(message.runId, message);
    }
  for (let index = 0; index < messages.length; index++) {
    const message = messages[index];
    const user =
      message.role === "user" && message.runId
        ? input.optimisticUsers.get(message.runId)
        : undefined;
    if (user)
      messages[index] = {
        ...message,
        attachments: message.attachments?.length
          ? message.attachments
          : user.attachments,
        assistantIdentity: message.assistantIdentity || user.assistantIdentity,
        enabledSkills: message.enabledSkills ?? user.enabledSkills,
        runModes: message.runModes ?? user.runModes,
      };
  }
  for (const [runId, user] of input.optimisticUsers)
    if (!userRuns.has(runId)) {
      byId.set(user.id, messages.length);
      messages.push({ ...user, runId });
      userRuns.add(runId);
    }
  const shell = (
    live: Message | undefined,
    id: string,
    runId: string | undefined,
    timestamp?: string,
  ): Message => ({
    id,
    role: "assistant",
    runId,
    content: "",
    parts: [],
    isStreaming: true,
    timestamp: live?.timestamp || new Date(timestamp || 0),
    assistantIdentity: live?.assistantIdentity,
    ...(live?.toolCalls !== undefined ? { toolCalls: [] } : {}),
    ...(live?.toolResults !== undefined ? { toolResults: [] } : {}),
    ...(live?.metadata !== undefined ? { metadata: live.metadata } : {}),
  });
  for (const [runId, live] of liveByRun) {
    if (!live.isStreaming || latestByRun.has(runId) || !userRuns.has(runId))
      continue;
    latestByRun.set(runId, messages.length);
    byId.set(live.id, messages.length);
    assistantIndexesByRun.set(runId, [messages.length]);
    messages.push(shell(live, live.id, runId));
  }
  const privateParts = new HistoryPartReplay(true);
  const noop = () => {};
  let scope: number | null = null;
  const context: EventHandlerContext = {
    replayOnly: true,
    replayParts: privateParts,
    sessionIdRef: { current: null },
    processedEventIdsRef: { current: new Set() },
    lastHistoryTimestampRef: { current: null },
    activeSubagentStackRef: { current: [...(input.activeSubagentStack || [])] },
    streamVersionRef: { current: 0 },
    setMessages: (update) => {
      if (scope === null) {
        messages = typeof update === "function" ? update(messages) : update;
        reindex();
      } else {
        const index = scope;
        const previous = messages[index];
        const next = typeof update === "function" ? update([previous]) : update;
        if (next.length === 1 && next[0].id === previous.id)
          messages[index] = next[0];
        else {
          messages.splice(index, 1, ...next);
          reindex();
        }
      }
    },
    setGoalsByRunId: (update) => {
      goals = typeof update === "function" ? update(goals) : update;
    },
    setActiveGoal: noop,
    setSessionId: noop,
    setConnectionStatus: noop,
    setIsInitializingSandbox: noop,
    setSandboxError: noop,
  };
  const liveRuns = new Set<string>();
  const targetsByLiveId = new Map<string, string>();
  const lifecycleByRun = new Map<string, boolean>();
  const controls = new Set(["user:message", "steer:message", "metadata"]);
  for (const { event, messageId } of input.events) {
    const data = event.data as EventData;
    const runId = event.run_id || data.run_id;
    if (runId) liveRuns.add(runId);
    const sources = historySourceIds(event);
    const covered =
      sources.length > 0 &&
      sources.every((source) => input.covered.has(source));
    const terminal = ["done", "complete", "error", "user:cancel"].includes(
      event.event_type,
    );
    if (runId && terminal) lifecycleByRun.set(runId, false);
    else if (
      runId &&
      !covered &&
      ["run:resumed", "user:message", "steer:message"].includes(
        event.event_type,
      )
    )
      lifecycleByRun.set(runId, true);
    const liveId = `${runId || ""}:${messageId}`;
    if (covered && event.event_type === "steer:message" && runId) {
      const latest = latestByRun.get(runId);
      if (latest !== undefined)
        targetsByLiveId.set(liveId, messages[latest].id);
    }
    if (covered && !["done", "complete"].includes(event.event_type)) continue;
    const mappedId = targetsByLiveId.get(liveId) || messageId;
    let targetIndex =
      byId.get(mappedId) ?? (runId ? latestByRun.get(runId) : undefined);
    const live =
      liveById.get(messageId) || (runId ? liveByRun.get(runId) : undefined);
    if (targetIndex !== undefined) {
      const target = messages[targetIndex];
      if (live?.toolResults !== undefined && target.toolResults === undefined)
        target.toolResults = [];
      if (live?.toolCalls !== undefined && target.toolCalls === undefined)
        target.toolCalls = [];
    }
    if (
      targetIndex === undefined &&
      ![
        "user:message",
        "steer:message",
        "goal:start",
        "goal:end",
        "done",
        "complete",
      ].includes(event.event_type)
    ) {
      targetIndex = messages.length;
      messages.push(shell(live, mappedId, runId, event.timestamp));
      byId.set(mappedId, targetIndex);
      if (runId) {
        latestByRun.set(runId, targetIndex);
        const indexes = assistantIndexesByRun.get(runId) || [];
        indexes.push(targetIndex);
        assistantIndexesByRun.set(runId, indexes);
      }
    }
    const targetId =
      targetIndex !== undefined ? messages[targetIndex].id : mappedId;
    scope =
      controls.has(event.event_type) || targetIndex === undefined
        ? null
        : targetIndex;
    // Control reducers inspect full parts; indexed ordinary reducers flush only
    // on their fallback path and once more before publishing the result.
    if (
      targetIndex !== undefined &&
      (controls.has(event.event_type) ||
        [
          "done",
          "complete",
          "run:resumed",
          "user:cancel",
          "approval_required",
        ].includes(event.event_type))
    )
      privateParts.flush(messages[targetIndex]);
    if (!data.depth && data.assistant_identity && runId) {
      for (const index of assistantIndexesByRun.get(runId) || []) {
        messages[index] = {
          ...messages[index],
          assistantIdentity: data.assistant_identity,
        };
      }
    }
    handleStreamEvent(
      {
        event: event.event_type as Parameters<
          typeof handleStreamEvent
        >[0]["event"],
        data: JSON.stringify({ ...data, ...(runId ? { run_id: runId } : {}) }),
      },
      targetId,
      String(event.id),
      event.timestamp,
      context,
    );
    scope = null;
  }
  const runtimeRuns = new Set([...liveRuns, ...input.optimisticUsers.keys()]);
  for (const [runId, live] of liveByRun)
    if (live.isStreaming) runtimeRuns.add(runId);
  for (const runId of runtimeRuns) {
    const live = liveByRun.get(runId);
    const targetIndex = latestByRun.get(runId);
    if (targetIndex === undefined) continue;
    const target = messages[targetIndex];
    privateParts.flush(target);
    const streaming = lifecycleByRun.get(runId) ?? live?.isStreaming;
    if (streaming === false) {
      const settled = settleAssistantMessage([target], target.id);
      if (settled.length) messages[targetIndex] = settled[0];
      else {
        messages.splice(targetIndex, 1);
        reindex();
        continue;
      }
    } else if (streaming === true)
      messages[targetIndex] = { ...target, isStreaming: true };
    // Keep the admitted SSE/onclose callback's fixed id on the newest turn.
    // Swap a conflicting older turn's id; never overwrite either turn's data.
    if (live && live.id !== messages[targetIndex].id) {
      const previousId = messages[targetIndex].id;
      const collision = byId.get(live.id);
      if (
        collision === undefined ||
        (messages[collision].role === "assistant" &&
          messages[collision].runId === runId)
      ) {
        if (collision !== undefined)
          messages[collision] = { ...messages[collision], id: previousId };
        messages[targetIndex] = { ...messages[targetIndex], id: live.id };
        byId.delete(previousId);
        byId.delete(live.id);
        if (collision !== undefined) byId.set(previousId, collision);
        byId.set(live.id, targetIndex);
      }
    }
  }
  for (const message of messages) privateParts.flush(message);
  return { messages, goals };
}
