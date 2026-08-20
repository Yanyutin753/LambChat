import type { Message } from "../../types/message";
import { clearAllLoadingStates } from "./messageParts";

/**
 * 插话送达时的"轮次分割"（对齐 Codex 的逐 item 渲染语义）。
 *
 * 实时视图中一个 run 的所有模型输出流进同一个助手消息（run 级
 * messageId）。插话送达（user:message 事件匹配到排队气泡）时：
 * 1. 封存当前流式助手消息（重命名 id、清加载态）；
 * 2. 在插话气泡之后插入新的助手占位（沿用原 messageId 接收后续事件）。
 *
 * 最终顺序：[助手轮1] [插话气泡] [助手轮2（继续流式）] —— 与刷新后
 * 历史加载器的轮次交错顺序一致。非插话的 user:message 不受影响。
 */
export function hasQueuedSteerMessage(
  messages: Message[],
  steerContent: string,
): boolean {
  return messages.some(
    (m) =>
      m.role === "user" &&
      m.metadata?.queued === true &&
      m.content === steerContent,
  );
}

export function splitAssistantTurnOnSteerDelivery(
  messages: Message[],
  steerContent: string,
  assistantId: string,
): Message[] {
  if (!hasQueuedSteerMessage(messages, steerContent)) return messages;

  const assistantIndex = messages.findIndex(
    (m) => m.id === assistantId && m.role === "assistant",
  );
  if (assistantIndex === -1) return messages;

  // 已分割过的轮次用 #tN 后缀，递增避免冲突
  const turnNumbers = messages
    .map((m) => m.id.match(/^.*#t(\d+)$/)?.[1])
    .filter((n): n is string => n != null)
    .map(Number);
  const nextTurn = (turnNumbers.length ? Math.max(...turnNumbers) : 0) + 1;

  const sealed: Message = {
    ...messages[assistantIndex],
    id: `${assistantId}#t${nextTurn}`,
    isStreaming: false,
    parts: clearAllLoadingStates(messages[assistantIndex].parts || []),
  };

  // 插话气泡（排队中、内容匹配）之后插入新助手轮次
  const steerIndex = messages.findIndex(
    (m) =>
      m.role === "user" &&
      m.metadata?.queued === true &&
      m.content === steerContent,
  );  // split 前已确认存在
  const freshTurn: Message = {
    id: assistantId,
    role: "assistant",
    content: "",
    timestamp: new Date(),
    parts: [],
    isStreaming: true,
  };

  const next = [...messages];
  next[assistantIndex] = sealed;
  next.splice(steerIndex + 1, 0, freshTurn);
  return next;
}
