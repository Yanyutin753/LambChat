import type { RefObject } from "react";

import i18n from "../../i18n";
import { sessionApi } from "../../services/api";
import { uuid } from "../../utils/uuid";

interface CreateSteerMessageOptions {
  sessionIdRef: RefObject<string | null>;
  onQueued: (steer: { id: string; content: string }) => void;
  onFailed: (steerId: string) => void;
  setError: (error: string | null) => void;
}

/**
 * Codex 式运行中插话：消息 POST 进后端队列，前端以"排队 chip"展示
 * （不直接插入对话流，避免插在流式回复中间）；送达后后端发
 * user:message 事件，由标准路径渲染正式气泡并移除 chip。
 */
export function createSteerMessage({
  sessionIdRef,
  onQueued,
  onFailed,
  setError,
}: CreateSteerMessageOptions) {
  return async (content: string) => {
    const text = content.trim();
    const currentSessionId = sessionIdRef.current;
    if (!text || !currentSessionId) return;

    const steer = { id: uuid(), content: text };
    onQueued(steer);
    try {
      await sessionApi.steer(currentSessionId, text);
    } catch (error) {
      console.error("[steerMessage] Failed to steer session:", error);
      onFailed(steer.id);
      setError(i18n.t("chat.steerFailed", "插话发送失败，请稍后重试"));
    }
  };
}
