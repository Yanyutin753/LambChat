import type {
  MessagePart,
  SubagentPart,
  ThinkingPart,
  ToolPart,
} from "../../types";
import type { SubagentStackItem } from "./types";

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

        // 如果有 thinking_id，精确匹配
        if (thinkingId !== undefined) {
          existingIndex = existingParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === thinkingId,
          );
        } else {
          // 如果没有 thinking_id，找最后一个 thinking part（且也没有 thinking_id）
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
  // Only warn for non-subagent parts (text, thinking, tool) - subagent parts themselves
  // are expected to be added at the root level when no parent exists
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

        // 如果有 thinking_id，精确匹配
        if (thinkingId !== undefined) {
          existingIndex = existingParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === thinkingId,
          );
        } else {
          // 如果没有 thinking_id，找最后一个 thinking part（且也没有 thinking_id）
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

/**
 * Update subagent result. Returns new parts array.
 */
export function updateSubagentResult(
  parts: MessagePart[],
  agentId: string,
  result: string,
  success: boolean,
  targetDepth: number,
): MessagePart[] {
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
        isPending: false,
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
        isPending: false,
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

/**
 * Update tool result at specified depth. Returns new parts array.
 * 直接在 parts 中查找匹配的 tool 并更新（支持 depth=0 的顶级工具）
 */
export function updateToolResultInDepth(
  parts: MessagePart[],
  toolCallId: string,
  result: string,
  success: boolean,
  error?: string,
  _targetDepth?: number,
  targetAgentId?: string,
): MessagePart[] {
  // 先尝试直接匹配顶级的 tool
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type === "tool" && p.id === toolCallId && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
      };
      return newParts;
    }
    // 向后兼容：没有 id 时按 name 匹配
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
      };
      return newParts;
    }
  }

  // 再尝试在 subagent 内部查找
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
  result: string,
  success: boolean,
  error?: string,
): MessagePart[] | null {
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    // 优先使用 tool_call_id 匹配
    if (p.type === "tool" && p.id === toolCallId && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
      };
      return newParts;
    }
    // 向后兼容：如果没有 id，则按 name 匹配
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
      };
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
): SubagentPart {
  return {
    type: "subagent",
    agent_id: agentId,
    agent_name: agentName,
    input: input,
    isPending: true,
    depth: depth,
    parts: [],
  };
}
