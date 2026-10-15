/** Selector indexes for history's flat execution cards. No live arrays are mutated. */
import type { MessagePart, SubagentPart } from "../../types";
import { historyReplayKey as key } from "./historyReplayKey";
import { HistoryPartSlots, type HistoryPartSlot } from "./historyPartSlots";

export interface PartRef {
  slot: HistoryPartSlot;
  owner: PartContainer;
  alive: boolean;
  keys: string[];
}
export interface PartContainer {
  slots: HistoryPartSlots;
  parent?: PartRef;
  refs: Map<number, PartRef>;
}
export const toolCandidateKey = key;

/** Lazy deletion keeps replacements cheap without losing first/last selector order. */
class OrderedRefs {
  private values: PartRef[] = [];
  constructor(private readonly before: (a: PartRef, b: PartRef) => boolean) {}
  add(ref: PartRef): void {
    let i = this.values.length;
    this.values.push(ref);
    while (i) {
      const parent = (i - 1) >> 1;
      if (!this.before(ref, this.values[parent])) break;
      this.values[i] = this.values[parent];
      i = parent;
    }
    this.values[i] = ref;
  }
  peek(
    valid: (ref: PartRef) => boolean = (ref) => ref.alive,
  ): PartRef | undefined {
    while (this.values.length) {
      const first = this.values[0];
      if (valid(first)) return first;
      this.pop();
    }
  }
  pop(): PartRef | undefined {
    const first = this.values[0];
    const tail = this.values.pop();
    if (!tail || !this.values.length) return first;
    let i = 0;
    while (i * 2 + 1 < this.values.length) {
      let child = i * 2 + 1;
      if (
        child + 1 < this.values.length &&
        this.before(this.values[child + 1], this.values[child])
      )
        child++;
      if (!this.before(this.values[child], tail)) break;
      this.values[i] = this.values[child];
      i = child;
    }
    this.values[i] = tail;
    return first;
  }
}
const containerPosition = (ref: PartRef): number =>
  ref.owner.parent?.slot.position ?? -1;
const first = (a: PartRef, b: PartRef): boolean =>
  containerPosition(a) < containerPosition(b) ||
  (containerPosition(a) === containerPosition(b) &&
    a.slot.position < b.slot.position);
const last = (a: PartRef, b: PartRef): boolean =>
  containerPosition(a) > containerPosition(b) ||
  (containerPosition(a) === containerPosition(b) &&
    a.slot.position > b.slot.position);
const childResult = (a: PartRef, b: PartRef): boolean =>
  containerPosition(a) > containerPosition(b) ||
  (containerPosition(a) === containerPosition(b) &&
    a.slot.position < b.slot.position);
interface Group {
  first: OrderedRefs;
  last: OrderedRefs;
  result: OrderedRefs;
  members: Set<PartRef>;
}
const treeLast = (a: PartRef, b: PartRef): boolean => {
  const aRoot = a.owner.parent?.slot.position ?? a.slot.position;
  const bRoot = b.owner.parent?.slot.position ?? b.slot.position;
  return (
    aRoot > bRoot || (aRoot === bRoot && a.slot.position > b.slot.position)
  );
};
const group = (lastOrder = last): Group => ({
  first: new OrderedRefs(first),
  last: new OrderedRefs(lastOrder),
  result: new OrderedRefs(childResult),
  members: new Set(),
});

export class HistoryToolCandidates {
  readonly root: PartContainer;
  private readonly groups = new Map<string, Group>();
  private readonly depthGroups = new Map<string, Map<number, Group>>();
  private readonly depthHeads = new Map<string, OrderedRefs>();
  private readonly children = new Map<number, PartContainer>();
  nested = false;
  private readonly deferred = new Set<PartContainer>();
  constructor(parts: MessagePart[]) {
    this.root = this.container(parts);
  }
  private container(parts: MessagePart[], parent?: PartRef): PartContainer {
    const owner = { parent, refs: new Map() } as PartContainer;
    owner.slots = new HistoryPartSlots(parts, (slot) =>
      this.changed(owner, slot),
    );
    return owner;
  }
  private add(key: string, ref: PartRef): void {
    let entry = this.groups.get(key);
    if (!entry)
      this.groups.set(
        key,
        (entry = group(
          key === toolCandidateKey("all", "ask") ? treeLast : last,
        )),
      );
    entry.members.add(ref);
    entry.first.add(ref);
    entry.last.add(ref);
    entry.result.add(ref);
  }
  private retire(ref: PartRef): void {
    ref.alive = false;
    for (const candidate of ref.keys)
      this.groups.get(candidate)?.members.delete(ref);
    if (ref.slot.part.type === "tool" && ref.owner.parent) {
      const part = ref.slot.part;
      const ids =
        !part.id && part.isPending && part.id !== ""
          ? [part.id, ""]
          : [part.id];
      for (const id of ids) {
        const resultKey = key("child-result", id);
        const depth = (ref.owner.parent.slot.part as SubagentPart).depth ?? 0;
        const next = this.depthGroups.get(resultKey)?.get(depth)?.result.peek();
        if (next) this.depthHeads.get(resultKey)?.add(next);
      }
    }
  }
  private changed(owner: PartContainer, slot: HistoryPartSlot): void {
    const old = owner.refs.get(slot.position);
    if (old) {
      this.retire(old);
    }
    const ref: PartRef = { slot, owner, alive: true, keys: [] };
    owner.refs.set(slot.position, ref);
    const part = slot.part;
    const local = (...values: unknown[]) =>
      ref.keys.push(
        key(owner.parent ? owner.parent.slot.position : "root", ...values),
      );
    const global = (...values: unknown[]) =>
      ref.keys.push(key("all", ...values));
    local("part");
    local("type", part.type);
    if (part.type !== "tool" || !part.argsPartial) local("non-draft");
    const dirty =
      part.type === "tool"
        ? part.isPending || (part.argsPartial && part.result === undefined)
        : part.type === "thinking"
          ? part.isStreaming
          : part.type === "todo"
            ? part.isStreaming ||
              part.items.some(
                (item) =>
                  item.status === "pending" || item.status === "in_progress",
              )
            : (part.type === "sandbox" || part.type === "memoryStatus") &&
              part.status === "starting";
    if (dirty) local("loading");
    if (part.type === "tool") {
      local("id", part.id);
      local("id-depth", part.id, part.depth ?? 0);
      if (part.isPending) {
        local("pending-name", part.name);
        if (!part.id) local("anonymous-depth", part.depth ?? 0);
      }
      if (part.name === "ask_human" && part.isPending) global("ask");
      if (part.isPending && part.result === undefined)
        global("pending-awaiting", Boolean(part.awaitingConfirmation));
      if (part.argsPartial) {
        local("draft");
        local("draft-id", part.id);
        local("draft-name", part.name);
        local("draft-agent", part.agent_id);
        local("draft-agent-id", part.agent_id, part.id);
        global("draft-agent", part.agent_id);
        global("draft-agent-id", part.agent_id, part.id);
        if (owner.parent) {
          global("child-draft");
          global(
            "child-draft-parent",
            (owner.parent.slot.part as SubagentPart).agent_id,
          );
        }
      } else {
        global("upgraded", part.agent_id, part.id);
        if (part.alias_id) global("upgraded", part.agent_id, part.alias_id);
      }
      if (!part.argsPartial || part.result !== undefined) {
        global("started", part.id);
        global("started-agent", part.id, part.agent_id);
      }
      if (part.result === undefined && !part.argsPartial && !part.cancelled) {
        const signature = key(part.name, JSON.stringify(part.args));
        local("dangling", signature);
        if (owner.parent) {
          global("child-dangling", signature);
          global(
            "child-dangling-parent",
            signature,
            (owner.parent.slot.part as SubagentPart).agent_id,
          );
        }
      }
      if (owner.parent) {
        const parent = owner.parent.slot.part as SubagentPart;
        const resultIds =
          !part.id && part.isPending && part.id !== ""
            ? [part.id, ""]
            : [part.id];
        for (const resultId of resultIds) {
          const resultKey = key("child-result", resultId);
          ref.keys.push(
            resultKey,
            key("child-result-agent", resultId, parent.depth, parent.agent_id),
          );
          let depths = this.depthGroups.get(resultKey);
          if (!depths) this.depthGroups.set(resultKey, (depths = new Map()));
          let depthGroup = depths.get(parent.depth ?? 0);
          if (!depthGroup)
            depths.set(parent.depth ?? 0, (depthGroup = group()));
          depthGroup.result.add(ref);
          let heads = this.depthHeads.get(resultKey);
          if (!heads)
            this.depthHeads.set(
              resultKey,
              (heads = new OrderedRefs(childResult)),
            );
          heads.add(ref);
        }
      }
    } else if (part.type === "thinking") local("thinking", part.thinking_id);
    else if (part.type === "subagent") {
      if (owner.parent) this.nested = true;
      else {
        local("agent", part.depth, part.agent_id);
        local("route", part.depth);
        if (part.isPending) local("pending-agent", part.depth, part.agent_id);
        const existing = this.children.get(slot.position);
        // Lifecycle replacements retain execution identity (agent/depth); only their state changes.
        if (existing && existing.slots.parts === part.parts)
          existing.parent = ref;
        else {
          if (existing)
            for (const child of existing.refs.values()) this.retire(child);
          this.children.set(
            slot.position,
            this.container(part.parts || [], ref),
          );
        }
      }
    }
    for (const candidate of ref.keys) this.add(candidate, ref);
  }

  local(
    owner: PartContainer,
    selector: unknown[],
    reverse = false,
  ): PartRef | undefined {
    return this.select(
      key(owner.parent ? owner.parent.slot.position : "root", ...selector),
      reverse,
    );
  }
  select(
    candidate: string,
    reverse = false,
    resultOrder = false,
  ): PartRef | undefined {
    const entry = this.groups.get(candidate);
    return (
      resultOrder ? entry?.result : reverse ? entry?.last : entry?.first
    )?.peek();
  }
  all(candidate: string): PartRef[] {
    return Array.from(this.groups.get(candidate)?.members || []).filter(
      (ref) => ref.alive,
    );
  }
  child(ref: PartRef): PartContainer {
    return this.children.get(ref.slot.position)!;
  }
  replace(ref: PartRef, part: MessagePart): PartRef {
    ref.owner.slots.replace(ref.slot, part);
    return ref.owner.refs.get(ref.slot.position)!;
  }
  append(owner: PartContainer, part: MessagePart): PartRef {
    const slot = owner.slots.append(part);
    return owner.refs.get(slot.position)!;
  }
  loading(owner: PartContainer): PartRef[] {
    return this.all(
      key(owner.parent ? owner.parent.slot.position : "root", "loading"),
    );
  }
  remove(ref: PartRef): void {
    this.retire(ref);
    ref.owner.refs.delete(ref.slot.position);
    ref.owner.slots.remove(ref.slot);
    this.deferred.add(ref.owner);
  }
  insertAfter(owner: PartContainer, position: number, part: MessagePart): void {
    owner.slots.insertAfter(position, part);
    this.deferred.add(owner);
  }
  materialize(): boolean {
    let changed = false;
    for (const owner of this.deferred)
      changed = owner.slots.materialize() || changed;
    this.deferred.clear();
    return changed;
  }
  result(
    id: string | undefined,
    depth: number,
    agent?: string,
  ): PartRef | undefined {
    const exactRoot = this.local(this.root, ["id-depth", id, depth], true);
    const anonymousRoot = !id
      ? this.local(this.root, ["anonymous-depth", depth], true)
      : undefined;
    const direct =
      !exactRoot ||
      (anonymousRoot && anonymousRoot.slot.position > exactRoot.slot.position)
        ? anonymousRoot
        : exactRoot;
    if (direct) return direct;
    const candidate = key("child-result", id);
    if (!agent) return this.select(candidate, false, true);
    const exact = this.select(
      key("child-result-agent", id, depth, agent),
      false,
      true,
    );
    const depths = this.depthGroups.get(candidate);
    const heads = this.depthHeads.get(candidate);
    const valid = (ref: PartRef) => {
      const parent = ref.owner.parent?.slot.part as SubagentPart | undefined;
      return !!parent && depths?.get(parent.depth ?? 0)?.result.peek() === ref;
    };
    let other = heads?.peek(valid);
    let excluded: PartRef | undefined;
    if (
      other &&
      (other.owner.parent!.slot.part as SubagentPart).depth === depth
    ) {
      excluded = heads!.pop();
      other = heads!.peek(valid);
      // Duplicate representatives of the excluded group are expired by identity below.
      while (
        other &&
        (other.owner.parent!.slot.part as SubagentPart).depth === depth
      ) {
        heads!.pop();
        other = heads!.peek(valid);
      }
    }
    if (excluded) heads!.add(excluded);
    return !exact || (other && childResult(other, exact)) ? other : exact;
  }
}
