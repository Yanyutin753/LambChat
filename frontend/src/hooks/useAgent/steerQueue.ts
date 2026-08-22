import { useCallback, useState } from "react";
import type { RefObject } from "react";

import { sessionApi } from "../../services/api";
import type { SteerItem } from "../../utils/mergeSteers";
import { uuid } from "../../utils/uuid";
import type { MessageAttachment } from "../../types";

interface SteerQueueOptions {
  sessionIdRef: RefObject<string | null>;
  deferSteer: (
    content: string,
    messageId: string,
    attachments?: MessageAttachment[],
  ) => void;
  removeDeferredSteer?: (content: string, messageId?: string) => void;
}

export function removeSteerItem(
  items: SteerItem[],
  content: string,
  messageId?: string,
): { remaining: SteerItem[]; removed?: SteerItem } {
  const index = messageId
    ? items.findIndex((item) => item.id === messageId)
    : items.findIndex((item) => item.content === content);
  if (index < 0) return { remaining: items };
  return {
    removed: items[index],
    remaining: [...items.slice(0, index), ...items.slice(index + 1)],
  };
}

/** Accepted-but-undelivered items become ordinary follow-up turns at run end. */
export function selectSteersForFollowUp(items: SteerItem[]): SteerItem[] {
  return items.filter((item) => item.queued && item.status !== "failed");
}

export interface PromoteSteerFollowUpsDeps {
  sessionId: string | null;
  cancelSteer: (sessionId: string, content: string, messageId: string) => Promise<unknown>;
  sendMessage: (content: string, attachments?: MessageAttachment[]) => Promise<unknown>;
  isCancelled?: (messageId: string) => boolean;
  clearSteer?: (content: string, messageId: string) => void;
}

/**
 * 把未送达插话补发为普通消息。
 *
 * 必须先清本地状态、再取消后端队列中的同一条，最后作为普通消息发送：
 * 后端队列按会话共享，若只补发不取消，新 run 的首次模型调用会把同
 * 一条插话再次注入（同内容投递两次）。取消失败不阻塞补发——后端在
 * 新 run 提交时也会兜底清空残留队列。
 */
export async function promoteSteerFollowUps(
  items: SteerItem[],
  deps: PromoteSteerFollowUpsDeps,
): Promise<void> {
  const { sessionId } = deps;
  if (!sessionId) return;
  for (const item of items) {
    if (deps.isCancelled?.(item.id)) continue;
    deps.clearSteer?.(item.content, item.id);
    try {
      await deps.cancelSteer(sessionId, item.content, item.id);
    } catch {
      // 取消失败继续补发；新 run 提交时的后端兜底清理会移除残留项
    }
    await deps.sendMessage(item.content, item.attachments);
  }
}

export interface PendingSteerSnapshot {
  message_id: string;
  content: string;
  created_at: string;
  attachments?: Array<
    Omit<MessageAttachment, "mimeType"> & {
      mimeType?: string;
      mime_type?: string;
    }
  >;
}

/**
 * 运行中插话（steer）的独立前端状态——与用户消息管线完全解耦：
 * - 发送：POST 后端队列 + 本地插话项（排队态），不触碰 messages
 * - 送达：后端注入模型调用时发 steer:message 事件 → 轮次分割 +
 *   本地 optimistic 项移除，正式消息由事件处理器写入 messages
 * - 取消：删除本地项 + DELETE 后端队列中未送达的消息
 */
export function useSteerQueue({
  sessionIdRef,
  deferSteer,
  removeDeferredSteer,
}: SteerQueueOptions) {
  const [steerMessages, setSteerMessages] = useState<SteerItem[]>([]);

  // 引用必须稳定：作为 props 传给 memo(ChatInput)，流式期间父级高频
  // 重渲染时不能破坏记忆化（否则编辑器每个 token 重渲染一次）
  const steerMessage = useCallback(
    async (content: string, attachments: MessageAttachment[] = []) => {
      const text = content.trim();
      const currentSessionId = sessionIdRef.current;
      if (!text || !currentSessionId) return;

      const item: SteerItem = {
        id: uuid(),
        content: text,
        attachments,
        queued: true,
        status: "pending",
        timestamp: new Date(),
      };
      setSteerMessages((prev) => [...prev, item]);
      try {
        await sessionApi.steer(currentSessionId, text, item.id, attachments);
      } catch (error) {
        console.error("[steerMessage] Failed to steer session:", error);
        const status =
          typeof error === "object" && error !== null && "status" in error
            ? (error as { status?: number }).status
            : undefined;
        // A 409 means the run ended between the status check and enqueue. It
        // is safe to preserve the user's intent as a normal next turn;
        // transport/auth/server failures must remain retryable instead.
        if (status === 409) {
          setSteerMessages((prev) =>
            prev.map((s) =>
              s.id === item.id
                ? { ...s, queued: false, status: "deferred", deferred: true }
                : s,
            ),
          );
          deferSteer(text, item.id, attachments);
          return;
        }
        setSteerMessages((prev) =>
          prev.map((s) =>
            s.id === item.id ? { ...s, queued: false, status: "failed" } : s,
          ),
        );
      }
    },
    [sessionIdRef, deferSteer],
  );

  const cancelSteer = useCallback(
    (content: string, messageId?: string) => {
      let removed: SteerItem | undefined;
      setSteerMessages((prev) => {
        const result = removeSteerItem(prev, content, messageId);
        removed = result.removed;
        return result.remaining;
      });
      removeDeferredSteer?.(content, messageId ?? removed?.id);
      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        sessionApi
          .cancelSteer(currentSessionId, content, messageId)
          .catch(() => {});
      }
    },
    [removeDeferredSteer, sessionIdRef],
  );

  const markSteerDelivered = useCallback(
    (content: string, messageId?: string) => {
      setSteerMessages((prev) => {
        const indexById = messageId
          ? prev.findIndex((s) => s.id === messageId)
          : -1;
        const index =
          indexById >= 0
            ? indexById
            : prev.findIndex((s) => s.content === content && s.queued);
        if (index === -1) return prev;
        return [...prev.slice(0, index), ...prev.slice(index + 1)];
      });
    },
    [],
  );

  const clearSteerMessages = useCallback(() => setSteerMessages([]), []);
  const hydrateSteers = useCallback((items: PendingSteerSnapshot[]) => {
    setSteerMessages((prev) => {
      const existing = new Map(prev.map((item) => [item.id, item]));
      for (const item of items) {
        if (!existing.has(item.message_id)) {
          existing.set(item.message_id, {
            id: item.message_id,
            content: item.content,
            attachments: item.attachments?.map((attachment) => ({
              ...attachment,
              mimeType: attachment.mimeType ?? attachment.mime_type ?? "",
            })),
            queued: true,
            status: "pending",
            timestamp: new Date(item.created_at),
          });
        }
      }
      return [...existing.values()].sort(
        (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
      );
    });
  }, []);
  const clearSteer = useCallback(
    (content: string, messageId?: string) =>
      setSteerMessages((prev) =>
        prev.filter((item) =>
          messageId ? item.id !== messageId : item.content !== content,
        ),
      ),
    [],
  );

  return {
    steerMessages,
    steerMessage,
    cancelSteer,
    markSteerDelivered,
    clearSteerMessages,
    clearSteer,
    hydrateSteers,
  };
}
