import { useCallback, useState } from "react";
import type { RefObject } from "react";

import i18n from "../../i18n";
import { sessionApi } from "../../services/api";
import type { SteerItem } from "../../utils/mergeSteers";
import { uuid } from "../../utils/uuid";

interface SteerQueueOptions {
  sessionIdRef: RefObject<string | null>;
  setError: (error: string | null) => void;
}

/**
 * 运行中插话（steer）的独立前端状态——与用户消息管线完全解耦：
 * - 发送：POST 后端队列 + 本地插话项（排队态），不触碰 messages
 * - 送达：后端注入模型调用时发 steer:message 事件 → 轮次分割 +
 *   本项转正式（渲染时按时间戳合并进消息流）
 * - 取消：删除本地项 + DELETE 后端队列中未送达的消息
 */
export function useSteerQueue({ sessionIdRef, setError }: SteerQueueOptions) {
  const [steerMessages, setSteerMessages] = useState<SteerItem[]>([]);

  // 引用必须稳定：作为 props 传给 memo(ChatInput)，流式期间父级高频
  // 重渲染时不能破坏记忆化（否则编辑器每个 token 重渲染一次）
  const steerMessage = useCallback(
    async (content: string) => {
      const text = content.trim();
      const currentSessionId = sessionIdRef.current;
      if (!text || !currentSessionId) return;

      const item: SteerItem = { id: uuid(), content: text, queued: true, timestamp: new Date() };
      setSteerMessages((prev) => [...prev, item]);
      try {
        await sessionApi.steer(currentSessionId, text);
      } catch (error) {
        console.error("[steerMessage] Failed to steer session:", error);
        setSteerMessages((prev) => prev.filter((s) => s.id !== item.id));
        setError(i18n.t("chat.steerFailed", "插话发送失败，请稍后重试"));
      }
    },
    [sessionIdRef, setError],
  );

  const cancelSteer = useCallback(
    (content: string) => {
      setSteerMessages((prev) => prev.filter((s) => s.content !== content));
      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        sessionApi.cancelSteer(currentSessionId, content).catch(() => {});
      }
    },
    [sessionIdRef],
  );

  const markSteerDelivered = useCallback((content: string) => {
    setSteerMessages((prev) =>
      prev.map((s) =>
        s.content === content && s.queued ? { ...s, queued: false } : s,
      ),
    );
  }, []);

  const clearSteerMessages = useCallback(() => setSteerMessages([]), []);

  return { steerMessages, steerMessage, cancelSteer, markSteerDelivered, clearSteerMessages };
}
