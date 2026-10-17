import type { Message } from "../../types/message";
import { clearAllLoadingStates } from "./messageParts";

/** A delivered steer closes a segment; only cancellation events stop the run. */
export function sealAssistantBeforeSteer(message: Message): Message {
  return {
    ...message,
    isStreaming: false,
    metadata: { ...message.metadata, continuedBySteer: true },
    parts: clearAllLoadingStates(message.parts || [], {
      preserveAskHuman: true,
      preserveTodos: true,
    }),
  };
}

/**
 * 插话送达时的"轮次分割"（对齐 Codex 的逐 item 渲染语义）。
 *
 * 实时视图中一个 run 的所有模型输出流进同一个助手消息（run 级
 * messageId）。插话送达（steer:message 事件）时：封存当前流式助手
 * 消息（重命名 id、清加载态、保留待办与运行结果），并追加新的
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

  const sealed: Message = sealAssistantBeforeSteer({
    ...messages[assistantIndex],
    id: `${assistantId}#t${nextTurn}`,
    isStreaming: false,
  });

  const freshTurn: Message = {
    id: assistantId,
    role: "assistant",
    assistantIdentity: messages[assistantIndex].assistantIdentity,
    runId: messages[assistantIndex].runId,
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
