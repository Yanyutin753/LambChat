/**
 * Message part manipulation utilities.
 *
 * Low-level building blocks for creating, updating, and routing
 * message parts (text, thinking, tool, subagent, sandbox).
 * Used by eventProcessor.ts (the unified event handler).
 */

import type {
  MessagePart,
  SandboxPart,
  SubagentPart,
  SummaryPart,
  ThinkingPart,
  ToolPart,
  TodoPart,
} from "../../types";
import type { SubagentStackItem } from "./types";

// ============================================
// Part creators
// ============================================

/**
 * Create a tool part from tool data.
 */
export function createToolPart(
  toolName: string,
  args: Record<string, unknown>,
  depth: number,
  agentId?: string,
  toolCallId?: string,
): ToolPart {
  return {
    type: "tool",
    id: toolCallId,
    name: toolName,
    args: args,
    isPending: true,
    depth,
    agent_id: agentId,
  };
}

/**
 * Create a thinking part from thinking data.
 */
export function createThinkingPart(
  content: string,
  thinkingId: string | undefined,
  depth: number,
  agentId?: string,
  isStreaming = true,
): ThinkingPart {
  return {
    type: "thinking",
    content,
    thinking_id: thinkingId,
    depth,
    agent_id: agentId,
    isStreaming,
  };
}

/**
 * Create a subagent part from agent call data.
 */
export function createSubagentPart(
  agentId: string,
  agentName: string,
  input: string,
  depth: number,
  timestamp?: string,
): SubagentPart {
  const startedAt = timestamp ? new Date(timestamp).getTime() : Date.now();
  return {
    type: "subagent",
    agent_id: agentId,
    agent_name: agentName,
    input: input,
    isPending: true,
    status: "running",
    depth: depth,
    parts: [],
    startedAt,
  };
}

// ============================================
// Depth management
// ============================================

/**
 * Add a part to the correct depth position in the parts array.
 * For subagent events (depth > 0), the event's depth equals the subagent's depth.
 * Returns a new parts array (immutable update).
 * Uses agent_id for precise matching to support parallel subagents.
 */
export function addPartToDepth(
  parts: MessagePart[],
  part: MessagePart,
  targetDepth: number,
  activeSubagentStack: SubagentStackItem[],
  targetAgentId?: string,
  messageId?: string,
): MessagePart[] {
  if (targetDepth <= 0) {
    // Merge adjacent text blocks
    if (part.type === "text") {
      const lastPart = parts[parts.length - 1];
      if (lastPart?.type === "text" && !lastPart.depth) {
        const newParts = [...parts];
        newParts[newParts.length - 1] = {
          ...lastPart,
          content: lastPart.content + part.content,
        };
        return newParts;
      }
    }
    return [...parts, part];
  }

  // Try to get effectiveAgentId from stack if not provided
  let effectiveAgentId = targetAgentId;
  if (!effectiveAgentId && messageId) {
    const relevantAgents = activeSubagentStack.filter(
      (item) =>
        item.message_id === messageId &&
        (item.depth === targetDepth || item.depth === targetDepth - 1),
    );
    if (relevantAgents.length > 0) {
      const lastAgent = relevantAgents[relevantAgents.length - 1];
      effectiveAgentId = lastAgent.agent_id;
    }
  }

  // Find matching subagent (using agent_id for precise matching)
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type === "subagent" && p.depth === targetDepth && p.isPending) {
      if (effectiveAgentId && p.agent_id !== effectiveAgentId) {
        continue;
      }
      const existingParts = p.parts || [];
      let newSubagentParts: MessagePart[];

      // Merge adjacent text or thinking blocks
      if (part.type === "text") {
        const lastPart = existingParts[existingParts.length - 1];
        if (lastPart?.type === "text") {
          newSubagentParts = [...existingParts];
          newSubagentParts[newSubagentParts.length - 1] = {
            ...lastPart,
            content: lastPart.content + part.content,
          };
        } else {
          newSubagentParts = [...existingParts, part];
        }
      } else if (part.type === "thinking") {
        const thinkingId = part.thinking_id;
        let existingIndex = -1;

        if (thinkingId !== undefined) {
          existingIndex = existingParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === thinkingId,
          );
        } else {
          for (let i = existingParts.length - 1; i >= 0; i--) {
            const p = existingParts[i];
            if (p.type === "thinking" && p.thinking_id === undefined) {
              existingIndex = i;
              break;
            }
          }
        }

        if (existingIndex >= 0) {
          const existing = existingParts[existingIndex] as ThinkingPart;
          newSubagentParts = [...existingParts];
          newSubagentParts[existingIndex] = {
            ...existing,
            content: existing.content + part.content,
            isStreaming: true,
          };
        } else {
          newSubagentParts = [...existingParts, part];
        }
      } else if (part.type === "todo") {
        // Upsert: replace existing todo or append — each subagent gets at most one todo
        const todoIdx = existingParts.findIndex((p) => p.type === "todo");
        if (todoIdx >= 0) {
          newSubagentParts = [...existingParts];
          newSubagentParts[todoIdx] = part;
        } else {
          newSubagentParts = [...existingParts, part];
        }
      } else if (part.type === "summary") {
        const summaryIdx = findSummaryIndex(existingParts, part.summary_id);
        if (summaryIdx >= 0) {
          const existing = existingParts[summaryIdx] as SummaryPart;
          newSubagentParts = [...existingParts];
          newSubagentParts[summaryIdx] = {
            ...existing,
            content: existing.content + part.content,
            isStreaming: part.isStreaming ? true : existing.isStreaming,
          };
        } else {
          newSubagentParts = [...existingParts, part];
        }
      } else {
        newSubagentParts = [...existingParts, part];
      }

      const newParts = [...parts];
      newParts[i] = { ...p, parts: newSubagentParts };
      return newParts;
    }

    // Recursively search nested subagents
    if (p.type === "subagent" && p.parts) {
      const result = findAndAddToSubagent(
        p,
        part,
        targetDepth,
        effectiveAgentId,
      );
      if (result) {
        const newParts = [...parts];
        newParts[i] = result;
        return newParts;
      }
    }
  }

  // If no matching subagent found, add to top level
  if (part.type !== "subagent") {
    console.warn(
      "[addPartToDepth] No matching subagent found for depth:",
      targetDepth,
      "agent_id:",
      effectiveAgentId,
      "adding to top level",
    );
  }
  return [...parts, part];
}

/**
 * Recursively find and add a part to a subagent.
 * Returns updated subagent or null if not found.
 */
export function findAndAddToSubagent(
  subagent: SubagentPart,
  part: MessagePart,
  targetDepth: number,
  targetAgentId?: string,
): SubagentPart | null {
  if (subagent.depth === targetDepth && subagent.isPending) {
    if (targetAgentId && subagent.agent_id !== targetAgentId) {
      // Not matching, continue recursive search
    } else {
      const existingParts = subagent.parts || [];
      let newParts: MessagePart[];

      if (part.type === "text") {
        const lastPart = existingParts[existingParts.length - 1];
        if (lastPart?.type === "text") {
          newParts = [...existingParts];
          newParts[newParts.length - 1] = {
            ...lastPart,
            content: lastPart.content + part.content,
          };
        } else {
          newParts = [...existingParts, part];
        }
      } else if (part.type === "thinking") {
        const thinkingId = part.thinking_id;
        let existingIndex = -1;

        if (thinkingId !== undefined) {
          existingIndex = existingParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === thinkingId,
          );
        } else {
          for (let i = existingParts.length - 1; i >= 0; i--) {
            const p = existingParts[i];
            if (p.type === "thinking" && p.thinking_id === undefined) {
              existingIndex = i;
              break;
            }
          }
        }

        if (existingIndex >= 0) {
          const existing = existingParts[existingIndex] as ThinkingPart;
          newParts = [...existingParts];
          newParts[existingIndex] = {
            ...existing,
            content: existing.content + part.content,
            isStreaming: true,
          };
        } else {
          newParts = [...existingParts, part];
        }
      } else if (part.type === "summary") {
        const summaryIdx = findSummaryIndex(existingParts, part.summary_id);
        if (summaryIdx >= 0) {
          const existing = existingParts[summaryIdx] as SummaryPart;
          newParts = [...existingParts];
          newParts[summaryIdx] = {
            ...existing,
            content: existing.content + part.content,
            isStreaming: part.isStreaming ? true : existing.isStreaming,
          };
        } else {
          newParts = [...existingParts, part];
        }
      } else {
        newParts = [...existingParts, part];
      }

      return { ...subagent, parts: newParts };
    }
  }

  // Recursively search nested subagents
  if (subagent.parts) {
    for (let i = subagent.parts.length - 1; i >= 0; i--) {
      const p = subagent.parts[i];
      if (p.type === "subagent") {
        const result = findAndAddToSubagent(
          p as SubagentPart,
          part,
          targetDepth,
          targetAgentId,
        );
        if (result) {
          const newParts = [...subagent.parts];
          newParts[i] = result;
          return { ...subagent, parts: newParts };
        }
      }
    }
  }
  return null;
}

// ============================================
// Subagent result
// ============================================

function findSummaryIndex(parts: MessagePart[], summaryId?: string): number {
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (part.type === "summary" && part.summary_id === summaryId) {
      return i;
    }
  }
  return -1;
}

/**
 * Update subagent result. Returns new parts array.
 */
export function updateSubagentResult(
  parts: MessagePart[],
  agentId: string,
  result: string,
  success: boolean,
  targetDepth: number,
  error?: string,
  timestamp?: string,
): MessagePart[] {
  const completedAt = timestamp ? new Date(timestamp).getTime() : Date.now();
  const status = success ? "complete" : "error";

  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (
      p.type === "subagent" &&
      p.agent_id === agentId &&
      p.depth === targetDepth &&
      p.isPending
    ) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
        status,
        completedAt,
      };
      return newParts;
    }
    if (p.type === "subagent" && p.parts) {
      const updatedSubagent = updateSubagentResultInParts(
        p.parts,
        agentId,
        result,
        success,
        targetDepth,
        error,
        completedAt,
        status,
      );
      if (updatedSubagent) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updatedSubagent };
        return newParts;
      }
    }
  }
  return parts;
}

/**
 * Recursively update subagent result in parts.
 */
export function updateSubagentResultInParts(
  parts: MessagePart[],
  agentId: string,
  result: string,
  success: boolean,
  targetDepth: number,
  error?: string,
  completedAt?: number,
  status?: "complete" | "error",
): MessagePart[] | null {
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (
      p.type === "subagent" &&
      p.agent_id === agentId &&
      p.depth === targetDepth &&
      p.isPending
    ) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
        status,
        completedAt,
      };
      return newParts;
    }
    if (p.type === "subagent" && p.parts) {
      const updatedParts = updateSubagentResultInParts(
        p.parts,
        agentId,
        result,
        success,
        targetDepth,
        error,
        completedAt,
        status,
      );
      if (updatedParts) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updatedParts };
        return newParts;
      }
    }
  }
  return null;
}

// ============================================
// Tool result
// ============================================

/**
 * Update tool result at specified depth. Returns new parts array.
 */
export function updateToolResultInDepth(
  parts: MessagePart[],
  toolCallId: string,
  result: string | Record<string, unknown>,
  success: boolean,
  error?: string,
  _targetDepth?: number,
  targetAgentId?: string,
): MessagePart[] {
  // Try direct match on top-level tools first
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type === "tool" && p.id === toolCallId && p.isPending) {
      const newParts = [...parts];
      newParts[i] = { ...p, result, success, error, isPending: false };
      return newParts;
    }
    // Backward compat: match by name when no id
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = { ...p, result, success, error, isPending: false };
      return newParts;
    }
  }

  // Then search inside subagents
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type === "subagent" && p.parts) {
      if (targetAgentId && p.agent_id !== targetAgentId) {
        continue;
      }
      const updatedParts = updateToolResultInPartsById(
        p.parts,
        toolCallId,
        result,
        success,
        error,
      );
      if (updatedParts) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updatedParts };
        return newParts;
      }
    }
  }
  return parts;
}

/**
 * Recursively update tool result in parts by tool_call_id.
 */
export function updateToolResultInPartsById(
  parts: MessagePart[],
  toolCallId: string,
  result: string | Record<string, unknown>,
  success: boolean,
  error?: string,
): MessagePart[] | null {
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (p.type === "tool" && p.id === toolCallId && p.isPending) {
      const newParts = [...parts];
      newParts[i] = { ...p, result, success, error, isPending: false };
      return newParts;
    }
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = { ...p, result, success, error, isPending: false };
      return newParts;
    }
    if (p.type === "subagent" && p.parts) {
      const updatedParts = updateToolResultInPartsById(
        p.parts,
        toolCallId,
        result,
        success,
        error,
      );
      if (updatedParts) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updatedParts };
        return newParts;
      }
    }
  }
  return null;
}

// ============================================
// Utility
// ============================================

/**
 * Clear all loading states in message parts recursively.
 * Sets isPending: false and cancelled: true on tools and subagents,
 * isStreaming: false on thinking, reverts in_progress todos to pending.
 * Returns a new parts array with updated loading states.
 */
export function clearAllLoadingStates(parts: MessagePart[]): MessagePart[] {
  return parts.map((part) => {
    switch (part.type) {
      case "tool": {
        const toolPart = part as ToolPart;
        if (!toolPart.isPending) return part;
        return { ...toolPart, isPending: false, cancelled: true };
      }
      case "thinking": {
        const thinkingPart = part as ThinkingPart;
        if (!thinkingPart.isStreaming) return part;
        return { ...thinkingPart, isStreaming: false };
      }
      case "subagent": {
        const subagentPart = part as SubagentPart;
        const updatedParts = subagentPart.parts
          ? clearAllLoadingStates(subagentPart.parts)
          : [];
        // Preserve existing terminal status (complete/error) instead of forcing cancelled
        const wasCompleted = subagentPart.status === "complete";
        const hadError = subagentPart.status === "error";
        return {
          ...subagentPart,
          isPending: false,
          cancelled: !wasCompleted && !hadError,
          status: wasCompleted ? "complete" : hadError ? "error" : "cancelled",
          completedAt: subagentPart.completedAt || Date.now(),
          parts: updatedParts,
        };
      }
      case "todo": {
        const todoPart = part as TodoPart;
        const hasInProgress = todoPart.items.some(
          (i) => i.status === "in_progress",
        );
        if (!hasInProgress) return part;
        return {
          ...todoPart,
          isStreaming: false,
          items: todoPart.items.map((i) =>
            i.status === "in_progress"
              ? { ...i, status: "pending" as const, activeForm: undefined }
              : i,
          ),
        };
      }
      case "sandbox": {
        const sandboxPart = part as SandboxPart;
        if (sandboxPart.status !== "starting") return part;
        return { ...sandboxPart, status: "cancelled" };
      }
      default:
        return part;
    }
  });
}
