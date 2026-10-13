import type { Message, TodoPart } from "../../types";

export function getSessionTodo(messages: Message[], currentRunId?: string | null): TodoPart | null {
  const latest = messages.at(-1);
  const runId = currentRunId ?? latest?.runId;
  if (latest?.runId && runId && latest.runId !== runId) return null;
  if (latest?.role === "user" && latest.runId !== runId && !latest.metadata?.steered) return null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (runId && message.runId !== runId) continue;
    if (message.role === "user" && !message.metadata?.steered) break;
    if (message.role !== "assistant") continue;
    // Only the main agent's top-level checklist; nested subagents own their plans.
    const parts = message.parts ?? [];
    for (let j = parts.length - 1; j >= 0; j--) {
      const part = parts[j];
      if (part.type === "todo") return part.items.length ? part : null;
    }
  }
  return null;
}
