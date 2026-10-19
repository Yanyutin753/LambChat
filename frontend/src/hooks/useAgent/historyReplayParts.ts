/** Private history construction only; live message updates stay immutable. */
import type { Message, MessagePart, SubagentPart, ToolPart } from "../../types";
import i18n from "../../i18n";
import type { EventData, SubagentStackItem } from "./types";
import {
  HistoryPartSlots,
  historySlotKey,
  historyArtifactKey,
  type HistoryPartSlot,
} from "./historyPartSlots";
import {
  HistoryToolCandidates,
  toolCandidateKey as key,
  type PartRef,
  type PartContainer,
} from "./historyToolCandidates";
import { processMessageEvent } from "./eventProcessor";
import {
  appendToolArgsDelta,
  createToolPart,
  createGeneratingToolPart,
  createThinkingPart,
  finishThinkingParts,
  createSubagentPart,
  upgradeGeneratingToolPart,
  addPartToDepth,
  mergeSummaryPart,
  mergeThinkingPart,
  updateSubagentResult,
  updateToolResultInDepth,
  clearAllLoadingStates,
} from "./messageParts";
import {
  takeOverDanglingToolPart,
  markPendingToolsAwaiting,
} from "./suspendedToolParts";

const approvalToolIds = (data: EventData): string[] => {
  const ids = Array.isArray(data.tool_call_ids)
    ? data.tool_call_ids.filter((id) => typeof id === "string" && id.length > 0)
    : [];
  return ids.length ? ids : data.tool_call_id ? [data.tool_call_id] : [];
};

const approvalResult = (data: EventData) =>
  typeof data.result === "object" && data.result !== null
    ? data.result
    : { status: data.success === false ? "rejected" : "success" };

/** Private replay arrays only: never attach this mutating builder to rendered/live message parts. */
export class HistoryPartReplay {
  private readonly candidates = new WeakMap<
    MessagePart[],
    HistoryToolCandidates
  >();
  constructor(private readonly streaming = false) {}
  private registry(message: Message): HistoryToolCandidates {
    const parts = (message.parts ??= []);
    let index = this.candidates.get(parts);
    if (!index) {
      index = new HistoryToolCandidates(parts);
      this.candidates.set(parts, index);
    } else index.root.slots.sync();
    return index;
  }
  flush(message: Message): void {
    const parts = message.parts;
    if (parts && this.candidates.get(parts)?.materialize())
      this.candidates.delete(parts);
  }
  private slots(message: Message): HistoryPartSlots {
    return this.registry(message).root.slots;
  }
  ensureApproval(
    message: Message,
    id: string,
    create: () => MessagePart,
  ): void {
    const index = this.registry(message);
    if (!index.local(index.root, ["id", id]))
      index.append(index.root, create());
  }
  repairApproval(
    message: Message,
    approval: {
      id: string;
      status: string;
      metadata?: Record<string, unknown> | null;
    },
    repair: (
      messages: Message[],
      approval: {
        id: string;
        status: string;
        metadata?: Record<string, unknown> | null;
      },
    ) => Message[],
  ): void {
    if (
      approval.status === "pending" ||
      approval.metadata?.approval_type !== "scheduled_task_create"
    )
      return;
    const slots = this.slots(message);
    for (const slot of slots.all(historySlotKey("ask", approval.id))) {
      const part = repair([{ ...message, parts: [slot.part] }], approval)[0]
        .parts?.[0];
      if (part) slots.replace(slot, part);
    }
  }
  private scalar(
    message: Message,
    eventType: string,
    data: EventData,
  ): boolean | undefined {
    if (
      (data.depth &&
        [
          "artifact:result",
          "summary",
          "recommend:questions",
          "followup:questions",
        ].includes(eventType)) ||
      [
        "agent:call",
        "agent:result",
        "thinking",
        "message:chunk",
        "approval_required",
        "approval_resolved",
        "hitl:suspended",
        "human_resume_started",
        "error",
        "complete",
        "done",
        "todo:updated",
      ].includes(eventType) ||
      eventType.startsWith("tool:")
    )
      return undefined;
    const converted = processMessageEvent(
      eventType,
      data,
      [],
      "",
      [],
      0,
      [],
      this.streaming,
    );
    if (converted.tokenUsage) message.tokenUsage = converted.tokenUsage;
    if (converted.duration) message.duration = converted.duration;
    const fresh = converted.parts[0];
    if (!fresh) return true; // unknown/no-op events preserve both registries.
    const slots = this.slots(message);
    let targets: HistoryPartSlot[];
    if (fresh.type === "artifact") {
      const key = historyArtifactKey(fresh);
      const target = key
        ? slots.first(historySlotKey("artifact", key))
        : undefined;
      targets = target ? [target] : [];
    } else if (fresh.type === "summary") {
      const target =
        !fresh.content && fresh.freed_tokens !== undefined
          ? slots.last(historySlotKey("type", "summary"))
          : slots.last(historySlotKey("summary", fresh.summary_id)) ||
            (fresh.content
              ? slots.last(historySlotKey("summary-stub"))
              : undefined);
      targets = target ? [target] : [];
    } else if (
      ["memoryStatus", "sandbox", "recommend_questions"].includes(fresh.type)
    )
      targets = slots.all(historySlotKey("type", fresh.type));
    else return undefined;
    if (!targets.length) slots.append(fresh);
    else
      for (const target of targets) {
        const next = processMessageEvent(
          eventType,
          data,
          [target.part],
          "",
          [],
          0,
          [],
          this.streaming,
        ).parts;
        if (next.length > 1) slots.append(next[next.length - 1]);
        else if (next[0]) slots.replace(target, next[0]);
      }
    return true;
  }
  private upgrade(
    index: HistoryToolCandidates,
    replacement: ToolPart,
    depth: number,
    dangling = false,
  ): PartRef | undefined {
    let owner = depth ? undefined : index.root;
    const signature = key(replacement.name, JSON.stringify(replacement.args));
    if (depth === 1) {
      const selector = dangling
        ? replacement.agent_id
          ? ["all", "child-dangling-parent", signature, replacement.agent_id]
          : ["all", "child-dangling", signature]
        : replacement.agent_id
          ? ["all", "child-draft-parent", replacement.agent_id]
          : ["all", "child-draft"];
      owner = index.select(key(...selector))?.owner;
    }
    if (!owner) return undefined;
    if (dangling) return index.local(owner, ["dangling", signature], true);
    return (
      (replacement.id
        ? index.local(owner, ["draft-id", replacement.id])
        : undefined) ||
      (replacement.name
        ? index.local(owner, ["draft-name", replacement.name], true)
        : undefined) ||
      index.local(owner, ["draft"], true)
    );
  }
  private replaceUpgrade(
    index: HistoryToolCandidates,
    ref: PartRef,
    replacement: ToolPart,
    dangling = false,
  ): void {
    const parent = ref.owner.parent?.slot.part as SubagentPart | undefined;
    if (parent && !parent.isPending && replacement.isPending)
      replacement = { ...replacement, isPending: false, cancelled: true };
    const next = dangling
      ? takeOverDanglingToolPart([ref.slot.part], replacement)
      : upgradeGeneratingToolPart([ref.slot.part], replacement);
    if (next) index.replace(ref, next[0]);
  }
  private route(
    index: HistoryToolCandidates,
    depth: number,
    agent?: string,
  ): PartContainer {
    if (!depth) return index.root;
    const ref = index.local(
      index.root,
      agent ? ["agent", depth, agent] : ["route", depth],
      true,
    );
    return ref ? index.child(ref) : index.root;
  }
  private append(
    index: HistoryToolCandidates,
    owner: PartContainer,
    part: MessagePart,
  ): void {
    if (part.type === "thinking") {
      const before = index.local(owner, ["non-draft"], true);
      const last = index.local(owner, ["part"], true);
      if (last && before !== last) {
        index.insertAfter(owner, before?.slot.position ?? -1, part);
        return;
      }
    }
    index.append(owner, part);
  }
  private add(
    index: HistoryToolCandidates,
    owner: PartContainer,
    part: MessagePart,
    depth: number,
  ): void {
    if (part.type === "text") {
      const before = index.local(owner, ["non-draft"], true);
      const last = index.local(owner, ["part"], true);
      if (
        before?.slot.part.type === "text" &&
        (owner.parent || depth || !before.slot.part.depth)
      )
        index.replace(before, {
          ...before.slot.part,
          content: before.slot.part.content + part.content,
        });
      else if (!last || before === last) index.append(owner, part);
      else index.insertAfter(owner, before?.slot.position ?? -1, part);
      return;
    }
    let target: PartRef | undefined;
    if (part.type === "thinking")
      target = index.local(owner, ["thinking", part.thinking_id], true);
    else if (part.type === "todo" && owner.parent)
      target = index.local(owner, ["type", "todo"]);
    else if (part.type === "summary") {
      const slots = owner.slots;
      const slot =
        !part.content && part.freed_tokens !== undefined
          ? slots.last(historySlotKey("type", "summary"))
          : slots.last(historySlotKey("summary", part.summary_id)) ||
            (part.content
              ? slots.last(historySlotKey("summary-stub"))
              : undefined);
      if (slot) target = owner.refs.get(slot.position);
    }
    if (owner.parent) {
      const parent = owner.parent.slot.part as SubagentPart;
      const result = addPartToDepth(
        [{ ...parent, parts: target ? [target.slot.part] : [] }],
        part,
        parent.depth ?? 0,
        [],
        parent.agent_id,
      )[0] as SubagentPart;
      const next = result.parts || [];
      if (target && next.length === 1) index.replace(target, next[0]);
      else if (next.length) this.append(index, owner, next[next.length - 1]);
    } else if (target) {
      // Fallback placement at the root uses the same thinking/text/summary merge helpers.
      const merged =
        part.type === "thinking" && target.slot.part.type === "thinking"
          ? mergeThinkingPart([target.slot.part], part, this.streaming) || [
              target.slot.part,
              part,
            ]
          : part.type === "summary"
            ? mergeSummaryPart([target.slot.part], part) || [
                target.slot.part,
                part,
              ]
            : addPartToDepth([target.slot.part], part, depth, []);
      if (merged.length === 1) index.replace(target, merged[0]);
      else index.append(owner, merged[merged.length - 1]);
    } else this.append(index, owner, part);
  }
  replay(
    message: Message,
    eventType: string,
    data: EventData,
    routeAgent?: string,
  ): boolean {
    message.toolCalls ??= [];
    const scalar = this.scalar(message, eventType, data);
    if (scalar !== undefined) return scalar;
    const index = this.registry(message);
    if (index.nested) return false; // The event producer creates root execution cards, never nested cards.
    const depth = data.depth || 0;
    const id = data.tool_call_id;
    const todoTool = data.tool === "todo_write" || data.tool === "write_todos";
    if (
      todoTool &&
      (eventType === "tool:result" || eventType === "tool:args:chunk")
    )
      return true;
    if (
      eventType === "hitl:suspended" ||
      eventType === "human_resume_started"
    ) {
      const awaiting = eventType === "hitl:suspended";
      for (const ref of index.all(key("all", "pending-awaiting", !awaiting)))
        index.replace(
          ref,
          markPendingToolsAwaiting([ref.slot.part], awaiting)[0],
        );
      return true;
    }
    if (eventType === "approval_resolved") {
      const ids = approvalToolIds(data);
      if (!ids.length) {
        const ref = index.select(key("all", "ask"), true);
        if (ref)
          index.replace(
            ref,
            processMessageEvent(
              eventType,
              data,
              [ref.slot.part],
              "",
              [],
              0,
              [],
              this.streaming,
            ).parts[0],
          );
      } else
        for (const toolId of ids) {
          const ref = index.result(toolId, depth, data.agent_id);
          if (ref)
            index.replace(
              ref,
              (Array.isArray(data.tool_call_ids) &&
              data.tool_call_ids.length > 0 &&
              data.success !== false
                ? markPendingToolsAwaiting(
                    [ref.slot.part],
                    false,
                    new Set([toolId]),
                  )
                : updateToolResultInDepth(
                    [ref.slot.part],
                    toolId,
                    approvalResult(data),
                    data.success !== false,
                    data.error,
                    (ref.slot.part as ToolPart).depth || 0,
                    data.agent_id,
                    data.timestamp,
                  ))[0],
            );
        }
      return true;
    }
    if (eventType === "agent:call" || eventType === "agent:result") {
      const agent = data.agent_id || "unknown";
      const ref = index.local(
        index.root,
        data.agent_call_id
          ? ["agent-call", data.agent_call_id]
          : [
              eventType === "agent:call" ? "pending-agent" : "agent",
              depth,
              agent,
            ],
        true,
      );
      let next: MessagePart;
      if (eventType === "agent:call") {
        const fresh = createSubagentPart(
          agent,
          data.agent_name || data.agent_id || i18n.t("chat.unknownAgent"),
          data.input || "",
          depth,
          data.timestamp,
          data.agent_avatar,
          data.status,
          data.agent_call_id,
        );
        next = ref
          ? addPartToDepth([ref.slot.part], fresh, depth, [], agent)[0]
          : fresh;
      } else {
        const previous =
          ref?.slot.part ||
          createSubagentPart(
            agent,
            data.agent_name || data.agent_id || i18n.t("chat.unknownAgent"),
            data.input || "",
            depth,
            data.timestamp,
            data.agent_avatar,
            data.status,
            data.agent_call_id,
          );
        const child = ref ? index.child(ref) : undefined;
        next = updateSubagentResult(
          [{ ...previous, parts: [] } as SubagentPart],
          agent,
          String(data.result || ""),
          data.success !== false,
          depth,
          data.error,
          data.timestamp,
          data.status,
          data.agent_call_id,
        )[0];
        if (child) {
          for (const thought of child.slots.all(
            historySlotKey("open-thinking", data.agent_id),
          )) {
            const ref = child.refs.get(thought.position);
            if (ref)
              index.replace(
                ref,
                finishThinkingParts(
                  [thought.part],
                  data.timestamp,
                  data.agent_id,
                )[0],
              );
          }
          if (!(next as SubagentPart).isPending)
            for (const loading of index.loading(child)) {
              const settled = clearAllLoadingStates([loading.slot.part], {
                discardToolDrafts: true,
              });
              if (settled[0]) index.replace(loading, settled[0]);
              else index.remove(loading);
            }
          (next as SubagentPart).parts = child.slots.parts;
        }
      }
      if (ref) index.replace(ref, next);
      else index.append(index.root, next);
      return true;
    }
    const owner = this.route(index, depth, data.agent_id || routeAgent);
    if (
      ["message:chunk", "tool:args:chunk", "tool:start"].includes(eventType)
    ) {
      for (const thought of owner.slots.all(
        historySlotKey("open-thinking", data.agent_id),
      )) {
        const ref = owner.refs.get(thought.position);
        if (ref)
          index.replace(
            ref,
            finishThinkingParts(
              [thought.part],
              data.timestamp,
              data.agent_id,
            )[0],
          );
      }
    }
    if (eventType === "tool:args:chunk") {
      const delta = typeof data.content === "string" ? data.content : "";
      if (!delta) return true;
      const draftId = typeof id === "string" && id.trim() ? id : undefined;
      const local = draftId
        ? ["draft-agent-id", data.agent_id, draftId]
        : ["draft-agent", data.agent_id];
      const ref =
        index.local(index.root, local, !draftId) ||
        index.select(key("all", ...local), !draftId, !!draftId);
      if (ref)
        index.replace(
          ref,
          appendToolArgsDelta(
            [ref.slot.part],
            data.tool || "",
            draftId,
            delta,
            depth,
            data.agent_id,
            [],
          )[0],
        );
      else if (
        !draftId ||
        !index.select(key("all", "upgraded", data.agent_id, draftId))
      )
        this.add(
          index,
          owner,
          createGeneratingToolPart(
            data.tool || "",
            draftId,
            delta,
            depth,
            data.agent_id,
          ),
          depth,
        );
      return true;
    }
    if (eventType === "tool:start" && !todoTool) {
      if (
        id &&
        index.select(
          key(
            "all",
            data.agent_id ? "started-agent" : "started",
            id,
            ...(data.agent_id ? [data.agent_id] : []),
          ),
        )
      )
        return true;
      const replacement = createToolPart(
        data.tool || "",
        data.args || {},
        depth,
        data.agent_id,
        id,
        data.timestamp,
      );
      const upgrade = this.upgrade(index, replacement, depth);
      const dangling = !upgrade
        ? this.upgrade(index, replacement, depth, true)
        : undefined;
      if (upgrade || dangling)
        this.replaceUpgrade(
          index,
          (upgrade || dangling)!,
          replacement,
          !!dangling,
        );
      else this.add(index, owner, replacement, depth);
      if (!depth)
        message.toolCalls.push({
          id,
          name: data.tool || "",
          args: data.args || {},
        });
      return true;
    }
    if (eventType === "tool:result") {
      const interrupt = `${data.error || ""} ${String(data.result || "")}`;
      const normalized = interrupt.toLowerCase();
      if (
        data.tool === "ask_human" &&
        data.success === false &&
        (interrupt.includes("GraphInterrupt") ||
          ((normalized.includes("cancelled") ||
            normalized.includes("canceled")) &&
            (normalized.includes("another message") ||
              normalized.includes("before it could be completed"))))
      )
        return true;
      if (!depth && !id) {
        const ref = index.local(index.root, ["pending-name", data.tool || ""]);
        const result = processMessageEvent(
          eventType,
          data,
          ref ? [ref.slot.part] : [],
          "",
          [],
          0,
          [],
          this.streaming,
        );
        if (ref) index.replace(ref, result.parts[0]);
        else if (result.parts[0]) index.append(index.root, result.parts[0]);
        if (result.toolResult)
          (message.toolResults ??= []).push(result.toolResult);
        return true;
      }
      const ref = index.result(id || "", depth, data.agent_id);
      if (ref)
        index.replace(
          ref,
          updateToolResultInDepth(
            [ref.slot.part],
            id || "",
            data.result || "",
            data.success !== false,
            data.error,
            (ref.slot.part as ToolPart).depth || 0,
            data.agent_id,
            data.timestamp,
          )[0],
        );
      else if (data.tool) {
        const completed = processMessageEvent(
          eventType,
          data,
          [],
          "",
          [],
          depth,
          [],
          this.streaming,
        ).parts[0] as ToolPart;
        const draft = this.upgrade(index, completed, depth);
        if (draft) this.replaceUpgrade(index, draft, completed);
        else this.add(index, owner, completed, depth);
      }
      return true;
    }
    if (eventType === "message:chunk" && !depth) {
      const content = data.content || "";
      if (!content) return true;
      this.add(index, index.root, { type: "text", content }, 0);
      message.content += content;
      return true;
    }
    if (
      [
        "thinking",
        "message:chunk",
        "todo:updated",
        "summary",
        "artifact:result",
        "recommend:questions",
        "followup:questions",
      ].includes(eventType) ||
      (todoTool && eventType === "tool:start")
    ) {
      const fresh =
        eventType === "thinking"
          ? data.content
            ? createThinkingPart(
                data.content,
                data.thinking_id,
                depth,
                data.agent_id,
                this.streaming,
                data.timestamp,
              )
            : undefined
          : eventType === "message:chunk"
            ? data.content
              ? {
                  type: "text" as const,
                  content: data.content,
                  depth,
                  agent_id: data.agent_id,
                }
              : undefined
            : processMessageEvent(
                eventType,
                data,
                [],
                "",
                [],
                depth,
                [],
                this.streaming,
              ).parts[0];
      if (fresh) {
        if (!depth && fresh.type === "todo") {
          const targets = index.root.slots.all(historySlotKey("type", "todo"));
          if (!targets.length) index.append(index.root, fresh);
          else
            for (const target of targets)
              index.root.slots.replace(target, fresh);
        } else this.add(index, owner, fresh, depth);
      }
      return true;
    }
    return false;
  }
}

/** Ordered pending executions without repeated array scans or middle splices. */
export class HistoryReplayStack {
  private readonly entries = new Map<number, SubagentStackItem>();
  private readonly exact = new Map<string, Set<number>>();
  private readonly agents = new Map<string, Set<number>>();
  private nextId = 0;
  private readonly depths = new Map<string, number[]>();
  constructor(private readonly output: SubagentStackItem[]) {
    for (const item of output) this.insert(item);
  }
  private key(item: SubagentStackItem): string {
    return key(item.agent_id, item.message_id, item.depth, item.agent_call_id);
  }
  private agent(item: SubagentStackItem): string {
    return item.agent_call_id
      ? key("call", item.agent_call_id, item.message_id)
      : key("agent", item.agent_id, item.message_id);
  }
  private insert(item: SubagentStackItem): void {
    const id = this.nextId++;
    this.entries.set(id, item);
    const depthKey = key(item.message_id, item.depth);
    let depthIds = this.depths.get(depthKey);
    if (!depthIds) this.depths.set(depthKey, (depthIds = []));
    depthIds.push(id);
    for (const [map, key] of [
      [this.exact, this.key(item)],
      [this.agents, this.agent(item)],
    ] as const) {
      let ids = map.get(key);
      if (!ids) map.set(key, (ids = new Set()));
      ids.add(id);
    }
  }
  latest(messageId: string, depth: number): string | undefined {
    let latest = -1;
    for (const level of [depth, depth - 1]) {
      const ids = this.depths.get(key(messageId, level));
      while (ids?.length && !this.entries.has(ids[ids.length - 1])) ids.pop();
      if (ids?.length) latest = Math.max(latest, ids[ids.length - 1]);
    }
    return this.entries.get(latest)?.agent_id;
  }
  add(item: SubagentStackItem): void {
    if (!this.exact.has(this.key(item))) this.insert(item);
  }
  remove(agent_id: string, message_id: string, agent_call_id?: string): void {
    const ids = this.agents.get(
      agent_call_id
        ? key("call", agent_call_id, message_id)
        : key("agent", agent_id, message_id),
    );
    const id = ids?.values().next().value;
    if (id === undefined) return;
    const item = this.entries.get(id)!;
    this.entries.delete(id);
    for (const [map, key] of [
      [this.exact, this.key(item)],
      [this.agents, this.agent(item)],
    ] as const) {
      const group = map.get(key)!;
      group.delete(id);
      if (!group.size) map.delete(key);
    }
  }
  clear(): void {
    this.entries.clear();
    this.exact.clear();
    this.agents.clear();
    this.depths.clear();
    this.output.length = 0;
  }
  flush(): void {
    this.output.length = 0;
    for (const item of this.entries.values()) this.output.push(item);
  }
}
