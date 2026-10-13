import type { MessagePart, SubagentPart } from "../../../types";

export interface SubagentPanelData {
  agentId: string;
  agentName: string;
  agentAvatar?: string;
  input: string;
  result?: string;
  success?: boolean;
  error?: string;
  isPending?: boolean;
  parts?: MessagePart[];
  history?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: SubagentPart["status"];
}

type Listener = () => void;

function shallowEqual(a: SubagentPanelData, b: SubagentPanelData): boolean {
  const partsEqual =
    a.parts === b.parts ||
    (Array.isArray(a.parts) &&
      Array.isArray(b.parts) &&
      a.parts.length === b.parts.length &&
      a.parts.every((part, index) => part === b.parts![index]));
  const historyEqual =
    a.history === b.history ||
    (a.history?.length === b.history?.length &&
      !!a.history &&
      !!b.history &&
      a.history.every((part, index) => part === b.history![index]));
  return (
    a.agentId === b.agentId &&
    a.agentName === b.agentName &&
    a.agentAvatar === b.agentAvatar &&
    a.input === b.input &&
    a.result === b.result &&
    a.success === b.success &&
    a.error === b.error &&
    a.isPending === b.isPending &&
    a.startedAt === b.startedAt &&
    a.completedAt === b.completedAt &&
    a.status === b.status &&
    partsEqual &&
    historyEqual
  );
}

export interface SubagentPanelStore {
  clear: () => void;
  delete: (agentId: string) => void;
  get: (agentId: string) => SubagentPanelData | undefined;
  set: (data: SubagentPanelData) => void;
  size: () => number;
  subscribe: (agentId: string, listener: Listener) => () => void;
}

export function createSubagentPanelStore(): SubagentPanelStore {
  const data = new Map<string, SubagentPanelData>();
  const listeners = new Map<string, Set<Listener>>();

  function emit(agentId: string) {
    const subscribed = listeners.get(agentId);
    if (!subscribed) return;
    subscribed.forEach((listener) => listener());
  }

  return {
    clear() {
      const agentIds = [...data.keys()];
      data.clear();
      agentIds.forEach(emit);
    },
    delete(agentId) {
      if (!data.delete(agentId)) {
        return;
      }
      emit(agentId);
    },
    get(agentId) {
      return data.get(agentId);
    },
    set(next) {
      const prev = data.get(next.agentId);
      if (prev && shallowEqual(prev, next)) return;
      data.set(next.agentId, next);
      emit(next.agentId);
    },
    size() {
      return data.size;
    },
    subscribe(agentId, listener) {
      const subscribed = listeners.get(agentId) ?? new Set<Listener>();
      subscribed.add(listener);
      listeners.set(agentId, subscribed);

      return () => {
        const current = listeners.get(agentId);
        if (!current) return;
        current.delete(listener);
        if (current.size === 0) {
          listeners.delete(agentId);
        }
      };
    },
  };
}

export const subagentPanelStore = createSubagentPanelStore();
