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
  MemoryStatusPart,
  SubagentPart,
  SummaryPart,
  ThinkingPart,
  ToolPart,
  TodoPart,
} from "../../types";
import { parseDate } from "../../utils/datetime";
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
  startedAt?: string,
): ToolPart {
  return {
    type: "tool",
    id: toolCallId,
    name: toolName,
    args: args,
    isPending: true,
    depth,
    agent_id: agentId,
    startedAt,
  };
}

/**
 * Create a generating tool part holding partial args text streamed from the
 * LLM (tool:args:chunk). Rendered by the same ToolCallItem via args.partial.
 */
export function createGeneratingToolPart(
  toolName: string,
  toolCallId: string | undefined,
  partialArgs: string,
  depth: number,
  agentId?: string,
): ToolPart {
  return {
    type: "tool",
    id: toolCallId,
    name: toolName,
    args: { partial: partialArgs },
    argsPartial: true,
    isPending: true,
    depth,
    agent_id: agentId,
  };
}

function findGeneratingToolIndex(
  parts: MessagePart[],
  toolCallId: string | undefined,
): number {
  if (toolCallId) {
    return parts.findIndex(
      (p) => p.type === "tool" && (p as ToolPart).argsPartial && p.id === toolCallId,
    );
  }
  for (let i = parts.length - 1; i >= 0; i--) {
    if (parts[i].type === "tool" && (parts[i] as ToolPart).argsPartial) return i;
  }
  return -1;
}

function appendPartialArgs(existing: ToolPart, delta: string): ToolPart {
  const current = typeof existing.args.partial === "string" ? existing.args.partial : "";
  return { ...existing, args: { partial: current + delta } };
}

function mergeToolArgsDeltaInParts(
  parts: MessagePart[],
  toolCallId: string | undefined,
  delta: string,
): MessagePart[] | null {
  const idx = findGeneratingToolIndex(parts, toolCallId);
  if (idx !== -1) {
    const newParts = [...parts];
    newParts[idx] = appendPartialArgs(newParts[idx] as ToolPart, delta);
    return newParts;
  }
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type === "subagent" && p.parts) {
      const updated = mergeToolArgsDeltaInParts(p.parts, toolCallId, delta);
      if (updated) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updated };
        return newParts;
      }
    }
  }
  return null;
}

/**
 * Append a streamed tool-args delta onto its generating part, creating the
 * part when this is its first delta. Falls back to addPartToDepth routing
 * for subagent placement.
 */
export function appendToolArgsDelta(
  parts: MessagePart[],
  toolName: string,
  toolCallId: string | undefined,
  delta: string,
  depth: number,
  agentId: string | undefined,
  activeSubagentStack: SubagentStackItem[],
  messageId?: string,
): MessagePart[] {
  const merged = mergeToolArgsDeltaInParts(parts, toolCallId, delta);
  if (merged) return merged;

  // 防御：对应的工具已转正（tool:start 已升级，id 或 alias 命中）时，
  // 迟到的增量直接丢弃——最终 args 已权威，再建 part 会留下一个永远
  // 停留在「参数生成中」的幽灵卡片
  if (toolCallId && hasUpgradedToolCallId(parts, toolCallId)) {
    return parts;
  }

  const part = createGeneratingToolPart(toolName, toolCallId, delta, depth, agentId);
  if (depth > 0) {
    return addPartToDepth(parts, part, depth, activeSubagentStack, agentId, messageId);
  }
  return [...parts, part];
}

function hasUpgradedToolCallId(parts: MessagePart[], toolCallId: string): boolean {
  return parts.some((p) => {
    if (p.type === "tool") {
      return (
        !p.argsPartial && (p.id === toolCallId || p.alias_id === toolCallId)
      );
    }
    return p.type === "subagent" && p.parts
      ? hasUpgradedToolCallId(p.parts, toolCallId)
      : false;
  });
}

/**
 * 定位 tool:start 应升级的生成中 part。
 *
 * 优先级：id 精确命中 > 按工具名取「最后一个」> 最后一个 argsPartial。
 * 必须与 findGeneratingToolIndex 的合并目标（反扫取最后一个）一致：
 * 若按位置取第一个，早前轮次残留的 stale 生成中 part（流式中断遗留）
 * 或并行工具执行顺序与生成顺序不一致时会错配——正在流式的新 part
 * 永远等不到升级，UI 卡在「参数生成中」不被替换。
 */
function findUpgradeTargetIndex(
  parts: MessagePart[],
  replacement: ToolPart,
): number {
  let nameMatch = -1;
  let anyMatch = -1;
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (p.type !== "tool" || !p.argsPartial) continue;
    if (replacement.id && p.id === replacement.id) return i;
    if (replacement.name && p.name === replacement.name) nameMatch = i;
    anyMatch = i;
  }
  return nameMatch !== -1 ? nameMatch : anyMatch;
}

/**
 * Replace the matching args-partial tool part with the final tool:start part,
 * keeping the earlier startedAt for honest elapsed timing.
 * depth 0 only upgrades top-level generating parts; nested subagent tools
 * (depth > 0) upgrade within their own subtree, matching where the args
 * chunks were routed.
 * The streaming-era id (if any) is preserved as alias_id so panels opened
 * during args streaming keep receiving live updates under the new id.
 * Returns null when no matching generating part exists (plain append path).
 */
export function upgradeGeneratingToolPart(
  parts: MessagePart[],
  replacement: ToolPart,
  targetDepth = 0,
): MessagePart[] | null {
  if (targetDepth > 0) {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (p.type !== "subagent" || !p.parts) continue;
      const updated = upgradeGeneratingToolPart(p.parts, replacement, targetDepth - 1);
      if (updated) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updated };
        return newParts;
      }
    }
    return null;
  }

  const idx = findUpgradeTargetIndex(parts, replacement);
  if (idx === -1) return null;
  const generating = parts[idx] as ToolPart;
  const newParts = [...parts];
  newParts[idx] = {
    ...replacement,
    startedAt: generating.startedAt ?? replacement.startedAt,
    alias_id:
      generating.id && generating.id !== replacement.id
        ? generating.id
        : replacement.alias_id,
  };
  return newParts;
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
  agentAvatar?: string,
): SubagentPart {
  const startedAt = timestamp ? parseDate(timestamp).getTime() : Date.now();
  return {
    type: "subagent",
    agent_id: agentId,
    agent_name: agentName,
    agent_avatar: agentAvatar,
    input: input,
    isPending: true,
    status: "running",
    depth: depth,
    parts: [],
    startedAt,
  };
}

// ============================================
// Part merge helpers
// ============================================

/**
 * Merge a thinking chunk into an existing parts array (reverse scan).
 * Returns a new array with content concatenated, or null if no match found.
 */
function mergeThinkingPart(
  parts: MessagePart[],
  part: ThinkingPart,
): MessagePart[] | null {
  const thinkingId = part.thinking_id;
  let existingIndex = -1;

  if (thinkingId !== undefined) {
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (
        p.type === "thinking" &&
        (p as ThinkingPart).thinking_id === thinkingId
      ) {
        existingIndex = i;
        break;
      }
    }
  } else {
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (
        p.type === "thinking" &&
        (p as ThinkingPart).thinking_id === undefined
      ) {
        existingIndex = i;
        break;
      }
    }
  }

  if (existingIndex < 0) return null;

  const newParts = [...parts];
  const existing = newParts[existingIndex] as ThinkingPart;
  newParts[existingIndex] = {
    ...existing,
    content: existing.content + part.content,
    isStreaming: true,
  };
  return newParts;
}

/**
 * Merge a text chunk into an existing parts array.
 * If the last part is text, concatenates content and returns a new array.
 * Otherwise returns null (caller should append).
 */
function mergeTextPart(
  parts: MessagePart[],
  content: string,
): MessagePart[] | null {
  const lastPart = parts[parts.length - 1];
  if (lastPart?.type === "text") {
    const newParts = [...parts];
    newParts[newParts.length - 1] = {
      ...lastPart,
      content: lastPart.content + content,
    };
    return newParts;
  }
  return null;
}

/**
 * 追加一段顶层正文（depth 0 的 message:chunk）。
 *
 * 流式下后端按阈值/定时 flush 正文，而工具参数首块直发，导致「先于工具
 * 调用生成的正文」可能在 tool:args:chunk 之后到达。模型输出顺序恒为
 * 「正文 → 工具参数」，仍在参数生成中（argsPartial，tool:start 之前）的
 * 工具不可能先于其前面的正文：把晚到的正文插回这些生成中工具之前并与
 * 相邻正文段合并，避免同一句被工具卡从中间劈开。
 */
export function appendTopLevelTextChunk(
  parts: MessagePart[],
  content: string,
): MessagePart[] {
  const lastPart = parts[parts.length - 1];
  if (lastPart?.type === "text" && !lastPart.depth) {
    const newParts = [...parts];
    newParts[newParts.length - 1] = {
      ...lastPart,
      content: lastPart.content + content,
    };
    return newParts;
  }

  let anchor = parts.length;
  while (anchor > 0) {
    const part = parts[anchor - 1];
    if (part.type === "tool" && (part as ToolPart).argsPartial) {
      anchor--;
      continue;
    }
    break;
  }

  const before = parts[anchor - 1];
  if (before?.type === "text" && !before.depth) {
    const newParts = [...parts];
    newParts[anchor - 1] = {
      ...before,
      content: before.content + content,
    };
    return newParts;
  }

  const textPart: MessagePart = { type: "text", content };
  return [...parts.slice(0, anchor), textPart, ...parts.slice(anchor)];
}

/**
 * Merge a summary chunk into an existing parts array.
 * Returns a new array with content concatenated, or null if no match found.
 */
function mergeSummaryPart(
  parts: MessagePart[],
  part: SummaryPart,
): MessagePart[] | null {
  const idx = findSummaryIndex(parts, part.summary_id);
  if (idx < 0) return null;

  const newParts = [...parts];
  const existing = newParts[idx] as SummaryPart;
  newParts[idx] = {
    ...existing,
    content: existing.content + part.content,
    isStreaming: part.isStreaming ? true : existing.isStreaming,
  };
  return newParts;
}

/**
 * Merge or append a part into a parts array.
 * Handles thinking, text, summary, and todo with merge semantics.
 * For all other types, appends a new copy.
 */
function mergeOrAppendPart(
  existingParts: MessagePart[],
  part: MessagePart,
): MessagePart[] {
  switch (part.type) {
    case "thinking": {
      const merged = mergeThinkingPart(existingParts, part);
      return merged ?? [...existingParts, part];
    }
    case "text": {
      const merged = mergeTextPart(existingParts, part.content);
      return merged ?? [...existingParts, part];
    }
    case "summary": {
      const merged = mergeSummaryPart(existingParts, part);
      return merged ?? [...existingParts, part];
    }
    case "todo": {
      // Upsert: at most one todo per subagent
      const todoIdx = existingParts.findIndex((p) => p.type === "todo");
      if (todoIdx >= 0) {
        const newParts = [...existingParts];
        newParts[todoIdx] = part;
        return newParts;
      }
      return [...existingParts, part];
    }
    default:
      return [...existingParts, part];
  }
}

// ============================================
// Depth management
// ============================================

/**
 * Search parts array for a matching subagent and merge/append the part into it.
 * Recursively descends into nested subagents. Returns updated parts array,
 * or null if no matching subagent was found.
 */
function findAndMergeInSubagent(
  parts: MessagePart[],
  part: MessagePart,
  targetDepth: number,
  effectiveAgentId?: string,
): MessagePart[] | null {
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];

    if (p.type === "subagent" && p.depth === targetDepth && p.isPending) {
      if (effectiveAgentId && p.agent_id !== effectiveAgentId) {
        continue;
      }
      const newSubagentParts = mergeOrAppendPart(p.parts || [], part);
      const newParts = [...parts];
      newParts[i] = { ...p, parts: newSubagentParts };
      return newParts;
    }

    // Recurse into nested subagents
    if (p.type === "subagent" && p.parts) {
      const result = findAndMergeInSubagent(
        p.parts,
        part,
        targetDepth,
        effectiveAgentId,
      );
      if (result) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: result };
        return newParts;
      }
    }
  }
  return null;
}

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
    // Merge adjacent text blocks at depth 0
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

  // Resolve effectiveAgentId from stack (reverse scan, no allocation)
  let effectiveAgentId = targetAgentId;
  if (!effectiveAgentId && messageId) {
    for (let i = activeSubagentStack.length - 1; i >= 0; i--) {
      const item = activeSubagentStack[i];
      if (
        item.message_id === messageId &&
        (item.depth === targetDepth || item.depth === targetDepth - 1)
      ) {
        effectiveAgentId = item.agent_id;
        break;
      }
    }
  }

  // Try to find matching subagent and merge into it
  const subagentResult = findAndMergeInSubagent(
    parts,
    part,
    targetDepth,
    effectiveAgentId,
  );
  if (subagentResult) return subagentResult;

  // Fallback: merge at top level when subagent block doesn't exist yet
  // (e.g. thinking arrives before agent:call)
  if (part.type === "thinking") {
    const merged = mergeThinkingPart(parts, part);
    if (merged) return merged;
  } else if (part.type === "text") {
    const merged = mergeTextPart(parts, part.content);
    if (merged) return merged;
  } else if (part.type !== "subagent") {
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
  const completedAt = timestamp ? parseDate(timestamp).getTime() : Date.now();
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
  completedAt?: string,
): MessagePart[] {
  // Try direct match on top-level tools first
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
        completedAt,
      };
      return newParts;
    }
    // Backward compat: match by name when no id
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
        completedAt,
      };
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
        completedAt,
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
  completedAt?: string,
): MessagePart[] | null {
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (p.type === "tool" && p.id === toolCallId && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
        completedAt,
      };
      return newParts;
    }
    if (p.type === "tool" && !p.id && p.isPending) {
      const newParts = [...parts];
      newParts[i] = {
        ...p,
        result,
        success,
        error,
        isPending: false,
        completedAt,
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
        completedAt,
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
 * Whether a message still contains an unanswered ask-human interrupt.
 * Ask-human may be nested inside one or more subagent parts.
 */
export function hasPendingAskHuman(parts: MessagePart[]): boolean {
  return parts.some((part) => {
    if (part.type === "tool") {
      return (
        part.name === "ask_human" &&
        part.isPending === true &&
        part.cancelled !== true
      );
    }

    if (part.type === "subagent") {
      return hasPendingAskHuman(part.parts ?? []);
    }

    return false;
  });
}

/**
 * Clear all loading states in message parts recursively.
 * Sets isPending: false and cancelled: true on tools and subagents,
 * isStreaming: false on thinking, cancels unfinished todos.
 * Returns a new parts array with updated loading states.
 */
export function clearAllLoadingStates(
  parts: MessagePart[],
  options?: { preserveAskHuman?: boolean },
): MessagePart[] {
  return parts.map((part) => {
    switch (part.type) {
      case "tool": {
        const toolPart = part as ToolPart;
        if (!toolPart.isPending) return part;
        if (options?.preserveAskHuman && toolPart.name === "ask_human") {
          return toolPart;
        }
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
          ? clearAllLoadingStates(subagentPart.parts, options)
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
        const hasUnfinished = todoPart.items.some(
          (i) => i.status === "pending" || i.status === "in_progress",
        );
        if (!hasUnfinished && !todoPart.isStreaming) return part;
        return {
          ...todoPart,
          isStreaming: false,
          items: todoPart.items.map((i) =>
            i.status === "pending" || i.status === "in_progress"
              ? { ...i, status: "cancelled" as const, activeForm: undefined }
              : i,
          ),
        };
      }
      case "sandbox": {
        const sandboxPart = part as SandboxPart;
        if (sandboxPart.status !== "starting") return part;
        return { ...sandboxPart, status: "cancelled" };
      }
      case "memoryStatus": {
        const memoryPart = part as MemoryStatusPart;
        if (memoryPart.status !== "starting") return part;
        return { ...memoryPart, status: "cancelled" };
      }
      default:
        return part;
    }
  });
}
