import type { Message } from "../../types/message";
import { clearAllLoadingStates } from "./messageParts";

/**
 * 插话打断了这段生成：给封存轮次补「已停止」视觉（cancelled 标志 +
 * cancelled part，与用户主动取消同款）。没有任何内容的空轮次不加，
 * 避免空气泡上凭空出现已停止标记。
 */
export function markInterruptedBySteer(message: Message): Message {
  const hasContent =
    (message.parts?.length ?? 0) > 0 || Boolean(message.content?.trim());
  if (!hasContent) return message;
  const parts = message.parts || [];
  if (parts.some((part) => part.type === "cancelled")) {
    return { ...message, cancelled: true };
  }
  return { ...message, cancelled: true, parts: [...parts, { type: "cancelled" }] };
}

/**
 * 插话送达时的"轮次分割"（对齐 Codex 的逐 item 渲染语义）。
 *
 * 实时视图中一个 run 的所有模型输出流进同一个助手消息（run 级
 * messageId）。插话送达（steer:message 事件）时：封存当前流式助手
 * 消息（重命名 id、清加载态、标记已停止——插话即打断），并追加新的
 * 助手占位（沿用原 messageId 接收后续事件）。插话本身在独立状态里，
 * 渲染时按时间戳落在封存轮次与新轮次之间。
 */
export function splitAssistantTurn(
  messages: Message[],
  assistantId: string,
): Message[] {
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

  const sealed: Message = markInterruptedBySteer({
    ...messages[assistantIndex],
    id: `${assistantId}#t${nextTurn}`,
    isStreaming: false,
    parts: clearAllLoadingStates(messages[assistantIndex].parts || [], {
      preserveAskHuman: true,
    }),
  });

  const freshTurn: Message = {
    id: assistantId,
    role: "assistant",
    content: "",
    // 继承原轮次时间戳（run 起点）：流式计时锚点跨轮次连续，插话不清零
    timestamp: messages[assistantIndex].timestamp,
    parts: [],
    isStreaming: true,
  };

  const next = [...messages];
  next.splice(assistantIndex + 1, 0, freshTurn);
  next[assistantIndex] = sealed;
  return next;
}
