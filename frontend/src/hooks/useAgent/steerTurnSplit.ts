import type { Message } from "../../types/message";
import { clearAllLoadingStates } from "./messageParts";

/**
 * 插话送达时的"轮次分割"（对齐 Codex 的逐 item 渲染语义）。
 *
 * 实时视图中一个 run 的所有模型输出流进同一个助手消息（run 级
 * messageId）。插话送达（steer:message 事件）时：封存当前流式助手
 * 消息（重命名 id、清加载态），并追加新的助手占位（沿用原
 * messageId 接收后续事件）。插话本身在独立状态里，渲染时按时间戳
 * 落在封存轮次与新轮次之间。
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

  const sealed: Message = {
    ...messages[assistantIndex],
    id: `${assistantId}#t${nextTurn}`,
    isStreaming: false,
    parts: clearAllLoadingStates(messages[assistantIndex].parts || [], {
      preserveAskHuman: true,
    }),
  };

  const freshTurn: Message = {
    id: assistantId,
    role: "assistant",
    content: "",
    timestamp: new Date(),
    parts: [],
    isStreaming: true,
  };

  const next = [...messages];
  next.splice(assistantIndex + 1, 0, freshTurn);
  next[assistantIndex] = sealed;
  return next;
}
