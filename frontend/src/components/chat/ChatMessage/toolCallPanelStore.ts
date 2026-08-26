import type { CollapsibleStatus } from "../../common/CollapsiblePill";
import type { Message, MessagePart, ToolPart } from "../../../types";

export interface ToolCallPanelData {
  /** Tool call ID (part.id) */
  toolCallId: string;
  toolName: string;
  formattedToolName: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
  status: CollapsibleStatus;
}

type Listener = () => void;

function shallowEqual(a: ToolCallPanelData, b: ToolCallPanelData): boolean {
  return (
    a.toolCallId === b.toolCallId &&
    a.toolName === b.toolName &&
    a.formattedToolName === b.formattedToolName &&
    a.args === b.args &&
    a.status === b.status &&
    a.isPending === b.isPending &&
    a.cancelled === b.cancelled &&
    a.success === b.success &&
    a.startedAt === b.startedAt &&
    a.completedAt === b.completedAt &&
    a.result === b.result
  );
}

export interface ToolCallPanelStore {
  clear: () => void;
  delete: (toolCallId: string) => void;
  get: (toolCallId: string) => ToolCallPanelData | undefined;
  set: (data: ToolCallPanelData) => void;
  subscribe: (toolCallId: string, listener: Listener) => () => void;
}

export function createToolCallPanelStore(): ToolCallPanelStore {
  const data = new Map<string, ToolCallPanelData>();
  const listeners = new Map<string, Set<Listener>>();

  function emit(toolCallId: string) {
    const subscribed = listeners.get(toolCallId);
    if (!subscribed) return;
    subscribed.forEach((listener) => listener());
  }

  return {
    clear() {
      const toolCallIds = [...data.keys()];
      data.clear();
      toolCallIds.forEach(emit);
    },
    delete(toolCallId) {
      if (!data.delete(toolCallId)) return;
      emit(toolCallId);
    },
    get(toolCallId) {
      return data.get(toolCallId);
    },
    set(next) {
      const prev = data.get(next.toolCallId);
      if (prev && shallowEqual(prev, next)) return;
      data.set(next.toolCallId, next);
      emit(next.toolCallId);
    },
    subscribe(toolCallId, listener) {
      const subscribed = listeners.get(toolCallId) ?? new Set<Listener>();
      subscribed.add(listener);
      listeners.set(toolCallId, subscribed);

      return () => {
        const current = listeners.get(toolCallId);
        if (!current) return;
        current.delete(listener);
        if (current.size === 0) listeners.delete(toolCallId);
      };
    },
  };
}

export const toolCallPanelStore = createToolCallPanelStore();

function deriveToolStatus(part: ToolPart): CollapsibleStatus {
  if (part.isPending) return "loading";
  if (part.cancelled) return "cancelled";
  if (part.success) return "success";
  if (part.result !== undefined) return "error";
  return "idle";
}

function normalizeToolArgs(
  args: Record<string, unknown>,
): Record<string, unknown> {
  if (args.partial === undefined) return args;
  try {
    return JSON.parse(args.partial as string) as Record<string, unknown>;
  } catch {
    return { partial: args.partial };
  }
}

// tool part 不可变替换：未变 part 保持引用，按引用缓存避免每次
// messages 变化都重跑 normalizeToolArgs 的 JSON.parse
const toolPanelDataCache = new WeakMap<ToolPart, ToolCallPanelData>();

function toToolCallPanelData(part: ToolPart): ToolCallPanelData | null {
  if (!part.id) return null;
  const cached = toolPanelDataCache.get(part);
  if (cached) return cached;

  const colonIndex = part.name.indexOf(":");
  const toolName =
    colonIndex > 0 ? part.name.substring(colonIndex + 1) : part.name;
  const formattedToolName = toolName
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");

  const data: ToolCallPanelData = {
    toolCallId: part.id,
    toolName,
    formattedToolName,
    args: normalizeToolArgs(part.args),
    result: part.result,
    success: part.success,
    isPending: part.isPending,
    cancelled: part.cancelled,
    startedAt: part.startedAt,
    completedAt: part.completedAt,
    status: deriveToolStatus(part),
  };
  toolPanelDataCache.set(part, data);
  return data;
}

function syncToolParts(parts: readonly MessagePart[]): void {
  parts.forEach((part) => {
    if (part.type === "tool") {
      const data = toToolCallPanelData(part);
      if (data) toolCallPanelStore.set(data);
      return;
    }
    if (part.type === "subagent" && part.parts) {
      syncToolParts(part.parts);
    }
  });
}

export function syncToolCallPanelStore(messages: readonly Message[]): void {
  messages.forEach((message) => syncToolParts(message.parts ?? []));
}
