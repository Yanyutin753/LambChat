/** Root-part references survive private append/replace updates; old heap entries expire lazily. */
import type { MessagePart } from "../../types";
import { historyReplayKey } from "./historyReplayKey";

// Adjacent float labels keep repeated late inserts between their anchor and the draft tail.
function nextPosition(position: number): number {
  if (position === 0) return Number.MIN_VALUE;
  const value = new Float64Array([position]);
  const bits = new BigUint64Array(value.buffer);
  bits[0] += position < 0 ? -1n : 1n;
  return value[0];
}

export interface HistoryPartSlot {
  position: number;
  part: MessagePart;
  keys: string[];
}

class SlotHeap {
  private readonly values: HistoryPartSlot[] = [];
  constructor(private readonly last: boolean) {}
  private before(a: HistoryPartSlot, b: HistoryPartSlot): boolean {
    return this.last ? a.position > b.position : a.position < b.position;
  }
  add(value: HistoryPartSlot): void {
    let index = this.values.length;
    this.values.push(value);
    while (index) {
      const parent = (index - 1) >> 1;
      if (!this.before(value, this.values[parent])) break;
      this.values[index] = this.values[parent];
      index = parent;
    }
    this.values[index] = value;
  }
  get(
    current: ReadonlyMap<number, HistoryPartSlot>,
  ): HistoryPartSlot | undefined {
    while (this.values.length) {
      const first = this.values[0];
      if (current.get(first.position) === first) return first;
      const tail = this.values.pop()!;
      if (!this.values.length) break;
      let index = 0;
      while (index * 2 + 1 < this.values.length) {
        let child = index * 2 + 1;
        if (
          child + 1 < this.values.length &&
          this.before(this.values[child + 1], this.values[child])
        )
          child++;
        if (!this.before(this.values[child], tail)) break;
        this.values[index] = this.values[child];
        index = child;
      }
      this.values[index] = tail;
    }
    return undefined;
  }
}

export const historySlotKey = (kind: string, value?: unknown): string =>
  historyReplayKey(kind, value);
export const historyArtifactKey = (
  part: Extract<MessagePart, { type: "artifact" }>,
): string => {
  const artifact = part.artifact;
  return "path" in artifact && artifact.path
    ? artifact.path
    : artifact.preview?.previewKey ?? artifact.id ?? "";
};

export class HistoryPartSlots {
  private readonly records = new Map<number, HistoryPartSlot>();
  private readonly members = new Map<string, Map<number, HistoryPartSlot>>();
  private readonly heaps = new Map<
    string,
    { first: SlotHeap; last: SlotHeap }
  >();
  private length = 0;
  private deferred = false;
  constructor(
    readonly parts: MessagePart[],
    private readonly changed?: (
      slot: HistoryPartSlot,
      previous?: HistoryPartSlot,
    ) => void,
  ) {
    this.sync();
  }
  sync(): void {
    while (this.length < this.parts.length) this.record(this.length++);
  }
  record(position: number): void {
    const part = this.parts[position];
    const previous = this.records.get(position);
    if (!part || previous?.part === part) return;
    for (const key of previous?.keys || [])
      this.members.get(key)?.delete(position);
    const keys = [historySlotKey("type", part.type)];
    if (part.type === "tool") {
      keys.push(historySlotKey("tool", part.id));
      if (part.name === "ask_human" && part.isPending)
        keys.push(historySlotKey("ask"), historySlotKey("ask", part.id));
    } else if (part.type === "thinking") {
      if (part.startedAt !== undefined && part.completedAt === undefined)
        keys.push(historySlotKey("open-thinking", part.agent_id));
    } else if (part.type === "artifact")
      keys.push(historySlotKey("artifact", historyArtifactKey(part)));
    else if (part.type === "summary") {
      keys.push(historySlotKey("summary", part.summary_id));
      if (part.summary_id == null) keys.push(historySlotKey("summary-stub"));
    }
    const entry = { position, part, keys };
    this.records.set(position, entry);
    for (const key of keys) {
      let members = this.members.get(key);
      if (!members) this.members.set(key, (members = new Map()));
      members.set(position, entry);
      let heaps = this.heaps.get(key);
      if (!heaps)
        this.heaps.set(
          key,
          (heaps = { first: new SlotHeap(false), last: new SlotHeap(true) }),
        );
      heaps.first.add(entry);
      heaps.last.add(entry);
    }
    this.changed?.(entry, previous);
  }
  insertAfter(position: number, part: MessagePart): HistoryPartSlot {
    let inserted = nextPosition(position);
    while (this.records.has(inserted)) inserted = nextPosition(inserted);
    this.parts[inserted] = part;
    this.record(inserted);
    this.deferred = true;
    return this.records.get(inserted)!;
  }
  remove(slot: HistoryPartSlot): void {
    for (const key of slot.keys) this.members.get(key)?.delete(slot.position);
    this.records.delete(slot.position);
    delete this.parts[slot.position];
    this.deferred = true;
  }
  materialize(): boolean {
    if (!this.deferred) return false;
    const ordered = Array.from(this.records.values()).sort(
      (a, b) => a.position - b.position,
    );
    for (const slot of ordered)
      if (!Number.isInteger(slot.position)) delete this.parts[slot.position];
    this.parts.length = 0;
    for (const slot of ordered) this.parts.push(slot.part);
    this.deferred = false;
    return true;
  }
  first(key: string): HistoryPartSlot | undefined {
    return this.heaps.get(key)?.first.get(this.members.get(key) || new Map());
  }
  last(key: string): HistoryPartSlot | undefined {
    return this.heaps.get(key)?.last.get(this.members.get(key) || new Map());
  }
  all(key: string): HistoryPartSlot[] {
    return Array.from(this.members.get(key)?.values() || []);
  }
  replace(slot: HistoryPartSlot, part: MessagePart): HistoryPartSlot {
    this.parts[slot.position] = part;
    this.record(slot.position);
    return this.records.get(slot.position)!;
  }
  append(part: MessagePart): HistoryPartSlot {
    const position = this.parts.length;
    this.parts.push(part);
    this.sync();
    return this.records.get(position)!;
  }
}
