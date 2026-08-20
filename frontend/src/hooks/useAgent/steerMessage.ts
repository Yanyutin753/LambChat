import type { RefObject } from "react";

import i18n from "../../i18n";
import { sessionApi } from "../../services/api";
import type { Message } from "../../types/message";
import { buildSteerUserMessage } from "../../utils/steerMessages";

interface CreateSteerMessageOptions {
  sessionIdRef: RefObject<string | null>;
  setMessages: (
    updater: (prev: Message[]) => Message[],
  ) => void;
  setError: (error: string | null) => void;
}

/**
 * Codex 式运行中插话：消息进入后端队列，当前步骤后注入；先乐观展示，
 * 失败时回滚乐观消息并提示。
 */
export function createSteerMessage({
  sessionIdRef,
  setMessages,
  setError,
}: CreateSteerMessageOptions) {
  return async (content: string) => {
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
}
