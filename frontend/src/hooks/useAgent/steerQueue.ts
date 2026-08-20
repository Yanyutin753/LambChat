import type { RefObject } from "react";

import i18n from "../../i18n";
import { sessionApi } from "../../services/api";
import type { Message } from "../../types/message";
import { buildSteerUserMessage } from "../../utils/steerMessages";

interface SteerQueueOptions {
  sessionIdRef: RefObject<string | null>;
  setMessages: (updater: (prev: Message[]) => Message[]) => void;
  setError: (error: string | null) => void;
}

/**
 * Codex 式运行中插话（前端状态）：
 * - 发送：POST 后端队列 + 在对话流底部追加"排队态"用户气泡
 *   （置灰 + 时钟角标，位置不再变动）
 * - 送达：后端注入模型调用时发 user:message 事件，事件处理器原地
 *   更新该气泡（清除排队态）
 * - 取消：删除排队气泡 + DELETE 后端队列中未送达的消息
 */
export function useSteerQueue({ sessionIdRef, setMessages, setError }: SteerQueueOptions) {
  const steerMessage = async (content: string) => {
    const text = content.trim();
    const currentSessionId = sessionIdRef.current;
    if (!text || !currentSessionId) return;

    const optimistic = buildSteerUserMessage({ previousCount: 0, content: text });
    setMessages((prev) => [...prev, optimistic]);
    try {
      await sessionApi.steer(currentSessionId, text);
    } catch (error) {
      console.error("[steerMessage] Failed to steer session:", error);
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError(i18n.t("chat.steerFailed", "插话发送失败，请稍后重试"));
    }
  };

  const cancelSteer = (content: string) => {
    setMessages((prev) =>
      prev.filter(
        (m) => !(m.role === "user" && m.metadata?.queued === true && m.content === content),
      ),
    );
    const currentSessionId = sessionIdRef.current;
    if (currentSessionId) {
      sessionApi.cancelSteer(currentSessionId, content).catch(() => {});
    }
  };

  return { steerMessage, cancelSteer };
}
