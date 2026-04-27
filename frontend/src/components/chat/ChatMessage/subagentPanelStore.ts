import type { MessagePart } from "../../../types";

export interface SubagentPanelData {
  agentId: string;
  agentName: string;
  input: string;
  result?: string;
  success?: boolean;
  error?: string;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
}

type Listener = () => void;

export interface SubagentPanelStore {
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
