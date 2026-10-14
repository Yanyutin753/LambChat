/** Private history construction only; live message updates stay immutable. */
import type { Message, MessagePart, SubagentPart } from "../../types";
import type { EventData, SubagentStackItem } from "./types";
import i18n from "../../i18n";
import { markPendingToolsAwaiting } from "./suspendedToolParts";
import { processMessageEvent } from "./eventProcessor";
import { createToolPart, createThinkingPart, createSubagentPart, createGeneratingToolPart, updateSubagentResult, updateToolResultInDepth } from "./messageParts";

interface HistoryToolIndex {
  parts: MessagePart[];
  byId: Map<string, number>;
  thinkingById: Map<string | undefined, number>;
  drafts: Set<string>;
  aliases: Map<string, number>;
  pendingSlots: Map<string, number[]>;
  todoSlots: number[];
  pendingById: Map<string, number>;
}

function tryReplayTopLevelPart(
  message: Message,
  eventType: string,
  data: EventData,
  indexes: WeakMap<Message, HistoryToolIndex>,
  depth = 0,
): boolean {
  const cached = indexes.get(message);
  if (cached && cached.parts === message.parts && (data.depth || 0) === depth &&
    (eventType === "message:chunk" || eventType === "thinking")) {
    const content = data.content || "";
    if (typeof content !== "string") return false;
    if (!content) return true;
    if (eventType === "message:chunk") {
      const last = cached.parts[cached.parts.length - 1];
      if (!depth && last?.type === "tool" && last.argsPartial) {
        // One tail draft moves by one slot; preceding history and thinking indices stay fixed.
        const anchor = cached.parts.length - 1;
        const before = cached.parts[anchor - 1];
        if (cached.drafts.size !== 1 || !last.id || (before?.type === "tool" && before.argsPartial)) return false;
        if (before?.type === "text" && !before.depth) {
          cached.parts[anchor - 1] = { ...before, content: before.content + content };
        } else {
          cached.parts.splice(anchor, 0, { type: "text", content });
          cached.byId.set(last.id, anchor + 1);
          if (cached.pendingById.has(last.id)) cached.pendingById.set(last.id, anchor + 1);
        }
      } else if (last?.type === "text" && (depth > 0 || !last.depth)) {
        cached.parts[cached.parts.length - 1] = { ...last, content: last.content + content };
      } else {
        cached.parts.push(depth ? { type: "text", content, depth, agent_id: data.agent_id } : { type: "text", content });
      }
      message.content += content;
    } else {
      const position = cached.thinkingById.get(data.thinking_id);
      const existing = position !== undefined ? cached.parts[position] : undefined;
      if (position !== undefined && existing?.type === "thinking") {
        cached.parts[position] = { ...existing, content: existing.content + content, ...(depth ? { isStreaming: true } : {}) };
      } else {
        cached.thinkingById.set(data.thinking_id, cached.parts.length);
        cached.parts.push(createThinkingPart(content, data.thinking_id, depth, data.agent_id, false));
      }
    }
    return true;
  }
  const todoUpdate = eventType === "todo:updated" || (eventType === "tool:start" &&
    ["todo_write", "write_todos"].includes(data.tool || ""));
  const awaitingEvent = eventType === "hitl:suspended" || eventType === "human_resume_started";
  const approvalEvent = eventType === "approval_resolved";
  const controlEvent = todoUpdate || awaitingEvent || approvalEvent;
  if (!controlEvent && !["tool:start", "tool:result", "tool:args:chunk"].includes(eventType)) return false;
  const id = data.tool_call_id;
  // shortcut: complex tool histories keep the shared processor; extend only with equivalence tests.
  if ((data.depth || 0) !== depth || (!controlEvent &&
    (typeof id !== "string" || !id || ["ask_human", "todo_write", "write_todos"].includes(data.tool || "")))) {
    indexes.delete(message);
    return false;
  }
  let index = indexes.get(message);
  if (!index || index.parts !== message.parts) {
    indexes.delete(message);
    index = { parts: message.parts || [], byId: new Map(), thinkingById: new Map(), drafts: new Set(), aliases: new Map(), pendingSlots: new Map(), todoSlots: [], pendingById: new Map() };
    for (let position = 0; position < index.parts.length; position++) {
      const part = index.parts[position];
      if (part.type === "subagent") return false;
      if (part.type === "thinking") index.thinkingById.set(part.thinking_id, position);
      if (part.type === "todo") index.todoSlots.push(position);
      if (part.type !== "tool") continue;
      if (!part.id || (part.depth || 0) !== depth || index.byId.has(part.id)) return false;
      index.byId.set(part.id, position);
      if (part.isPending && part.result === undefined) index.pendingById.set(part.id, position);
      if (part.argsPartial) index.drafts.add(part.id);
      if (part.alias_id) index.aliases.set(JSON.stringify([part.alias_id, part.agent_id]), position);
      if (part.result === undefined && !part.argsPartial && !part.cancelled) {
        const signature = JSON.stringify([part.name, JSON.stringify(part.args)]);
        let slots = index.pendingSlots.get(signature);
        if (!slots) index.pendingSlots.set(signature, slots = []);
        slots.push(position);
      }
    }
    indexes.set(message, index);
  }
  if (awaitingEvent) {
    for (const [id, slot] of index.pendingById) {
      const part = index.parts[slot];
      if (part.type === "tool" && part.isPending && part.result === undefined) {
        index.parts[slot] = markPendingToolsAwaiting([part], eventType === "hitl:suspended")[0];
      } else index.pendingById.delete(id);
    }
    return true;
  }
  if (approvalEvent) {
    const ids = approvalToolIds(data);
    if (!ids.length || ids.some(id => !index.byId.has(id))) return false;
    const result = approvalResult(data);
    for (const id of ids) {
      const slot = index.byId.get(id)!;
      const part = index.parts[slot];
      index.parts[slot] = updateToolResultInDepth([part], id, result, data.success !== false,
        data.error, depth, data.agent_id, data.timestamp)[0];
      index.pendingById.delete(id);
      index.drafts.delete(id);
    }
    return true;
  }
  if (todoUpdate) {
    // Keep conversion and every item field authoritative, without passing the growing history.
    const todo = processMessageEvent(eventType, data, [], "", [], 0, [], false).parts[0];
    if (todo?.type !== "todo") return true; // empty updates leave the existing checklist untouched.
    if (!index.todoSlots.length) {
      index.todoSlots.push(index.parts.length);
      index.parts.push(todo);
    } else if (depth) {
      index.parts[index.todoSlots[0]] = todo; // shared child merge updates the first checklist.
    } else {
      for (const slot of index.todoSlots) index.parts[slot] = todo; // shared root upsert replaces all.
    }
    message.parts = index.parts;
    return true;
  }
  if (typeof id !== "string" || !id) return false;
  const position = index.byId.get(id);
  if (eventType === "tool:args:chunk") {
    const delta = typeof data.content === "string" ? data.content : "";
    if (!delta) return true;
    const existing = position === undefined ? undefined : index.parts[position];
    if (existing?.type === "tool") {
      if (existing.agent_id !== data.agent_id) return false;
      if (!existing.argsPartial) return true;
      index.parts[position!] = { ...existing, args: { partial: (typeof existing.args.partial === "string" ? existing.args.partial : "") + delta } };
      return true;
    }
    if (index.aliases.has(JSON.stringify([id, data.agent_id]))) return true;
    index.byId.set(id, index.parts.length);
    index.drafts.add(id);
    index.pendingById.set(id, index.parts.length);
    index.parts.push(createGeneratingToolPart(data.tool || "", id, delta, depth, data.agent_id));
    message.parts = index.parts;
    return true;
  }
  if (eventType === "tool:start") {
    const existing = position === undefined ? undefined : index.parts[position];
    if (existing?.type === "tool" && (!existing.argsPartial || existing.result !== undefined) &&
      (!data.agent_id || existing.agent_id === data.agent_id)) return true;
    const singleDraftId = index.drafts.size === 1 ? index.drafts.values().next().value : undefined;
    const upgradePosition = position !== undefined && index.drafts.has(id) ? position
      : position === undefined && singleDraftId ? index.byId.get(singleDraftId) : undefined;
    if (upgradePosition !== undefined) {
      const generating = index.parts[upgradePosition];
      if (generating.type !== "tool" || (depth && generating.agent_id !== data.agent_id) || depth > 1) return false;
      const replacement = createToolPart(data.tool || "", data.args || {}, depth, data.agent_id, id, data.timestamp);
      const alias = generating.id && generating.id !== id ? generating.id : replacement.alias_id;
      index.parts[upgradePosition] = { ...replacement, startedAt: generating.startedAt ?? replacement.startedAt, alias_id: alias };
      if (generating.id) { index.drafts.delete(generating.id); index.byId.delete(generating.id); index.pendingById.delete(generating.id); }
      if (generating.alias_id) index.aliases.delete(JSON.stringify([generating.alias_id, generating.agent_id]));
      index.byId.set(id, upgradePosition);
      index.pendingById.set(id, upgradePosition);
      if (alias) index.aliases.set(JSON.stringify([alias, data.agent_id]), upgradePosition);
      const signature = signatureOf(replacement.name, replacement.args);
      let slots = index.pendingSlots.get(signature);
      if (!slots) index.pendingSlots.set(signature, slots = []);
      slots.push(upgradePosition);
      if (!depth) (message.toolCalls ??= []).push({ id, name: replacement.name, args: replacement.args });
      return true;
    }
    if (position !== undefined) {
      const existing = index.parts[position];
      if (existing.type === "tool" && (!data.agent_id || existing.agent_id === data.agent_id)) return true;
      indexes.delete(message);
      return false;
    }
    if (index.drafts.size) return false; // name/last-draft upgrade may target a different ID.
    const name = data.tool || "";
    const args = data.args || {};
    const signature = JSON.stringify([name, JSON.stringify(args)]);
    // Lazy removal is amortized linear and preserves the shared last matching pending slot.
    const slots = index.pendingSlots.get(signature);
    while (slots?.length) {
      const slot = slots[slots.length - 1];
      const pending = index.parts[slot];
      if (pending.type === "tool" && !pending.argsPartial && !pending.cancelled && pending.result === undefined &&
        signatureOf(pending.name, pending.args) === signature) {
        if (depth > 1) return false; // shared depth recursion does not target flat depth-2 cards.
        if (pending.id) { index.byId.delete(pending.id); index.pendingById.delete(pending.id); }
        if (pending.alias_id) index.aliases.delete(JSON.stringify([pending.alias_id, pending.agent_id]));
        index.byId.set(id, slot);
        index.pendingById.set(id, slot);
        index.parts[slot] = createToolPart(name, args, depth, data.agent_id, id, data.timestamp);
        if (!depth) (message.toolCalls ??= []).push({ id, name, args });
        return true;
      }
      slots.pop();
    }
    index.byId.set(id, index.parts.length);
    index.pendingById.set(id, index.parts.length);
    index.parts.push(createToolPart(name, args, depth, data.agent_id, id, data.timestamp));
    message.parts = index.parts;
    if (!depth) (message.toolCalls ??= []).push({ id, name, args });
    let pendingSlots = index.pendingSlots.get(signature);
    if (!pendingSlots) index.pendingSlots.set(signature, pendingSlots = []);
    pendingSlots.push(index.parts.length - 1);
    return true;
  }
  if (position === undefined) {
    indexes.delete(message);
    return false;
  }
  const part = index.parts[position];
  if (part.type !== "tool") return false;
  index.drafts.delete(id);
  index.pendingById.delete(id);
  index.parts[position] = updateToolResultInDepth([part], id, data.result || "", data.success !== false,
    data.error, depth, data.agent_id, data.timestamp)[0];
  return true;
}


interface HistoryTreeIndex {
  parts: MessagePart[];
  agents: Map<string, { slot: number; message: Message }>;
  tools: Map<string, { parts: MessagePart[]; slot: number }>;
  owners: Map<MessagePart[], Map<number, string>>;
  aliases: Map<string, { parts: MessagePart[]; slot: number }>;
  pending: Map<string, { parts: MessagePart[]; slot: number }>;
  containers: Map<MessagePart[], { depth: number; agentId: string; message: Message }>;
}

const signatureOf = (name: string, args: unknown) => JSON.stringify([name, JSON.stringify(args)]);
const agentKey = (depth: number, agent: string) => JSON.stringify([depth, agent]);
const approvalToolIds = (data: EventData): string[] => {
  const batch = Array.isArray(data.tool_call_ids) ? data.tool_call_ids.filter(
    (id): id is string => typeof id === "string" && id.length > 0,
  ) : [];
  return batch.length ? batch : typeof data.tool_call_id === "string" && data.tool_call_id ? [data.tool_call_id] : [];
};
const approvalResult = (data: EventData) => typeof data.result === "object" && data.result !== null
  ? data.result : { status: data.success === false ? "rejected" : "success" };


/** Explicit execution routing stays indexed; ambiguous drafts, recovery and late callbacks fall back intact. */
export class HistoryPartReplay {
  private readonly indexes = new WeakMap<Message, HistoryToolIndex>();
  private readonly trees = new WeakMap<Message, HistoryTreeIndex>();

  replay(message: Message, eventType: string, data: EventData): boolean {
    const depth = data.depth || 0;
    const todoTool = ["todo_write", "write_todos"].includes(data.tool || "");
    const todoUpdate = eventType === "todo:updated" || (todoTool && eventType === "tool:start");
    const awaitingEvent = eventType === "hitl:suspended" || eventType === "human_resume_started";
    const approvalEvent = eventType === "approval_resolved";
    message.toolCalls ??= [];
    if (todoTool && (eventType === "tool:args:chunk" || eventType === "tool:result")) return true;
    if (!depth && !this.trees.has(message) && tryReplayTopLevelPart(message, eventType, data, this.indexes)) return true;
    if (!depth && (eventType === "agent:call" || eventType === "agent:result")) return false;
    if (depth && !awaitingEvent && !approvalEvent && (typeof data.agent_id !== "string" || !data.agent_id)) return false;
    if (!["agent:call", "agent:result", "tool:start", "tool:result", "tool:args:chunk", "thinking", "message:chunk", "todo:updated", "hitl:suspended", "human_resume_started", "approval_resolved"].includes(eventType)) {
      this.indexes.delete(message);
      this.trees.delete(message);
      return false;
    }
    let tree = this.trees.get(message);
    if (!tree || tree.parts !== message.parts) {
      tree = { parts: message.parts || [], agents: new Map(), tools: new Map(), owners: new Map(), aliases: new Map(), pending: new Map(), containers: new Map() };
      for (let slot = 0; slot < tree.parts.length; slot++) {
        const part = tree.parts[slot];
        if (part.type !== "subagent") {
          if (part.type === "tool") {
            if (!part.id || part.depth || tree.tools.has(part.id)) return false;
            tree.tools.set(part.id, { parts: tree.parts, slot });
            if (part.isPending && part.result === undefined) tree.pending.set(part.id, { parts: tree.parts, slot });
            if (part.alias_id) tree.aliases.set(JSON.stringify([part.alias_id, part.agent_id]), { parts: tree.parts, slot });
            let owners = tree.owners.get(tree.parts);
            if (!owners) tree.owners.set(tree.parts, owners = new Map());
            owners.set(slot, part.id);
          }
          continue;
        }
        const key = agentKey(part.depth || 0, part.agent_id);
        if (tree.agents.has(key)) return false;
        const child: Message = { ...message, parts: part.parts || [], content: "", toolCalls: [] };
        tree.agents.set(key, { slot, message: child });
        tree.containers.set(child.parts!, { depth: part.depth || 0, agentId: part.agent_id, message: child });
        for (let childSlot = 0; childSlot < child.parts!.length; childSlot++) {
          const tool = child.parts![childSlot];
          if (tool.type === "subagent") return false;
          if (tool.type !== "tool") continue;
          if (!tool.id || (tool.depth || 0) !== (part.depth || 0) || tree.tools.has(tool.id)) return false;
          tree.tools.set(tool.id, { parts: child.parts!, slot: childSlot });
          if (tool.isPending && tool.result === undefined) tree.pending.set(tool.id, { parts: child.parts!, slot: childSlot });
          if (tool.alias_id) tree.aliases.set(JSON.stringify([tool.alias_id, tool.agent_id]), { parts: child.parts!, slot: childSlot });
          let owners = tree.owners.get(child.parts!);
          if (!owners) tree.owners.set(child.parts!, owners = new Map());
          owners.set(childSlot, tool.id);
        }
      }
      const rootIndex: HistoryToolIndex = { parts: tree.parts, byId: new Map(), thinkingById: new Map(), drafts: new Set(), aliases: new Map(), pendingSlots: new Map(), todoSlots: [], pendingById: new Map() };
      tree.parts.forEach((part, slot) => {
        if (part.type === "thinking") rootIndex.thinkingById.set(part.thinking_id, slot);
        if (part.type === "todo") rootIndex.todoSlots.push(slot);
        if (part.type === "tool" && part.id) {
          rootIndex.byId.set(part.id, slot);
          if (part.isPending && part.result === undefined) rootIndex.pendingById.set(part.id, slot);
          if (part.argsPartial) rootIndex.drafts.add(part.id);
          if (part.alias_id) rootIndex.aliases.set(JSON.stringify([part.alias_id, part.agent_id]), slot);
          if (part.result === undefined && !part.argsPartial && !part.cancelled) {
            const signature = signatureOf(part.name, part.args);
            let slots = rootIndex.pendingSlots.get(signature);
            if (!slots) rootIndex.pendingSlots.set(signature, slots = []);
            slots.push(slot);
          }
        }
      });
      this.indexes.set(message, rootIndex);
      this.trees.set(message, tree);
    }
    const fallback = () => { this.indexes.delete(message); this.trees.delete(message); return false; };
    if (awaitingEvent) {
      for (const [id, location] of tree.pending) {
        const part = location.parts[location.slot];
        if (part.type === "tool" && part.isPending && part.result === undefined) {
          location.parts[location.slot] = markPendingToolsAwaiting([part], eventType === "hitl:suspended")[0];
        } else tree.pending.delete(id);
      }
      return true;
    }
    if (approvalEvent) {
      const ids = approvalToolIds(data);
      if (!ids.length) return fallback();
      // Validate the entire batch before mutation, including the original root/child scope rules.
      for (const id of ids) {
        const location = tree.tools.get(id);
        if (!location) return fallback();
        const part = location.parts[location.slot];
        if (part.type !== "tool") return fallback();
        const container = tree.containers.get(location.parts);
        if (!container && (part.depth || 0) !== depth) return fallback();
        if (container && data.agent_id && container.depth === depth && container.agentId !== data.agent_id) return fallback();
      }
      const result = approvalResult(data);
      for (const id of ids) {
        const location = tree.tools.get(id)!;
        const part = location.parts[location.slot];
        location.parts[location.slot] = updateToolResultInDepth([part], id, result, data.success !== false,
          data.error, part.type === "tool" ? part.depth || 0 : depth, data.agent_id, data.timestamp)[0];
        tree.pending.delete(id);
        const container = tree.containers.get(location.parts);
        const index = this.indexes.get(container?.message || message);
        if (index && index.parts === location.parts) { index.pendingById.delete(id); index.drafts.delete(id); }
      }
      return true;
    }
    const key = agentKey(depth, data.agent_id || "");
    const target = depth ? tree.agents.get(key) : { slot: -1, message };
    if (eventType === "agent:call") {
      if (!data.agent_id) return fallback();
      if (target) return fallback(); // queued/resumed/repeated executions retain shared recovery semantics.
      const part = createSubagentPart(data.agent_id, data.agent_name || data.agent_id || i18n.t("chat.unknownAgent"),
        data.input || "", depth, data.timestamp, data.agent_avatar, data.status);
      const child: Message = { ...message, parts: part.parts, content: "", toolCalls: [] };
      this.indexes.set(child, { parts: child.parts!, byId: new Map(), thinkingById: new Map(), drafts: new Set(), aliases: new Map(), pendingSlots: new Map(), todoSlots: [], pendingById: new Map() });
      tree.agents.set(key, { slot: tree.parts.length, message: child });
      tree.containers.set(child.parts!, { depth, agentId: data.agent_id, message: child });
      tree.parts.push(part);
      message.parts = tree.parts;
      return true;
    }
    if (!target) return fallback();
    const agent = depth ? tree.parts[target.slot] as SubagentPart : undefined;
    if (eventType === "agent:result") {
      // Reuse the exact settlement helper on the one uniquely addressed execution.
      if (!agent || !data.agent_id) return fallback();
      tree.parts[target.slot] = updateSubagentResult([agent], data.agent_id, String(data.result || ""),
        data.success !== false, depth, data.error, data.timestamp, data.status)[0];
      const settled = tree.parts[target.slot] as SubagentPart;
      target.message.parts = settled.parts || [];
      if (settled.parts !== agent.parts) {
        this.indexes.delete(target.message);
        for (const part of agent.parts || []) if (part.type === "tool" && part.id) { tree.tools.delete(part.id); tree.pending.delete(part.id); }
        tree.containers.set(target.message.parts, { depth, agentId: data.agent_id, message: target.message });
        target.message.parts.forEach((part, slot) => {
          if (part.type === "tool" && part.id) {
            tree!.tools.set(part.id, { parts: target.message.parts!, slot });
            if (part.isPending && part.result === undefined) tree!.pending.set(part.id, { parts: target.message.parts!, slot });
            let owners = tree!.owners.get(target.message.parts!);
            if (!owners) tree!.owners.set(target.message.parts!, owners = new Map());
            owners.set(slot, part.id);
          }
        });
      }
      return true;
    }
    if (agent && !agent.isPending) return fallback(); // late child events must inherit settled loading states.
    const id = data.tool_call_id;
    const existing = typeof id === "string" ? tree.tools.get(id) : undefined;
    if (eventType === "tool:args:chunk") {
      if (existing && existing.parts !== target.message.parts) return fallback();
      const key = JSON.stringify([id, data.agent_id]);
      const alias = tree.aliases.get(key);
      const part = alias?.parts[alias.slot];
      if (part?.type === "tool" && part.alias_id === id && part.agent_id === data.agent_id && alias?.parts !== target.message.parts) return fallback();
    }
    if (eventType === "tool:start" && !todoUpdate) {
      if (existing) {
        const part = existing.parts[existing.slot];
        if (part.type === "tool" && !part.argsPartial && (!data.agent_id || part.agent_id === data.agent_id)) return true;
        if (part.type === "tool" && part.argsPartial && existing.parts === target.message.parts) {
          // Exact ID upgrade stays inside its explicit execution; other draft targets fall back.
        } else return fallback();
      }
    } else if (eventType === "tool:result" && (!existing || existing.parts !== target.message.parts)) {
      return fallback();
    }
    if (!tryReplayTopLevelPart(target.message, eventType, data, this.indexes, depth)) return fallback();
    if (agent) agent.parts = target.message.parts;
    if (!depth && eventType === "message:chunk") {
      const last = target.message.parts?.[target.message.parts.length - 1];
      if (last?.type === "tool" && last.argsPartial && last.id) {
        const slot = this.indexes.get(target.message)?.byId.get(last.id);
        const old = tree.tools.get(last.id);
        if (slot !== undefined && old && slot !== old.slot) {
          const owners = tree.owners.get(target.message.parts!);
          owners?.delete(old.slot);
          owners?.set(slot, last.id);
          tree.tools.set(last.id, { parts: target.message.parts!, slot });
          if (tree.pending.has(last.id)) tree.pending.set(last.id, { parts: target.message.parts!, slot });
        }
      }
    }
    if (eventType === "tool:result" && typeof id === "string") tree.pending.delete(id);
    if (!todoUpdate && (eventType === "tool:start" || eventType === "tool:args:chunk") && typeof id === "string") {
      const slot = this.indexes.get(target.message)?.byId.get(id);
      if (slot === undefined) return true; // ignored late alias delta.
      let owners = tree.owners.get(target.message.parts!);
      if (!owners) tree.owners.set(target.message.parts!, owners = new Map());
      const replaced = owners.get(slot);
      if (replaced && replaced !== id) { tree.tools.delete(replaced); tree.pending.delete(replaced); }
      owners.set(slot, id);
      tree.tools.set(id, { parts: target.message.parts!, slot });
      const part = target.message.parts![slot];
      if (part.type === "tool" && part.isPending && part.result === undefined) tree.pending.set(id, { parts: target.message.parts!, slot });
      else tree.pending.delete(id);
      if (part.type === "tool" && part.alias_id) {
        tree.aliases.set(JSON.stringify([part.alias_id, part.agent_id]), { parts: target.message.parts!, slot });
      }
    }
    return true;
  }
}


/** Ordered pending executions without repeated array scans or middle splices. */
export class HistoryReplayStack {
  private readonly entries = new Map<number, SubagentStackItem>();
  private readonly exact = new Map<string, Set<number>>();
  private readonly agents = new Map<string, Set<number>>();
  private nextId = 0;
  constructor(private readonly output: SubagentStackItem[]) {
    for (const item of output) this.insert(item);
  }
  private key(item: SubagentStackItem): string { return JSON.stringify([item.agent_id, item.message_id, item.depth]); }
  private agent(item: SubagentStackItem): string { return JSON.stringify([item.agent_id, item.message_id]); }
  private insert(item: SubagentStackItem): void {
    const id = this.nextId++;
    this.entries.set(id, item);
    for (const [map, key] of [[this.exact, this.key(item)], [this.agents, this.agent(item)]] as const) {
      let ids = map.get(key);
      if (!ids) map.set(key, ids = new Set());
      ids.add(id);
    }
  }
  add(item: SubagentStackItem): void { if (!this.exact.has(this.key(item))) this.insert(item); }
  remove(agent_id: string, message_id: string): void {
    const ids = this.agents.get(JSON.stringify([agent_id, message_id]));
    const id = ids?.values().next().value;
    if (id === undefined) return;
    const item = this.entries.get(id)!;
    this.entries.delete(id);
    for (const [map, key] of [[this.exact, this.key(item)], [this.agents, this.agent(item)]] as const) {
      const group = map.get(key)!;
      group.delete(id);
      if (!group.size) map.delete(key);
    }
  }
  clear(): void { this.entries.clear(); this.exact.clear(); this.agents.clear(); this.output.length = 0; }
  flush(): void {
    this.output.length = 0;
    for (const item of this.entries.values()) this.output.push(item);
  }
}
